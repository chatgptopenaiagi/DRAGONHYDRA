"""Public-boundary contract tests using a fixed local mock upstream.

No production credentials or services are used. Every signed request is checked
against the exact outgoing URL and body, so URL rewriting cannot hide drift.
"""
from contextlib import contextmanager
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = Path(__file__).resolve().parents[1] / 'reverse-proxy' / 'gateway.py'
spec = importlib.util.spec_from_file_location('dragon_public_gateway_review', MODULE_PATH)
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)
API = '/dragon/api/v1'
ID = 'a' * 64
PUBLIC = 'https://verified-test.trycloudflare.com'
REAL_ASYNC_CLIENT = httpx.AsyncClient


class GatewayTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'state' / 'tests').mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'state' / 'tests', prefix='gateway-test-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.endpoint = self.directory / 'endpoint.json'
        self.secret = self.directory / 'bridge.json'
        self.config = self.directory / 'gateway.json'
        self.endpoint.write_text(json.dumps({'url': 'http://127.0.0.1:19002'}), encoding='utf-8')
        self.secret.write_text(json.dumps({'secret': 'gateway-test-secret-only'}), encoding='utf-8')
        self.config.write_text(json.dumps({'joomla_origin': 'http://127.0.0.1:19001',
            'api_endpoint_file': str(self.endpoint), 'bridge_secret_file': str(self.secret),
            'vps_public_ips': ['192.0.2.20']}), encoding='utf-8')
        self.app = gateway.create_gateway(self.config)
        self.client = TestClient(self.app, base_url=PUBLIC, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.forwarded = []

    def upstream(self, request):
        self.forwarded.append(request)
        if request.url.port == 19001:
            return httpx.Response(200, text='<html><body><h1>Actual Joomla shape</h1><link rel="stylesheet" href="http://127.0.0.1:19001/media/system/site.css"></body></html>',
                headers={'Content-Type': 'text/html', 'Set-Cookie': 'private_joomla_session=must-not-escape; HttpOnly'})
        return httpx.Response(200, json={'items': [{'id': ID, 'name': 'Retained match'}], 'total': 1})

    @contextmanager
    def transport(self, handler=None):
        transport = httpx.MockTransport(handler or self.upstream)
        with patch.object(gateway.httpx, 'AsyncClient', side_effect=lambda **kw: REAL_ASYNC_CLIENT(transport=transport, **kw)):
            yield

    def test_write_and_preflight_methods_are_denied_without_upstream(self):
        with self.transport():
            for method in ('POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'TRACE'):
                response = self.client.request(method, API + '/matches')
                self.assertEqual(response.status_code, 403, method)
                self.assertEqual(response.json()['error']['code'], 'PUBLIC_ROUTE_DENIED')
        self.assertFalse(self.forwarded)

    def test_private_routes_and_encoded_path_bypasses_are_denied(self):
        paths = ['/administrator', '/administrator/index.php', '/phpmyadmin', '/configuration.php', '/installation',
                 '/.git/config', '/.env', '/vault', '/logs', '/cache', API + '/jobs', API + '/connections',
                 API + '/session', API + '/openapi.json', API + '/updates', API + '/exports', '/api/index.php',
                 '/%61dministrator/', '/%2e%2e/configuration.php', '/%252e%252e/configuration.php',
                 '/media/system/%2e%2e/%2e%2e/configuration.php', '/media/system/a\\configuration.php']
        with self.transport():
            for path in paths:
                response = self.client.get(path)
                self.assertEqual(response.status_code, 403, path)
        self.assertFalse(self.forwarded)

    def test_joomla_query_bypasses_and_duplicate_parameters_are_denied(self):
        paths = ['/?option=com_users', '/index.php?option=com_config', '/index.php?task=users.login',
                 '/index.php?option=com_content&view=article&view=featured',
                 '/index.php?%6fption=com_users', '/index.php?option=&view=article',
                 '/index.php?option=com_content&view=article&format=raw',
                 '/index.php?option=com_content&view=article&id=1%2f..%2fadministrator',
                 API + '/matches?url=http://evil.test', API + '/matches?limit=51',
                 API + '/matches?offset=-1', API + '/matches?limit=1&limit=2']
        with self.transport():
            for path in paths:
                self.assertEqual(self.client.get(path).status_code, 403, path)
        self.assertFalse(self.forwarded)

    def test_host_boundary_and_origin_are_not_reflected_as_credentials(self):
        original=json.loads(self.config.read_text())
        for origin in ('http://127.0.0.1:19001/administrator','http://user:password@127.0.0.1:19001',
                       'http://127.0.0.1:19001?route=administrator','http://127.0.0.1:19001#private'):
            self.config.write_text(json.dumps({**original,'joomla_origin':origin}))
            with self.assertRaises(ValueError):
                gateway.create_gateway(self.config)
        self.config.write_text(json.dumps(original))
        with self.transport():
            for host in ('evil.test', 'trycloudflare.com.evil.test', 'a.trycloudflare.com.evil.test', 'evil.test@localhost'):
                self.assertEqual(self.client.get('/', headers={'Host': host}).status_code, 403, host)
            response = self.client.get('/', headers={'Host': '192.0.2.20', 'Origin': 'https://evil.test',
                'Cookie': 'admin=1', 'Authorization': 'Bearer visitor-secret'})
            self.assertEqual(response.status_code, 200)
        self.assertNotIn('access-control-allow-origin', response.headers)
        self.assertNotIn('cookie', self.forwarded[-1].headers)
        self.assertNotIn('authorization', self.forwarded[-1].headers)

    def test_joomla_frontend_and_assets_use_only_fixed_upstream(self):
        with self.transport():
            for path in ('/', '/index.php?option=com_content&view=article&id=1', '/media/system/site.css?v=123',
                         '/media/system/js/core.min.js?017f13',
                         '/media/templates/site/cassiopeia/css/vendor/joomla-custom-elements/joomla-alert.min.css?0.4.1'):
                response = self.client.get(path, headers={'Cookie': 'admin=true', 'Authorization': 'Bearer do-not-forward'})
                self.assertEqual(response.status_code, 200, path)
                self.assertNotIn('set-cookie', response.headers)
            self.assertIn('/sports', self.client.get('/').text)
        for req in self.forwarded:
            self.assertEqual(req.url.host, '127.0.0.1')
            self.assertEqual(req.url.port, 19001)
            self.assertNotIn('authorization', req.headers)
            self.assertNotIn('cookie', req.headers)

    def test_read_routes_have_valid_reader_hmac_for_exact_outgoing_url(self):
        paths = [API + '/matches?limit=24&offset=0&search=', API + '/matches?search=Manchester%20United',
                 API + '/matches?timezone=Europe%2FBerlin', API + '/teams/' + ID,
                 API + '/competitions/' + ID + '/standings', API + '/matches/' + ID + '/predictions']

        def verify(request):
            self.forwarded.append(request)
            headers = request.headers
            self.assertEqual(headers['x-dragon-roles'], 'reader')
            self.assertEqual(headers['x-dragon-user'], 'joomla:public-gateway')
            signed = '\n'.join((request.method, request.url.raw_path.decode('ascii'), headers['x-dragon-time'],
                headers['x-dragon-nonce'], headers['x-dragon-user'], headers['x-dragon-roles'], hashlib.sha256(request.content).hexdigest()))
            expected = hmac.new(b'gateway-test-secret-only', signed.encode(), hashlib.sha256).hexdigest()
            valid = hmac.compare_digest(expected, headers['x-dragon-signature'])
            return httpx.Response(200 if valid else 401, json={'items': [], 'valid_hmac': valid})

        with self.transport(verify):
            for path in paths:
                response = self.client.get(path, headers={'Cookie': 'session=private', 'Authorization': 'Bearer private'})
                self.assertEqual(response.status_code, 200, path)
                self.assertTrue(response.json()['valid_hmac'])
        self.assertTrue(all('cookie' not in r.headers and 'authorization' not in r.headers for r in self.forwarded))

    def test_api_response_sanitizes_credentials_and_sensitive_source_url_parts(self):
        def handler(request):
            return httpx.Response(200, json={'items': [{'id': ID, 'source_url': 'https://user:password@example.test/data?event=1&api_key=secret&token=private#fragment',
                'credential_ref': 'private-reference', 'password': 'never-public', 'nested': {'access_token': 'private', 'score': 2}}]})
        with self.transport(handler):
            response = self.client.get(API + '/matches')
        row = response.json()['items'][0]
        self.assertEqual(row['source_url'], 'https://example.test/data?event=1')
        self.assertNotIn('credential_ref', row)
        self.assertNotIn('password', row)
        self.assertEqual(row['nested'], {'score': 2})

    def test_upstream_connection_errors_return_friendly_bounded_errors(self):
        def broken(request):
            raise httpx.ConnectError('password=must-not-leak', request=request)
        with self.transport(broken):
            for path in ('/', API + '/matches'):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 503)
                self.assertNotIn('must-not-leak', response.text)
        self.assertEqual(response.json()['error']['code'], 'PUBLIC_SOURCE_UNAVAILABLE')

    def test_joomla_upstream_server_errors_are_replaced_with_friendly_page(self):
        with self.transport(lambda request: httpx.Response(500, text='<html><body>SQL password=must-not-leak</body></html>', headers={'Content-Type': 'text/html'})):
            response = self.client.get('/')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('must-not-leak', response.text)

    def test_upstream_redirects_cannot_escape_to_admin_or_another_origin(self):
        for location in ('https://evil.test/', '//evil.test/', 'http://127.0.0.1:19001/administrator/', '/index.php?option=com_users', '/configuration.php'):
            with self.transport(lambda request: httpx.Response(302, headers={'Location': location})):
                response = self.client.get('/', follow_redirects=False)
            self.assertEqual(response.status_code, 403, location)
        with self.transport(lambda request: httpx.Response(302, headers={'Location': 'http://127.0.0.1:19001/index.php?option=com_content&view=article&id=1'})):
            response = self.client.get('/', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['location'].startswith(PUBLIC + '/index.php?'))

    def test_api_endpoint_metadata_cannot_redirect_proxy_to_external_server(self):
        self.endpoint.write_text(json.dumps({'url': 'https://evil.test'}), encoding='utf-8')
        with self.transport():
            response = self.client.get(API + '/matches')
        self.assertEqual(response.status_code, 503)
        self.assertFalse(self.forwarded)

    def test_public_shell_health_and_static_assets_need_no_private_upstream(self):
        with self.transport():
            for path in ('/public-health', '/sports', '/sports/matches/' + ID, '/public-assets/site.js', '/public-assets/site.css'):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, path)
        self.assertFalse(self.forwarded)

    def test_cache_prevents_repeated_provider_work_and_rate_limit_is_bounded(self):
        with self.transport():
            self.assertEqual(self.client.get(API + '/matches').status_code, 200)
            self.assertEqual(self.client.get(API + '/matches').status_code, 200)
            self.assertEqual(len(self.forwarded), 1)
            for _ in range(178):
                self.assertEqual(self.client.get('/public-health').status_code, 200)
            limited = self.client.get('/public-health')
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.headers['retry-after'], '60')


if __name__ == '__main__':
    unittest.main()
