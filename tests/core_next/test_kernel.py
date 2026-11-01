from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dragonhydra.kernel import KernelConfig, ModuleDefinition
from dragonhydra.kernel.contracts import STATES
from dragonhydra.kernel.registry import ModuleRegistry

LAB = Path(r'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB')


class Probe:
    contract_version = 'core-next.engine/1'
    def __init__(self, state='READY'):
        self.calls, self.stops, self.state = 0, 0, state

    def observe(self):
        self.calls += 1
        return {'state': self.state, 'reason': 'EXPLICIT_TEST_PROBE', 'metrics': {'calls': self.calls}}

    def stop(self):
        self.stops += 1


class RegistryTests(unittest.TestCase):
    def test_dependency_validation_duplicate_unknown_cycle_and_adapter_binding(self):
        a = ModuleDefinition('a', 'A', 'Test', 'Test')
        b = ModuleDefinition('b', 'B', 'Test', 'Test', ('a',))
        with self.assertRaisesRegex(ValueError, 'DUPLICATE'):
            ModuleRegistry((a, a), {'a': Probe()})
        with self.assertRaisesRegex(ValueError, 'UNKNOWN_MODULE_DEPENDENCY'):
            ModuleRegistry((b,), {'b': Probe()})
        with self.assertRaisesRegex(ValueError, 'CYCLE'):
            ModuleRegistry((replace(a, dependencies=('b',)), b), {'a': Probe(), 'b': Probe()})
        with self.assertRaisesRegex(ValueError, 'BINDING'):
            ModuleRegistry((a,), {})

    def test_lifecycle_expiry_dependency_states_and_pure_status_reads(self):
        at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        clock = [at]
        a, b = Probe(), Probe()
        registry = ModuleRegistry((ModuleDefinition('a', 'A', 'Test', 'Test'),
            ModuleDefinition('b', 'B', 'Test', 'Test', ('a',))), {'a': a, 'b': b},
            ttl_seconds=5, clock=lambda: clock[0], installation_id='test-install')
        self.assertEqual(registry.item('a')['state'], 'UNVERIFIED')
        registry.start(); registry.start()
        self.assertEqual((a.calls, b.calls), (1, 1))
        self.assertEqual(registry.item('b')['state'], 'READY')
        registry.record('a', 'UNAVAILABLE', 'DEVICE_UNAVAILABLE')
        self.assertEqual(registry.item('b')['state'], 'DEGRADED')
        for _ in range(3):
            registry.items()
        self.assertEqual((a.calls, b.calls), (1, 1))
        clock[0] += timedelta(seconds=5)
        self.assertEqual(registry.item('b')['state'], 'EXPIRED')
        self.assertEqual(registry.item('b')['observation']['installation_id'], 'test-install')
        self.assertIsNotNone(registry.item('b')['last_success'])
        registry.stop()
        self.assertEqual(registry.item('a')['state'], 'STOPPED')
        self.assertEqual((a.stops, b.stops), (1, 1))

    def test_operation_evidence_does_not_renew_old_counter_evidence(self):
        at = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
        r = ModuleRegistry((ModuleDefinition('a', 'A', 'Test', 'Test'),), {'a': Probe()},
                           ttl_seconds=5, clock=lambda: at[0])
        r.start()
        sampled = r.item('a')['observation']['metrics_sampled_at']
        at[0] += timedelta(seconds=6)
        r.record_operation('a', 'read', 'READY', 'EXPLICIT_READ_COMPLETED')
        item = r.item('a')
        self.assertEqual(item['state'], 'READY')
        self.assertEqual(item['observation']['metrics_sampled_at'], sampled)
        self.assertEqual(item['observation']['metrics_state'], 'EXPIRED')
        self.assertEqual(item['observation']['last_operation']['operation'], 'read')

    def test_required_state_vocabulary_is_not_collapsed(self):
        self.assertTrue({'NOT_IMPLEMENTED', 'NOT_CONFIGURED', 'UNVERIFIED', 'READY', 'DEGRADED',
                         'UNAVAILABLE', 'NOT_APPLICABLE'} <= STATES)
        probe = Probe('NOT_APPLICABLE')
        r = ModuleRegistry((ModuleDefinition('a', 'A', 'Test', 'Test'),), {'a': probe})
        r.start()
        self.assertEqual(r.item('a')['state'], 'NOT_APPLICABLE')
        probe.state = 'INVALID'
        r.refresh('a')
        self.assertEqual(r.item('a')['state'], 'DEGRADED')

    def test_missing_optional_dependency_limits_its_capability_without_blocking_other_engines(self):
        class OptionalProbe(Probe):
            def read(self):
                return []
            def export(self):
                return []
        definition = ModuleDefinition('a', 'A', 'Test', 'Test', optional_dependencies=('missing',),
            capabilities=('read', 'optional_export'), supported_operations=('read', 'export'),
            capability_operations=(('read', ('read',)), ('optional_export', ('export',))),
            capability_dependencies=(('optional_export', ('missing',)),))
        unrelated = ModuleDefinition('b', 'B', 'Test', 'Test')
        r = ModuleRegistry((definition, unrelated), {'a': OptionalProbe(), 'b': Probe()})
        r.start()
        self.assertEqual(r.item('a')['state'], 'READY')
        self.assertEqual(r.item('b')['state'], 'READY')
        caps = {x['id']: x for x in r.item('a')['capability_status']}
        self.assertTrue(caps['read']['available'])
        self.assertFalse(caps['optional_export']['available'])
        self.assertEqual(r.item('a')['optional_dependency_status'][0]['state'], 'NOT_IMPLEMENTED')

    def test_schema_engine_contract_and_unsupported_capability_declarations_are_rejected(self):
        base = ModuleDefinition('a', 'A', 'Test', 'Test')
        with self.assertRaisesRegex(ValueError, 'SCHEMA_VERSION_MISMATCH'):
            ModuleRegistry((replace(base, schema_version='other/2'),), {'a': Probe()})
        with self.assertRaisesRegex(ValueError, 'CONTRACT_VERSION_MISMATCH'):
            ModuleRegistry((base,), {'a': object()})
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED_MODULE_CAPABILITY_OPERATION'):
            ModuleRegistry((replace(base, capabilities=('invented',),
                capability_operations=(('invented', ('does_not_exist',)),)),), {'a': Probe()})


