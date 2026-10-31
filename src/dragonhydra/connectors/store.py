"""Additive provider observations in the application's selected SQLite database.

Records are provider-scoped. Candidate cross-source matches are review items,
never silent joins. Original documents and every changed observation survive.
"""
from contextlib import closing
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from .core import ConnectorError, redact_url, utc_now


PROVENANCE_FIELD = '_acquisition_bindings'
ACQUISITION_COLUMNS = ('id', 'provider', 'adapter_version', 'original_url', 'resolved_url',
                       'captured_at', 'sha256', 'raw_reference', 'bytes', 'content_type', 'http_status')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def semantic_digest(record):
    """Compare source content independently of store bindings and capture clocks."""
    semantic = dict(record)
    semantic.pop(PROVENANCE_FIELD, None)
    semantic['attributes'] = {key: value for key, value in record.get('attributes', {}).items()
                              if key not in ('captured_at', 'retrieved_at')}
    return digest(semantic)


class Store:
    def __init__(self, product):
        self.product = product
        with closing(product.connect()) as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS connector_acquisitions (
              id TEXT PRIMARY KEY, provider TEXT NOT NULL, adapter_version TEXT NOT NULL,
              original_url TEXT NOT NULL, resolved_url TEXT NOT NULL, captured_at TEXT NOT NULL,
              sha256 TEXT NOT NULL, raw_reference TEXT NOT NULL, bytes INTEGER NOT NULL,
              content_type TEXT NOT NULL, http_status INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS connector_observations (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
              provider TEXT NOT NULL, source_record_id TEXT NOT NULL, sport TEXT NOT NULL,
              event_date TEXT NOT NULL, status TEXT NOT NULL, content_hash TEXT NOT NULL,
              acquisition_id TEXT NOT NULL REFERENCES connector_acquisitions(id),
              received_at TEXT NOT NULL, usable_at TEXT NOT NULL, record TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS connector_latest ON connector_observations(provider,source_record_id,seq DESC);
            CREATE INDEX IF NOT EXISTS connector_events ON connector_observations(sport,event_date,status);
            CREATE TABLE IF NOT EXISTS connector_quarantine (
              id TEXT PRIMARY KEY, provider TEXT NOT NULL, source_record_id TEXT,
              reason TEXT NOT NULL, acquisition_id TEXT, record TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS connector_identity_review (
              id TEXT PRIMARY KEY, provider TEXT NOT NULL, source_record_id TEXT NOT NULL,
              other_provider TEXT NOT NULL, other_record_id TEXT NOT NULL, reason TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'review_required', created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS connector_attempts (
              id TEXT PRIMARY KEY, job_id TEXT, provider TEXT NOT NULL, operation TEXT NOT NULL,
              started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
              result TEXT, error TEXT);
            CREATE INDEX IF NOT EXISTS connector_attempt_provider ON connector_attempts(provider,started_at DESC);
            CREATE TABLE IF NOT EXISTS connector_settings (
              provider TEXT PRIMARY KEY, config TEXT NOT NULL DEFAULT '{}',
              interval_seconds INTEGER NOT NULL DEFAULT 0, next_due REAL NOT NULL DEFAULT 0);
            ''')
            # v1's lifetime content uniqueness lost A -> B -> A corrections.
            # Retain every historical row/ID and replace only the owned table's
            # uniqueness constraint, atomically, before accepting new writes.
            definition = db.execute("SELECT sql FROM sqlite_master WHERE name='connector_observations'").fetchone()[0]
            if 'UNIQUE(provider,source_record_id,content_hash)' in definition.replace(' ', '').replace('\n', ''):
                db.execute('BEGIN IMMEDIATE')
                replacement = definition.replace('connector_observations', 'connector_observations_v2', 1)
                replacement = re.sub(r',\s*UNIQUE\s*\(provider,\s*source_record_id,\s*content_hash\)', '', replacement, flags=re.IGNORECASE)
                db.execute(replacement)
                db.execute('INSERT INTO connector_observations_v2 SELECT * FROM connector_observations')
                db.execute('DROP TABLE connector_observations')
                db.execute('ALTER TABLE connector_observations_v2 RENAME TO connector_observations')
                db.execute('CREATE INDEX connector_latest ON connector_observations(provider,source_record_id,seq DESC)')
                db.execute('CREATE INDEX connector_events ON connector_observations(sport,event_date,status)')
            db.commit()

    def receipt(self, provider, doc):
        with closing(self.product.connect()) as db:
            db.execute('INSERT INTO connector_acquisitions VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (doc.acquisition_id, provider, provider+'/1', doc.url, doc.resolved_url,
                 doc.captured_at, doc.sha256, doc.raw_reference, len(doc.body), doc.content_type, doc.http_status))
            db.commit()

    def settings(self, provider):
        with closing(self.product.connect()) as db:
            row = db.execute('SELECT config,interval_seconds,next_due FROM connector_settings WHERE provider=?', (provider,)).fetchone()
        return {'config': json.loads(row[0]), 'interval_seconds': row[1], 'next_due': row[2]} if row else {'config': {}, 'interval_seconds': 0, 'next_due': 0}

    def start(self, provider, operation, job_id=None):
        ident = uuid4().hex
        with closing(self.product.connect()) as db:
            db.execute('INSERT INTO connector_attempts(id,job_id,provider,operation,started_at,status) VALUES(?,?,?,?,?,?)',
                (ident, job_id, provider, operation, utc_now(), 'running'))
            db.commit()
        return ident

    def finish(self, ident, result=None, error=None):
        with closing(self.product.connect()) as db:
            db.execute('UPDATE connector_attempts SET finished_at=?,status=?,result=?,error=? WHERE id=?',
                (utc_now(), 'failed' if error else 'succeeded', json.dumps(result) if result else None,
                 json.dumps(error) if error else None, ident))
            db.commit()

    def attempts(self, provider, limit=10):
        with closing(self.product.connect()) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute('SELECT * FROM connector_attempts WHERE provider=? ORDER BY started_at DESC LIMIT ?', (provider, limit)).fetchall()
        return [{**dict(r), 'result': json.loads(r['result']) if r['result'] else None,
                 'error': json.loads(r['error']) if r['error'] else None} for r in rows]

    @staticmethod
    def validate(record):
        if PROVENANCE_FIELD in record:
            raise ValueError('RESERVED_PROVENANCE_FIELD')
        for field in ('source_record_id', 'sport', 'competition', 'home', 'away', 'event_date', 'source_document_sha256'):
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise ValueError('MISSING_'+field.upper())
        date.fromisoformat(record['event_date'])
        if record['status'] not in ('historical_result', 'scheduled', 'live', 'cancelled', 'synthetic'):
            raise ValueError('INVALID_STATUS')
        if record['home'] == record['away']:
            raise ValueError('IDENTICAL_PARTICIPANTS')
        for field in ('score_home', 'score_away'):
            if record.get(field) is not None and (type(record[field]) is not int or record[field] < 0):
                raise ValueError('INVALID_SCORE')
        if not isinstance(record.get('odds', []), list):
            raise ValueError('INVALID_ODDS')
        for quote in record.get('odds', []):
            if not isinstance(quote, dict):
                raise ValueError('INVALID_ODDS')
            price = quote.get('decimal_odds')
            if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 1:
                raise ValueError('INVALID_ODDS')
            for field in ('provider', 'feed', 'market', 'period', 'selection', 'settlement_rules'):
                if not quote.get(field):
                    raise ValueError('INCOMPLETE_MARKET_IDENTITY')
        Store.references(record)

    @staticmethod
    def references(record):
        """Only adapter-declared source hashes become document dependencies."""
        result = {}

        def add(value, field):
            if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value):
                raise ValueError('INVALID_DOCUMENT_REFERENCE')
            result.setdefault(value, []).append(field)

        add(record.get('source_document_sha256'), 'source_document_sha256')
        for index, quote in enumerate(record.get('odds', [])):
            if 'source_document_sha256' in quote:
                add(quote['source_document_sha256'], 'odds/'+str(index)+'/source_document_sha256')
        attributes = record.get('attributes', {})
        if not isinstance(attributes, dict):
            raise ValueError('INVALID_ATTRIBUTES')
        if 'catalog_sha256' in attributes:
            add(attributes['catalog_sha256'], 'attributes/catalog_sha256')
        if 'related_source_sha256' in attributes:
            related = attributes['related_source_sha256']
            if not isinstance(related, list) or len(related) > 256:
                raise ValueError('INVALID_DOCUMENT_REFERENCE')
            for index, value in enumerate(related):
                add(value, 'attributes/related_source_sha256/'+str(index))
        return result

    @staticmethod
    def _acquisition_row(db, ident):
        row = db.execute('SELECT '+','.join(ACQUISITION_COLUMNS)+' FROM connector_acquisitions WHERE id=?', (ident,)).fetchone()
        return dict(zip(ACQUISITION_COLUMNS, row)) if row else None

    @staticmethod
    def _acquisition_metadata(row):
        # Raw response bytes and filesystem paths are deliberately absent. URLs
        # are redacted again for older receipts that predate retaining Transport.
        result = {key: row[key] for key in ACQUISITION_COLUMNS if key != 'raw_reference'}
        for key in ('original_url', 'resolved_url'):
            result[key] = redact_url(result[key])
        result['metadata_url'] = '/dragon/api/v1/connections/'+row['provider']+'/acquisitions/'+row['id']
        return result

    def acquisition(self, provider, ident):
        with closing(self.product.connect()) as db:
            row = self._acquisition_row(db, ident)
        if not row or row['provider'] != provider:
            raise LookupError('ACQUISITION_NOT_FOUND')
        return self._acquisition_metadata(row)

    def _supplied_documents(self, db, provider, documents):
        """Validate each complete payload once, rather than once per sports row."""
        result = {}
        for doc in documents:
            value = {'document': doc, 'error': None, 'metadata': None}
            retained = self._acquisition_row(db, doc.acquisition_id)
            if not retained:
                value['error'] = 'MISSING_ACQUISITION'
            elif retained['provider'] != provider:
                value['error'] = 'ACQUISITION_PROVIDER_MISMATCH'
            elif (hashlib.sha256(doc.body).hexdigest() != doc.sha256
                  or retained['sha256'] != doc.sha256 or retained['bytes'] != len(doc.body)
                  or retained['captured_at'] != doc.captured_at or retained['original_url'] != doc.url
                  or retained['resolved_url'] != doc.resolved_url or retained['raw_reference'] != doc.raw_reference
                  or retained['content_type'] != doc.content_type or retained['http_status'] != doc.http_status):
                value['error'] = 'ACQUISITION_METADATA_MISMATCH'
            elif retained['http_status'] != 200:
                value['error'] = 'ACQUISITION_NOT_SUCCESSFUL'
            else:
                value['metadata'] = self._acquisition_metadata(retained)
            result.setdefault(doc.sha256, {})[doc.acquisition_id] = value
        return result

    def _bindings(self, provider, record, supplied):
        documents = {}
        for source_hash, references in self.references(record).items():
            candidates = list(supplied.get(source_hash, {}).values())
            if not candidates:
                raise ValueError('MISSING_ACQUISITION')
            if len(candidates) != 1:
                raise ValueError('AMBIGUOUS_ACQUISITION')
            selected = candidates[0]
            if selected['error']:
                raise ValueError(selected['error'])
            documents[source_hash] = {'acquisition': selected['metadata'], 'references': references}
        return {'version': 1, 'provider': provider, 'documents': documents}

    def _validated_bindings(self, provider, record, supplied, conflict=False):
        self.validate(record)
        if conflict:
            raise ValueError('AMBIGUOUS_SOURCE_ID')
        return self._bindings(provider, record, supplied)

    def validate_batch(self, provider, records, documents):
        """Shared read-only preflight for Test diagnostics and Sync counts."""
        groups = {}
        for record in records:
            groups.setdefault(record.get('source_record_id', ''), set()).add(digest(record))
        valid, reasons = [], {}
        with closing(self.product.connect()) as db:
            supplied = self._supplied_documents(db, provider, documents)
            for record in records:
                try:
                    self._validated_bindings(provider, record, supplied,
                                             len(groups[record.get('source_record_id', '')]) > 1)
                    valid.append(record)
                except ValueError as error:
                    reasons[str(error)] = reasons.get(str(error), 0)+1
        return {'valid_records': valid, 'normalized_rows': len(valid), 'invalid_rows': len(records)-len(valid),
                'normalization_errors': reasons}

    def bound_documents(self, observation):
        """Resolve exact persisted acquisition IDs, never the newest matching hash."""
        record, provider = observation['record'], observation['provider']
        saved = record.get(PROVENANCE_FIELD)
        if saved is None:
            # The primary observation FK is evidence for the primary payload in
            # legacy rows. It establishes no binding to a secondary hash.
            try:
                primary = self.acquisition(provider, observation['acquisition_id'])
            except LookupError:
                return []
            if primary['sha256'] != observation['raw_sha256']:
                return []
            return [{**primary, 'status': 'bound', 'references': ['source_document_sha256'],
                     'binding_basis': 'legacy_primary_foreign_key'}]
        if not isinstance(saved, dict) or saved.get('version') != 1 or saved.get('provider') != provider or not isinstance(saved.get('documents'), dict):
            return []
        result = []
        with closing(self.product.connect()) as db:
            for source_hash, binding in saved['documents'].items():
                item = {'sha256': source_hash, 'status': 'unresolved', 'code': 'BOUND_ACQUISITION_UNAVAILABLE'}
                if isinstance(binding, dict) and isinstance(binding.get('acquisition'), dict) and isinstance(binding.get('references'), list):
                    expected = binding['acquisition']
                    retained = self._acquisition_row(db, expected.get('id'))
                    item['references'] = binding['references']
                    if (retained and retained['provider'] == provider and retained['sha256'] == source_hash
                            and self._acquisition_metadata(retained) == expected):
                        item = {**expected, 'status': 'bound', 'references': binding['references'],
                                'binding_basis': 'stored_acquisition_id'}
                result.append(item)
        return result

    @staticmethod
    def quote_source(observation, quote, index):
        source_hash = quote.get('source_document_sha256')
        if not source_hash:
            return {'status': 'unresolved', 'code': 'QUOTE_SOURCE_UNDECLARED'}
        reference = 'odds/'+str(index)+'/source_document_sha256'
        for document in observation.get('source_documents', []):
            if document.get('sha256') != source_hash:
                continue
            if document['status'] != 'bound':
                return {'status': 'unresolved', 'code': document.get('code', 'BOUND_ACQUISITION_UNAVAILABLE')}
            if reference in document['references'] or document.get('binding_basis') == 'legacy_primary_foreign_key':
                return document
        return {'status': 'unresolved', 'code': 'QUOTE_ACQUISITION_UNBOUND'}

    def ingest(self, provider, records, documents):
        candidates = {}
        for record in records:
            key = record.get('source_record_id', '')
            candidates.setdefault(key, []).append(record)
        inserted, quarantined, unchanged, normalized = 0, 0, 0, 0
        reasons = {}
        with closing(self.product.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            supplied = self._supplied_documents(db, provider, documents)
            for native_id, group in candidates.items():
                conflict = len({digest(r) for r in group}) > 1
                for record in group[:1] if not conflict else group:
                    weight = 1 if conflict else len(group)
                    try:
                        bindings = self._validated_bindings(provider, record, supplied, conflict)
                        primary = bindings['documents'][record['source_document_sha256']]['acquisition']
                    except (ValueError, KeyError) as exc:
                        reason = str(exc) if isinstance(exc, ValueError) else 'MISSING_ACQUISITION'
                        reasons[reason] = reasons.get(reason, 0)+weight
                        qid = digest([provider, record, reason])
                        db.execute('INSERT OR IGNORE INTO connector_quarantine VALUES(?,?,?,?,?,?,?)',
                            (qid, provider, native_id, reason, None, json.dumps(record), utc_now()))
                        quarantined += 1
                        continue
                    normalized += weight
                    content_hash = semantic_digest(record)
                    previous = db.execute('SELECT id,content_hash,record FROM connector_observations WHERE provider=? AND source_record_id=? ORDER BY seq DESC LIMIT 1', (provider, native_id)).fetchone()
                    # Historical adapters hashed their capture attributes. Compare
                    # the last retained record under today's semantic projection
                    # without rewriting its immutable hash, ID or provenance.
                    if previous and (previous[1] == content_hash or semantic_digest(json.loads(previous[2])) == content_hash):
                        unchanged += 1
                        continue
                    evidence_id = digest(['observation-v2', provider, native_id, content_hash, previous[0] if previous else None])
                    retained_record = {**record, PROVENANCE_FIELD: bindings}
                    cursor = db.execute('INSERT OR IGNORE INTO connector_observations(id,provider,source_record_id,sport,event_date,status,content_hash,acquisition_id,received_at,usable_at,record) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                        (evidence_id, provider, native_id, record['sport'], record['event_date'], record['status'],
                         content_hash, primary['id'], primary['captured_at'], utc_now(), json.dumps(retained_record, ensure_ascii=False)))
                    inserted += cursor.rowcount
                    unchanged += 1-cursor.rowcount
            db.commit()
        # A committed writer acknowledgement is distinct from the receipt time;
        # readers use their completed read snapshot, never a pre-commit clock alone.
        self.review_identities(provider)
        return {'inserted': inserted, 'unchanged': unchanged, 'quarantined': quarantined,
                'normalized_rows': normalized, 'invalid_rows': len(records)-normalized, 'normalization_errors': reasons,
                'record_count': self.count(provider), 'persistence_acknowledged_at': utc_now(),
                'matches_url': '/dragon/api/v1/matches?provider='+provider,
                'records_url': '/dragon/api/v1/connections/'+provider+'/records'}

    def review_identities(self, provider):
        index = {}
        items = self.rows()
        for legacy in self.product.rows():
            if '_connector' not in legacy:
                items.append({'provider': legacy['source_id'], 'source_record_id': legacy['fixture_key'],
                    'record': {'sport': 'football', 'event_date': legacy['event_date'],
                               'home': legacy['home'], 'away': legacy['away']}})
        for item in items:
            record = item['record']
            key = (record['sport'], record['event_date'], *sorted((record['home'].casefold().strip(), record['away'].casefold().strip())))
            index.setdefault(key, []).append(item)
        with closing(self.product.connect()) as db:
            for group in index.values():
                selected = [r for r in group if r['provider'] == provider]
                other = [r for r in group if r['provider'] != provider]
                for left in selected:
                    for right in other:
                        parts = sorted(((left['provider'], left['source_record_id']), (right['provider'], right['source_record_id'])))
                        ident = digest(['candidate-mapping-v1', parts])
                        reason = 'Same sport, date and participant text across sources; competition, aliases, scheduled-time revisions and market compatibility require review. Records remain separate.'
                        db.execute('INSERT OR IGNORE INTO connector_identity_review(id,provider,source_record_id,other_provider,other_record_id,reason,created_at) VALUES(?,?,?,?,?,?,?)',
                            (ident, left['provider'], left['source_record_id'], right['provider'], right['source_record_id'], reason, utc_now()))
            db.commit()

    def rows(self, provider=None, sport=None):
        query = '''SELECT o.*,a.original_url,a.resolved_url,a.sha256 AS raw_sha256,a.raw_reference,a.adapter_version
          FROM connector_observations o JOIN connector_acquisitions a ON a.id=o.acquisition_id
          WHERE o.seq=(SELECT MAX(n.seq) FROM connector_observations n WHERE n.provider=o.provider AND n.source_record_id=o.source_record_id)'''
        args = []
        for name, value in (('provider', provider), ('sport', sport)):
            if value:
                query += ' AND o.'+name+'=?'
                args.append(value)
        query += ' ORDER BY o.event_date DESC,o.id'
        with closing(self.product.connect()) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(query, args).fetchall()
        return [{**dict(row), 'record': json.loads(row['record'])} for row in rows]

    def count(self, provider):
        with closing(self.product.connect()) as db:
            return db.execute('SELECT COUNT(DISTINCT source_record_id) FROM connector_observations WHERE provider=?', (provider,)).fetchone()[0]

    def evidence(self, ident):
        with closing(self.product.connect()) as db:
            db.row_factory = sqlite3.Row
            row = db.execute('SELECT o.*,a.original_url,a.resolved_url,a.sha256 AS raw_sha256,a.raw_reference,a.adapter_version FROM connector_observations o JOIN connector_acquisitions a ON a.id=o.acquisition_id WHERE o.id=?', (ident,)).fetchone()
        if not row:
            raise LookupError('EVIDENCE_NOT_FOUND')
        result = {**dict(row), 'evidence_id': row['id'], 'source_id': row['provider'], 'record': json.loads(row['record'])}
        result['source_documents'] = self.bound_documents(result)
        return result

    def page(self, provider, limit=50, offset=0, status=None):
        rows = self.rows(provider)
        if status:
            rows = [r for r in rows if r['status'] == status]
        return {'items': rows[offset:offset+limit], 'total': len(rows), 'limit': limit, 'offset': offset,
                'as_of': utc_now(), 'identity_policy': 'Provider-scoped; cross-provider identities require explicit review.'}
