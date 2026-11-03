"""Package integrity, PHP transport/identity and access-control regression tests.

These checks do not substitute for installing the extension in Joomla.
"""
from __future__ import annotations

import hashlib
import hmac
import http.server
import importlib.util
import io
import json
import re
from pathlib import Path
import subprocess
import threading
import unittest
from uuid import uuid4
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'server' / 'joomla'
PHP = Path('C:/xampp/php/php.exe')
API_CLIENT = SOURCE / 'com_dragonhydra/admin/src/Service/ApiClient.php'


def php(source):
    result = subprocess.run([str(PHP), '-r', source], capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout


class JoomlaPackageTests(unittest.TestCase):
    def test_manifests_reference_existing_payloads(self):
        package = ET.parse(SOURCE / 'pkg_dragonhydra.xml').getroot()
        self.assertEqual('package', package.get('type'))
        self.assertEqual('dragonhydra', package.findtext('packagename'))
        self.assertEqual(['cassiopeia_dragonhydra', 'com_dragonhydra'], [entry.get('id') for entry in package.findall('files/file')])
        component = ET.parse(SOURCE / 'com_dragonhydra/dragonhydra.xml').getroot()
        self.assertEqual('Dragonhydra\\Component\\Dragonhydra', component.findtext('namespace'))
        root = SOURCE / 'com_dragonhydra'
        for node in component.findall('administration/files/*'):
            self.assertTrue((root / 'admin' / node.text).exists(), node.text)
        for node in component.findall('administration/languages/language'):
            self.assertTrue((root / 'admin/language' / node.text).exists(), node.text)
        self.assertTrue((root / component.findtext('scriptfile')).is_file())

    def test_reproducible_package_and_no_secrets(self):
        spec = importlib.util.spec_from_file_location('build_joomla', ROOT / 'scripts/build_joomla.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        target = ROOT / 'runtime/scratch' / ('joomla-package-test-' + uuid4().hex + '.zip')
        try:
            first = builder.build(target)
            second = builder.build(target)
            self.assertEqual(first['sha256'], second['sha256'])
            with zipfile.ZipFile(target) as package:
                self.assertEqual({'pkg_dragonhydra.xml', 'constituents/com_dragonhydra.zip', 'constituents/tpl_cassiopeia_dragonhydra.zip'}, set(package.namelist()))
                with zipfile.ZipFile(io.BytesIO(package.read('constituents/com_dragonhydra.zip'))) as component:
                    self.assertIn('admin/services/provider.php', component.namelist())
                    self.assertIn('admin/src/Controller/ActionsController.php', component.namelist())
                    self.assertNotIn('configuration.php', component.namelist())
                    self.assertFalse(any(n.startswith('/') or '..' in n.split('/') for n in component.namelist()))
        finally:
            target.unlink(missing_ok=True)
            target.with_suffix('.manifest.json').unlink(missing_ok=True)

    def test_acl_and_csrf_protect_every_mutation(self):
        access = ET.parse(SOURCE / 'com_dragonhydra/admin/access.xml').getroot()
        actions = {x.get('name') for x in access.findall('section/action')}
        self.assertIn('dragonhydra.import', actions)
        controller = (SOURCE / 'com_dragonhydra/admin/src/Controller/ActionsController.php').read_text()
        self.assertIn("Session::checkToken('post')", controller)
        self.assertIn("authorise('core.manage'", controller)
        self.assertIn("authorise('dragonhydra.import'", controller)
        # Four direct actions and the shared workflow are guarded. Forecast and
        # evaluation delegate to that same workflow; a raw historic count of
        # three omitted the implemented observation and research operations.
        guarded = set(re.findall(r'(?:public|private) function (\w+)\([^)]*\): void\s*\{\s*\$this->guard\(\);', controller))
        self.assertEqual({'sync', 'probe', 'cancel', 'observe', 'workflow'}, guarded)
        public = set(re.findall(r'public function (\w+)\(', controller))
        self.assertEqual({'sync', 'probe', 'cancel', 'observe', 'forecast', 'evaluate'}, public)
        self.assertRegex(controller, r"public function forecast\(\): void\s*\{\s*\$this->workflow\('forecasts'\);\s*\}")
        self.assertRegex(controller, r"public function evaluate\(\): void\s*\{\s*\$this->workflow\('evaluations'\);\s*\}")
        self.assertIn('CORE_NEXT_INSTALLATION_MISMATCH', controller)
        self.assertNotIn('shell_exec', controller)
        self.assertNotIn('exec(', controller)

    def test_uninstall_retains_kernel_data(self):
        sql = (SOURCE / 'com_dragonhydra/admin/sql/uninstall.mysql.utf8.sql').read_text()
        self.assertTrue(all(not line.strip() or line.lstrip().startswith('--') for line in sql.splitlines()))
        self.assertIn('retained', (SOURCE / 'com_dragonhydra/script.php').read_text())

    @unittest.skipUnless(PHP.is_file(), 'Registered PHP CLI unavailable; syntax/transport checks not run')
    def test_php_syntax(self):
        for path in SOURCE.rglob('*.php'):
            result = subprocess.run([str(PHP), '-l', str(path)], capture_output=True, text=True, timeout=10)
            self.assertEqual(0, result.returncode, str(path) + result.stdout + result.stderr)

    @unittest.skipUnless(PHP.is_file(), 'Registered PHP CLI unavailable')
    def test_hmac_golden_identity_contract(self):
        body = '{}'
        path = '/dragon/api/v1/connections/openfootball/sync'
        fields = ['POST', path, '1793352000', '00112233445566778899aabbccddeeff', 'joomla:42', 'admin', hashlib.sha256(body.encode()).hexdigest()]
        expected = hmac.new(b'a' * 32, '\n'.join(fields).encode(), 'sha256').hexdigest()
        result = php("define('_JEXEC', 1); require " + json.dumps(str(API_CLIENT)) + "; echo \\Dragonhydra\\Component\\Dragonhydra\\Administrator\\Service\\ApiClient::signature(str_repeat('a',32),'POST'," + json.dumps(path) + ",'1793352000','00112233445566778899aabbccddeeff','joomla:42','admin','{}');")
        self.assertEqual(expected, result)

    @unittest.skipUnless(PHP.is_file(), 'Registered PHP CLI unavailable')
    def test_endpoint_validation_rejects_ssrf(self):
        bases = ['https://example.org/dragon/api/v1', 'file:///etc/passwd',
                 'http://127.0.0.1:8731/dragon/api/v1?redirect=x',
                 'http://user:pass@127.0.0.1:8731/dragon/api/v1',
                 'http://localhost.evil/dragon/api/v1', 'http://127.0.0.1:8731/elsewhere']
        source = "define('_JEXEC', 1); require " + json.dumps(str(API_CLIENT)) + "; $count=0; foreach(json_decode(" + json.dumps(json.dumps(bases)) + ",true) as $base) { try { \\Dragonhydra\\Component\\Dragonhydra\\Administrator\\Service\\ApiClient::validateBase($base); } catch (\\RuntimeException $e) { $count++; } } echo $count;"
        self.assertEqual(str(len(bases)), php(source))

    @unittest.skipUnless(PHP.is_file(), 'Registered PHP CLI unavailable')
    def test_real_php_http_request_signs_path_body_and_identity(self):
        seen = []
        secret = 'fixture-secret-not-a-product-credential-0000'

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers['Content-Length']))
                fields = ['POST', self.path, self.headers['X-Dragon-Time'], self.headers['X-Dragon-Nonce'], self.headers['X-Dragon-User'], self.headers['X-Dragon-Roles'], hashlib.sha256(raw).hexdigest()]
                valid = hmac.compare_digest(self.headers['X-Dragon-Signature'], hmac.new(secret.encode(), '\n'.join(fields).encode(), 'sha256').hexdigest())
                seen.append({'valid': valid, 'path': self.path, 'body': raw, 'user': self.headers['X-Dragon-User']})
                payload = json.dumps({'id': 'fixture-job', 'status': 'queued'}).encode()
                self.send_response(202 if valid else 401)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}/dragon/api/v1'
            source = "define('_JEXEC',1); require " + json.dumps(str(API_CLIENT)) + "; $client=new \\Dragonhydra\\Component\\Dragonhydra\\Administrator\\Service\\ApiClient(" + ','.join(map(json.dumps, [base, secret, 'joomla:42', 'admin'])) + "); echo json_encode($client->request('POST','/connections/openfootball/sync',[]));"
            result = json.loads(php(source))
            self.assertEqual('fixture-job', result['id'])
            self.assertEqual(1, len(seen))
            self.assertTrue(seen[0]['valid'])
            self.assertEqual(b'{}', seen[0]['body'])
            self.assertEqual('/dragon/api/v1/connections/openfootball/sync', seen[0]['path'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
