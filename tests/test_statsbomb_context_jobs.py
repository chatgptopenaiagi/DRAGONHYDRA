"""Synthetic retained Transport responses and durable job crash boundaries."""
from contextlib import closing
from copy import deepcopy
from email.message import Message
import io
import json
import threading
import unittest
from unittest.mock import patch
from urllib.error import URLError

from dragonhydra import source_context
from dragonhydra.cognition import memory
from dragonhydra.connectors import statsbomb_context as binding, statsbomb_context_jobs as context_jobs
from dragonhydra.connectors import research, statsbomb_context_parser as parser
from dragonhydra.jobs import Jobs
from dragonhydra.product import Product
import test_statsbomb_context as fixtures
from test_statsbomb_context_parser import EVENTS, LINEUPS, raw


class Crash(BaseException):
    """An unhandled process boundary, deliberately outside worker Exception."""


class Response:
    def __init__(self, body, url, status=200):
        self.stream, self.url, self.status = io.BytesIO(body), url, status
        self.headers = Message()
        self.headers['Content-Type'] = 'application/json'
        self.headers['Content-Length'] = str(len(body))
    def read(self, size): return self.stream.read(size)
    def getcode(self): return self.status
    def geturl(self): return self.url
    def __enter__(self): return self
    def __exit__(self, *args): self.stream.close()


