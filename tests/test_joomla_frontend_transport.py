"""Real private PHP export transport, using only an isolated synthetic HTTP fixture."""
import base64
import hashlib
import hmac
import http.server
import json
from pathlib import Path
import subprocess
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
PHP = ROOT / 'build/workstation/test-install/application files/web/php/php.exe'
INI = ROOT / 'build/workstation/test-install/state data/web-config/php.ini'
CLIENT = ROOT / 'server/joomla/com_dragonhydra/admin/src/Service/ApiClient.php'
FIXTURE_SECRET = 'synthetic-export-transport-fixture-not-a-workstation-secret'
JOB = 'a' * 32


@unittest.skipUnless(PHP.is_file(), 'Existing matching private PHP runtime is required')
class FrontendExportTransportTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.response_status = 200
        self.response_filename = JOB + '.csv'
        self.response_body = b'team,score\nFixture,1\n'
        test = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                fields = ['GET', self.path, self.headers['X-Dragon-Time'], self.headers['X-Dragon-Nonce'],
                          self.headers['X-Dragon-User'], self.headers['X-Dragon-Roles'], hashlib.sha256(b'').hexdigest()]
                expected = hmac.new(FIXTURE_SECRET.encode(), '\n'.join(fields).encode(), 'sha256').hexdigest()
                test.requests.append({'valid_hmac': hmac.compare_digest(self.headers['X-Dragon-Signature'], expected),
                                      'path': self.path, 'identity': self.headers['X-Dragon-User'],
                                      'role': self.headers['X-Dragon-Roles']})
                self.send_response(test.response_status)
                self.send_header('Content-Disposition', 'attachment; filename="' + test.response_filename + '"')
                if test.response_status == 302:
                    self.send_header('Location', '/not-an-export')
                self.send_header('Content-Length', str(len(test.response_body)))
                self.end_headers()
                self.wfile.write(test.response_body)

        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)

    def invoke(self, path):
        args = [f'http://127.0.0.1:{self.server.server_port}/dragon/api/v1', FIXTURE_SECRET, 'joomla:476', 'reader']
        source = "define('_JEXEC',1);require " + json.dumps(str(CLIENT)) + ";$client=new \\Dragonhydra\\Component\\Dragonhydra\\Administrator\\Service\\ApiClient(" + ','.join(map(json.dumps, args)) + ");try{$r=$client->download(" + json.dumps(path) + ");$r['body']=base64_encode($r['body']);echo json_encode($r);}catch(\\RuntimeException $e){echo json_encode(['denied'=>true]);}"
        result = subprocess.run([str(PHP), '-c', str(INI), '-r', source], capture_output=True, text=True, timeout=25)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_exact_export_is_signed_with_reader_identity_and_binary_preserved(self):
        response = self.invoke('/exports/' + JOB + '/download')
        self.assertEqual(base64.b64decode(response['body']), self.response_body)
        self.assertEqual(response['filename'], JOB + '.csv')
        self.assertTrue(response['content_type'].startswith('text/csv'))
        self.assertEqual(self.requests, [{'valid_hmac': True, 'path': '/dragon/api/v1/exports/' + JOB + '/download',
                                         'identity': 'joomla:476', 'role': 'reader'}])

    def test_arbitrary_or_credential_bearing_paths_are_rejected_before_network(self):
        for path in ['/system', '//example.org/', '/exports/../download', '/exports/' + JOB + '/download?token=fixture']:
            self.assertTrue(self.invoke(path)['denied'])
        self.assertEqual(self.requests, [])

    def test_unauthorized_not_ready_redirects_and_wrong_filenames_are_denied(self):
        for status in (401, 409, 302):
            self.response_status = status
            self.assertTrue(self.invoke('/exports/' + JOB + '/download')['denied'])
        self.response_status = 200
        self.response_filename = 'b' * 32 + '.csv'
        self.assertTrue(self.invoke('/exports/' + JOB + '/download')['denied'])
        self.assertEqual(len(self.requests), 4)


if __name__ == '__main__':
    unittest.main()
