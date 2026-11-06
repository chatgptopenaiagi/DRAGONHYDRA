"""In-process ASGI and isolated filesystem tests; never a listening product server."""
from contextlib import closing
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

API = '/dragon/api/v1'
BASE = API + '/realtime'
TOKEN = 'virtual-api-fixture-session-not-a-real-key'


@unittest.skipUnless(importlib.util.find_spec('fastapi') and importlib.util.find_spec('httpx'), 'Pinned API fixture environment required')
class RealtimeAPITests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        self.temp = tempfile.TemporaryDirectory(prefix='genesis6-api-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / 'state'
        self.source = self.state / 'virtual-source'
        self.source.mkdir(parents=True)
        for target in ('dragonhydra.local_ai_settings.Settings.public', 'dragonhydra.connectors.vault.Vault.get',
                       'dragonhydra.connectors.service.Connections.run', 'dragonhydra.connectors.core.Transport.get',
                       'dragonhydra.local_ai.infer'):
            guard = patch(target, side_effect=AssertionError('REAL_CREDENTIAL_PROVIDER_OR_INFERENCE_FORBIDDEN'))
            guard.start(); self.addCleanup(guard.stop)
        self.app = create_app(self.state, local_token=TOKEN, bridge_secret='', start_worker=False,
            source_root=self.source, realtime_config={'auto_investigate': False})
        client = TestClient(self.app)
        self.client = client.__enter__()
        self.addCleanup(lambda: client.__exit__(None, None, None))
        self.client.headers['Authorization'] = 'Bearer ' + TOKEN

    def scenario(self):
        response = self.client.post(BASE+'/scenarios', json={'scenario_id': 'standard', 'source_mode': 'DEMONSTRATION'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIs(response.json()['synthetic'], True)
        return response.json()['match_id']

    def test_all_advertised_universe_generators_are_available_through_api(self):
        from dragonhydra.realtime.worlds import UNIVERSES
        for universe in UNIVERSES:
            with self.subTest(universe=universe):
                response = self.client.post(BASE+'/scenarios', json={
                    'scenario_id': 'universe', 'source_mode': 'DEMONSTRATION',
                    'universe': universe, 'seed': 42})
                self.assertEqual(response.status_code, 200, response.text)
                mid = response.json()['match_id']
                snapshot = self.client.get(BASE+'/matches/'+mid).json()
                self.assertEqual(snapshot['descriptor']['universe'], universe)
                self.assertEqual(snapshot['state']['revision'], 0)

    def journal(self):
        with closing(sqlite3.connect(self.app.state.realtime.store.path)) as db:
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            return {name: db.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall() for name in tables}

    def test_existing_authentication_covers_research_and_update_stream(self):
        self.client.headers.clear()
        for path in (BASE+'/status', BASE+'/matches', BASE+'/tools', API+'/updates'):
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.post(BASE+'/scenarios', json={}).status_code, 401)
        response = self.client.post(API+'/session', json={'token': TOKEN})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(BASE+'/status').status_code, 200)
        self.assertEqual(self.client.post(API+'/session/logout', json={}).status_code, 200)
        self.assertEqual(self.client.get(BASE+'/status').status_code, 401)

    def test_concrete_extension_is_opt_in_and_reads_are_passive(self):
        modules = self.client.get(API+'/modules?scope=all').json()
        self.assertEqual(modules['inventory'], {'engines': 7, 'supporting': 12, 'total': 19})
        module = next(x for x in modules['items'] if x['id'] == 'realtime_research')
        self.assertIn('RealtimeService', module['implementation_reference'])
        match = self.scenario()
        before = self.journal()
        for path in ('/status', '/matches', '/matches/'+match, '/matches/'+match+'/timeline?limit=200',
                     '/matches/'+match+'/events', '/tools', '/budgets', '/evaluation', '/experiments'):
            response = self.client.get(BASE+path)
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(before, self.journal())
        self.assertIsNone(self.app.state.jobs.thread)

    def test_explicit_replay_uses_synthetic_state_and_horizon_contract(self):
        match = self.scenario()
        response = self.client.post(BASE+'/replay/'+match, json={'action': 'step', 'speed': 100, 'steps': 1})
        self.assertEqual(response.status_code, 200, response.text)
        snapshot = response.json()
        self.assertIs(snapshot['synthetic'], True)
        self.assertEqual(snapshot['state']['revision'], 1)
        self.assertEqual(set(snapshot['current_forecast']['forecast']['horizons']), {'1','5','10','30','FULL_TIME'})
        self.assertEqual(len(self.client.get(BASE+'/matches/'+match+'/events').json()['items']), 1)

    def test_strict_requests_reject_live_modes_extra_keys_and_real_ids(self):
        for body in ({'source_mode': 'LIVE'}, {'credential': 'not-a-real-key'}, {'seed': True}, {'universe': 'production'}, {'scenario_id': 'old-data'}):
            self.assertEqual(self.client.post(BASE+'/scenarios', json=body).status_code, 422)
        match = self.scenario()
        for body in ({'action':'step','steps':0}, {'action':'step','steps':101}, {'action':'step','speed':101}, {'action':'shell'}, {'action':'step','steps':1.0}):
            self.assertEqual(self.client.post(BASE+'/replay/'+match, json=body).status_code, 422)
        self.assertEqual(self.client.get(BASE+'/matches/'+'a'*64).status_code, 422)
        self.assertEqual(self.client.get(BASE+'/matches/'+match+'/timeline?limit=201').status_code, 422)
        self.assertEqual(self.client.post(BASE+'/events', json={'source_mode':'LIVE'}).status_code, 422)
        self.assertEqual(self.client.post(BASE+'/matches/'+match+'/branches', json={'at_revision':True}).status_code, 422)

    def test_reader_cannot_mutate_research_and_legacy_work_is_barred(self):
        cookie = 'virtual-reader-session-cookie-fixture'
        with closing(self.app.state.product.connect()) as db:
            db.execute('INSERT INTO product_sessions VALUES(?,?,?,?)', (hashlib.sha256(cookie.encode()).hexdigest(), 'virtual:reader', '["reader"]', time.time()+3600))
            db.commit()
        self.client.headers.clear(); self.client.cookies.set(self.app.state.session_cookie_name, cookie)
        self.assertEqual(self.client.get(BASE+'/status').status_code, 200)
        self.assertEqual(self.client.post(BASE+'/scenarios', json={}).status_code, 403)
        self.client.cookies.clear(); self.client.headers['Authorization'] = 'Bearer '+TOKEN
        for path in ('/jobs', '/matches/'+'a'*64+'/forecasts', '/exports', '/research/storage/initialize', '/connections/api-football/test', '/local-model/configuration'):
            self.assertEqual(self.client.post(API+path, json={}).status_code, 403)
        self.assertEqual(self.client.get(API+'/connections').status_code, 403)
        self.assertIs(self.client.get(API+'/system').json()['local_ai']['configured'], False)
        self.assertEqual(self.client.get(API+'/local-model/configuration').json()['credential_source'], 'none')

    def test_host_origin_and_request_size_limits_still_apply(self):
        self.assertEqual(self.client.get(BASE+'/status', headers={'Host':'external.invalid'}).status_code, 400)
        self.assertEqual(self.client.post(BASE+'/scenarios', json={}, headers={'Origin':'https://external.invalid'}).status_code, 403)
        self.assertEqual(self.client.post(BASE+'/scenarios', content='x'*32769, headers={'Content-Type':'application/json'}).status_code, 413)


class ExtensionAndRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='genesis6-runtime-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    @unittest.skipUnless(importlib.util.find_spec('fastapi') and importlib.util.find_spec('httpx'), 'Pinned API fixture environment required')
    def test_default_application_keeps_eighteen_modules_and_legacy_behavior(self):
        from fastapi.testclient import TestClient
        from dragonhydra.api import create_app
        app=create_app(self.root/'default',local_token=TOKEN,start_worker=False,source_root=self.root/'empty')
        client=TestClient(app);self.addCleanup(client.close)
        client.headers['Authorization']='Bearer '+TOKEN
        self.assertIsNone(app.state.realtime);self.assertIs(app.state.virtual_mode,False)
        self.assertEqual(client.get(API+'/modules?scope=all').json()['inventory']['total'],18)
        # The ordinary app reaches its retained-resource validation; it is not
        # globally blocked by the opt-in simulation middleware.
        response=client.post(API+'/jobs',json={'kind':'explanation','match_id':'a'*64})
        self.assertEqual(response.status_code,404)

    def test_default_inventory_and_transactional_prestart_extension(self):
        from dragonhydra.product import Product
        from dragonhydra.kernel.contracts import ModuleDefinition
        class Probe:
            contract_version='core-next.engine/1'
            def observe(self): raise AssertionError('REGISTRATION_MUST_NOT_PROBE')
            def read(self): return {'synthetic':True}
            def stop(self): pass
        product=Product(self.root/'product', source_root=self.root/'empty-source')
        kernel=product.kernel
        self.assertEqual(kernel.registry.inventory()['total'],18)
        definition=ModuleDefinition('fixture_extension','Fixture','Synthetic fixture','Research',dependencies=('sqlite_storage',),
            capabilities=('read',),supported_operations=('read',),capability_operations=(('read',('read',)),),
            implementation_reference='fixture.Probe',configuration_requirements=('sqlite_state',))
        for invalid in (replace(definition,id='data'),replace(definition,dependencies=('missing',)),replace(definition,supported_operations=('missing',),capability_operations=(('read',('missing',)),))):
            with self.assertRaises(ValueError):kernel.register_extension(invalid,Probe())
            self.assertEqual(kernel.registry.inventory()['total'],18)
        kernel.register_extension(definition,Probe())
        self.assertEqual(kernel.registry.inventory()['total'],19)
        self.assertIs(kernel.observer.registry,kernel.registry)
        with patch.object(kernel.observer,'start'):
            kernel.start()
        with self.assertRaisesRegex(ValueError,'AFTER_START'):
            kernel.register_extension(replace(definition,id='another'),Probe())

    def test_virtual_context_refuses_retained_profiles_and_nonempty_sources(self):
        from dragonhydra.api import create_app
        state=self.root/'old';source=state/'virtual-source';source.mkdir(parents=True)
        (state/'workstation.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'ADOPTION'):
            create_app(state,local_token=TOKEN,source_root=source,realtime_config={})
        self.assertFalse((state/'core.sqlite3').exists())
        (state/'workstation.json').unlink();(source/'original-sports.csv').write_text('forbidden fixture')
        with self.assertRaisesRegex(ValueError,'EMPTY_VIRTUAL_SOURCE'):
            create_app(state,local_token=TOKEN,source_root=source,realtime_config={})
        self.assertFalse((state/'core.sqlite3').exists())
        (source/'original-sports.csv').unlink()
        (state/'core.sqlite3').write_bytes(b'fixture existing database must not be opened')
        (state/'.genesis6-runtime.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'MARKER_INVALID'):
            create_app(state,local_token=TOKEN,source_root=source,realtime_config={})

    def test_marker_adoption_boundary_and_exclusive_os_lock(self):
        from dragonhydra.realtime.server import prepare_state,runtime_lock,MARKER
        lane=self.root/'GENESIS-6-REALTIME-INTELLIGENCE';lane.mkdir()
        state,source=prepare_state(lane/'runtime'/'fixture',lane=lane)
        self.assertTrue((state/MARKER).is_file());self.assertEqual(list(source.iterdir()),[])
        self.assertEqual(prepare_state(state,lane=lane),(state,source))
        with runtime_lock(state):
            with self.assertRaisesRegex(RuntimeError,'ALREADY_RUNNING'):
                with runtime_lock(state):pass
        wrong=lane/'runtime'/'unowned';wrong.mkdir();(wrong/'data.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'ADOPTION'):
            prepare_state(wrong,lane=lane)
        with self.assertRaisesRegex(ValueError,'OWN_RUNTIME'):
            prepare_state(self.root/'profiles'/'old',lane=lane)

    def test_server_ports_and_build_info_are_separate_from_startup(self):
        from dragonhydra.realtime.server import port_number,main
        self.assertEqual(port_number(19380),19380)
        for port in (18740,18751,0,65536):
            with self.assertRaises(ValueError):port_number(port)
        with patch('dragonhydra.realtime.server.LANE',Path('C:/virtual/GENESIS-6-REALTIME-INTELLIGENCE')),patch('dragonhydra.realtime.server.source_identity',return_value={'source_sha':'a'*40,'synthetic':True}),patch('dragonhydra.realtime.server.prepare_state',side_effect=AssertionError('BUILD_INFO_MUST_NOT_CREATE_STATE')):
            from contextlib import redirect_stdout
            import io
            output=io.StringIO()
            with redirect_stdout(output):self.assertEqual(main(['--build-info']),0)
            self.assertEqual(json.loads(output.getvalue())['source_sha'],'a'*40)


if __name__ == '__main__':unittest.main()
