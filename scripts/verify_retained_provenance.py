"""Re-ingest exact retained provider cohorts in a private SQLite backup.

This is retained_evidence_not_fresh_http verification. It never starts a server,
creates an acquisition/capture clock, reads credentials or writes running state.
The receipt IDs in successful original attempts identify secondary documents;
an ambiguous original cohort is rejected rather than guessed from equal hashes.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import time
import traceback
from unittest.mock import patch
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
EXPECTED = {'football-data-couk': 380, 'statsbomb': 64, 'nflverse': 285, 'moneypuck': 1394, 'cricsheet': 17}
MODE = 'retained_evidence_not_fresh_http'


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')).encode()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf-8')


def connect(path, readonly=False):
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=15) if readonly else sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    return db


def table_digest(db, table):
    rows = db.execute('SELECT * FROM "' + table + '" ORDER BY rowid').fetchall()
    return {'rows': len(rows), 'sha256': hashlib.sha256(b'\n'.join(canonical(list(row)) for row in rows)).hexdigest()}


def baseline(path):
    with closing(connect(path, True)) as db:
        schema = [list(row) for row in db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY type,name')]
        tables = {name: table_digest(db, name) for name in
                  ('connector_observations', 'connector_quarantine', 'connector_acquisitions', 'connector_attempts')}
        counts = {provider: db.execute('SELECT COUNT(DISTINCT source_record_id) FROM connector_observations WHERE provider=?', (provider,)).fetchone()[0]
                  for provider in EXPECTED}
        return {'schema_sha256': hashlib.sha256(canonical(schema)).hexdigest(), 'tables': tables, 'counts': counts}


class CountingHashlib:
    """Count the Store's full-payload hash once per live Document body object."""
    def __init__(self, documents):
        self.bodies = {id(doc.body): doc.acquisition_id for doc in documents}
        self.counts = {doc.acquisition_id: 0 for doc in documents}

    def sha256(self, data=b'', *args, **kwargs):
        ident = self.bodies.get(id(data))
        if ident is not None:
            self.counts[ident] += 1
        return hashlib.sha256(data, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(hashlib, name)


def counted(operation, documents, store_module):
    counter = CountingHashlib(documents)
    with patch.object(store_module, 'hashlib', counter):
        result = operation()
    assert all(value == 1 for value in counter.counts.values()), 'A payload was not validated exactly once in this operation.'
    return result, counter.counts


def cohorts(db, provider, store_module):
    rows = db.execute('''SELECT o.* FROM connector_observations o
      WHERE provider=? AND seq=(SELECT MAX(n.seq) FROM connector_observations n
      WHERE n.provider=o.provider AND n.source_record_id=o.source_record_id) ORDER BY o.source_record_id''', (provider,)).fetchall()
    grouped = defaultdict(list)
    for row in rows:
        record = json.loads(row['record'])
        record.pop(store_module.PROVENANCE_FIELD, None)
        grouped[row['acquisition_id']].append({'id': row['id'], 'content_hash': row['content_hash'], 'record': record})
    attempts = []
    for row in db.execute("SELECT id,result FROM connector_attempts WHERE provider=? AND operation='sync' AND status='succeeded' AND result IS NOT NULL", (provider,)):
        result = json.loads(row['result'])
        if result.get('provider') != provider or not isinstance(result.get('acquisitions'), list):
            raise ValueError('INVALID_RETAINED_ATTEMPT')
        attempts.append((row['id'], result['acquisitions']))
    output = []
    for primary_id, observations in grouped.items():
        candidates = {}
        for attempt_id, acquisitions in attempts:
            ids = [item['id'] for item in acquisitions]
            if len(ids) != len(set(ids)):
                raise ValueError('DUPLICATE_RETAINED_ACQUISITION_ID')
            if primary_id in ids:
                key = tuple(sorted(ids))
                if key not in candidates:
                    candidates[key] = {'attempt_ids': [], 'acquisitions': acquisitions}
                elif canonical(candidates[key]['acquisitions']) != canonical(acquisitions):
                    raise ValueError('CONFLICTING_RETAINED_COHORT_METADATA')
                candidates[key]['attempt_ids'].append(attempt_id)
        if len(candidates) != 1:
            raise ValueError('AMBIGUOUS_OR_MISSING_ORIGINAL_COHORT:' + provider + ':' + primary_id)
        cohort = next(iter(candidates.values()))
        required = set()
        for observation in observations:
            required.update(store_module.Store.references(observation['record']))
        selected = []
        for source_hash in sorted(required):
            choices = [item for item in cohort['acquisitions'] if item['sha256'] == source_hash]
            if len(choices) != 1:
                raise ValueError('AMBIGUOUS_OR_MISSING_REQUIRED_DOCUMENT:' + provider)
            summary = choices[0]
            receipt = db.execute('SELECT * FROM connector_acquisitions WHERE id=?', (summary['id'],)).fetchone()
            if not receipt or receipt['provider'] != provider or receipt['http_status'] != 200:
                raise ValueError('INVALID_RETAINED_RECEIPT')
            receipt = dict(receipt)
            for left, right in (('sha256', 'sha256'), ('original_url', 'url'), ('resolved_url', 'resolved_url'), ('bytes', 'bytes')):
                if receipt[left] != summary[right]:
                    raise ValueError('ATTEMPT_AND_RECEIPT_DISAGREE')
            selected.append(receipt)
        if primary_id not in {item['id'] for item in selected}:
            raise ValueError('ORIGINAL_PRIMARY_DOCUMENT_NOT_REQUIRED')
        output.append({'provider': provider, 'primary_id': primary_id, 'attempt_ids': cohort['attempt_ids'],
                       'original_cohort_ids': [item['id'] for item in cohort['acquisitions']],
                       'receipts': selected, 'observations': observations})
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=ROOT / 'runtime/connections/product')
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, work, output = args.state.resolve(), args.work.resolve(), args.output.resolve()
    if (not source.is_relative_to(ROOT) or not (source / 'core.sqlite3').is_file()
            or not work.is_relative_to(ROOT / 'runtime/scratch') or not work.name.startswith('provenance-retained-')
            or work.exists() or not output.is_relative_to(ROOT / 'build/connections/evidence') or output.exists()):
        parser.error('Use the existing project state and fresh owned private work/evidence paths.')
    work.mkdir(parents=True); output.mkdir(parents=True)
    from dragonhydra.server import protect
    protect(work); protect(output)
    started = time.monotonic()
    report = {'schema_version': 1, 'mode': MODE, 'started_at': stamp(), 'passed': False,
              'source_state': str(source.relative_to(ROOT)), 'private_work': str(work.relative_to(ROOT)),
              'source_database_open_mode': 'ro', 'fresh_http': False, 'new_acquisitions_created': False,
              'capture_clock_policy': 'Exact retained receipt clocks only; current verification/persistence acknowledgements are not captures.',
              'cohorts': [], 'http_calls_attempted': 0}
    source_paths = ('src/dragonhydra/connectors/store.py', 'src/dragonhydra/connectors/core.py',
                    'src/dragonhydra/connectors/service.py', 'src/dragonhydra/product.py',
                    'src/dragonhydra/connectors/research.py', 'src/dragonhydra/connectors/football.py',
                    'src/dragonhydra/api.py', 'scripts/verify_retained_provenance.py')
    report['source_bindings'] = {name: digest(ROOT / name) for name in source_paths}
    state = work / 'state'; state.mkdir()
    snapshot = state / 'core.sqlite3'
    try:
        with closing(connect(source / 'core.sqlite3', True)) as original, closing(connect(snapshot)) as copied:
            original.backup(copied)
        report['before'] = baseline(snapshot)
        assert report['before']['counts'] == EXPECTED
        from dragonhydra.connectors import store as store_module
        from dragonhydra.connectors.core import Document
        from dragonhydra.product import Product, identity
        with closing(connect(snapshot, True)) as db:
            groups = [cohort for provider in EXPECTED for cohort in cohorts(db, provider, store_module)]
        raw_source = (source / 'raw/connectors').resolve()
        raw_target = state / 'raw/connectors'; raw_target.mkdir(parents=True)
        documents = {}
        receipts = {}
        for cohort in groups:
            for receipt in cohort['receipts']:
                ident, reference = receipt['id'], receipt['raw_reference']
                if ident in documents:
                    assert receipts[ident] == receipt
                    continue
                if Path(reference).name != reference or reference in ('', '.', '..'):
                    raise ValueError('UNSAFE_RETAINED_RAW_REFERENCE')
                original = (raw_source / reference).resolve()
                assert original.is_relative_to(source) and original.is_relative_to(ROOT) and original.is_file() and not original.is_symlink()
                copied = raw_target / reference
                if not copied.exists():
                    shutil.copyfile(original, copied)
                assert copied.stat().st_size == receipt['bytes']
                # The Store operation performs the sole body hash per supplied
                # acquisition. Copying/loading does not rehash MoneyPuck per row.
                body = copied.read_bytes()
                documents[ident] = Document(receipt['original_url'], receipt['resolved_url'], body, receipt['captured_at'],
                                             receipt['sha256'], receipt['content_type'], ident, reference, receipt['http_status'])
                receipts[ident] = receipt
        write_json(work / 'RETAINED-ACQUISITIONS.json', list(receipts.values()))
        report['retained_documents_loaded'] = len(documents)
        report['retained_raw_bytes_loaded'] = sum(len(item.body) for item in documents.values())
        product = Product(state)
        assert baseline(snapshot)['schema_sha256'] == report['before']['schema_sha256'], 'The replay changed the database schema.'
        store = product.connector_store

        def no_http(*args, **kwargs):
            report['http_calls_attempted'] += 1
            raise AssertionError('HTTP_NOT_ALLOWED_IN_RETAINED_VERIFICATION')

        with patch.object(urllib.request, 'urlopen', no_http), patch.object(urllib.request.OpenerDirector, 'open', no_http):
            for cohort in groups:
                tick = time.monotonic()
                provider = cohort['provider']
                records = [item['record'] for item in cohort['observations']]
                supplied = [documents[item['id']] for item in cohort['receipts']]
                report['active_cohort'] = {'provider': provider, 'original_primary_id': cohort['primary_id'],
                                           'records': len(records), 'supplied_acquisition_ids': [doc.acquisition_id for doc in supplied]}
                validation, preflight_hashes = counted(lambda: store.validate_batch(provider, records, supplied), supplied, store_module)
                report['active_cohort']['preflight'] = {'valid_rows': len(validation['valid_records']),
                                                        'invalid_rows': validation['invalid_rows'], 'normalization_errors': validation['normalization_errors'],
                                                        'body_hash_counts': preflight_hashes}
                assert validation['invalid_rows'] == 0 and len(validation['valid_records']) == len(records)
                result, ingest_hashes = counted(lambda: store.ingest(provider, records, supplied), supplied, store_module)
                report['active_cohort'].update(ingest_result=result, ingest_body_hash_counts=ingest_hashes)
                assert result['inserted'] == 0 and result['unchanged'] == len(records) and result['quarantined'] == 0
                assert result['record_count'] == EXPECTED[provider]
                assert result['normalized_rows'] == len(records) and result['invalid_rows'] == 0
                entry = {'provider': provider, 'mode': MODE, 'records': len(records), 'original_primary_id': cohort['primary_id'],
                         'original_attempt_ids': cohort['attempt_ids'], 'original_cohort_ids': cohort['original_cohort_ids'],
                         'required_acquisition_ids': [doc.acquisition_id for doc in supplied],
                         'original_capture_clocks': {doc.acquisition_id: doc.captured_at for doc in supplied},
                         'preflight_body_hash_counts': preflight_hashes, 'ingest_body_hash_counts': ingest_hashes,
                         'result': result, 'elapsed_seconds': round(time.monotonic() - tick, 3)}
                if provider == 'statsbomb':
                    catalogs = {record['attributes']['catalog_sha256'] for record in records}
                    without_catalog = [doc for doc in supplied if doc.sha256 not in catalogs]
                    rejected, omission_hashes = counted(lambda: store.validate_batch(provider, records, without_catalog), without_catalog, store_module)
                    assert rejected['invalid_rows'] == len(records) and rejected['normalization_errors'] == {'MISSING_ACQUISITION': len(records)}
                    entry['catalog_omission_preflight'] = {'invalid_rows': rejected['invalid_rows'], 'normalization_errors': rejected['normalization_errors'],
                                                         'body_hash_counts': omission_hashes, 'quarantine_written': False}
                report['cohorts'].append(entry)
                print(json.dumps({'provider': provider, 'mode': MODE, 'inserted': result['inserted'], 'unchanged': result['unchanged'],
                                  'quarantined': result['quarantined'], 'payloads_validated_once_per_operation': len(supplied)}), flush=True)
            archive = next(group for group in groups if group['provider'] == 'football-data-couk')
            selected = next(item for item in archive['observations'] if item['record'].get('odds'))
            primary = documents[archive['primary_id']]
            match_id = identity('fixture', 'football-data-couk', selected['record']['source_record_id'])
            odds = product.odds(match_id, history=True)
            assert odds['items'] and odds['axis'] == 'archive_phase'
            for quote in odds['items']:
                assert quote['provenance_status'] == 'bound' and quote['acquisition_id'] == primary.acquisition_id
                assert quote['captured_at'] == primary.captured_at and quote['source_document_sha256'] == primary.sha256
                assert quote['source_url'] == primary.url and quote['resolved_source_url'] == primary.resolved_url
                assert quote['quote_at'] is None and quote['archive_phase'] in ('opening', 'closing')
            report['archive_quote_projection'] = {'passed': True, 'match_id': match_id, 'quotes': len(odds['items']),
                                                   'primary_acquisition_id': primary.acquisition_id,
                                                   'captured_at': primary.captured_at, 'sha256': primary.sha256,
                                                   'axis': odds['axis'], 'quote_at_available': False,
                                                   'legacy_primary_binding_retained': True}
        report['after'] = baseline(snapshot)
        assert report['after'] == report['before'], 'Replay added or changed an observation, receipt, quarantine, attempt or schema.'
        assert report['http_calls_attempted'] == 0
        for name, expected in report['source_bindings'].items():
            assert digest(ROOT / name) == expected, 'Verification source changed during execution.'
        report['passed'] = True
        report.pop('active_cohort', None)
    except Exception as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error),
                           'line': traceback.extract_tb(error.__traceback__)[-1].lineno}
    finally:
        report.update(finished_at=stamp(), elapsed_seconds=round(time.monotonic() - started, 3))
        write_json(output / 'verification.json', report)
        write_json(work / 'VERIFICATION.json', report)
    print(json.dumps({'passed': report['passed'], 'mode': MODE, 'elapsed_seconds': report['elapsed_seconds'],
                      'error': report.get('error'), 'http_calls_attempted': report['http_calls_attempted'],
                      'report': str((output / 'verification.json').relative_to(ROOT))}), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