class ContextJobTests(unittest.TestCase):
    document = fixtures.StatsBombContextTests.document
    readonly = fixtures.StatsBombContextTests.readonly

    def setUp(self):
        fixtures.StatsBombContextTests.setUp(self)
        self.jobs = Jobs(self.product)
        self.match_id = self.product.match_id({'source_id':'statsbomb','fixture_key':'3869685'})
        self.request = context_jobs.prepare(self.product, self.match_id)
        self.calls = []
        self.bodies = {'events':raw(EVENTS), 'lineups':raw(LINEUPS)}
        self.status = 200
        self.open_error = None
        self.network = patch('dragonhydra.connectors.core.build_opener', return_value=self)
        self.network.start()
        self.addCleanup(self.network.stop)

    def open(self, request, timeout):
        self.calls.append(request.full_url)
        self.assertIn(request.full_url, binding.ROLE_URLS.values())
        if self.open_error:
            raise self.open_error
        role = next(role for role, url in binding.ROLE_URLS.items() if url == request.full_url)
        return Response(self.bodies[role], request.full_url, self.status)

    def submit(self, key=None):
        return self.jobs.submit('statsbomb_context', self.request, 'synthetic-context-owner', key)

    def journal(self, job):
        with closing(self.product.connect()) as db:
            row = db.execute('SELECT result FROM connector_attempts WHERE id=?', (context_jobs.attempt_id(job),)).fetchone()
        return json.loads(row[0])

    def count(self, table):
        with closing(self.product.connect()) as db:
            return db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]

    def context_rows(self):
        with closing(self.product.connect()) as db:
            if not source_context._tables(db): return ([], [])
            return (db.execute('SELECT * FROM cognitive_records ORDER BY record_id').fetchall(),
                    db.execute('SELECT * FROM cognitive_receipts ORDER BY record_id').fetchall())

    def restart(self, job):
        with closing(self.product.connect()) as db:
            db.execute('UPDATE product_jobs SET lease_until=0 WHERE id=?', (job['id'],))
            db.commit()
        self.jobs = Jobs(Product(self.product.state))
        self.assertTrue(self.jobs.run_once())
        return self.jobs.get(job['id'])

    def successful(self):
        job = self.submit()
        self.assertTrue(self.jobs.run_once())
        completed = self.jobs.get(job['id'])
        self.assertEqual(completed['status'], 'succeeded', completed)
        return job, completed

    def test_two_bounded_gets_and_semantic_duplicate_keep_original_context_and_receipts(self):
        job, first = self.successful()
        self.assertEqual(self.calls, list(binding.ROLE_URLS.values()))
        original = self.context_rows()
        _, second = self.successful()
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(first['result'], second['result'])
        self.assertEqual(self.context_rows(), original)
        self.assertEqual(set(self.journal(job)['roles']), {'events','lineups'})
        self.assertEqual(self.journal(job)['outcome'], first['result'])
        self.assertEqual(self.count('connector_observations'), 1)

    def test_crash_after_intent_before_get_never_reissues_that_role(self):
        job = self.submit()
        reserve = context_jobs._reserve
        def crash(*args):
            reserve(*args)
            raise Crash()
        with patch.object(context_jobs, '_reserve', side_effect=crash), self.assertRaises(Crash):
            self.jobs.run_once()
        self.assertEqual(self.calls, [])
        recovered = self.restart(job)
        self.assertEqual(recovered['status'], 'failed')
        self.assertIn('OUTCOME_UNKNOWN', recovered['error']['code'])
        self.assertEqual(self.calls, [])

    def test_response_before_receipt_and_receipt_journal_failure_leave_no_unjournaled_acquisition(self):
        for boundary in ('before-sink', 'inside-sink'):
            with self.subTest(boundary=boundary):
                job = self.submit()
                before = self.count('connector_acquisitions')
                save = context_jobs._save
                def fail_save(db, current, journal, **kwargs):
                    if any(role['state']=='complete' for role in journal['roles'].values()):
                        raise Crash()
                    return save(db, current, journal, **kwargs)
                target = patch.object(context_jobs, '_complete', side_effect=Crash()) if boundary == 'before-sink' else patch.object(context_jobs, '_save', side_effect=fail_save)
                previous = len(self.calls)
                with target, self.assertRaises(Crash): self.jobs.run_once()
                self.assertEqual(len(self.calls), previous+1)
                self.assertEqual(self.count('connector_acquisitions'), before)
                self.assertEqual(self.journal(job)['roles']['events']['state'], 'intent')
                self.assertTrue((self.raw/(memory._hash(self.bodies['events'])+'.payload')).exists())
                recovered = self.restart(job)
                self.assertEqual(recovered['status'], 'failed')
                self.assertEqual(len(self.calls), previous+1)

    def test_completed_first_role_restarts_with_only_the_second_get(self):
        job = self.submit()
        complete = context_jobs._complete
        def crash(*args):
            complete(*args)
            raise Crash()
        with patch.object(context_jobs, '_complete', side_effect=crash), self.assertRaises(Crash): self.jobs.run_once()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.journal(job)['roles']['events']['state'], 'complete')
        completed = self.restart(job)
        self.assertEqual(completed['status'], 'succeeded', completed)
        self.assertEqual(len(self.calls), 2)

    def test_two_receipts_restart_without_get_and_pending_context_receipt_is_recovered(self):
        for boundary in ('before-context', 'record-commit', 'receipt-commit', 'outcome-commit'):
            with self.subTest(boundary=boundary):
                job = self.submit()
                before_calls = len(self.calls)
                finish = context_jobs._finish
                execute = self.jobs.execute
                receipt = memory._revision_receipt
                def crash_new_receipt(db, kind, scope, record_id, acknowledged, validate):
                    if db.execute('SELECT 1 FROM cognitive_receipts WHERE record_id=?', (record_id,)).fetchone() is None:
                        raise Crash()
                    return receipt(db, kind, scope, record_id, acknowledged, validate)
                def crash_finish(*args, **kwargs):
                    if kwargs.get('outcome') is not None: raise Crash()
                    return finish(*args, **kwargs)
                def crash_execute(current):
                    execute(current)
                    raise Crash()
                if boundary == 'before-context': target = patch.object(context_jobs, '_ensure_context_schema', side_effect=Crash())
                elif boundary == 'record-commit': target = patch.object(memory, '_revision_receipt', side_effect=crash_new_receipt)
                elif boundary == 'receipt-commit': target = patch.object(context_jobs, '_finish', side_effect=crash_finish)
                else: target = patch.object(self.jobs, 'execute', side_effect=crash_execute)
                # Force a new semantic revision for each boundary, not a duplicate.
                self.bodies['events'] = raw(EVENTS[:1+(before_calls//2)%4])
                with target, self.assertRaises(Crash): self.jobs.run_once()
                self.assertEqual(len(self.calls), before_calls+2)
                records_before, receipts_before = self.context_rows()
                completed = self.restart(job)
                self.assertEqual(completed['status'], 'succeeded', completed)
                self.assertEqual(len(self.calls), before_calls+2)
                if boundary != 'before-context':
                    self.assertEqual(self.context_rows()[0], records_before)
                else:
                    self.assertEqual(len(self.context_rows()[0]), len(records_before)+1)
                if boundary in ('receipt-commit','outcome-commit'):
                    self.assertEqual(self.context_rows()[1], receipts_before)

    def test_network_failures_have_no_automatic_retry_and_keep_prior_context(self):
        self.successful()
        previous = self.context_rows()
        for failure in (429, 503, TimeoutError('synthetic'), URLError('synthetic')):
            with self.subTest(failure=type(failure).__name__ if isinstance(failure, Exception) else failure):
                self.status = failure if type(failure) is int else 200
                self.open_error = failure if isinstance(failure, Exception) else None
                before = len(self.calls)
                job = self.submit()
                self.assertTrue(self.jobs.run_once())
                result = self.jobs.get(job['id'])
                self.assertEqual((result['status'], result['attempts']), ('failed',1), result)
                self.assertFalse(self.jobs.run_once())
                self.assertEqual(len(self.calls), before+1)
                self.assertEqual(self.context_rows(), previous)

    def test_invalid_or_forged_projection_cannot_write_with_binding_only_validation(self):
        self.successful()
        previous = self.context_rows()
        job = self.submit()
        self.bodies['events'] = b'not-json'
        self.assertTrue(self.jobs.run_once())
        self.assertEqual(self.jobs.get(job['id'])['status'], 'failed')
        self.assertEqual(self.context_rows(), previous)
        self.bodies['events'] = raw(EVENTS)
        forged = parser.parse(self.bodies['events'], self.bodies['lineups'], parent=self.request['parent'])
        forged['event_summary']['row_count'] += 100
        job = self.submit()
        with patch.object(parser, 'parse', return_value=forged): self.assertTrue(self.jobs.run_once())
        result = self.jobs.get(job['id'])
        self.assertEqual(result['status'], 'failed')
        self.assertIn('RECONSTRUCTION', result['error']['code'])
        self.assertEqual(self.context_rows(), previous)

    def test_cancellation_after_retention_or_before_context_write_preserves_prior_context(self):
        self.successful()
        previous = self.context_rows()
        for boundary in ('receipt','context'):
            with self.subTest(boundary=boundary):
                job = self.submit()
                before_acquisitions, before_calls = self.count('connector_acquisitions'), len(self.calls)
                complete, append = context_jobs._complete, source_context.append
                def cancel_receipt(*args):
                    self.jobs.cancel(job['id'])
                    return complete(*args)
                def cancel_append(*args, **kwargs):
                    self.jobs.cancel(job['id'])
                    return append(*args, **kwargs)
                target = patch.object(context_jobs, '_complete', side_effect=cancel_receipt) if boundary == 'receipt' else patch.object(source_context, 'append', side_effect=cancel_append)
                # Changed bytes ensure context publication is attempted.
                self.bodies['events'] = raw(EVENTS[:2])
                with target: self.assertTrue(self.jobs.run_once())
                self.assertEqual(self.jobs.get(job['id'])['status'], 'cancelled')
                self.assertEqual(len(self.calls)-before_calls, 1 if boundary=='receipt' else 2)
                self.assertEqual(self.count('connector_acquisitions')-before_acquisitions, 0 if boundary=='receipt' else 2)
                self.assertEqual(self.context_rows(), previous)

    def test_stale_owner_cannot_receipt_or_overwrite_new_failed_claim_after_retention(self):
        job = self.submit()
        entered, resume = threading.Event(), threading.Event()
        complete = context_jobs._complete
        failures = []
        def paused(*args):
            entered.set()
            self.assertTrue(resume.wait(10))
            return complete(*args)
        def worker():
            try: self.jobs.run_once()
            except BaseException as error: failures.append(error)
        with patch.object(context_jobs, '_complete', side_effect=paused):
            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            try:
                self.assertTrue(entered.wait(10))
                with closing(self.product.connect()) as db:
                    db.execute('UPDATE product_jobs SET lease_until=0 WHERE id=?', (job['id'],)); db.commit()
                newer = Jobs(Product(self.product.state))
                self.assertTrue(newer.run_once())
                final, events, journal = newer.get(job['id']), newer.updates(0), self.journal(job)
                self.assertEqual(final['status'], 'failed')
                self.assertEqual(final['attempts'], 2)
            finally:
                resume.set(); thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(self.jobs.get(job['id']), final)
        self.assertEqual(self.jobs.updates(0), events)
        self.assertEqual(self.journal(job), journal)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.count('connector_acquisitions'), 4)

    def test_context_attempts_do_not_replace_normal_provider_health_or_diagnostics(self):
        attempt = self.store.start('statsbomb','test')
        self.store.finish(attempt,result={'retrieved_rows':12})
        self.successful()
        health = self.jobs.providers.describe('statsbomb')
        self.assertEqual(health['status'], 'working')
        self.assertEqual(health['last_retrieval_count'], 12)
        self.assertEqual(health['last_diagnostic']['id'], attempt)

    def late_resume(self, outcome_committed):
        old = self.submit()
        finish, execute = context_jobs._finish, self.jobs.execute
        def crash_finish(*args, **kwargs):
            if kwargs.get('outcome') is not None: raise Crash()
            return finish(*args, **kwargs)
        def crash_execute(job):
            execute(job)
            raise Crash()
        target = patch.object(self.jobs, 'execute', side_effect=crash_execute) if outcome_committed else patch.object(context_jobs, '_finish', side_effect=crash_finish)
        with target, self.assertRaises(Crash): self.jobs.run_once()
        first_id = self.context_rows()[0][0][1]
        self.bodies['events'] = raw(EVENTS[:2])
        _, newer = self.successful()
        self.assertNotEqual(newer['result']['context_record_id'], first_id)
        self.assertEqual(len(self.calls), 4)
        rows = self.context_rows()
        resumed = self.restart(old)
        self.assertEqual(resumed['status'], 'succeeded', resumed)
        self.assertEqual(resumed['result']['context_record_id'], first_id)
        self.assertEqual(self.context_rows(), rows)
        self.assertEqual(len(self.calls), 4)

    def test_completed_outcome_resumes_its_exact_record_after_another_job_advances(self):
        self.late_resume(True)

    def test_publication_marker_recovers_original_commit_after_another_job_advances(self):
        self.late_resume(False)

    def test_uncommitted_publication_conflicts_instead_of_reverting_another_job(self):
        old = self.submit()
        with patch.object(source_context, 'append', side_effect=Crash()), self.assertRaises(Crash): self.jobs.run_once()
        self.assertIsNotNone(self.journal(old)['publication'])
        self.bodies['events'] = raw(EVENTS[:2])
        _, newer = self.successful()
        original = self.context_rows()
        result = self.restart(old)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('PUBLICATION_CONFLICT', result['error']['code'])
        self.assertEqual(self.context_rows(), original)
        self.assertEqual(len(self.calls), 4)

    def test_queued_job_keeps_frozen_parent_after_metadata_revision(self):
        job = self.submit()
        changed = deepcopy(fixtures.MATCH)
        changed['away_score'] = 4
        matches = self.document([changed], research.STATSBOMB_BASE+'matches/43/106.json')
        class Retained:
            def get(inner, url): return self.catalog if url.endswith('competitions.json') else matches
        record = research._statsbomb({'competition_id':43,'season_id':106}, Retained(), lambda:None)[0]
        self.store.ingest('statsbomb', [record], [self.catalog,matches])
        newest = self.store.rows('statsbomb')[0]['id']
        self.assertNotEqual(newest, self.observation_id)
        self.assertTrue(self.jobs.run_once())
        completed = self.jobs.get(job['id'])
        self.assertEqual(completed['status'], 'succeeded', completed)
        self.assertEqual(completed['result']['parent_observation_id'], self.observation_id)
        latest = source_context.latest(self.path, 'statsbomb', '3869685', parent_observation_id=newest,
            validate_dependencies=parser.make_validator(self.raw))
        self.assertEqual(latest['availability'], 'parent_changed')
        self.assertEqual(self.store.rows('statsbomb')[0]['record']['score_away'], 4)

    def test_generic_timeout_and_urlerror_are_terminal_for_context_jobs(self):
        for error in (TimeoutError('synthetic'), URLError('synthetic')):
            with self.subTest(error=type(error).__name__):
                job = self.submit()
                with patch.object(context_jobs, '_reserve', side_effect=error): self.assertTrue(self.jobs.run_once())
                self.assertEqual((self.jobs.get(job['id'])['status'], self.jobs.get(job['id'])['attempts']), ('failed',1))
                self.assertFalse(self.jobs.run_once())
                self.assertEqual(self.calls, [])

    def test_cancel_between_context_commit_and_receipt_leaves_recoverable_pending_record(self):
        job = self.submit()
        receipt = memory._revision_receipt
        def cancel(db, kind, scope, record_id, acknowledged, validate):
            if db.execute('SELECT 1 FROM cognitive_receipts WHERE record_id=?', (record_id,)).fetchone() is None:
                self.jobs.cancel(job['id'])
            return receipt(db, kind, scope, record_id, acknowledged, validate)
        with patch.object(memory, '_revision_receipt', side_effect=cancel): self.assertTrue(self.jobs.run_once())
        self.assertEqual(self.jobs.get(job['id'])['status'], 'cancelled')
        records, receipts = self.context_rows()
        self.assertEqual((len(records),len(receipts)), (1,0))
        _, completed = self.successful()
        self.assertEqual(self.context_rows()[0], records)
        self.assertEqual(len(self.context_rows()[1]), 1)
        self.assertEqual(completed['result']['context_record_id'], records[0][1])
        self.assertEqual(len(self.calls), 4)

    def test_stale_owner_cannot_context_commit_after_a_new_claim_publishes(self):
        job = self.submit()
        entered, resume = threading.Event(), threading.Event()
        append = source_context.append
        failures = []
        old_thread = None
        def paused(*args, **kwargs):
            if threading.current_thread() is old_thread:
                entered.set()
                self.assertTrue(resume.wait(10))
            return append(*args, **kwargs)
        def worker():
            try: self.jobs.run_once()
            except BaseException as error: failures.append(error)
        with patch.object(source_context, 'append', side_effect=paused):
            old_thread = threading.Thread(target=worker, daemon=True)
            old_thread.start()
            try:
                self.assertTrue(entered.wait(10))
                with closing(self.product.connect()) as db:
                    db.execute('UPDATE product_jobs SET lease_until=0 WHERE id=?', (job['id'],)); db.commit()
                newer = Jobs(Product(self.product.state))
                self.assertTrue(newer.run_once())
                final, events, rows = newer.get(job['id']), newer.updates(0), self.context_rows()
                self.assertEqual(final['status'], 'succeeded', final)
            finally:
                resume.set(); old_thread.join(10)
        self.assertFalse(old_thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(self.jobs.get(job['id']), final)
        self.assertEqual(self.jobs.updates(0), events)
        self.assertEqual(self.context_rows(), rows)
        self.assertEqual(len(self.calls), 2)

    def test_corrupt_completed_role_blocks_recovery_before_another_get(self):
        job = self.submit()
        complete = context_jobs._complete
        def crash(*args):
            complete(*args)
            raise Crash()
        with patch.object(context_jobs, '_complete', side_effect=crash), self.assertRaises(Crash): self.jobs.run_once()
        (self.raw/(memory._hash(self.bodies['events'])+'.payload')).write_bytes(b'changed')
        result = self.restart(job)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('INTEGRITY', result['error']['code'])
        self.assertEqual(len(self.calls), 1)


if __name__ == '__main__': unittest.main()