class IndependentPortTests(unittest.TestCase):
    def test_engines_execute_against_declared_ports_without_product_or_kernel(self):
        from dragonhydra.kernel.ports import ApplicationContext, StoragePort, MemoryPort
        from dragonhydra.kernel.engines import OddsEngine, MemoryEngine, PredictionEngine
        def forbidden(*args, **kwargs):
            raise AssertionError('Unrequested concrete storage/model operation')
        storage = StoragePort(LAB, LAB/'unused.sqlite3', LAB, LAB, forbidden)
        context = ApplicationContext(storage, object(), lambda: '2026-01-20T12:00:00Z')
        class Data:
            def find(self, match_id):
                return {'outcome': 'home'}
        class Models:
            forecast = staticmethod(forbidden)
        memory_port = MemoryPort(forbidden, forbidden, forbidden, forbidden)
        prediction = PredictionEngine(context, Data(), Models(), memory_port)
        self.assertFalse(prediction.predictions('finished')['available'])
        calls = []
        odds = OddsEngine(context, Data(), lambda rows, at, **kw: calls.append((rows, at, kw)) or {'accepted': True}, forbidden)
        self.assertTrue(odds.signals([], 'cutoff', max_age_seconds=5)['accepted'])
        self.assertEqual(calls, [([], 'cutoff', {'max_age_seconds': 5})])
        class Backend:
            @staticmethod
            def as_of(path, cutoff):
                return {'bound_path': path.name, 'cutoff': cutoff}
        self.assertEqual(MemoryEngine(context, Backend()).view('cutoff'),
                         {'bound_path': 'unused.sqlite3', 'cutoff': 'cutoff'})


