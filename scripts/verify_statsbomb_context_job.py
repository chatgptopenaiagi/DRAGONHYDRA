"""Independent isolated API/job acceptance with fake provider responses.

Uses the real job coordinator, SQLite journal, Transport retention, parser,
context receipts and authenticated ASGI API. No actual provider HTTP, server
installation, live-state mutation or model call is permitted.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
from email.message import Message
import hashlib
import io
import json
from pathlib import Path
import secrets
import sqlite3
import sys
import threading
import time
import traceback
from unittest.mock import patch
from urllib.error import URLError
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fastapi.testclient import TestClient
from dragonhydra import source_context
from dragonhydra.api import create_app
from dragonhydra.cognition import memory
from dragonhydra.connectors import research, statsbomb_context as binding, statsbomb_context_jobs as service
from dragonhydra.connectors.core import ConnectorError, Document, Transport, utc_now
from dragonhydra.jobs import Jobs
from dragonhydra.product import API, Product, identity
from dragonhydra.server import protect
from verify_statsbomb_parser import EVENTS, SQUADS, canonical


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class Crash(BaseException):
    """A process-death seam deliberately bypassing ordinary job exception handling."""


class Response:
    def __init__(self, url, body, status=200):
        self.url, self.body, self.status = url, io.BytesIO(body), status
        self.headers = Message()
        self.headers['Content-Type'] = 'application/json'
        self.headers['Content-Length'] = str(len(body))
        if status == 302:
            self.headers['Location'] = binding.ROLE_URLS['lineups']
        if status == 429:
            self.headers['Retry-After'] = '60'

    def __enter__(self): return self
    def __exit__(self, *args): self.body.close()
    def getcode(self): return self.status
    def geturl(self): return self.url
    def read(self, size): return self.body.read(size)


class FakeProvider:
    def __init__(self, case):
        self.case = case
        self.requests = []
        self.bodies = {'events': canonical(EVENTS), 'lineups': canonical(SQUADS)}
        self.behavior = None
        self.on_open = None

    def factory(self, *args, **kwargs):
        assert kwargs['max_bytes'] == 8 * 1024 * 1024 and kwargs['follow_redirects'] is False
        transport = Transport(*args, **kwargs)
        transport.opener = self
        return transport

    def open(self, request, timeout):
        assert request.get_method() == 'GET' and request.full_url in binding.ROLE_URLS.values()
        assert not any(key.lower() in ('authorization', 'x-auth-token') for key, value in request.header_items())
        role = next(role for role, url in binding.ROLE_URLS.items() if url == request.full_url)
        self.requests.append({'job_id': self.case.active_job, 'role': role, 'url': request.full_url})
        if self.on_open:
            self.on_open(role)
        if self.behavior == 'network-error':
            raise URLError('SYNTHETIC transport interruption')
        status = self.behavior if type(self.behavior) is int else 200
        return Response(request.full_url, self.bodies[role], status)


class Case:
    def __init__(self, owner, name):
        self.owner, self.name = owner, name
        self.state = owner.output / name / 'SYNTHETIC-state'
        self.state.mkdir(parents=True); protect(self.state)
        self.token = secrets.token_urlsafe(32); owner.secrets.append(self.token)
        self.app = create_app(self.state, local_token=self.token, start_worker=False)
        self.product, self.jobs = self.app.state.product, self.app.state.jobs
        self.client = TestClient(self.app)
        self.headers = {'Authorization': 'Bearer ' + self.token}
        self.raw = self.state / 'raw/connectors'; self.raw.mkdir(parents=True, exist_ok=True)
        self.native = {'match_id': 3869685, 'match_date': '2022-12-18', 'kick_off': '17:00:00.000',
                       'competition': {'competition_id': 43, 'competition_name': 'FIFA World Cup'},
                       'season': {'season_id': 106, 'season_name': '2022'},
                       'home_team': {'home_team_id': 779, 'home_team_name': 'Argentina'},
                       'away_team': {'away_team_id': 771, 'away_team_name': 'France'},
                       'home_score': 3, 'away_score': 3, 'match_status': 'available',
                       'SYNTHETIC_ACCEPTANCE_ONLY': True}
        self.catalog = self.document([{'competition_id': 43, 'season_id': 106, 'competition_name': 'FIFA World Cup', 'season_name': '2022'}],
                                     research.STATSBOMB_BASE + 'competitions.json')
        self.original_parent = self.metadata()
        self.match_id = identity('fixture', 'statsbomb', '3869685')
        self.path = '/matches/' + self.match_id + '/source-context'
        self.events_path = '/matches/' + self.match_id + '/source-events'
        self.net = FakeProvider(self)
        self.active_job = None
        self.job_ids = []
        owner.cases.append(self)

    def document(self, data, url):
        body = canonical(data); sha = hashlib.sha256(body).hexdigest()
        resolved = url.replace(research.STATSBOMB_BASE, 'https://raw.githubusercontent.com/hudl/open-data/refs/heads/master/data/')
        doc = Document(url, resolved, body, utc_now(), sha, 'application/json', uuid4().hex, sha + '.payload')
        (self.raw / doc.raw_reference).write_bytes(body)
        self.product.connector_store.receipt('statsbomb', doc)
        return doc

    def metadata(self):
        match_doc = self.document([self.native], research.STATSBOMB_BASE + 'matches/43/106.json')
        catalog = self.catalog
        class RetainedOnly:
            def get(self, url): return catalog if url == catalog.url else match_doc
        record = research._statsbomb({'competition_id': 43, 'season_id': 106}, RetainedOnly(), lambda: None)[0]
        result = self.product.connector_store.ingest('statsbomb', [record], [catalog, match_doc])
        assert result['inserted'] == 1 and result['quarantined'] == 0
        attempt = self.product.connector_store.start('statsbomb', 'sync')
        self.product.connector_store.finish(attempt, result={'provider': 'statsbomb', 'retrieved_rows': 1,
            'acquisitions': [{'id': doc.acquisition_id, 'sha256': doc.sha256, 'url': doc.url,
                              'resolved_url': doc.resolved_url, 'bytes': len(doc.body)} for doc in (catalog, match_doc)]})
        return self.product.connector_store.rows('statsbomb')[0]['id']

    def get(self, path=None, **kwargs):
        response = self.client.get(API + (path or self.path), headers=self.headers, **kwargs)
        assert response.status_code == 200, response.text
        return response.json()

    def submit(self, key=None):
        response = self.client.post(API + self.path, headers={**self.headers, 'Idempotency-Key': key or uuid4().hex}, json={})
        assert response.status_code == 202, response.text
        job = response.json(); assert job['kind'] == 'statsbomb_context'
        self.active_job = job['id']
        if job['id'] not in self.job_ids:
            self.job_ids.append(job['id'])
        return job

    def work(self, actor=None):
        with patch.object(service, 'Transport', self.net.factory):
            return (actor or self.jobs).run_once()

    def expire(self, job_id=None):
        with closing(self.product.connect()) as db:
            db.execute('UPDATE product_jobs SET lease_until=0 WHERE id=?', (job_id or self.active_job,)); db.commit()

    def journal(self, job_id=None):
        with closing(self.product.connect()) as db:
            row = db.execute('SELECT status,result,error FROM connector_attempts WHERE id=?',
                             ('statsbomb-context:' + (job_id or self.active_job),)).fetchone()
        assert row is not None
        return {'status': row[0], 'result': json.loads(row[1]), 'error': json.loads(row[2]) if row[2] else None}

    def count(self, table):
        with closing(self.product.connect()) as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            return db.execute('SELECT count(*) FROM "' + table + '"').fetchone()[0] if exists else 0

    def job(self, job_id=None): return self.jobs.get(job_id or self.active_job)

    def assert_unavailable_fields(self, value):
        assert value['availability'] != 'available'
        assert not any(key in value for key in ('projection', 'items', 'total'))
        text = json.dumps(value)
        assert 'raw_reference' not in text and str(self.state) not in text and self.token not in text


class Acceptance:
    def __init__(self, output):
        self.output = output.resolve()
        assert self.output.is_relative_to(ROOT / 'build/connections') and not self.output.exists()
        self.output.mkdir(parents=True); protect(self.output)
        self.cases, self.checks, self.secrets = [], [], []
        self.network_attempts = 0
        self.report = {'schema_version': 1, 'passed': False, 'mode': 'isolated_asgi_fake_provider_real_jobs_transport_sqlite',
                       'checks': self.checks, 'started_at': datetime.now(timezone.utc).isoformat(),
                       'provider_http': False, 'live_state_changed': False, 'windows_service_changed': False,
                       'source_bindings': {name: digest(ROOT / name) for name in (
                           'scripts/verify_statsbomb_context_job.py', 'scripts/verify_statsbomb_parser.py',
                           'src/dragonhydra/api.py', 'src/dragonhydra/jobs.py', 'src/dragonhydra/source_context.py',
                           'src/dragonhydra/cognition/memory.py', 'src/dragonhydra/connectors/core.py',
                           'src/dragonhydra/connectors/service.py', 'src/dragonhydra/connectors/statsbomb_context_jobs.py',
                           'src/dragonhydra/connectors/statsbomb_context_view.py', 'src/dragonhydra/connectors/statsbomb_context.py',
                           'src/dragonhydra/connectors/statsbomb_context_parser.py')}}

    def check(self, name, **details):
        self.checks.append({'name': name, 'passed': True, **details})
        print(json.dumps({'passed': name}), flush=True)

    def forbid_http(self, *args, **kwargs):
        self.network_attempts += 1
        raise AssertionError('Actual HTTP is forbidden; only the case fake opener may return provider responses.')

    def crash_work(self, case):
        try:
            case.work()
        except Crash:
            pass
        else:
            raise AssertionError('The expected process-death seam did not execute.')
        assert case.job()['status'] == 'running'

    def basic_api(self):
        case = Case(self, 'api-success-and-auth')
        missing = case.get(); assert missing['availability'] == 'not_requested'
        case.assert_unavailable_fields(case.get(case.events_path))
        assert case.count('cognitive_records') == 0
        assert case.client.get(API + case.path).status_code == 401
        reader = secrets.token_urlsafe(32); self.secrets.append(reader)
        with closing(case.product.connect()) as db:
            db.execute('INSERT INTO product_sessions VALUES(?,?,?,?)', (hashlib.sha256(reader.encode()).hexdigest(), 'SYNTHETIC:reader', '["reader"]', time.time() + 60)); db.commit()
        assert case.client.post(API + case.path, headers={'Cookie': 'dragon_session=' + reader}, json={}).status_code == 403
        assert case.client.post(API + case.path, headers=case.headers, json={'url': 'https://example.invalid'}).status_code == 422
        job = case.submit('SYNTHETIC-identical-request')
        assert case.submit('SYNTHETIC-identical-request')['id'] == job['id']
        assert case.work() and case.job()['status'] == 'succeeded'
        assert len(case.net.requests) == 2
        assert case.submit('SYNTHETIC-identical-request')['id'] == job['id']
        assert not case.work() and len(case.net.requests) == 2
        with patch.object(Product, 'find', side_effect=AssertionError('GET cannot use legacy schema helpers')), \
                patch.object(Product, 'rows', side_effect=AssertionError('GET cannot use legacy schema helpers')), \
                patch.object(memory, '_schema', side_effect=AssertionError('GET cannot initialize schema')):
            available = case.get()
            page = case.get(case.events_path + '?offset=1&limit=2')
        assert available['availability'] == 'available' and available['projection']['event_summary']['row_count'] == 4
        assert page['total'] == 4 and page['items'] == EVENTS[1:3]
        assert available['parent_observation_id'] == available['context_parent_observation_id'] == case.original_parent
        assert len(available['documents']) == 2 and all('metadata_url' in doc for doc in available['documents'])
        assert 'raw_reference' not in json.dumps(available) and str(case.state) not in json.dumps(available)
        assert case.client.get(API + case.events_path + '?limit=201', headers=case.headers).status_code == 422
        assert case.count('connector_observations') == 1 and case.count('cognitive_records') == 1
        self.check('Authenticated admin-only API queues one idempotent job; two fake GETs produce exact retained context/page; GET avoids legacy DDL and private paths')

    def crash_resume(self):
        intent = Case(self, 'crash-after-intent')
        intent.submit()
        original = service._reserve
        def reserve_then_die(*args, **kwargs):
            original(*args, **kwargs); raise Crash()
        with patch.object(service, '_reserve', reserve_then_die):
            self.crash_work(intent)
        assert len(intent.net.requests) == 0 and intent.journal()['result']['roles']['events']['state'] == 'intent'
        intent.expire(); assert intent.work(Jobs(intent.product))
        assert intent.job()['status'] == 'failed' and len(intent.net.requests) == 0
        assert intent.count('connector_acquisitions') == 2
        self.check('A crash after durable request intent spends that role even before open; recovery fails explicitly and never reissues the uncertain GET')

        receipt = Case(self, 'crash-after-first-receipt')
        receipt.submit(); complete = service._complete
        def complete_then_die(*args, **kwargs):
            complete(*args, **kwargs); raise Crash()
        with patch.object(service, '_complete', complete_then_die):
            self.crash_work(receipt)
        assert len(receipt.net.requests) == 1 and receipt.journal()['result']['roles']['events']['state'] == 'complete'
        assert receipt.count('connector_acquisitions') == 3
        receipt.expire(); assert receipt.work(Jobs(receipt.product))
        assert receipt.job()['status'] == 'succeeded' and len(receipt.net.requests) == 2
        assert [r['role'] for r in receipt.net.requests] == ['events', 'lineups']
        self.check('First receipt and journal survive process death; a new claim reuses the first bytes and requests only the remaining role')

    def atomic_and_retry(self):
        atomic = Case(self, 'atomic-receipt-journal')
        atomic.submit()
        with closing(atomic.product.connect()) as db:
            db.execute("CREATE TRIGGER SYNTHETIC_atomic_failure BEFORE UPDATE OF result ON connector_attempts WHEN NEW.operation='statsbomb_context' AND json_extract(NEW.result,'$.roles.events.state')='complete' BEGIN SELECT RAISE(ABORT,'SYNTHETIC atomic receipt journal failure'); END")
            db.commit()
        assert atomic.work() and atomic.job()['status'] == 'failed'
        assert len(atomic.net.requests) == 1 and atomic.count('connector_acquisitions') == 2
        assert atomic.journal()['result']['roles']['events']['state'] == 'intent'
        assert (atomic.raw / (hashlib.sha256(canonical(EVENTS)).hexdigest() + '.payload')).is_file()
        assert not atomic.work() and len(atomic.net.requests) == 1
        self.check('Journal update failure rolls back its acquisition insert atomically; complete orphan raw bytes remain diagnostic and the spent request is not retried')

        for behavior in ('network-error', 429, 302):
            case = Case(self, 'no-http-retry-' + str(behavior))
            before_health = next(row for row in case.get('/connections')['items'] if row['id'] == 'statsbomb')
            case.submit(); case.net.behavior = behavior
            assert case.work() and case.job()['status'] == 'failed'
            assert case.job()['attempts'] == 1 and not case.work() and len(case.net.requests) == 1
            after_health = next(row for row in case.get('/connections')['items'] if row['id'] == 'statsbomb')
            assert after_health['status'] == before_health['status'] == 'working'
            assert after_health['last_import'] == before_health['last_import']
            case.assert_unavailable_fields(case.get(case.events_path))
        ordinary = Case(self, 'normal-provider-retry')
        job = ordinary.jobs.submit('connector_sync', {'provider': 'statsbomb'}, 'SYNTHETIC:owner')
        with patch.object(ordinary.jobs.providers, 'run', side_effect=ConnectorError('RATE_LIMITED', 'SYNTHETIC retry', retry_after=60)):
            assert ordinary.jobs.run_once()
        assert ordinary.jobs.get(job['id'])['status'] == 'queued'
        self.check('Context network/rate-limit/redirect failures make no automatic HTTP retry and do not poison metadata health; normal provider retry policy remains queued')

    def fences(self):
        cancel_sink = Case(self, 'cancel-inside-receipt-sink')
        cancel_sink.submit(); complete = service._complete
        def cancel_before_complete(*args, **kwargs):
            cancel_sink.jobs.cancel(cancel_sink.active_job)
            return complete(*args, **kwargs)
        with patch.object(service, '_complete', cancel_before_complete):
            assert cancel_sink.work()
        assert cancel_sink.job()['status'] == 'cancelled' and cancel_sink.count('connector_acquisitions') == 2
        assert cancel_sink.journal()['result']['roles']['events']['state'] == 'intent'
        self.check('Cancellation between retained-body completion and the receipt sink is fenced inside its SQLite transaction')

        stale = Case(self, 'actual-stale-workers')
        stale.submit(); entered, release = threading.Event(), threading.Event()
        def block(role):
            assert role == 'events'; entered.set(); assert release.wait(15)
        stale.net.on_open = block
        with patch.object(service, 'Transport', stale.net.factory), ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(stale.jobs.run_once)
            try:
                assert entered.wait(10)
                stale.expire()
                assert Jobs(stale.product).run_once()
                assert stale.job()['status'] == 'failed'
            finally:
                release.set()
            assert first.result(timeout=15)
        assert len(stale.net.requests) == 1 and stale.count('connector_acquisitions') == 2
        assert stale.count('cognitive_records') == 0
        self.check('A real second worker reclaims an expired claim while its predecessor is blocked; the spent GET is not repeated and the stale worker cannot receipt or publish')

        append_case = Case(self, 'cancel-inside-context-append')
        append_case.submit(); append = source_context.append
        def cancel_append(*args, **kwargs):
            append_case.jobs.cancel(append_case.active_job)
            return append(*args, **kwargs)
        with patch.object(source_context, 'append', cancel_append):
            assert append_case.work()
        assert append_case.job()['status'] == 'cancelled' and len(append_case.net.requests) == 2
        assert append_case.count('cognitive_records') == 0
        self.check('Cancellation after both roles validate still prevents context insertion through the guard inside append')

        recover_case = Case(self, 'cancel-inside-context-recovery')
        recover_case.submit()
        with patch.object(memory, '_revision_receipt', side_effect=Crash()):
            self.crash_work(recover_case)
        assert recover_case.count('cognitive_records') == 1 and recover_case.count('cognitive_receipts') == 0
        recover_case.assert_unavailable_fields(recover_case.get(recover_case.events_path))
        recover_case.expire(); recover = source_context.recover
        def cancel_recover(*args, **kwargs):
            recover_case.jobs.cancel(recover_case.active_job)
            return recover(*args, **kwargs)
        with patch.object(source_context, 'recover', cancel_recover):
            assert recover_case.work(Jobs(recover_case.product))
        assert recover_case.job()['status'] == 'cancelled' and recover_case.count('cognitive_receipts') == 0
        assert len(recover_case.net.requests) == 2
        self.check('Cancellation during pending-record recovery is fenced before receipt insertion; no HTTP is repeated and GET remains explicitly unavailable')

    def publication(self):
        case = Case(self, 'frozen-parent-and-outcome')
        first = case.submit('SYNTHETIC-old-parent')
        case.native['home_score'] = 4
        new_parent = case.metadata(); assert new_parent != case.original_parent
        assert case.work() and case.job()['status'] == 'succeeded'
        old_context = case.job()['result']['context_record_id']
        changed = case.get(); assert changed['availability'] == 'parent_changed'
        assert changed['parent_observation_id'] == new_parent and changed['context_parent_observation_id'] == case.original_parent
        case.assert_unavailable_fields(case.get(case.events_path))
        assert case.client.post(API + case.path, headers={**case.headers, 'Idempotency-Key': 'SYNTHETIC-old-parent'}, json={}).status_code == 409
        second = case.submit('SYNTHETIC-new-parent')
        assert case.work() and case.job()['status'] == 'succeeded'
        new_context = case.job()['result']['context_record_id']; assert new_context != old_context
        assert case.get()['availability'] == 'available' and case.count('cognitive_records') == 2
        with closing(case.product.connect()) as db:
            db.execute("UPDATE product_jobs SET status='interrupted' WHERE id=?", (first['id'],)); db.commit()
        case.active_job = first['id']
        assert case.work(Jobs(case.product))
        assert case.job()['result']['context_record_id'] == old_context
        assert case.count('cognitive_records') == 2 and case.get()['context_record_id'] == new_context
        assert len(case.net.requests) == 4
        self.check('Queued job keeps its immutable old parent; explicit new-parent request creates a new revision; completed-outcome recovery returns its original context without rebinding or reversion')

        conflict = Case(self, 'crash-publication-conflict')
        first = conflict.submit('SYNTHETIC-first-publication')
        with patch.object(source_context, 'append', side_effect=Crash()):
            self.crash_work(conflict)
        assert conflict.journal()['result']['publication'] is not None
        assert conflict.count('cognitive_records') == 0 and len(conflict.net.requests) == 2
        altered_events = deepcopy(EVENTS); altered_events.append({'id': '00000000-0000-0000-0000-000000000005', 'index': 5, 'type': {'id': 30, 'name': 'Pass'}})
        conflict.net.bodies['events'] = canonical(altered_events)
        second = conflict.submit('SYNTHETIC-competing-publication')
        assert conflict.work(Jobs(conflict.product)) and conflict.job()['status'] == 'succeeded'
        winner = conflict.job()['result']['context_record_id']
        conflict.active_job = first['id']; conflict.expire()
        assert conflict.work(Jobs(conflict.product)) and conflict.job()['status'] == 'failed'
        assert conflict.count('cognitive_records') == 1 and conflict.get()['context_record_id'] == winner
        assert len(conflict.net.requests) == 4
        self.check('A crash after publication intent followed by a competing revision fails closed on recovery; no extra GET, silent newer-head binding or old-content reversion occurs')

    def run(self):
        import urllib.request
        original_connect = sqlite3.connect
        def isolated_connect(database, *args, **kwargs):
            value = str(database)
            if value.startswith('file:'):
                assert value.startswith(self.output.as_uri() + '/'), 'Unrelated or live SQLite access is forbidden.'
            else:
                assert value == ':memory:' or Path(database).resolve().is_relative_to(self.output), 'Unrelated or live SQLite access is forbidden.'
            return original_connect(database, *args, **kwargs)
        try:
            with patch.object(urllib.request.OpenerDirector, 'open', self.forbid_http), \
                    patch.object(urllib.request, 'urlopen', self.forbid_http), patch.object(sqlite3, 'connect', isolated_connect):
                self.basic_api()
                self.crash_resume()
                self.atomic_and_retry()
                self.fences()
                self.publication()
            assert self.network_attempts == 0
            assert all(digest(ROOT / name) == sha for name, sha in self.report['source_bindings'].items())
            self.report['passed'] = True
        except BaseException as error:
            self.report['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
        finally:
            self.report['cases'] = []
            for case in self.cases:
                try:
                    self.report['cases'].append({'name': case.name, 'state': str(case.state.relative_to(ROOT)),
                        'fake_provider_requests': case.net.requests,
                        'jobs': [{'id': ident, 'status': case.jobs.get(ident)['status'], 'attempts': case.jobs.get(ident)['attempts'],
                                  'error': case.jobs.get(ident)['error']} for ident in case.job_ids],
                        'connector_observations': case.count('connector_observations'),
                        'connector_acquisitions': case.count('connector_acquisitions'),
                        'context_records': case.count('cognitive_records'), 'context_receipts': case.count('cognitive_receipts')})
                    by_job = {}
                    for request in case.net.requests:
                        by_job[request['job_id']] = by_job.get(request['job_id'], 0) + 1
                    assert all(count <= 2 for count in by_job.values())
                    case.client.close(); case.jobs.close()
                except Exception as error:
                    self.report['passed'] = False
                    self.report['case_report_error'] = type(error).__name__ + ': ' + str(error)
            self.report.update(finished_at=datetime.now(timezone.utc).isoformat(), check_groups=len(self.checks),
                               forbidden_http_attempts=self.network_attempts)
            text = json.dumps(self.report, ensure_ascii=False, indent=2)
            for secret in self.secrets:
                text = text.replace(secret, '[REDACTED]')
            (self.output / 'verification.json').write_text(text + '\n', encoding='utf-8')
        print(json.dumps({'passed': self.report['passed'], 'groups': len(self.checks), 'cases': len(self.cases),
                          'forbidden_http_attempts': self.network_attempts, 'error': self.report.get('error', {}).get('message'),
                          'report': str((self.output / 'verification.json').relative_to(ROOT))}))
        return 0 if self.report['passed'] else 1


def main():
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument('--output', required=True, type=Path)
    args = argument_parser.parse_args()
    assert not sys.flags.optimize
    return Acceptance(args.output).run()


if __name__ == '__main__':
    raise SystemExit(main())
