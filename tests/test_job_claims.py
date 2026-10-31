"""Controlled two-worker lease races; no provider HTTP or service threads."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from dragonhydra import public_results
from dragonhydra.jobs import Cancelled, ClaimLost, Interrupted, Jobs
from dragonhydra.product import Product

ROOT = Path(__file__).resolve().parents[1]


class JobClaimTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'runtime/scratch', prefix='job-claims-')
        self.addCleanup(self.temp.cleanup)
        self.product = Product(Path(self.temp.name)/'state')
        self.old, self.new = Jobs(self.product), Jobs(self.product)

    def submit(self, kind='explanation', payload=None):
        return self.old.submit(kind, payload or {'match_id':'synthetic-fixture'}, 'synthetic-claim-owner')

    def expire(self, job_id):
        with closing(self.product.connect()) as db:
            db.execute("UPDATE product_jobs SET lease_until=0 WHERE id=? AND status='running'", (job_id,))
            db.commit()

    def thread(self, worker):
        results, failures = [], []

        def run():
            try:
                results.append(worker.run_once())
            except BaseException as error:
                failures.append(error)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread, results, failures

    def finish(self, thread, failures):
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive(), 'Controlled worker failed to finish.')
        self.assertFalse(failures, failures)

    def test_old_success_failure_retry_cancel_stop_and_heartbeat_cannot_replace_new_result_or_events(self):
        for outcome in ('success', 'failure', 'retry', 'cancel', 'stop', 'heartbeat'):
            with self.subTest(outcome=outcome):
                job = self.submit()
                entered, resume = threading.Event(), threading.Event()

                def paused(running):
                    self.assertEqual(running['attempts'], 1)
                    entered.set()
                    self.assertTrue(resume.wait(10))
                    if outcome == 'failure':
                        raise RuntimeError('synthetic-old-failure')
                    if outcome == 'retry':
                        raise TimeoutError('synthetic-old-timeout')
                    if outcome == 'cancel':
                        raise Cancelled()
                    if outcome == 'stop':
                        raise Interrupted()
                    if outcome == 'heartbeat':
                        self.old.check(running['id'], running['attempts'])
                    return {'worker':'old'}

                with patch.object(self.old, 'execute', side_effect=paused):
                    thread, results, failures = self.thread(self.old)
                    try:
                        self.assertTrue(entered.wait(10))
                        self.expire(job['id'])
                        with patch.object(self.new, 'execute', return_value={'worker':'new'}):
                            self.assertTrue(self.new.run_once())
                        completed = self.new.get(job['id'])
                        self.assertEqual((completed['status'], completed['attempts'], completed['result']),
                                         ('succeeded', 2, {'worker':'new'}))
                        events = self.new.updates(0)
                    finally:
                        resume.set()
                        self.finish(thread, failures)
                self.assertEqual(results, [True])
                self.assertEqual(self.new.get(job['id']), completed)
                self.assertEqual(self.new.updates(0), events)

    def test_old_heartbeat_cannot_renew_a_new_running_claim(self):
        job = self.submit()
        old_entered, new_entered = threading.Event(), threading.Event()
        old_resume, new_resume = threading.Event(), threading.Event()

        def old_operation(running):
            old_entered.set()
            self.assertTrue(old_resume.wait(10))
            return {'worker':'old'}

        def new_operation(running):
            self.assertEqual(running['attempts'], 2)
            new_entered.set()
            self.assertTrue(new_resume.wait(10))
            return {'worker':'new'}

        with patch.object(self.old, 'execute', side_effect=old_operation), patch.object(self.new, 'execute', side_effect=new_operation):
            old_thread, _, old_failures = self.thread(self.old)
            new_thread = None
            try:
                self.assertTrue(old_entered.wait(10))
                self.expire(job['id'])
                new_thread, _, new_failures = self.thread(self.new)
                self.assertTrue(new_entered.wait(10))
                before = self.new.get(job['id'])
                events = self.new.updates(0)
                with self.assertRaises(ClaimLost):
                    self.old.check(job['id'], 1)
                self.assertEqual(self.new.get(job['id']), before)
                self.assertEqual(self.new.updates(0), events)
            finally:
                new_resume.set()
                if new_thread:
                    self.finish(new_thread, new_failures)
                old_resume.set()
                self.finish(old_thread, old_failures)
        self.assertEqual(self.new.get(job['id'])['result'], {'worker':'new'})

    def test_generation_is_captured_inside_claim_without_post_commit_get(self):
        job = self.submit()
        captured = []

        def execute(running):
            captured.append(running['attempts'])
            self.old.check(running['id'], running['attempts'])
            return {'synthetic':True}

        with (patch.object(self.old, 'get', side_effect=AssertionError('Post-claim get cannot establish ownership.')),
              patch.object(self.old, 'execute', side_effect=execute)):
            self.assertTrue(self.old.run_once())
        self.assertEqual(captured, [1])
        self.assertEqual(self.old.get(job['id'])['status'], 'succeeded')

    def test_provider_callback_uses_the_original_claim_before_further_work(self):
        job = self.submit('connector_sync', {'provider':'statsbomb'})
        entered, resume = threading.Event(), threading.Event()
        further_work = []

        def provider(provider, operation, check, job_id):
            entered.set()
            self.assertTrue(resume.wait(10))
            check()
            further_work.append('must-not-run')
            return {'worker':'old'}

        with patch.object(self.old.providers, 'run', side_effect=provider):
            thread, _, failures = self.thread(self.old)
            try:
                self.assertTrue(entered.wait(10))
                self.expire(job['id'])
                with patch.object(self.new.providers, 'run', return_value={'worker':'new'}):
                    self.assertTrue(self.new.run_once())
            finally:
                resume.set()
                self.finish(thread, failures)
        self.assertEqual(further_work, [])
        self.assertEqual(self.new.get(job['id'])['result'], {'worker':'new'})

    def test_old_import_progress_and_import_event_cannot_publish_after_reclaim(self):
        job = self.submit('import_public', {'mode':'retained'})
        entered, resume = threading.Event(), threading.Event()
        ingest = public_results.ingest_bytes

        def retained_batch(*args, **kwargs):
            result = ingest(*args, **kwargs)
            entered.set()
            self.assertTrue(resume.wait(10))
            return result

        with patch('dragonhydra.jobs.public_results.ingest_bytes', side_effect=retained_batch):
            thread, _, failures = self.thread(self.old)
            try:
                self.assertTrue(entered.wait(10))
                self.expire(job['id'])
                with patch.object(self.new, 'execute', return_value={'worker':'new'}):
                    self.assertTrue(self.new.run_once())
                completed, events = self.new.get(job['id']), self.new.updates(0)
            finally:
                resume.set()
                self.finish(thread, failures)
        self.assertEqual(self.new.get(job['id']), completed)
        self.assertEqual(self.new.updates(0), events)
        self.assertFalse(any(event['topic']=='import' for event in events))

    def test_current_owner_cancel_is_terminal_even_after_operation_returns(self):
        for cooperative in (True, False):
            with self.subTest(cooperative=cooperative):
                job = self.submit()

                def cancel(running):
                    self.old.cancel(running['id'])
                    if cooperative:
                        self.old.check(running['id'], running['attempts'])
                    return {'synthetic':'completed-before-cancellation-check'}

                with patch.object(self.old, 'execute', side_effect=cancel):
                    self.assertTrue(self.old.run_once())
                result = self.old.get(job['id'])
                self.assertEqual((result['status'], result['attempts'], result['error']['code']), ('cancelled', 1, 'CANCELLED'))
                self.assertFalse(self.old.run_once())
                self.assertFalse(any(event['topic']=='data' and event['data']['job_id']==job['id'] for event in self.old.updates(0)))

    def test_require_claim_is_select_only_inside_a_read_only_transaction(self):
        job = self.submit()
        with closing(self.product.connect()) as db:
            db.execute("UPDATE product_jobs SET status='running',attempts=7,deadline=? WHERE id=?", (time.time()+120, job['id']))
            db.commit()
        with closing(sqlite3.connect(self.product.db_path.as_uri()+'?mode=ro', uri=True)) as db:
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            traced = []
            db.set_trace_callback(traced.append)
            state = Jobs.require_claim(db, job['id'], 7)
            self.assertEqual(state['attempts'], 7)
            with self.assertRaises(ClaimLost):
                Jobs.require_claim(db, job['id'], 6)
            self.assertTrue(traced and all(sql.lstrip().startswith('SELECT') for sql in traced))
            self.assertTrue(db.in_transaction)
        for invalid in (True, 0, -1, '7'):
            with closing(self.product.connect()) as db, self.assertRaises(ValueError):
                Jobs.require_claim(db, job['id'], invalid)

    def test_current_claim_deadline_and_direct_legacy_checks_are_preserved(self):
        job = self.submit()
        self.old.check(job['id'])  # Legacy direct checks may inspect a queued job.
        with closing(self.product.connect()) as db:
            db.execute("UPDATE product_jobs SET status='running',attempts=1,deadline=?,heartbeat=5 WHERE id=?", (time.time()-1, job['id']))
            db.commit()
        with self.assertRaises(TimeoutError):
            self.old.check(job['id'], 1)
        self.assertEqual(self.old.get(job['id'])['heartbeat'], 5)
        self.old.cancel(job['id'])
        with self.assertRaises(Cancelled):
            self.old.check(job['id'])

    def export_match(self):
        self.submit('import_public', {'mode':'retained'})
        self.assertTrue(self.old.run_once())
        return self.product.match_id(self.product.rows()[0])

    def test_stale_export_temps_and_publication_cannot_replace_new_artifact_manifest_or_events(self):
        match_id = self.export_match()
        original_write, original_replace = Path.write_text, os.replace
        main_thread = threading.current_thread()
        for pause_at in ('complete-manifest', 'partial-artifact'):
            with self.subTest(pause_at=pause_at):
                job = self.submit('export', {'match_id':match_id, 'format':'json'})
                entered, resume = threading.Event(), threading.Event()
                replacements = []

                def pause():
                    entered.set()
                    self.assertTrue(resume.wait(10))

                def write(path, content, *args, **kwargs):
                    owned_old = path.parent == self.product.exports and path.name.startswith(job['id']+'.json.claim-1.')
                    manifest = path.name.endswith('.manifest.tmp')
                    if owned_old and not manifest and pause_at == 'partial-artifact':
                        original_write(path, 'partial-old-writer', encoding='utf-8')
                        pause()
                    result = original_write(path, content, *args, **kwargs)
                    if owned_old and manifest and pause_at == 'complete-manifest':
                        pause()
                    return result

                def replace(source, target):
                    replacements.append((Path(source), Path(target)))
                    return original_replace(source, target)

                def explanation(_):
                    return {'worker':'new' if threading.current_thread() is main_thread else 'old'}

                with (patch.object(Path, 'write_text', new=write), patch('dragonhydra.jobs.os.replace', side_effect=replace),
                      patch.object(self.product, 'explanation', side_effect=explanation)):
                    thread, _, failures = self.thread(self.old)
                    try:
                        self.assertTrue(entered.wait(10))
                        old_temps = {path:path.read_bytes() for path in self.product.exports.glob(job['id']+'.json.claim-1.*.tmp')}
                        self.assertEqual(len(old_temps), 2 if pause_at == 'complete-manifest' else 1)
                        self.expire(job['id'])
                        self.assertTrue(self.new.run_once())
                        artifact = self.product.exports/(job['id']+'.json')
                        manifest = artifact.with_suffix('.json.manifest.json')
                        final_bytes, manifest_bytes = artifact.read_bytes(), manifest.read_bytes()
                        self.assertEqual(json.loads(final_bytes)['explanation']['worker'], 'new')
                        self.assertEqual(json.loads(manifest_bytes)['explanation']['worker'], 'new')
                        completed, events = self.new.get(job['id']), self.new.updates(0)
                        self.assertEqual(completed['attempts'], 2)
                        self.assertEqual({path:path.read_bytes() for path in old_temps}, old_temps)
                    finally:
                        resume.set()
                        self.finish(thread, failures)
                self.assertEqual(artifact.read_bytes(), final_bytes)
                self.assertEqual(manifest.read_bytes(), manifest_bytes)
                self.assertEqual(self.new.get(job['id']), completed)
                self.assertEqual(self.new.updates(0), events)
                self.assertEqual(len(replacements), 2)
                self.assertTrue(all('.claim-2.' in source.name for source, _ in replacements))
                self.assertEqual(list(self.product.exports.glob(job['id']+'*.tmp')), [])

    def test_export_publication_checks_late_cancel_and_deadline_and_cleans_only_private_temps(self):
        match_id = self.export_match()
        original_write = Path.write_text
        for action in ('cancel', 'deadline'):
            with self.subTest(action=action):
                job = self.submit('export', {'match_id':match_id, 'format':'json'})

                def write(path, content, *args, **kwargs):
                    result = original_write(path, content, *args, **kwargs)
                    if path.parent == self.product.exports and path.name.startswith(job['id']) and path.name.endswith('.manifest.tmp'):
                        if action == 'cancel':
                            self.old.cancel(job['id'])
                        else:
                            with closing(self.product.connect()) as db:
                                db.execute('UPDATE product_jobs SET deadline=? WHERE id=?', (time.time()-1, job['id']))
                                db.commit()
                    return result

                with patch.object(Path, 'write_text', new=write):
                    self.assertTrue(self.old.run_once())
                result = self.old.get(job['id'])
                self.assertEqual(result['status'], 'cancelled' if action == 'cancel' else 'queued')
                self.assertEqual(list(self.product.exports.glob(job['id']+'*')), [])
                self.assertFalse(any(event['topic']=='data' and event['data']['job_id']==job['id'] for event in self.old.updates(0)))

    def test_export_holds_writer_lock_across_both_final_replacements(self):
        match_id = self.export_match()
        job = self.submit('export', {'match_id':match_id, 'format':'json'})
        first_replaced, resume = threading.Event(), threading.Event()
        original_replace = os.replace

        def replace(source, target):
            result = original_replace(source, target)
            if Path(target).name == job['id']+'.json':
                first_replaced.set()
                self.assertTrue(resume.wait(10))
            return result

        with patch('dragonhydra.jobs.os.replace', side_effect=replace):
            thread, _, failures = self.thread(self.old)
            try:
                self.assertTrue(first_replaced.wait(10))
                with closing(sqlite3.connect(self.product.db_path, timeout=0)) as contender:
                    with self.assertRaisesRegex(sqlite3.OperationalError, 'locked'):
                        contender.execute('BEGIN IMMEDIATE')
            finally:
                resume.set()
                self.finish(thread, failures)
        artifact = self.product.exports/(job['id']+'.json')
        self.assertEqual(json.loads(artifact.read_bytes()), json.loads(artifact.with_suffix('.json.manifest.json').read_bytes()))
        self.assertEqual(self.old.get(job['id'])['status'], 'succeeded')


if __name__ == '__main__':
    unittest.main()
