"""Independent regression cases for recovery and immutable import receipts."""
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class ProductReviewTests(unittest.TestCase):
    def setUp(self):
        from dragonhydra.jobs import Jobs
        from dragonhydra.product import Product
        (ROOT / 'runtime' / 'scratch').mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'runtime' / 'scratch', prefix='product-review-')
        self.addCleanup(self.temp.cleanup)
        self.product = Product(Path(self.temp.name), ROOT)
        self.jobs = Jobs(self.product)

    def test_graceful_worker_stop_keeps_running_job_recoverable(self):
        job = self.jobs.submit('import_public', {'mode': 'retained'}, 'local:owner')

        def stop_during_operation(running):
            self.jobs.stop.set()
            self.jobs.check(running['id'])

        with patch.object(self.jobs, 'execute', side_effect=stop_during_operation):
            self.jobs.run_once()
        stopped = self.jobs.get(job['id'])
        self.assertIn(stopped['status'], ('queued', 'interrupted'),
                      'A service stop must preserve a running job for recovery, not cancel the user action.')
        self.jobs.stop.clear()
        self.jobs.run_once()
        self.assertEqual(self.jobs.get(job['id'])['status'], 'succeeded')
        self.assertGreater(len(self.product.rows()), 0)

    def test_explicit_user_cancel_remains_terminal(self):
        job = self.jobs.submit('import_public', {'mode': 'retained'}, 'local:owner')

        def cancel_during_operation(running):
            self.jobs.cancel(running['id'])
            self.jobs.check(running['id'])

        with patch.object(self.jobs, 'execute', side_effect=cancel_during_operation):
            self.jobs.run_once()
        self.assertEqual(self.jobs.get(job['id'])['status'], 'cancelled')
        self.assertFalse(self.jobs.run_once())

    def test_cancelled_expired_lease_does_not_become_stranded_queued_job(self):
        job = self.jobs.submit('import_public', {'mode': 'retained'}, 'local:owner')
        with closing(self.product.connect()) as db:
            db.execute("UPDATE product_jobs SET status='running',attempts=1,cancel_requested=1,lease_until=0 WHERE id=?", (job['id'],))
            db.commit()
        self.assertFalse(self.jobs.run_once())
        self.assertEqual(self.jobs.get(job['id'])['status'], 'cancelled')

    def test_repeated_graceful_restarts_do_not_exhaust_transport_retry_budget(self):
        job = self.jobs.submit('import_public', {'mode': 'retained'}, 'local:owner')
        with closing(self.product.connect()) as db:
            db.execute("UPDATE product_jobs SET status='interrupted',attempts=3,lease_until=NULL WHERE id=?", (job['id'],))
            db.commit()
        self.assertTrue(self.jobs.run_once())
        self.assertEqual(self.jobs.get(job['id'])['status'], 'succeeded')

    def test_duplicate_import_preserves_original_raw_receipts(self):
        first = self.jobs.submit('import_public', {'mode': 'retained'}, 'local:owner')
        self.jobs.run_once()
        self.assertEqual(self.jobs.get(first['id'])['status'], 'succeeded')
        before = {p.name: p.read_bytes() for p in (self.product.state / 'raw').glob('*.receipt.json')}
        self.assertEqual(len(before), 2)
        second = self.jobs.submit('import_public', {'mode': 'retained'}, 'local:owner')
        self.jobs.run_once()
        self.assertEqual(self.jobs.get(second['id'])['result']['inserted'], 0)
        after = {p.name: p.read_bytes() for p in (self.product.state / 'raw').glob('*.receipt.json')}
        self.assertEqual(before, after, 'A duplicate import must not rewrite the original capture receipt clock.')

    @unittest.skipUnless(importlib.util.find_spec('fastapi'), 'HTTP checks require runtime/server-env')
    def test_non_ascii_pairing_token_is_rejected_without_server_error(self):
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        app = create_app(Path(self.temp.name) / 'api', local_token='review-local-token-1234567890', start_worker=False)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post('/dragon/api/v1/session', json={'token': '\u00e9' * 30})
        self.assertIn(response.status_code, (400, 401, 422))
        self.assertIn('error', response.json())

    @unittest.skipUnless(importlib.util.find_spec('fastapi'), 'HTTP checks require runtime/server-env')
    def test_invalid_content_length_has_machine_readable_error(self):
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        app = create_app(Path(self.temp.name) / 'api', local_token='review-local-token-1234567890', start_worker=False)
        with TestClient(app, raise_server_exceptions=False) as client:
            for value in ('invalid', '-1'):
                response = client.post('/dragon/api/v1/session', content=b'{}', headers={'Content-Length': value})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['error']['code'], 'INVALID_CONTENT_LENGTH')


if __name__ == '__main__':
    unittest.main()
