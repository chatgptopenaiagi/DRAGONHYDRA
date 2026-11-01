"""Exercise the actual read-only PHP registry projection, ACL guard and templates in isolation."""
import json
from pathlib import Path
import subprocess
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'server/joomla/com_dragonhydra'
PHP = ROOT / 'build/workstation/test-install/application files/web/php/php.exe'
ADAPTER = COMPONENT / 'admin/src/Service/SystemModules.php'
FIXTURE = ROOT / 'tests/installation/joomla_control_render_fixture.php'


def module(module_id='data_engine', state='ready', expires='2100-01-01T00:00:00Z'):
    return {'definition': {'module_id': module_id, 'display_name': 'Fixture data engine', 'category': 'data',
                           'required_for_core': True, 'actual_build_or_module_version': 'fixture',
                           'configuration_requirements': [], 'implemented_capabilities': ['Retained reads'],
                           'password': 'PRIVATE_FIXTURE_SECRET'},
            'observation': {'module_id': module_id, 'runtime_state': state, 'implementation_state': 'implemented',
                            'configuration_state': 'configured', 'observed_at': '2026-01-01T00:00:00Z',
                            'evidence_expires_at': expires, 'reason': 'Retained fixture data',
                            'sanitized_metrics': {'table_count': 4, 'configured': True,
                                                  'api_token': 'PRIVATE_FIXTURE_SECRET', 'path': 'PRIVATE_FIXTURE_SECRET'},
                            'password': 'PRIVATE_FIXTURE_SECRET'},
            'operations': [{'operation_id': 'read_matches', 'label': 'Matches', 'read_only': True,
                            'available': True, 'reference': 'https://untrusted.invalid/PRIVATE_FIXTURE_SECRET'}],
            'dependencies': []}


def registry(modules=None):
    return {'schema_version': 1, 'read_only': True, 'registry_version': 'module-registry/1',
            'as_of': '2026-01-01T00:00:00Z', 'core_state': 'ready',
            'modules': [module()] if modules is None else modules,
            'private_runtime': 'PRIVATE_FIXTURE_SECRET'}


