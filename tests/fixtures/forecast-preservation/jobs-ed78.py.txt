"""Persisted, bounded jobs and committed update outbox for the product server."""
from __future__ import annotations

from contextlib import closing
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from urllib.request import Request, urlopen
from urllib.error import URLError
from uuid import uuid4

from . import public_results
from .product import API, now

PUBLIC_FILES = ('openfootball-2025-26-en1.json', 'openfootball-2026-27-en1.json')
PUBLIC_URLS = ('https://raw.githubusercontent.com/openfootball/football.json/master/2025-26/en.1.json',
               'https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/en.1.json')
TARGETS = (
 ('api-football', 'API-FOOTBALL / API-SPORTS', 'https://www.api-football.com/documentation_v3', 'api-key'),
 ('the-odds-api', 'The Odds API', 'https://the-odds-api.com/liveapi/guides/v4/', 'api-key'),
 ('sportmonks', 'Sportmonks', 'https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/fixtures', 'api-token'),
 ('football-data-org', 'football-data.org', 'https://docs.football-data.org/general/v4/index.html', 'api-key'),
 ('football-data-couk', 'Football-Data.co.uk', 'https://www.football-data.co.uk/', 'none'),
 ('openfootball', 'OpenFootball', 'https://github.com/openfootball/football.json', 'none'),
 ('statsbomb', 'StatsBomb Open Data', 'https://github.com/statsbomb/open-data', 'none'),
 ('nflverse', 'nflverse', 'https://github.com/nflverse/nflverse-data', 'none'),
 ('moneypuck', 'MoneyPuck', 'https://moneypuck.com/data.htm', 'none'),
 ('cricsheet', 'Cricsheet', 'https://cricsheet.org/downloads/', 'none'),
)


def fetch_public(url):
    # The caller supplies a registry-owned URL, never user text. Retain bytes before parsing.
    with urlopen(Request(url, headers={'User-Agent': 'DRAGONHYDRA/0.3 public-fixture-import'}), timeout=15) as response:
        if response.geturl() not in PUBLIC_URLS:
            raise ValueError('UNEXPECTED_SOURCE_REDIRECT')
        content_type = response.headers.get_content_type()
        if content_type not in ('application/json', 'text/plain'):
            raise ValueError('SOURCE_CONTENT_TYPE')
        raw = response.read(8*1024*1024+1)
        if len(raw) > 8*1024*1024:
            raise ValueError('SOURCE_SIZE_LIMIT')
        return raw


class Cancelled(Exception):
    pass


class Interrupted(Exception):
    """The service stopped; the user did not cancel the persisted command."""


class ClaimLost(Exception):
    """Another claim or terminal transition owns this persisted job now."""


