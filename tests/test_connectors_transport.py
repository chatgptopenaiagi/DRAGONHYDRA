"""Transport rejection cases retain received bytes and redact account material."""
from io import BytesIO
from http.client import IncompleteRead
from email.message import Message
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import BaseHandler, Request
from urllib.response import addinfourl

from dragonhydra.connectors.core import ConnectorError, SafeRedirect, Transport

ROOT = Path(__file__).resolve().parents[1]


class Headers(dict):
    def get_content_type(self):
        return self.get('Content-Type', 'application/json')


class Response(BytesIO):
    def __init__(self, raw, status=200, headers=None):
        super().__init__(raw)
        self.status = status
        self.headers = Headers(headers or {})

    def getcode(self):
        return self.status

    def geturl(self):
        return 'https://api.the-odds-api.com/v4/sports?apiKey=private-fixture-key'


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'runtime'/'scratch', prefix='http-contract-')
        self.addCleanup(self.temp.cleanup)
        self.receipts = []
        self.transport = Transport(Path(self.temp.name), self.receipts.append)

    def respond(self, raw, status=200, headers=None):
        self.transport.opener.open = lambda *a, **k: Response(raw, status, headers)
        return self.transport.get('https://api.the-odds-api.com/v4/sports?apiKey=private-fixture-key')

    def test_invalid_json_retains_exact_bytes_before_parse(self):
        doc = self.respond(b'{broken-json')
        with self.assertRaises(ConnectorError) as cm:
            doc.json()
        self.assertEqual(cm.exception.code, 'INVALID_JSON')
        self.assertEqual((Path(self.temp.name)/doc.raw_reference).read_bytes(), b'{broken-json')
        self.assertNotIn('private-fixture-key', doc.url)
        self.assertNotIn('private-fixture-key', doc.resolved_url)

    def test_html_page_is_not_successful_dataset(self):
        with self.assertRaises(ConnectorError) as cm:
            self.respond(b'<html>Error</html>', headers={'Content-Type': 'text/html'})
        self.assertEqual(cm.exception.code, 'UNEXPECTED_HTML')
        self.assertEqual(len(self.receipts), 1)

    def test_rate_limit_preserves_retry_after_without_leaking_url(self):
        with self.assertRaises(ConnectorError) as cm:
            self.respond(b'{"error":"quota"}', 429, {'Retry-After': '120'})
        self.assertEqual((cm.exception.code, cm.exception.retry_after, cm.exception.http_status), ('RATE_LIMITED', 120, 429))
        self.assertNotIn('private-fixture-key', str(cm.exception))
        self.assertEqual(self.receipts[0].http_status, 429)

    def test_authentication_denial_is_distinct_from_network(self):
        with self.assertRaises(ConnectorError) as cm:
            self.respond(b'{"error":"denied"}', 403)
        self.assertEqual(cm.exception.code, 'AUTH_REJECTED')
        self.assertEqual(cm.exception.http_status, 403)

    def test_midstream_network_interruptions_do_not_commit_partial_evidence(self):
        for error in (TimeoutError('fixture timeout'), ConnectionResetError('fixture reset'),
                      IncompleteRead(b'partial', 10)):
            with self.subTest(error=type(error).__name__):
                response = Response(b'')
                response.read = unittest.mock.Mock(side_effect=[b'{"partial":', error])
                self.transport.opener.open = lambda *a, **k: response
                with self.assertRaises(ConnectorError) as cm:
                    self.transport.get('https://api.the-odds-api.com/v4/sports?apiKey=private-fixture-key')
                self.assertEqual((cm.exception.code, cm.exception.retry_after), ('NETWORK_UNAVAILABLE', 60))
                self.assertNotIn('private-fixture-key', str(cm.exception))
                self.assertTrue(response.closed)
                self.assertEqual(list(Path(self.temp.name).iterdir()), [])
                self.assertEqual(self.receipts, [])
                self.assertEqual(self.transport.documents, [])
        raw = b'{"record":"complete retry"}'
        doc = self.respond(raw, headers={'Content-Length': str(len(raw))})
        self.assertEqual(doc.body, raw)
        self.assertEqual(len(self.receipts), 1)

    def test_short_transfer_is_rejected_before_valid_partial_json_can_be_imported(self):
        with self.assertRaises(ConnectorError) as cm:
            self.respond(b'[]', headers={'Content-Length': '100'})
        self.assertEqual(cm.exception.code, 'NETWORK_UNAVAILABLE')
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])
        self.assertEqual(self.receipts, [])
        self.assertEqual(self.transport.documents, [])

    def test_chunked_transfer_ignores_content_length_as_http_framing_requires(self):
        doc = self.respond(b'[]', headers={'Transfer-Encoding': 'chunked', 'Content-Length': '100'})
        self.assertEqual(doc.json(), [])

    def test_transient_http_errors_retain_exact_bytes_and_cooldown(self):
        for status in (500, 502, 503, 504):
            with self.subTest(status=status):
                raw = b'{"error":"temporary outage"}'
                with self.assertRaises(ConnectorError) as cm:
                    self.respond(raw, status, {'Retry-After': '120'})
                self.assertEqual((cm.exception.code, cm.exception.http_status, cm.exception.retry_after),
                                 ('NETWORK_UNAVAILABLE', status, 120))
                doc = self.receipts[-1]
                self.assertEqual((Path(self.temp.name)/doc.raw_reference).read_bytes(), raw)
                self.assertEqual(doc.http_status, status)
                self.assertNotIn('private-fixture-key', str(cm.exception))

    def test_permanent_http_errors_are_not_classified_as_transient(self):
        for status in (400, 404, 422, 501):
            with self.subTest(status=status):
                with self.assertRaises(ConnectorError) as cm:
                    self.respond(b'{"error":"permanent"}', status)
                self.assertEqual((cm.exception.code, cm.exception.http_status), ('HTTP_ERROR', status))
                self.assertIsNone(cm.exception.retry_after)

    def test_download_limit_is_bounded(self):
        self.transport.max_bytes = 10
        with self.assertRaises(ConnectorError) as cm:
            self.respond(b'12345678901')
        self.assertEqual(cm.exception.code, 'DOWNLOAD_LIMIT')
        self.assertIn('10 byte', cm.exception.message)

    def redirect_opener(self, transport, status=302):
        """Exercise urllib's actual redirect processing without network access."""
        calls = []

        class RedirectFixture(BaseHandler):
            handler_order = 100

            def https_open(self, request):
                calls.append(request.full_url)
                headers = Message()
                headers['Content-Type'] = 'application/json'
                if len(calls) == 1:
                    headers['Location'] = 'https://raw.githubusercontent.com/hudl/open-data/master/next.json'
                    response = addinfourl(BytesIO(b'{"redirect":true}'), headers, request.full_url, status)
                    response.msg = 'Redirect'
                else:
                    response = addinfourl(BytesIO(b'[]'), headers, request.full_url, 200)
                    response.msg = 'OK'
                return response

        transport.opener.add_handler(RedirectFixture())
        return calls

    def test_bounded_mode_retains_redirect_without_another_request(self):
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status):
                receipts = []
                transport = Transport(Path(self.temp.name), receipts.append, follow_redirects=False)
                calls = self.redirect_opener(transport, status)
                with self.assertRaises(ConnectorError) as cm:
                    transport.get('https://raw.githubusercontent.com/hudl/open-data/master/initial.json')
                self.assertEqual((cm.exception.code, cm.exception.http_status), ('REDIRECT_REJECTED', status))
                self.assertIsNone(cm.exception.retry_after)
                self.assertEqual(len(calls), 1)
                self.assertEqual(len(receipts), 1)
                self.assertEqual(receipts[0].body, b'{"redirect":true}')
                self.assertEqual(receipts[0].http_status, status)
                self.assertEqual(receipts[0].url, receipts[0].resolved_url)
                self.assertEqual((Path(self.temp.name)/receipts[0].raw_reference).read_bytes(), receipts[0].body)

    def test_default_redirect_mode_preserves_registered_public_redirects(self):
        calls = self.redirect_opener(self.transport)
        doc = self.transport.get('https://github.com/hudl/open-data/raw/refs/heads/master/initial.json')
        self.assertEqual(len(calls), 2)
        self.assertEqual(doc.body, b'[]')
        self.assertEqual(doc.http_status, 200)
        self.assertEqual(len(self.receipts), 1)
        self.assertEqual(doc.resolved_url, calls[-1])

    def test_bounded_mode_rejects_other_3xx_responses(self):
        self.transport = Transport(Path(self.temp.name), self.receipts.append, follow_redirects=False)
        with self.assertRaises(ConnectorError) as cm:
            self.respond(b'{"not_modified":true}', 304)
        self.assertEqual((cm.exception.code, cm.exception.http_status), ('REDIRECT_REJECTED', 304))
        self.assertEqual(len(self.receipts), 1)

    def test_authentication_cannot_follow_redirect_to_another_registered_host(self):
        request = Request('https://api.football-data.org/v4/matches', headers={'X-Auth-Token': 'private-fixture-key'})
        with self.assertRaises(ConnectorError) as cm:
            SafeRedirect().redirect_request(request, None, 302, 'redirect', {}, 'https://github.com/example')
        self.assertEqual(cm.exception.code, 'AUTH_REDIRECT_REJECTED')

    def test_failed_raw_write_leaves_no_partial_committed_path_and_can_retry(self):
        raw = b'{"record":"stable"}'
        with patch('dragonhydra.connectors.core.os.fsync', side_effect=OSError('fixture disk failure')):
            with self.assertRaises(ConnectorError) as cm:
                self.respond(raw)
        self.assertEqual(cm.exception.code, 'RAW_RETENTION_FAILED')
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])
        doc = self.respond(raw)
        self.assertEqual((Path(self.temp.name)/doc.raw_reference).read_bytes(), raw)

    def test_existing_corrupt_committed_payload_is_never_overwritten(self):
        raw = b'{"record":"stable"}'
        path = Path(self.temp.name)/(hashlib.sha256(raw).hexdigest()+'.payload')
        path.write_bytes(b'damaged committed evidence')
        with self.assertRaises(ConnectorError) as cm:
            self.respond(raw)
        self.assertEqual(cm.exception.code, 'RAW_INTEGRITY_FAILURE')
        self.assertEqual(path.read_bytes(), b'damaged committed evidence')


if __name__=='__main__':
    unittest.main()