@unittest.skipUnless(PHP.is_file(), 'Existing matching private Windows PHP runtime required')
class JoomlaControlCenterTests(unittest.TestCase):
    def php(self, source):
        result = subprocess.run([str(PHP), '-n', '-r', source], capture_output=True,
                                text=True, encoding='utf-8', timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('Warning:', result.stdout)
        return result.stdout

    def project(self, data=None, filters='', now=1793520000):
        data = registry() if data is None else data
        code = ('define("_JEXEC",1);require ' + json.dumps(str(ADAPTER)) + ';'
                '$r=json_decode(' + json.dumps(json.dumps(data)) + ',true);'
                'echo json_encode(\\Dragonhydra\\Component\\Dragonhydra\\Administrator\\Service\\SystemModules::project($r,'
                + filters + (',' if filters else '"","","",') + str(now) + '));')
        return json.loads(self.php(code))

    def render(self, scenario):
        result = subprocess.run([str(PHP), '-n', str(FIXTURE), scenario], capture_output=True,
                                text=True, encoding='utf-8', timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('Warning:', result.stdout)
        self.assertNotIn('Fatal error', result.stdout)
        return result.stdout

    def test_read_fetches_exact_route_once_and_input_never_becomes_backend_path(self):
        code = ('define("_JEXEC",1);require ' + json.dumps(str(ADAPTER)) + ';$paths=[];'
                '$r=json_decode(' + json.dumps(json.dumps(registry())) + ',true);'
                '$out=\\Dragonhydra\\Component\\Dragonhydra\\Administrator\\Service\\SystemModules::load('
                'function($p)use(&$paths,$r){$paths[]=$p;return $r;},"../../elsewhere","https://evil.invalid","../../secret");'
                'echo json_encode([$paths,$out["group"],$out["status"],$out["requested_id"]]);')
        self.assertEqual(json.loads(self.php(code)), [['/system/modules'], '', '', ''])

    def test_projection_omits_private_config_extra_metrics_and_arbitrary_url(self):
        result = self.project()
        self.assertNotIn('PRIVATE_FIXTURE_SECRET', json.dumps(result))
        self.assertNotIn('untrusted.invalid', json.dumps(result))
        self.assertEqual(result['modules']['data_engine']['metrics'], {'table_count': '4', 'configured': 'Yes'})
        self.assertEqual(result['core_ready'], 1)

    def test_backend_build_identity_whitelists_hashes_and_unknown_is_not_inferred(self):
        data = {'version':'0.4.0-alpha.1','build':{'version':'0.4.0-alpha.1','build_kind':'source-locked-development',
                'source_sha':'a'*40,'source_content_sha256':'b'*64,'private_token':'PRIVATE_FIXTURE_SECRET'}}
        code = ('define("_JEXEC",1);require ' + json.dumps(str(ADAPTER)) + ';'
                'echo json_encode([\\Dragonhydra\\Component\\Dragonhydra\\Administrator\\Service\\SystemModules::buildIdentity(json_decode('
                + json.dumps(json.dumps(data)) + ',true)),\\Dragonhydra\\Component\\Dragonhydra\\Administrator\\Service\\SystemModules::buildIdentity([])]);')
        identity, missing = json.loads(self.php(code))
        self.assertEqual(identity, {key: data['build'][key] for key in ('version','build_kind','source_sha','source_content_sha256')})
        self.assertEqual(missing, {'version':None,'build_kind':None,'source_sha':None,'source_content_sha256':None})
        rendered = self.render('normal')
        self.assertIn('Associated backend build', rendered)
        self.assertIn('data-backend-build="source_sha">Not reported', rendered)

    def test_expired_ready_evidence_becomes_unverified_without_changing_implementation(self):
        result = self.project(registry([module(expires='2026-01-01T00:00:01Z')]))
        item = result['modules']['data_engine']
        self.assertEqual(item['state'], 'configured_unverified')
        self.assertEqual(item['reported_state'], 'ready')
        self.assertEqual(item['implementation_state'], 'implemented')
        self.assertEqual(result['core_ready'], 0)
        self.assertIn('expired', item['reason'])

    def test_dependency_state_uses_current_projected_evidence(self):
        parent = module('api_server'); parent['dependencies'] = [{'module_id': 'data_engine', 'required': True, 'runtime_state': 'ready'}]
        expired = module(expires='2026-01-01T00:00:01Z')
        result = self.project(registry([parent, expired]))
        self.assertEqual(result['modules']['api_server']['dependencies'][0]['runtime_state'], 'configured_unverified')

    def test_future_or_mismatched_installation_evidence_is_not_ready(self):
        future = module(); future['observation']['observed_at'] = '2099-01-01T00:00:00Z'
        self.assertEqual(self.project(registry([future]))['modules']['data_engine']['state'], 'configured_unverified')
        wrong = registry(); wrong['installation_id'] = 'local-fixture-one'
        wrong['modules'][0]['observation']['installation_id'] = 'local-fixture-two'
        code = ('define("_JEXEC",1);require ' + json.dumps(str(ADAPTER)) + ';try{'
                '\\Dragonhydra\\Component\\Dragonhydra\\Administrator\\Service\\SystemModules::project(json_decode('
                + json.dumps(json.dumps(wrong)) + ',true));echo "accepted";}catch(\\RuntimeException $e){echo "rejected";}')
        self.assertEqual(self.php(code), 'rejected')

    def test_group_status_and_detail_filter_existing_snapshot(self):
        result = self.project(registry([module(), module('ai_engine', 'not_implemented')]), '"data","not_implemented","ai_engine"')
        self.assertEqual(list(result['visible']), ['ai_engine'])
        self.assertEqual(result['selected']['id'], 'ai_engine')
        self.assertEqual(result['total'], 2)

    def test_invalid_or_mutable_registry_does_not_render_fabricated_success(self):
        for data in ({'schema_version': 2, 'read_only': True, 'modules': []},
                     {'schema_version': 1, 'read_only': False, 'modules': []}, registry([module(), module()])):
            code = ('define("_JEXEC",1);require ' + json.dumps(str(ADAPTER)) + ';try{'
                    '\\Dragonhydra\\Component\\Dragonhydra\\Administrator\\Service\\SystemModules::project(json_decode('
                    + json.dumps(json.dumps(data)) + ',true));echo "accepted";}catch(\\RuntimeException $e){echo "rejected";}')
            self.assertEqual(self.php(code), 'rejected')

    def test_actual_admin_view_denies_permission_before_any_bridge_read(self):
        view = COMPONENT / 'admin/src/View/Dashboard/HtmlView.php'
        code = ('namespace Joomla\\CMS\\MVC\\View {class HtmlView {}}'
                'namespace Joomla\\CMS {class Factory{static function getApplication(){return new class{'
                'function getIdentity(){return new class{function authorise($a,$c){return false;}};}};}}}'
                'namespace{define("_JEXEC",1);require ' + json.dumps(str(view)) + ';'
                'try{(new \\Dragonhydra\\Component\\Dragonhydra\\Administrator\\View\\Dashboard\\HtmlView())->display();'
                'echo "accepted";}catch(\\RuntimeException $e){echo $e->getCode();}}')
        self.assertEqual(self.php(code), '403')

    def test_actual_template_renders_group_evidence_details_and_real_read_links(self):
        rendered = self.render('normal')
        for text in ('System Control Center', 'Infrastructure', 'Odds and prediction', 'Optional AI',
                     'Memory and evaluation', 'Installation observation', 'Configuration requirements',
                     'Evidence expires', 'Browse retained matches', 'section=matches'):
            self.assertIn(text, rendered)
        self.assertNotIn('PRIVATE_FIXTURE_SECRET', rendered)
        self.assertNotIn('untrusted.invalid', rendered)
        self.assertNotIn('method="post"', rendered)
        self.assertIn('no enabled execution control in Joomla', rendered)
        self.assertIn('This CLI operation is not exposed through Joomla.', rendered)

    def test_actual_template_empty_error_and_filtered_states_are_honest(self):
        empty = self.render('empty')
        self.assertIn('No module definitions were reported', empty)
        self.assertIn('data-module-total="0"', empty)
        unavailable = self.render('unavailable')
        self.assertIn('Module status is unavailable', unavailable)
        self.assertIn('Readiness has not been verified', unavailable)
        self.assertNotIn('data-module-total', unavailable)
        self.assertIn('No modules match these filters', self.render('filtered'))
        self.assertIn('requested module is not present', self.render('missing'))

    def test_actual_template_escapes_backend_values_and_never_reports_expired_ready(self):
        rendered = self.render('escaped')
        self.assertIn('&lt;script&gt;fixture_attack()&lt;/script&gt;', rendered)
        self.assertIn('&lt;img src=x onerror=fixture_attack()&gt;', rendered)
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('<img src=x', rendered)
        expired = self.render('expired')
        self.assertIn('Configured, unverified', expired)
        self.assertIn('current readiness is unverified', expired)
        self.assertIn('Evidence missing or expired', expired)

    def test_component_menu_and_versions_and_assets_are_reproducible(self):
        component = ET.parse(COMPONENT / 'dragonhydra.xml').getroot()
        package = ET.parse(ROOT / 'server/joomla/pkg_dragonhydra.xml').getroot()
        template = ET.parse(ROOT / 'server/joomla/tpl_cassiopeia_dragonhydra/templateDetails.xml').getroot()
        self.assertEqual({component.findtext('version'), package.findtext('version'), template.findtext('version')}, {'0.4.1-dev.3'})
        self.assertIn('option=com_dragonhydra&section=control', [item.get('link') for item in component.findall('administration/submenu/menu')])
        assets = json.loads((COMPONENT / 'media/joomla.asset.json').read_text())
        self.assertIn('com_dragonhydra.control', [item['name'] for item in assets['assets']])


if __name__ == '__main__':
    unittest.main()
