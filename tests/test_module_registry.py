"""Registry contracts, freshness, instance isolation and genuinely passive reads."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
import threading
import time
import tomllib
from types import SimpleNamespace
import unittest
from unittest.mock import patch


AVAILABLE = importlib.util.find_spec('fastapi') is not None
API = '/dragon/api/v1'


@unittest.skipUnless(AVAILABLE, 'Use the existing pinned application runtime')
class ModuleRegistryTests(unittest.TestCase):
    def setUp(self):
        from dragonhydra.product import Product
        from dragonhydra.jobs import Jobs
        self.temp = tempfile.TemporaryDirectory(prefix='dragon-registry-')
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)/'kernel'
        self.product = Product(self.state)
        self.jobs = Jobs(self.product)
        # An observed worker substitute avoids starting a dispatcher in tests.
        self.jobs.thread = SimpleNamespace(is_alive=lambda: True)
        self.at = datetime(2026, 11, 1, 14, 0, tzinfo=timezone.utc)

    def result(self, **kwargs):
        from dragonhydra.module_registry import snapshot
        return snapshot(self.product, self.jobs, at=self.at, process_id=1234, **kwargs)

    def modules(self, result=None):
        return {entry['definition']['module_id']: entry for entry in (result or self.result())['modules']}

    def write_receipt(self, *, seconds_ago=0, ttl=30, pid=1234, url='http://127.0.0.1:18744'):
        observed = self.at-timedelta(seconds=seconds_ago)
        document = {'schema_version': 2, 'observer': 'workstation-supervisor',
                    'service_name': 'DragonhydraWorkstationTest',
                    'api_url': url, 'joomla_url': 'http://127.0.0.1:18740',
                    'observed_at': observed.isoformat(),
                    'evidence_expires_at': (observed+timedelta(seconds=ttl)).isoformat(),
                    'observations': {module_id: {
                        'runtime_state': 'ready', 'reason_code': 'PROBE_OK',
                        'last_success_at': (observed-timedelta(seconds=1)).isoformat(),
                        'reason': 'secret=canary-must-not-be-projected',
                        'sanitized_metrics': {'pid': pid, 'probe_http_status': 200,
                                              'token': 'secret-canary', 'endpoint': 'private-canary'}}
                        for module_id in ('api_server', 'web_server', 'administration', 'website', 'storage_mariadb', 'supervisor')}}
        (self.state.parent/'status.json').write_text(json.dumps(document), encoding='utf-8')
        (self.state/'endpoint.json').write_text(json.dumps({'url': 'http://127.0.0.1:18744', 'pid': 1234}), encoding='utf-8')
        return document

    def test_complete_typed_definitions_and_known_operations(self):
        from dragonhydra.module_registry import DEFINITIONS, RegistryDefinitions
        self.assertEqual(len(DEFINITIONS.modules), 18)
        self.assertEqual(RegistryDefinitions.model_validate(DEFINITIONS.model_dump()), DEFINITIONS)
        modules = self.modules()
        self.assertEqual(set(modules), {'web_server', 'administration', 'website', 'api_server',
            'data_engine', 'odds_engine', 'prediction_engine', 'ai_engine', 'memory_engine',
            'evaluation_engine', 'windows_desktop', 'android_client', 'storage_sqlite',
            'storage_mariadb', 'evidence_store', 'durable_jobs', 'scheduler', 'supervisor'})
        self.assertEqual(self.result()['summary']['core_required'], 3)
        root = Path(__file__).resolve().parents[1]
        for module in DEFINITIONS.modules:
            for reference in module.implementation_reference:
                self.assertTrue((root/reference).exists(), reference)

    def test_definition_validation_rejects_duplicate_unknown_cycle_and_claims(self):
        from dragonhydra.module_registry import DEFINITIONS, RegistryDefinitions
        from pydantic import ValidationError
        baseline = DEFINITIONS.model_dump(mode='json')
        cases = []
        duplicate = json.loads(json.dumps(baseline))
        duplicate['modules'].append(duplicate['modules'][0])
        cases.append(duplicate)
        unknown = json.loads(json.dumps(baseline))
        unknown['modules'][0]['required_dependencies'] = ['missing_engine']
        cases.append(unknown)
        cycle = json.loads(json.dumps(baseline))
        cycle['modules'][0]['required_dependencies'] = ['administration']
        cases.append(cycle)
        config = json.loads(json.dumps(baseline))
        config['modules'][0]['configuration_requirements'][0]['reference'] = 'invented.password'
        cases.append(config)
        operation = json.loads(json.dumps(baseline))
        operation['modules'][3]['supported_operations'][0]['reference'] = 'POST /shell/execute'
        cases.append(operation)
        capability = json.loads(json.dumps(baseline))
        capability['modules'][3]['implemented_capabilities'].append('roadmap autonomous provider intelligence')
        cases.append(capability)
        unsupported_binding = json.loads(json.dumps(baseline))
        unsupported_binding['modules'][3]['implemented_capabilities'].append('frequency')
        cases.append(unsupported_binding)
        for case in cases:
            with self.subTest(case=cases.index(case)), self.assertRaises(ValidationError):
                RegistryDefinitions.model_validate(case)

    def test_declared_versions_and_console_references_match_canonical_owners(self):
        import xml.etree.ElementTree as ET
        from dragonhydra.module_registry import DEFINITIONS, OPERATIONS
        from dragonhydra.cognition import evaluation, memory, models
        from dragonhydra import market_signals
        root = Path(__file__).resolve().parents[1]
        definitions = {item.module_id: item for item in DEFINITIONS.modules}
        for name, module in (('evaluation_engine', evaluation), ('memory_engine', memory),
                             ('prediction_engine', models), ('odds_engine', market_signals)):
            self.assertEqual(definitions[name].actual_build_or_module_version, module.VERSION)
        self.assertEqual(set(definitions['prediction_engine'].implemented_capabilities), set(models.NAMES)|{'ensemble'})
        component_version = ET.parse(root/'server/joomla/com_dragonhydra/dragonhydra.xml').getroot().findtext('version')
        self.assertEqual(definitions['administration'].actual_build_or_module_version, component_version)
        self.assertEqual(definitions['website'].actual_build_or_module_version, component_version)
        android = next(line.split(':', 1)[1].strip() for line in
            (root/'android/dragonhydra_mobile/pubspec.yaml').read_text().splitlines() if line.startswith('version:'))
        self.assertEqual(definitions['android_client'].actual_build_or_module_version, android)
        desktop = json.loads((root/'client/desktop/src-tauri/tauri.conf.json').read_text())['version']
        self.assertEqual(definitions['windows_desktop'].actual_build_or_module_version, desktop)
        entries = tomllib.loads((root/'pyproject.toml').read_text())['project']['scripts']
        for operation in OPERATIONS.values():
            if operation.kind == 'cli':
                self.assertIn(operation.reference.split()[0], entries)

    def test_internal_readiness_does_not_claim_external_or_model_health(self):
        modules, result = self.modules(), self.result()
        self.assertEqual(result['core_state'], 'ready')
        self.assertEqual(modules['storage_sqlite']['observation']['runtime_state'], 'ready')
        self.assertEqual(modules['durable_jobs']['observation']['runtime_state'], 'ready')
        self.assertEqual(modules['memory_engine']['observation']['runtime_state'], 'installed_not_configured')
        self.assertEqual(modules['scheduler']['observation']['runtime_state'], 'not_applicable')
        for key in ('web_server', 'administration', 'website', 'storage_mariadb', 'supervisor', 'windows_desktop', 'android_client', 'prediction_engine', 'odds_engine'):
            self.assertEqual(modules[key]['observation']['runtime_state'], 'configured_unverified', key)
        self.assertTrue(result['read_only'])
        self.assertFalse(result['network_probes'])

    def test_current_bound_heartbeat_can_observe_external_services(self):
        self.write_receipt()
        modules = self.modules()
        for key in ('web_server', 'administration', 'website', 'storage_mariadb', 'supervisor'):
            self.assertEqual(modules[key]['observation']['runtime_state'], 'ready', key)
            self.assertEqual(modules[key]['observation']['last_success_at'], '2026-11-01T13:59:59.000000Z')
        self.assertEqual(modules['supervisor']['observation']['sanitized_metrics']['service_name'], 'DragonhydraWorkstationTest')
        for key, module in modules.items():
            if key != 'supervisor':
                self.assertNotIn('service_name', module['observation']['sanitized_metrics'])
        encoded = json.dumps(self.result())
        self.assertNotIn('canary', encoded)
        self.assertNotIn(str(self.state), encoded)
        self.assertNotIn('18744', encoded)
        self.assertIn('not administrator authentication', modules['administration']['definition']['description'])

    def test_service_identity_is_allowlisted_and_only_projected_on_supervisor(self):
        from dragonhydra.module_registry import Observation
        from pydantic import ValidationError
        for name in ('DragonhydraInvalid;secret=private-canary', 'C:/private-canary', 1234):
            document = self.write_receipt()
            document['service_name'] = name
            (self.state.parent/'status.json').write_text(json.dumps(document), encoding='utf-8')
            result = self.result()
            self.assertNotIn('service_name', self.modules(result)['supervisor']['observation']['sanitized_metrics'])
            self.assertNotIn('private-canary', json.dumps(result))
        self.write_receipt()
        for module_id, value in (('supervisor', 'DragonhydraInvalid;command'), ('supervisor', 1234),
                                 ('api_server', 'DragonhydraWorkstationTest')):
            observation = self.modules()['supervisor']['observation']
            observation['module_id'] = module_id
            observation['sanitized_metrics']['service_name'] = value
            with self.assertRaises(ValidationError):
                Observation.model_validate(observation)

    def test_supervisor_ready_requires_a_real_fresh_success_clock(self):
        for missing, value in ((True, None), (False, None),
                               (False, (self.at+timedelta(seconds=1)).isoformat()),
                               (False, (self.at-timedelta(seconds=91)).isoformat())):
            with self.subTest(missing=missing, value=value):
                document = self.write_receipt()
                if missing:
                    document['observations']['web_server'].pop('last_success_at')
                else:
                    document['observations']['web_server']['last_success_at'] = value
                (self.state.parent/'status.json').write_text(json.dumps(document), encoding='utf-8')
                observation = self.modules()['web_server']['observation']
                self.assertEqual(observation['runtime_state'], 'configured_unverified')
                self.assertIsNone(observation['last_success_at'])

    def test_stale_evidence_never_remains_ready(self):
        self.write_receipt(seconds_ago=31)
        for key in ('web_server', 'administration', 'website', 'storage_mariadb', 'supervisor'):
            observation = self.modules()[key]['observation']
            self.assertEqual(observation['runtime_state'], 'configured_unverified')
            self.assertEqual(observation['reason_code'], 'EVIDENCE_EXPIRED')
            self.assertLess(datetime.fromisoformat(observation['evidence_expires_at'].replace('Z', '+00:00')), self.at)
        self.assertEqual(self.result()['core_state'], 'ready')

    def test_other_kernel_pid_endpoint_and_long_or_future_heartbeat_rejected(self):
        for arguments in ({'pid': 4321}, {'url': 'http://127.0.0.1:18743'},
                          {'ttl': 3600}, {'seconds_ago': -20}):
            with self.subTest(arguments=arguments):
                self.write_receipt(**arguments)
                self.assertNotEqual(self.modules()['web_server']['observation']['runtime_state'], 'ready')
        document = self.write_receipt()
        document['observer'] = 'arbitrary-source-document'
        (self.state.parent/'status.json').write_text(json.dumps(document))
        self.assertEqual(self.modules()['web_server']['observation']['reason_code'], 'SUPERVISOR_UNVERIFIED')

    def test_bad_or_oversized_heartbeat_is_safely_unverified(self):
        for raw in ('{"password":"secret-canary"', 'x'*65537):
            (self.state.parent/'status.json').write_text(raw)
            encoded = json.dumps(self.result())
            self.assertNotIn('secret-canary', encoded)
            self.assertEqual(self.modules()['supervisor']['observation']['reason_code'], 'SUPERVISOR_EVIDENCE_INVALID')

    def test_status_reads_never_initialize_memory_or_write_domain_state(self):
        def state_snapshot():
            with closing(sqlite3.connect(self.product.db_path)) as db:
                tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
                return {name: db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for (name,) in tables}
        before = state_snapshot()
        before_files = {str(path.relative_to(self.state)) for path in self.state.rglob('*')}
        with patch('dragonhydra.cognition.memory.as_of', side_effect=AssertionError('schema-creating API used')), \
             patch('socket.create_connection', side_effect=AssertionError('network probe used')), \
             patch.object(self.jobs, 'submit', side_effect=AssertionError('job write used')), \
             patch.object(self.jobs.providers, 'schedule_due', side_effect=AssertionError('schedule dispatched')):
            self.result()
            self.result()
        self.assertEqual(state_snapshot(), before)
        self.assertNotIn('cognitive_records', before)
        self.assertEqual({str(path.relative_to(self.state)) for path in self.state.rglob('*')}, before_files)

    def test_optional_ai_absent_or_invalid_does_not_degrade_core(self):
        with patch.dict('os.environ', {'DRAGONHYDRA_LOCAL_AI_URL': '', 'DRAGONHYDRA_LOCAL_AI_KEY': ''}):
            self.assertEqual(self.modules()['ai_engine']['observation']['runtime_state'], 'installed_not_configured')
            (self.state/'local-ai.json').write_text('{"secret":"secret-canary"}')
            result = self.result()
            self.assertEqual(self.modules(result)['ai_engine']['observation']['runtime_state'], 'unavailable')
            self.assertEqual(result['core_state'], 'ready')
            self.assertNotIn('secret-canary', json.dumps(result))

    def test_failed_store_and_worker_are_honest_and_raw_error_is_private(self):
        self.jobs.thread = None
        self.assertEqual(self.modules()['durable_jobs']['observation']['runtime_state'], 'unavailable')
        with patch('dragonhydra.module_registry.sqlite3.connect', side_effect=sqlite3.OperationalError('C:/private/secret-canary')):
            result = self.result()
        self.assertEqual(self.modules(result)['storage_sqlite']['observation']['runtime_state'], 'unavailable')
        self.assertNotEqual(result['core_state'], 'ready')
        self.assertNotIn('secret-canary', json.dumps(result))

    def test_administrator_operations_are_not_available_to_reader(self):
        for role, expected in (('reader', False), ('admin', True)):
            result = self.result(role=role)
            operations = {operation['operation_id']: operation for entry in result['modules'] for operation in entry['operations']}
            self.assertEqual(operations['create_forecast']['available'], expected)
            self.assertTrue(operations['read_matches']['available'])
            self.assertFalse(operations['internal_supervisor']['available'])


@unittest.skipUnless(AVAILABLE, 'Use the existing pinned application runtime')
class ModuleRegistryAPITests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        self.temp = tempfile.TemporaryDirectory(prefix='dragon-registry-api-')
        self.addCleanup(self.temp.cleanup)
        self.app = create_app(Path(self.temp.name), local_token='isolated-registry-token',
                              bridge_secret='isolated-registry-bridge', start_worker=False)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def signed(self, method, path, body=b'', role='reader'):
        stamp, nonce = str(int(time.time())), secrets.token_hex(16)
        user = 'joomla:registry-test'
        value = '\n'.join((method, path, stamp, nonce, user, role, hashlib.sha256(body).hexdigest()))
        return {'X-Dragon-User': user, 'X-Dragon-Roles': role, 'X-Dragon-Time': stamp,
                'X-Dragon-Nonce': nonce, 'X-Dragon-Signature': hmac.new(b'isolated-registry-bridge', value.encode(), hashlib.sha256).hexdigest()}

    def test_anonymous_denied_and_signed_reader_allowed_without_job_writes(self):
        path = API+'/system/modules'
        self.assertEqual(self.client.get(path).status_code, 401)
        with closing(self.app.state.product.connect()) as db:
            before_jobs = db.execute('SELECT COUNT(*) FROM product_jobs').fetchone()[0]
        result = self.client.get(path, headers=self.signed('GET', path))
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['summary']['total_modules'], 18)
        with closing(self.app.state.product.connect()) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM product_jobs').fetchone()[0], before_jobs)
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='cognitive_records'").fetchone())
        self.assertEqual(result.headers['cache-control'], 'no-store')

    def test_every_declared_http_operation_exists_in_actual_api_schema(self):
        from dragonhydra.module_registry import OPERATIONS
        paths = self.app.openapi()['paths']
        for operation in OPERATIONS.values():
            if operation.kind == 'http':
                method, path = operation.reference.split(' ', 1)
                self.assertIn(path, paths, operation.operation_id)
                self.assertIn(method.lower(), paths[path], operation.operation_id)

    def test_workflow_permissions_empty_body_and_idempotent_job_contract(self):
        from dragonhydra import public_results
        product = self.app.state.product
        with closing(product.connect()) as db:
            public_results.ingest_bytes(db, json.dumps({'name': 'Isolated 2026/27', 'matches': [
                {'date': '2090-01-01', 'team1': 'One', 'team2': 'Two'}]}).encode(),
                source_id='registry-api-fixture', source_url='https://example.test/fixtures')
        match_id = product.matches()['items'][0]['id']
        path = API+'/matches/'+match_id+'/cognition-history'
        response = self.client.get(path, headers=self.signed('GET', path))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['counts']['predictions'], 0)
        for suffix in ('forecasts', 'evaluations'):
            path = API+'/matches/'+match_id+'/'+suffix
            reader = self.client.post(path, content=b'{}', headers={**self.signed('POST', path, b'{}'), 'Content-Type': 'application/json'})
            self.assertEqual(reader.status_code, 403)
            self.client.headers['Authorization'] = 'Bearer isolated-registry-token'
            self.assertEqual(self.client.post(path, json={'secret': 'not-allowed'}).status_code, 422)
            first = self.client.post(path, json={}, headers={'Idempotency-Key': 'isolated-'+suffix})
            second = self.client.post(path, json={}, headers={'Idempotency-Key': 'isolated-'+suffix})
            self.assertEqual(first.status_code, 202, first.text)
            self.assertEqual(first.json()['id'], second.json()['id'])
            self.assertEqual(first.json()['owner'], 'local:owner')
            self.client.headers.clear()
        with closing(product.connect()) as db:
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='cognitive_records'").fetchone())


if __name__ == '__main__':
    unittest.main()