class Jobs:
    def __init__(self, product):
        self.product = product
        from .connectors.service import Connections
        self.providers = Connections(product)
        self.stop = threading.Event()
        self.thread = None
        with closing(self.product.connect()) as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS product_schema (version INTEGER PRIMARY KEY);
            INSERT OR IGNORE INTO product_schema VALUES(1);
            CREATE TABLE IF NOT EXISTS product_jobs (
              id TEXT PRIMARY KEY, owner TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
              idempotency_key TEXT, status TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
              attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              heartbeat REAL, lease_until REAL, deadline REAL, cancel_requested INTEGER NOT NULL DEFAULT 0,
              result TEXT, error TEXT, UNIQUE(owner,idempotency_key));
            CREATE TABLE IF NOT EXISTS product_updates (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, payload TEXT NOT NULL, committed_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS product_sessions (
              token_hash TEXT PRIMARY KEY, user TEXT NOT NULL, roles TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS product_bridge_nonces (nonce TEXT PRIMARY KEY, expires REAL NOT NULL);
            ''')
            # Additive migration: queued retry eligibility survives process restarts.
            columns = {r[1] for r in db.execute('PRAGMA table_info(product_jobs)')}
            if 'next_attempt' not in columns:
                db.execute('ALTER TABLE product_jobs ADD COLUMN next_attempt REAL NOT NULL DEFAULT 0')
            db.commit()

        kernel=getattr(self.product,'kernel',None)
        if hasattr(kernel,'bind_worker'):
            kernel.bind_worker(self)

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop.clear()
        self.thread = threading.Thread(target=self.run, name='dragonhydra-job-worker', daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=35)

    def submit(self, kind, payload, owner, key=None):
        if key is not None and not 1 <= len(key) <= 128:
            raise ValueError('INVALID_IDEMPOTENCY_KEY')
        doc = json.dumps(payload, sort_keys=True)
        with closing(self.product.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT id,kind,payload FROM product_jobs WHERE owner=? AND idempotency_key=?', (owner, key)).fetchone() if key else None
            if old:
                if old[1:] != (kind, doc):
                    raise ValueError('IDEMPOTENCY_CONFLICT')
                return self.get(old[0])
            job_id = uuid4().hex
            stamp = now()
            db.execute('INSERT INTO product_jobs(id,owner,kind,payload,idempotency_key,status,created_at,updated_at) VALUES(?,?,?,?,?,\'queued\',?,?)',
                       (job_id, owner, kind, doc, key, stamp, stamp))
            self.event(db, 'job', {'id': job_id, 'status': 'queued'})
            db.commit()
        return self.get(job_id)

    def replay_local_context(self, owner, key, match_id, context_record_id):
        """Replay an explicit context request without rebuilding its frozen data.

        Only package/3 local-explanation requests use this selector comparison.
        The ordinary submit transaction still resolves concurrent first calls.
        """
        if key is not None and not 1 <= len(key) <= 128:
            raise ValueError('INVALID_IDEMPOTENCY_KEY')
        if key is None:
            return None
        with closing(self.product.connect()) as db:
            db.row_factory = sqlite3.Row
            row = db.execute('SELECT * FROM product_jobs WHERE owner=? AND idempotency_key=?', (owner, key)).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row['payload'])
            package = payload['package']
            from .local_ai import SCHEMA_CONTEXT
            matching = (row['kind'] == 'local_explanation' and isinstance(package, dict)
                        and package.get('schema_version') == SCHEMA_CONTEXT
                        and package['event']['id'] == match_id
                        and package['evidence']['C1']['id'] == context_record_id)
        except (ValueError, TypeError, KeyError):
            matching = False
        if not matching:
            raise ValueError('IDEMPOTENCY_CONFLICT')
        return self._decode_job(row)

    @staticmethod
    def event(db, topic, payload):
        db.execute('INSERT INTO product_updates(topic,payload,committed_at) VALUES(?,?,?)', (topic, json.dumps(payload), now()))

    def get(self, job_id):
        with closing(self.product.connect()) as db:
            db.row_factory = __import__('sqlite3').Row
            row = db.execute('SELECT * FROM product_jobs WHERE id=?', (job_id,)).fetchone()
        if not row:
            raise LookupError('JOB_NOT_FOUND')
        return self._decode_job(row)

    @staticmethod
    def _decode_job(row):
        result = dict(row)
        for name in ('payload', 'result', 'error'):
            result[name] = json.loads(result[name]) if result[name] else None
        return result

    @staticmethod
    def require_claim(db, job_id, claim):
        """Pure SELECT ownership guard for a caller's existing transaction.

        The generation is captured by the worker while claiming the job. This
        helper does not renew a lease, commit, or initialize schema. Callers
        decide cancellation/deadline policy using the returned current state.
        """
        if type(claim) is not int or claim < 1:
            raise ValueError('INVALID_JOB_CLAIM')
        row = db.execute("SELECT status,attempts,cancel_requested,deadline FROM product_jobs "
                         "WHERE id=? AND status='running' AND attempts=?", (job_id, claim)).fetchone()
        if row is None:
            raise ClaimLost()
        return dict(zip(('status', 'attempts', 'cancel_requested', 'deadline'), row))

    def cancel(self, job_id):
        with closing(self.product.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status FROM product_jobs WHERE id=?', (job_id,)).fetchone()
            if not row:
                raise LookupError('JOB_NOT_FOUND')
            if row[0] in ('queued', 'running', 'interrupted'):
                state = 'cancelled' if row[0] != 'running' else 'running'
                db.execute('UPDATE product_jobs SET cancel_requested=1,status=?,updated_at=? WHERE id=?', (state, now(), job_id))
                self.event(db, 'job', {'id': job_id, 'status': state})
            db.commit()
        return self.get(job_id)

    def check(self, job_id, claim=None):
        """Check and heartbeat a claim; direct legacy callers may omit it.

        Worker callbacks always supply their captured generation. Omitting it
        checks current job state without asserting ownership of an old claim.
        """
        with closing(self.product.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            if claim is None:
                row = db.execute('SELECT status,attempts,cancel_requested,deadline FROM product_jobs WHERE id=?', (job_id,)).fetchone()
                if row is None:
                    raise LookupError('JOB_NOT_FOUND')
                job = dict(zip(('status', 'attempts', 'cancel_requested', 'deadline'), row))
            else:
                job = self.require_claim(db, job_id, claim)
            if job['cancel_requested']:
                raise Cancelled()
            if self.stop.is_set():
                raise Interrupted()
            tick = time.time()
            if job['deadline'] and tick > job['deadline']:
                raise TimeoutError('JOB_DEADLINE_EXCEEDED')
            if job['status'] == 'running':
                updated = db.execute("UPDATE product_jobs SET heartbeat=?,lease_until=? "
                                     "WHERE id=? AND status='running' AND attempts=?",
                                     (tick, tick+45, job_id, job['attempts']))
                if updated.rowcount != 1:
                    raise ClaimLost()
            db.commit()

    def run_once(self):
        if self.stop.is_set():
            return False
        self.providers.schedule_due(self)
        with closing(self.product.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            stale = db.execute("SELECT id,attempts,cancel_requested,status FROM product_jobs WHERE status='interrupted' OR (status='running' AND lease_until < ?)", (time.time(),)).fetchall()
            for job_id, attempts, cancelled, previous in stale:
                recoverable = not cancelled and (previous == 'interrupted' or attempts < 3)
                state = 'cancelled' if cancelled else 'queued' if recoverable else 'failed'
                error = json.dumps({'code': 'CANCELLED' if cancelled else 'INTERRUPTED',
                    'message': 'Cancelled by the user.' if cancelled else 'Worker stopped or its lease expired; recovering the idempotent operation.'})
                db.execute('UPDATE product_jobs SET status=?,error=?,updated_at=?,lease_until=NULL,next_attempt=0 WHERE id=?', (state, error, now(), job_id))
                if not cancelled:
                    self.event(db, 'job', {'id': job_id, 'status': 'interrupted', 'recoverable': recoverable})
                self.event(db, 'job', {'id': job_id, 'status': state, 'recoverable': recoverable})
            row = db.execute("SELECT id FROM product_jobs WHERE status='queued' AND cancel_requested=0 AND next_attempt<=? ORDER BY created_at LIMIT 1", (time.time(),)).fetchone()
            if not row:
                db.commit()
                return False
            job_id = row[0]
            tick = time.time()
            db.execute("UPDATE product_jobs SET status='running',attempts=attempts+1,heartbeat=?,lease_until=?,deadline=?,updated_at=? WHERE id=?",
                       (tick, tick+45, tick+120, now(), job_id))
            # Freeze the complete execution snapshot, including its generation,
            # while the claim transaction still excludes competing claimants.
            db.row_factory = __import__('sqlite3').Row
            job = self._decode_job(db.execute('SELECT * FROM product_jobs WHERE id=?', (job_id,)).fetchone())
            claim = job['attempts']
            self.event(db, 'job', {'id': job_id, 'status': 'running'})
            db.commit()
        try:
            self.check(job_id, claim)
            result = self.execute(job)
            state, error = 'succeeded', None
        except ClaimLost:
            # A stale worker must not publish a new terminal event or replace
            # the outcome of the generation that now owns this job.
            return True
        except Cancelled:
            result, state, error = None, 'cancelled', {'code': 'CANCELLED', 'message': 'Cancelled before the next operation.'}
        except Interrupted:
            result, state, error = None, 'interrupted', {'code': 'INTERRUPTED', 'message': 'Service stopped; the idempotent job will recover when the worker restarts.'}
        except Exception as exc:
            # Never expose exception text from network transports or credentials.
            result, state, error = None, 'failed', {'code': 'JOB_OPERATION_FAILED', 'message': type(exc).__name__+' during '+job['kind']+'. Retained data remains available.'}
            from .connectors.core import ConnectorError
            if isinstance(exc, ConnectorError):
                error = {'code': exc.code, 'message': exc.message, 'http_status': exc.http_status, 'retry_after': exc.retry_after}
            if job['kind'] != 'statsbomb_context' and isinstance(exc, (TimeoutError, URLError)) and job['attempts'] < 3:
                state = 'queued'
                error['code'] = 'RETRY_PENDING'
                error['message'] = 'Temporary source failure; bounded retry pending. Retained data remains available.'
            if job['kind'] != 'statsbomb_context' and isinstance(exc, ConnectorError) and exc.code in ('NETWORK_UNAVAILABLE', 'RATE_LIMITED') and job['attempts'] < 3:
                state = 'queued'
        with closing(self.product.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                current = self.require_claim(db, job_id, claim)
            except ClaimLost:
                db.rollback()
                return True
            if current['cancel_requested']:
                result, state, error = None, 'cancelled', {'code': 'CANCELLED', 'message': 'Cancelled by the user; retained data remains available.'}
            next_attempt = time.time()+max(2**claim, (error or {}).get('retry_after') or 0) if state == 'queued' else None
            updated = db.execute("UPDATE product_jobs SET status=?,progress=?,result=?,error=?,updated_at=?,heartbeat=?,lease_until=NULL, "
                                 "next_attempt=COALESCE(?,next_attempt) WHERE id=? AND status='running' AND attempts=?",
                       (state, 100 if state == 'succeeded' else 0, json.dumps(result) if result else None,
                        json.dumps(error) if error else None, now(), time.time(), next_attempt, job_id, claim))
            if updated.rowcount != 1:
                db.rollback()
                return True
            self.event(db, 'job', {'id': job_id, 'status': state})
            if state == 'succeeded':
                self.event(db, 'data', {'job_id': job_id, 'kind': job['kind']})
            db.commit()
        return True

    def run(self):
        while not self.stop.is_set():
            try:
                self.product.kernel.observation_tick()
            except Exception:
                # Observer failures stay scoped; existing jobs keep running.
                pass
            try:
                worked = self.run_once()
            except Exception:
                worked = False
            if not worked:
                self.stop.wait(0.2)

    def execute(self, job):
        return self.product.kernel.dispatch_job(self, job)

    def import_public(self, job_id, mode, claim=None):
        imports = []
        for filename, url in zip(PUBLIC_FILES, PUBLIC_URLS):
            self.check(job_id, claim)
            retained = self.product.source_root / 'data' / 'raw' / filename
            receipt = None
            if mode == 'retained':
                raw = retained.read_bytes()
                receipt = json.loads(retained.with_suffix('.json.receipt.json').read_text(encoding='utf-8-sig'))
                url = receipt['source_url']
            else:
                raw = fetch_public(url)
            captured = now()
            fingerprint = hashlib.sha256(raw).hexdigest()
            directory = self.product.state / 'raw'
            directory.mkdir(exist_ok=True)
            raw_path = directory / (fingerprint+'.json')
            # Exact bytes are retained even if schema validation fails.
            if not raw_path.exists():
                raw_path.write_bytes(raw)
            manifest = {'source_url': url, 'sha256': fingerprint, 'bytes': len(raw), 'captured_at': captured,
                        'mode': mode, 'adapter': public_results.ADAPTER_VERSION,
                        'source_capture_receipt': receipt}
            # A content-addressed receipt records the first local retention. Reuse
            # must not rewrite its capture clock or substitute a different mode.
            receipt_path = directory / (fingerprint+'.receipt.json')
            try:
                with receipt_path.open('x', encoding='utf-8') as receipt_file:
                    json.dump(manifest, receipt_file, indent=2)
            except FileExistsError:
                pass
            self.check(job_id, claim)
            with closing(self.product.connect()) as db:
                result = public_results.ingest_bytes(db, raw, source_id=filename, source_url=url,
                    acquisition_id=fingerprint, source_receipt=receipt)
            imports.append(result)
            with closing(self.product.connect()) as db:
                db.execute('BEGIN IMMEDIATE')
                if claim is not None:
                    self.require_claim(db, job_id, claim)
                updated = db.execute("UPDATE product_jobs SET progress=?,heartbeat=?,lease_until=? WHERE id=? AND status='running' "
                                     + ("AND attempts=?" if claim is not None else ''),
                    (len(imports)*45, time.time(), time.time()+45, job_id, *((claim,) if claim is not None else ())))
                if updated.rowcount != 1:
                    raise ClaimLost()
                self.event(db, 'import', {'job_id': job_id, 'source_id': filename, 'inserted': result['inserted']})
                db.commit()
        rows = self.product.rows()
        return {'imports': imports, 'record_count': len(rows), 'inserted': sum(r['inserted'] for r in imports),
                'mode': mode, 'matches_url': API+'/matches', 'last_import': now()}

    def export(self, job):
        row = self.product.present(self.product.find(job['payload']['match_id']))
        kind = job['payload']['format']
        report = {'schema_version': 1, 'generated_at': now(), 'match': row,
                  'explanation': self.product.explanation(row['id']), 'analysis_mode': 'reconstructed_historical_research'}
        report['odds'] = self.product.odds(row['id'])
        report['statistics'] = self.product.find(row['id']).get('_connector', {}).get('statistics', {})
        path = self.product.exports / (job['id']+'.'+kind)
        report_path = path.with_suffix(path.suffix+'.manifest.json')
        private = path.name+'.claim-'+str(job['attempts'])+'.'+uuid4().hex
        temp = path.with_name(private+'.tmp')
        report_temp = path.with_name(private+'.manifest.tmp')
        def safe(value):
            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
                return "'"+value
            return value
        columns = ['id', 'event_date', 'competition', 'home', 'away', 'home_goals', 'away_goals', 'status', 'source_id', 'evidence_id', 'usable_at']
        values = [row['id'], row['event_date'], row['competition'], row['home']['name'], row['away']['name'],
                  row['score']['home'] if row['score'] else None, row['score']['away'] if row['score'] else None,
                  row['status'], row['source_id'], row['evidence_id'], row['usable_at']]
        try:
            self.check(job['id'], job['attempts'])
            if kind == 'json':
                temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            elif kind == 'csv':
                with temp.open('w', encoding='utf-8-sig', newline='') as out:
                    writer = csv.writer(out)
                    writer.writerow(columns)
                    writer.writerow([safe(v) for v in values])
            else:
                from openpyxl import Workbook
                workbook = Workbook()
                sheet = workbook.active
                sheet.title = 'Match'
                sheet.append(columns)
                sheet.append([safe(v) for v in values])
                sheet.freeze_panes = 'A2'
                sheet.auto_filter.ref = sheet.dimensions
                for col in sheet.columns:
                    sheet.column_dimensions[col[0].column_letter].width = min(48, max(14, max(len(str(c.value or '')) for c in col)+2))
                metadata = workbook.create_sheet('Metadata')
                for k, v in {'schema_version': 1, 'generated_at': report['generated_at'], 'source_url': row['source_url'],
                             'analysis_mode': report['analysis_mode'], 'kickoff_precision': row['time_precision'],
                             'odds': report['odds']['reason'], 'explanation_kind': 'deterministic', 'score_scope': row.get('score_scope')}.items():
                    metadata.append([k, safe(v)])
                if report['odds']['items']:
                    sheet = workbook.create_sheet('Odds')
                    fields = ['provider', 'feed', 'market', 'period', 'selection', 'line', 'decimal_odds', 'state', 'quote_at', 'archive_phase', 'captured_at', 'evidence_id']
                    sheet.append(fields)
                    for quote in report['odds']['items']:
                        sheet.append([safe(quote.get(field)) for field in fields])
                    sheet.freeze_panes = 'A2'
                if report['statistics']:
                    sheet = workbook.create_sheet('Statistics')
                    sheet.append(['statistic', 'source_value'])
                    for key, value in report['statistics'].items():
                        sheet.append([safe(key), safe(json.dumps(value) if isinstance(value, (dict, list)) else value)])
                workbook.save(temp)
            report_temp.write_text(json.dumps(report, indent=2), encoding='utf-8')
            fingerprint, size = hashlib.sha256(temp.read_bytes()).hexdigest(), temp.stat().st_size
            # Slow rendering finishes before taking this lock. Reclaim and
            # cancellation cannot interleave the ownership guard with either
            # final replacement for this generation.
            with closing(self.product.connect()) as db:
                db.execute('BEGIN IMMEDIATE')
                current = self.require_claim(db, job['id'], job['attempts'])
                if current['cancel_requested']:
                    raise Cancelled()
                if self.stop.is_set():
                    raise Interrupted()
                if current['deadline'] and time.time() > current['deadline']:
                    raise TimeoutError('JOB_DEADLINE_EXCEEDED')
                os.replace(temp, path)
                os.replace(report_temp, report_path)
                db.commit()
            return {'filename': path.name, 'download_url': API+'/exports/'+job['id']+'/download',
                    'sha256': fingerprint, 'bytes': size, 'format': kind, 'location': str(path)}
        finally:
            # Only this invocation's unpublished siblings belong to this worker.
            temp.unlink(missing_ok=True)
            report_temp.unlink(missing_ok=True)


    def connections(self):
        rows = [r for r in self.product.rows() if r['source_id'].startswith('openfootball-')]
        last = max((r['usable_at'] for r in rows), default=None)
        items = [{'id': key, 'name': name, 'registration_url': url, 'authentication': auth,
                    'implemented': key == 'openfootball', 'fixture_tested': key == 'openfootball',
                    'status': ('Imported retained data' if rows else 'Public source available') if key == 'openfootball' else ('Requires connection' if auth != 'none' else 'Adapter not integrated'),
                    'record_count': len(rows) if key == 'openfootball' else 0,
                    'last_import': last if key == 'openfootball' else None,
                    'capabilities': ['historical_fixtures', 'results'] if key == 'openfootball' else [],
                    'live': False, 'reason': 'Retained import and bounded public fetch implemented; no live stream.' if key == 'openfootball' else 'Registry target; no service import claimed.'}
                   for key, name, url, auth in TARGETS]
        for item in items:
            if item['id'] != 'openfootball':
                item.update(self.providers.describe(item['id']))
        return {'items': items}

    def updates(self, after):
        with closing(self.product.connect()) as db:
            rows = db.execute('SELECT seq,topic,payload,committed_at FROM product_updates WHERE seq>? ORDER BY seq LIMIT 100', (after,)).fetchall()
        return [{'id': r[0], 'topic': r[1], 'data': json.loads(r[2]), 'committed_at': r[3]} for r in rows]