class ComposedAPITests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        self.temp = tempfile.TemporaryDirectory(dir=LAB, prefix='kernel-test-')
        self.addCleanup(self.temp.cleanup)
        self.app = create_app(Path(self.temp.name), local_token='core-next-test-token-123456789',
            bridge_secret='core-next-test-only-bridge-secret', start_worker=False,
            kernel_config=KernelConfig('core-next-test-install', environment_id='candidate'))
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.client.headers['Authorization'] = 'Bearer core-next-test-token-123456789'
        self.p = self.app.state.product

    def snapshot(self):
        with closing(self.p.connect()) as db:
            return list(db.iterdump())

    def test_status_authentication_schema_no_engine_calls_and_no_state_writes(self):
        self.client.headers.clear()
        self.assertEqual(self.client.get('/dragon/api/v1/modules').status_code, 401)
        self.client.headers['Authorization'] = 'Bearer core-next-test-token-123456789'
        before = self.snapshot()
        with patch.object(self.p.kernel.registry, 'refresh', side_effect=AssertionError('Status must not probe')):
            listing = self.client.get('/dragon/api/v1/modules').json()
            detail = self.client.get('/dragon/api/v1/modules/ai').json()
            self.assertEqual(self.client.get('/dragon/api/v1/modules/missing').status_code, 404)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(detail['state'], 'NOT_CONFIGURED')
        self.assertEqual(listing['installation']['installation_id'], 'core-next-test-install')
        for item in listing['items']:
            for key in ('required_dependencies', 'optional_dependencies', 'configuration_requirements',
                        'supported_operations', 'data_domains', 'verification_references',
                        'observed_at', 'expires_at', 'last_success', 'observation'):
                self.assertIn(key, item)
        system = self.client.get('/dragon/api/v1/system').json()
        self.assertEqual(system['backend'], 'sqlite')
        self.assertEqual(system['installation'], listing['installation'])

    def test_canonical_schema_separates_bound_implementation_configuration_and_runtime_evidence(self):
        detail = self.client.get('/dragon/api/v1/modules/ai').json()
        self.assertEqual(detail['module_id'], 'ai')
        self.assertEqual(detail['display_name'], detail['name'])
        self.assertEqual(detail['actual_version_or_build'], detail['version'])
        self.assertEqual(detail['implementation_state'], 'BOUND')
        self.assertEqual(detail['configuration_state'], 'NOT_CONFIGURED')
        self.assertEqual(detail['runtime_state'], 'UNVERIFIED')
        for key in ('reason_code', 'human_readable_reason', 'last_success_at', 'evidence_expires_at',
                    'sanitized_metrics', 'evidence_reference', 'implementation_state',
                    'configuration_state', 'runtime_state'):
            self.assertIn(key, detail)
            self.assertEqual(detail[key], detail['observation'][key])
        for key in ('kind', 'responsibility', 'implemented_capabilities'):
            self.assertIn(key, detail)

    @unittest.skipUnless(os.name == 'nt', 'Existing Windows DPAPI stored-key configuration')
    def test_owner_ai_configuration_refreshes_cached_status_without_model_inference(self):
        from dragonhydra import local_ai
        from dragonhydra.local_ai_settings import URL_ENV, KEY_ENV
        with patch.dict(os.environ, {URL_ENV: '', KEY_ENV: ''}), \
             patch.object(local_ai, 'infer', side_effect=AssertionError('Configuration must not infer')) as infer:
            response = self.client.put('/dragon/api/v1/local-model/configuration', json={
                'endpoint': 'http://127.0.0.1:18990', 'credential': 'core-next-fixture-key-1234567890'})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()['configured'])
            detail = self.client.get('/dragon/api/v1/modules/ai').json()
            self.assertEqual(detail['configuration_state'], 'CONFIGURED')
            self.assertEqual(detail['runtime_state'], 'UNVERIFIED')
            self.assertTrue(detail['observation']['metrics']['configured'])
            response = self.client.put('/dragon/api/v1/local-model/configuration', json={
                'endpoint': '', 'remove_credential': True})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()['configured'])
            detail = self.client.get('/dragon/api/v1/modules/ai').json()
            self.assertEqual(detail['configuration_state'], 'NOT_CONFIGURED')
            self.assertEqual(detail['runtime_state'], 'UNVERIFIED')
            infer.assert_not_called()

    def test_unique_cookie_old_cookie_ignored_logout_revoke_only_own_installation(self):
        self.client.headers.clear()
        old_cookie = 'old-origin-cookie-should-stay'
        self.client.cookies.set('dragon_session', old_cookie)
        # Even a matching token hash in this database does not authorize the old cookie name.
        with closing(self.p.connect()) as db:
            db.execute('INSERT INTO product_sessions VALUES(?,?,?,?)',
                (hashlib.sha256(old_cookie.encode()).hexdigest(), 'local:owner', '["admin"]', 9999999999))
            db.commit()
        self.assertEqual(self.client.get('/dragon/api/v1/modules').status_code, 401)
        response = self.client.post('/dragon/api/v1/session', json={'token': 'core-next-test-token-123456789'})
        self.assertEqual(response.status_code, 200)
        name = self.app.state.session_cookie_name
        self.assertNotEqual(name, 'dragon_session')
        self.assertIn(name+'=', response.headers['set-cookie'])
        self.assertEqual(self.client.get('/dragon/api/v1/modules').status_code, 200)
        token = self.client.cookies.get(name)
        blocked = self.client.post('/dragon/api/v1/session/logout', headers={'Origin': 'https://other.test'})
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(self.client.post('/dragon/api/v1/session/logout').status_code, 200)
        self.assertEqual(self.client.cookies.get('dragon_session'), old_cookie)
        self.assertEqual(self.client.get('/dragon/api/v1/modules').status_code, 401)
        self.client.cookies.set(name, token)
        self.assertEqual(self.client.get('/dragon/api/v1/modules').status_code, 401)

    def test_real_data_api_uses_injected_engine_and_disabled_dependency_does_not_fallback(self):
        engine = self.p.kernel.engines['data']
        with patch.object(engine, 'matches', return_value={'items': [], 'total': 0, 'limit': 50,
                          'offset': 0, 'as_of': 'test', 'timestamp_semantics': 'test'}) as called:
            self.assertEqual(self.client.get('/dragon/api/v1/matches').status_code, 200)
            called.assert_called_once()
        self.p.kernel.registry.disabled = frozenset({'data'})
        with self.assertRaisesRegex(ValueError, 'DEPENDENCY_DISABLED'):
            self.p.kernel.execute('prediction', 'predictions', 'absent')

    def test_explicit_retained_import_refreshes_counts_and_status_reads_do_not_probe(self):
        initial = self.client.get('/dragon/api/v1/modules/data').json()
        self.assertEqual(initial['observation']['metrics']['retained_observation_count'], 0)
        job = self.app.state.jobs.submit('import_public', {'mode': 'retained'}, 'local:owner', 'kernel-count-refresh')
        self.app.state.jobs.run_once()
        self.assertEqual(self.app.state.jobs.get(job['id'])['status'], 'succeeded')
        with closing(self.p.connect()) as db:
            expected = db.execute('SELECT COUNT(*) FROM public_fixture_records').fetchone()[0]
        refreshed = self.client.get('/dragon/api/v1/modules/data').json()
        self.assertGreater(expected, 0)
        self.assertEqual(refreshed['observation']['metrics']['public_fixture_records'], expected)
        sampled = refreshed['observation']['metrics_sampled_at']
        self.p.matches(limit=1)
        with patch.object(self.p.kernel.engines['data'], 'observe', side_effect=AssertionError('Status must not refresh')):
            again = self.client.get('/dragon/api/v1/modules/data').json()
            self.client.get('/dragon/api/v1/modules')
        self.assertEqual(again['observation']['metrics']['public_fixture_records'], expected)
        self.assertEqual(again['observation']['metrics_sampled_at'], sampled)
        self.assertEqual(again['observation']['last_operation']['operation'], 'matches')

    def test_optional_memory_disabled_blocks_persistence_before_execution_but_not_forecast(self):
        from dragonhydra import public_results
        future = (datetime.now(timezone.utc)+timedelta(days=5)).date().isoformat()
        doc = {'name': 'Fictional optional dependency test', 'matches': [
            {'date': '2025-01-01', 'team1': 'A', 'team2': 'B', 'score': {'ft': [2, 1]}},
            {'date': future, 'team1': 'C', 'team2': 'D'}]}
        with closing(self.p.connect()) as db:
            public_results.ingest_bytes(db, json.dumps(doc).encode(), source_id='fictional-optional-test',
                source_url='fictional:optional-dependency-test', acquisition_id='fixed-test-input')
        target = next(row for row in self.p.rows() if row['result_state'] == 'unavailable')
        match_id = self.p.match_id(target)
        self.p.kernel.registry.disabled = frozenset({'memory'})
        self.assertTrue(self.p.predictions(match_id)['available'])
        with patch.object(self.p.kernel.engines['prediction'], 'persist',
                          side_effect=AssertionError('Must reject before engine execution')), \
             patch.object(self.p.kernel.engines['memory'], 'record_model',
                          side_effect=AssertionError('Must not record any model')):
            with self.assertRaisesRegex(ValueError, 'OPERATION_DEPENDENCY_UNAVAILABLE'):
                self.p.kernel.execute('prediction', 'persist', match_id)
        with closing(self.p.connect()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='cognitive_records'").fetchone()[0], 0)

    def test_actual_prospective_forecast_persists_before_later_outcome_evaluation(self):
        from dragonhydra import public_results, research
        from dragonhydra.cognition import models, memory
        from core_next.characterization import FrozenDateTime, AT
        doc = {'name': 'Fictional prospective lifecycle test', 'matches': [
            {'date': '2026-01-01', 'team1': 'A', 'team2': 'B', 'score': {'ft': [2, 1]}},
            {'date': '2026-01-25', 'team1': 'C', 'team2': 'D'}]}
        clock = [AT]
        with patch.object(public_results, '_now', side_effect=lambda: clock[0]), \
             patch.object(memory, '_now', side_effect=lambda: clock[0]), \
             patch.object(models, 'datetime', FrozenDateTime), patch.object(research, 'datetime', FrozenDateTime), \
             patch('dragonhydra.product.now', side_effect=lambda: clock[0]):
            with closing(self.p.connect()) as db:
                public_results.ingest_bytes(db, json.dumps(doc).encode(), source_id='fictional-persistence-test',
                    source_url='fictional:explicit-prospective-test', acquisition_id='before-event')
            target = next(r for r in self.p.rows() if r['result_state'] == 'unavailable')
            match_id = self.p.match_id(target)
            saved = self.p.kernel.execute('prediction', 'persist', match_id)
            self.assertTrue(saved['predictions'])
            self.assertGreater(self.p.kernel.module('memory')['observation']['metrics']['cognitive_records'], 0)
            before = self.p.kernel.execute('evaluation', 'evaluate', clock[0])
            self.assertTrue(all(g['metrics']['brier']['sample_size'] == 0 for g in before['groups']))
            clock[0] = '2026-01-28T12:00:00.000000Z'
            doc['matches'][1]['score'] = {'ft': [1, 0]}
            with closing(self.p.connect()) as db:
                received = public_results.ingest_bytes(db, json.dumps(doc).encode(),
                    source_id='fictional-persistence-test', source_url='fictional:explicit-prospective-test',
                    acquisition_id='after-event')
                outcome = next(r for r in public_results.as_of(db, received['usable_at'])
                               if r['acquisition_id'] == 'after-event' and r['home'] == 'C')
            self.p.kernel.execute('memory', 'attach_outcome', outcome['evidence_id'])
            result = self.p.kernel.execute('evaluation', 'evaluate', clock[0])
            self.assertTrue(result['groups'])
            self.assertTrue(all(g['metrics']['brier']['sample_size'] == 1 for g in result['groups']))
            group = next(g for g in result['groups'] if g['model_name'] == 'frequency')
            self.p.kernel.execute('evaluation', 'persist', {'run_id': 'core-next-evaluation-fixture',
                'model_name': group['model_name'], 'model_version': group['model_version'],
                'metric': 'brier', 'evaluation_cutoff': clock[0], **group['evaluation_scope']})
            with closing(self.p.connect()) as db:
                expected = db.execute('SELECT COUNT(*) FROM cognitive_records').fetchone()[0]
            self.assertEqual(self.p.kernel.module('memory')['observation']['metrics']['cognitive_records'], expected)
            self.assertEqual(self.p.kernel.module('evaluation')['observation']['metrics']['cognitive_records'], expected)
            self.assertEqual(self.p.kernel.module('evaluation')['observation']['last_operation']['state'], 'READY')
            self.assertFalse(self.p.predictions(match_id)['available'])
