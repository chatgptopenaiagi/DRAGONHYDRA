"""Offline acceptance-helper safety tests; no credentials, installed store or browser calls."""
import importlib.util
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('system_control_browser_under_test', ROOT / 'tests/installation/system_control_browser.py')
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)


class SystemControlBrowserHarnessTests(unittest.TestCase):
    def test_job_proof_ignores_legitimate_existing_status_updates_and_never_reads_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            database = state / 'kernel/core.sqlite3'; database.parent.mkdir()
            with closing(sqlite3.connect(database)) as db:
                db.execute('CREATE TABLE product_jobs(id TEXT,kind TEXT,status TEXT,payload TEXT,owner TEXT)')
                db.execute('INSERT INTO product_jobs VALUES(?,?,?,?,?)', ('a'*32,'forecast','running','PRIVATE_FIXTURE_SECRET','PRIVATE_FIXTURE_SECRET'))
                db.commit()
            with patch.object(HARNESS,'STATE',state):
                before = HARNESS.job_snapshot(database)
                with closing(sqlite3.connect(database)) as db:
                    db.execute("UPDATE product_jobs SET status='succeeded'")
                    db.commit()
                after = HARNESS.job_snapshot(database)
            self.assertEqual(before['ids'],after['ids'])
            proof=HARNESS.snapshot_evidence(before,after)
            self.assertTrue(proof['existing_job_statuses_changed'])
            self.assertEqual(proof['before_ids_sha256'],proof['after_ids_sha256'])
            self.assertNotIn('PRIVATE_FIXTURE_SECRET',json.dumps([before,after,proof]))

    def test_job_probe_rejects_any_other_database(self):
        with self.assertRaises(AssertionError):
            HARNESS.job_snapshot(ROOT/'some-other-installation/core.sqlite3')

    def test_output_must_be_fresh_scoped_and_reports_refuse_secret_values(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            with patch.object(HARNESS,'BASE',base):
                acceptance=HARNESS.Acceptance(base/'browser-offline-fixture')
                self.assertFalse(acceptance.apply_workflow)
                acceptance.private_values=['PRIVATE_FIXTURE_SECRET']
                acceptance.report['unsafe']='PRIVATE_FIXTURE_SECRET'
                with self.assertRaises(AssertionError): acceptance.save()
                self.assertFalse((acceptance.output/'verification.json').exists())
                del acceptance.report['unsafe']; acceptance.save()
                self.assertNotIn('PRIVATE_FIXTURE_SECRET',(acceptance.output/'verification.json').read_text())
                with self.assertRaises(AssertionError): HARNESS.Acceptance(base/'browser-offline-fixture')
                with self.assertRaises(AssertionError): HARNESS.Acceptance(base/'unscoped-output')


if __name__=='__main__':
    unittest.main()
