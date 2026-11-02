"""Run the real PHP registry adapter/templates with isolated, counted API doubles."""
from __future__ import annotations
from contextlib import closing
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PHP = Path(os.environ.get('DRAGONHYDRA_TEST_PHP', 'C:/xampp/php/php.exe'))
COMPONENT = ROOT / 'server/joomla/com_dragonhydra'
MODEL = COMPONENT / 'admin/src/Model/ControlCenterModel.php'
NOW = 1793534400
IDENTITY = {'product': 'DRAGONHYDRA CORE NEXT', 'edition': 'CORE NEXT', 'installation_id': 'core-next-fixture',
            'environment_id': 'candidate', 'build_id': 'core-next-test', 'source_commit': 'a' * 40, 'version': '0.5.0-dev.1'}


def module(ident='data', **changes):
    return dict(id=ident, name=ident.title(), version='1', state='READY', reason='Retained evidence is available.',
                description='Existing module', category='Data', layer='engine', origin='built-in', observed_at='2026-11-01T11:59:00Z',
                expires_at='2026-11-01T12:30:00Z', dependencies=[], capabilities=['Read retained records'],
                operations=[{'id':'status', 'label':'Read status', 'method':'GET', 'enabled':True}],
                observation={'metrics':{'records':0}, 'evidence':['Synthetic retained fixture']}) | changes


@unittest.skipUnless(PHP.is_file(), 'Verified existing PHP CLI is required')
class CoreNextControlTests(unittest.TestCase):
    def php(self, body, prefix=''):
        code = prefix + "namespace { define('_JEXEC', 1); require " + json.dumps(str(MODEL)) + '; ' + body + ' }'
        # The full real registry exceeds Windows' command-line length; stream
        # fixture code through stdin and keep it out of process arguments.
        run = subprocess.run([str(PHP), '-n'], input='<?php '+code, capture_output=True, text=True, timeout=15)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        return run.stdout

    def render(self,center,can_import=False):
        prefix=('namespace Joomla\\CMS\\HTML {class HTMLHelper{static function _($x){return "<input type=hidden name=synthetic_csrf value=1>";}}}'
                'namespace Joomla\\CMS\\Language {class Text{static function _($x){return $x;}}}'
                'namespace Joomla\\CMS\\Router {class Route{static function _($x,$b=false){return $x;}}}')
        body='$v=new class{public $section="overview",$error=null,$center=[],$jobId="",$data=[],$probe=[],$canImport=false,$dashboardUrl="",$workflowMatchId="",$workflowKeys=[];function render($path){ob_start();require $path;return ob_get_clean();}};'
        body+='$v->center=json_decode('+json.dumps(json.dumps(center))+',true);$v->section=$v->center["section"];$v->canImport='+str(can_import).lower()+';echo $v->render('+json.dumps(str(COMPONENT/'admin/tmpl/dashboard/default.php'))+');'
        return self.php(body,prefix)

    def build(self, inputs=None, authorised=True, identity=None, items=None, detail=None, expected='core-next-fixture', system_identity=None, inventory=None):
        identity = IDENTITY if identity is None else identity
        registry = {'schema_version':'core-next.modules/1', 'installation':identity, 'items':[module()] if items is None else items}
        if inventory is not None: registry['inventory']=inventory
        responses = {'/modules?scope=all':registry, '/system':{'status':'ready', 'backend':'sqlite', 'installation':system_identity or identity}}
        if detail is not None:
            responses['/modules/' + detail['id']] = detail
        body = ('$responses=json_decode(' + json.dumps(json.dumps(responses)) + ',true);$calls=[];'
                '$m=new \\Dragonhydra\\Component\\Dragonhydra\\Administrator\\Model\\ControlCenterModel(' + json.dumps(expected) + ');'
                '$result=$m->build(json_decode(' + json.dumps(json.dumps(inputs or {})) + ',true),'
                + ('true' if authorised else 'false') + ',function($p)use(&$calls,$responses){$calls[]=$p;'
                'if(!isset($responses[$p]))throw new \\RuntimeException("PRIVATE_BACKEND_DETAIL");return $responses[$p];},' + str(NOW) + ');'
                'echo json_encode(["result"=>$result,"calls"=>$calls]);')
        return json.loads(self.php(body))

    def test_anonymous_and_missing_installation_binding_make_no_backend_request(self):
        for kwargs in [{'authorised':False}, {'expected':''}]:
            with self.subTest(kwargs=kwargs):
                got = self.build(**kwargs)
                self.assertEqual(got['calls'], [])
                self.assertIsNotNone(got['result']['error'])

    def test_original_product_and_other_candidate_identity_block_before_other_reads(self):
        for identity in [IDENTITY | {'product':'DRAGONHYDRA'}, IDENTITY | {'installation_id':'another-profile'}]:
            with self.subTest(identity=identity):
                got = self.build(identity=identity)
                self.assertEqual(got['calls'], ['/modules?scope=all'])
                self.assertFalse(got['result']['installation'])
                self.assertFalse(got['result']['modules'])
                self.assertIsNotNone(got['result']['error'])

    def test_overview_reads_only_registry_and_system_and_preserves_real_zero(self):
        got = self.build()
        self.assertEqual(got['calls'], ['/modules?scope=all','/system'])
        self.assertIsNone(got['result']['error'])
        self.assertEqual(got['result']['modules']['data']['observation']['metrics']['records'], 0)
        self.assertEqual(got['result']['installation']['installation_id'], 'core-next-fixture')

    def test_shared_registry_inventory_separates_six_engines_and_twelve_supporting_modules(self):
        engines=['data','odds','prediction','ai','memory','evaluation']
        supporting=['web_server','joomla_administration','joomla_website','api_server','sqlite_storage','mariadb_storage',
                    'durable_jobs','provider_scheduler','runtime_supervisor','windows_desktop','android_client','packaging_recovery']
        items=[module(key) for key in engines]+[module(key,layer='supporting',category='Infrastructure') for key in supporting]
        result=self.build(items=items,inventory={'engines':6,'supporting':12,'total':18})
        self.assertIsNone(result['result']['error'])
        self.assertEqual(result['result']['inventory'],{'engines':6,'supporting':12,'total':18,'unclassified':0})
        self.assertEqual(result['calls'],['/modules?scope=all','/system'])
        filtered=self.build(inputs={'section':'modules','layer':'supporting','category':'Infrastructure'},items=items,
                            inventory={'engines':6,'supporting':12,'total':18})
        self.assertEqual(set(filtered['result']['visible_modules']),set(supporting))
        self.assertEqual(filtered['result']['inventory']['engines'],6)
        mismatch=self.build(items=items,inventory={'engines':18,'supporting':0,'total':18})
        self.assertIsNotNone(mismatch['result']['error'])
        small=self.build(items=[module()])
        self.assertEqual(small['result']['inventory']['total'],1)

    def test_state_colors_are_labeled_and_evidence_age_is_preserved_without_probe(self):
        got=self.build(items=[module()])
        expected=NOW-int(__import__('datetime').datetime.fromisoformat('2026-11-01T11:59:00+00:00').timestamp())
        self.assertEqual(got['result']['modules']['data']['evidence_age_seconds'],expected)
        code='echo json_encode(['
        for state in ['READY','DEGRADED','UNAVAILABLE','UNKNOWN','EXPIRED','NOT_APPLICABLE']:
            code+='[\\Dragonhydra\\Component\\Dragonhydra\\Administrator\\Model\\ControlCenterModel::tone("'+state+'"),\\Dragonhydra\\Component\\Dragonhydra\\Administrator\\Model\\ControlCenterModel::stateLabel("'+state+'")],'
        code+=']);'
        self.assertEqual(json.loads(self.php(code)),[['green','Ready'],['amber','Degraded'],['red','Unavailable'],['neutral','Unknown'],['amber','Expired'],['neutral','Not applicable']])

    def test_actual_overview_and_layer_filter_render_inventory_and_separate_health_controls(self):
        items=[module(key) for key in ['data','odds','prediction','ai','memory','evaluation']]
        items+=[module('support_'+str(i),layer='supporting',category='Infrastructure') for i in range(12)]
        result=self.build(items=items,inventory={'engines':6,'supporting':12,'total':18})['result']
        rendered=self.render(result,True)
        for field,count in [('engines',6),('supporting',12),('total',18)]:
            self.assertIn('data-inventory="'+field+'">'+str(count)+'</strong>',rendered)
        for text in ('Refresh display','Run local checks','task=actions.observe','synthetic_csrf','data-tone="green"','data-tone="amber"','data-tone="red"','data-tone="neutral"'):
            self.assertIn(text,rendered)
        self.assertNotIn('task=actions.forecast',rendered)
        reader=self.render(result,False)
        self.assertNotIn('task=actions.observe',reader)
        filtered=self.build(inputs={'section':'modules','layer':'supporting'},items=items)['result']
        filtered_html=self.render(filtered)
        self.assertEqual(filtered_html.count('data-module-layer="supporting"'),12)
        self.assertNotIn('data-module-layer="engine"',filtered_html)

    def test_capability_proof_is_operation_scoped_when_optional_model_is_not_configured(self):
        item=module('ai',state='NOT_CONFIGURED',reason='OPTIONAL_MODEL_NOT_CONFIGURED',capability_status=[
            {'id':'evidence_package','available':True,'verified_operations':['package'],'operation_status':[
                {'id':'package','state':'READY','observed_at':'2026-11-01T11:59:00Z','expires_at':'2026-11-01T12:30:00Z',
                 'observation_id':'synthetic-package-proof','verification_scope':['DETERMINISTIC_PACKAGE_ONLY'],'reason':'OPERATION_SUCCEEDED'},
                {'id':'inference','state':'UNVERIFIED','observed_at':None,'expires_at':None,'verification_scope':[],'reason':'NO_OPERATION_EVIDENCE'}]}])
        center=self.build(inputs={'section':'ai'},items=[item],detail=item|{'installation':IDENTITY})['result']
        rendered=self.render(center)
        self.assertIn('Available for named verified operations',rendered)
        self.assertIn('synthetic-package-proof',rendered)
        self.assertIn('2026-11-01T11:59:00Z',rendered)
        self.assertIn('DETERMINISTIC_PACKAGE_ONLY',rendered)
        self.assertIn('No operation evidence',rendered)
        self.assertIn('Not configured',rendered)
        self.assertIn('does not verify every operation or an optional model',rendered)

    def test_unknown_and_expired_observations_cannot_be_presented_as_ready(self):
        got = self.build(items=[module('data', state='ADVERTISED'), module('ai', expires_at='2026-11-01T11:59:00Z')])
        self.assertEqual(got['result']['modules']['data']['state'], 'UNKNOWN')
        self.assertEqual(got['result']['modules']['ai']['state'], 'EXPIRED')
        self.assertIn('No new probe', got['result']['modules']['ai']['reason'])

    def test_ready_without_bounded_evidence_is_unknown_and_duplicate_ids_fail(self):
        got = self.build(items=[module(expires_at=None)])
        self.assertEqual(got['result']['modules']['data']['state'], 'UNKNOWN')
        self.assertIn('does not establish readiness', got['result']['modules']['data']['reason'])
        duplicate = self.build(items=[module(), module()])
        self.assertEqual(duplicate['calls'], ['/modules?scope=all'])
        self.assertIsNotNone(duplicate['result']['error'])

    def test_known_module_detail_has_same_instance_and_does_not_run_prediction(self):
        item = module('prediction')
        got = self.build(inputs={'section':'prediction'}, items=[item], detail=item | {'installation':IDENTITY})
        self.assertEqual(got['calls'], ['/modules?scope=all','/modules/prediction'])
        self.assertEqual(got['result']['module']['id'], 'prediction')
        self.assertIsNone(got['result']['error'])
        bad = self.build(inputs={'section':'prediction'}, items=[item], detail=item | {'installation':IDENTITY | {'installation_id':'original'}})
        self.assertIsNone(bad['result']['module'])
        self.assertIsNotNone(bad['result']['error'])

    def test_unknown_or_traversal_module_cannot_become_an_arbitrary_proxy(self):
        for selection in ['not-registered', '../../connections/openfootball/sync', 'data?admin=true']:
            with self.subTest(selection=selection):
                got = self.build(inputs={'section':'modules','module':selection})
                self.assertEqual(got['calls'], ['/modules?scope=all'])
                self.assertIsNotNone(got['result']['error'])
                self.assertNotIn('PRIVATE_BACKEND_DETAIL', json.dumps(got))

    def test_system_identity_cannot_silently_switch_to_an_original_backend(self):
        got = self.build(system_identity=IDENTITY | {'installation_id':'old'})
        self.assertFalse(got['result']['system'])
        self.assertIsNotNone(got['result']['error'])

    def test_detail_render_escapes_data_and_shows_disabled_operation_reason(self):
        item = module('ai', name='<script>bad()</script>', state='UNAVAILABLE', reason='No model is configured.',
                      operations=[{'id':'start','label':'Start model','method':'POST','enabled':False,'reason':'No owned inference runtime is configured.'}])
        center = self.build(inputs={'section':'ai'}, items=[item], detail=item | {'installation':IDENTITY})['result']
        prefix = ('namespace Joomla\\CMS\\HTML { class HTMLHelper {static function _($x){return "";}} } '
                  'namespace Joomla\\CMS\\Language { class Text {static function _($x){return $x;}} } '
                  'namespace Joomla\\CMS\\Router { class Route {static function _($x,$b=false){return $x;}} } ')
        template = COMPONENT / 'admin/tmpl/dashboard/default.php'
        body = ('$view=new class {public $section="ai",$error=null,$jobId="",$data=[],$center=[],$probe=[],$canImport=false,$dashboardUrl="";'
                'function render($path){ob_start();require $path;return ob_get_clean();}};'
                '$view->center=json_decode(' + json.dumps(json.dumps(center)) + ',true);echo $view->render(' + json.dumps(str(template)) + ');')
        html = self.php(body, prefix)
        self.assertIn('DRAGONHYDRA <span>CORE NEXT</span>', html)
        self.assertIn('core-next-fixture', html)
        self.assertIn('Disabled here', html)
        self.assertIn('No owned inference runtime is configured.', html)
        self.assertIn('&lt;script&gt;bad()&lt;/script&gt;', html)
        self.assertNotIn('<script>', html)
        self.assertNotIn('<form', html)
        self.assertNotIn('X-Dragon-Signature', html)

    def test_package_identity_and_real_assets_are_included_without_new_status_tables(self):
        package = ET.parse(ROOT / 'server/joomla/pkg_dragonhydra.xml').getroot()
        component = ET.parse(COMPONENT / 'dragonhydra.xml').getroot()
        template = ET.parse(ROOT / 'server/joomla/tpl_cassiopeia_dragonhydra/templateDetails.xml').getroot()
        expected = json.loads((ROOT / 'packaging/release/version.json').read_text())['joomla_version']
        self.assertEqual([package.findtext('version'), component.findtext('version'), template.findtext('version')], [expected] * 3)
        assets = json.loads((COMPONENT / 'media/joomla.asset.json').read_text())
        self.assertIn('com_dragonhydra.control-center', [a['name'] for a in assets['assets']])
        self.assertTrue((COMPONENT / 'media/css/control-center.css').is_file())
        model = MODEL.read_text()
        self.assertNotIn('DatabaseInterface', model)
        self.assertNotIn('file_put_contents', model)
        self.assertNotIn("'POST'", model)

    @unittest.skipUnless(os.environ.get('DRAGONHYDRA_CHARACTERIZATION_SNAPSHOT'), 'Explicit private snapshot required for real-registry integration')
    def test_real_candidate_registry_shape_survives_php_adapter_without_status_side_effects(self):
        from fastapi.testclient import TestClient
        sys.path.insert(0, str(ROOT/'src'))
        from dragonhydra.api import API, create_app
        from dragonhydra.kernel import KernelConfig
        snapshot = Path(os.environ['DRAGONHYDRA_CHARACTERIZATION_SNAPSHOT']).resolve()
        lab = ROOT.parent/(ROOT.name+'-LAB')
        self.assertTrue(snapshot.is_relative_to(lab.resolve()))
        temporary = lab/'tests'; temporary.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='joomla-registry-',dir=temporary) as directory:
            state = Path(directory)
            shutil.copyfile(snapshot,state/'core.sqlite3')
            app = create_app(state,local_token='synthetic-control-test-token',start_worker=False,
                kernel_config=KernelConfig(installation_id='core-next-control-fixture',environment_id='candidate',version='0.5.0-dev.1'))
            with TestClient(app) as client:
                client.headers['Authorization'] = 'Bearer synthetic-control-test-token'
                registry = client.get(API+'/modules?scope=all').json()
                responses = {'/modules?scope=all':registry,'/system':client.get(API+'/system').json()}
                for item in registry['items']:
                    responses['/modules/'+item['id']] = client.get(API+'/modules/'+item['id']).json()
                before = app.state.product.kernel.modules()
                code = ('$responses=json_decode('+json.dumps(json.dumps(responses))+',true);$calls=[];$results=[];'
                        '$m=new \\Dragonhydra\\Component\\Dragonhydra\\Administrator\\Model\\ControlCenterModel("core-next-control-fixture");'
                        '$read=function($p)use($responses,&$calls){$calls[]=$p;return $responses[$p];};'
                        'foreach(["overview","infrastructure","modules","odds","prediction","ai","memory","evaluation"] as $section){'
                        '$results[$section]=$m->build(["section"=>$section],true,$read);}'
                        '$results["data"]=$m->build(["section"=>"modules","module"=>"data"],true,$read);'
                        'echo json_encode(["results"=>$results,"calls"=>$calls]);')
                adapted = json.loads(self.php(code))
                for section,result in adapted['results'].items():
                    self.assertIsNone(result['error'],section)
                    self.assertEqual(result['installation']['installation_id'],'core-next-control-fixture')
                    if result['module']:
                        expected = responses['/modules/'+result['module']['id']]
                        self.assertEqual(result['module']['state'],expected['state'])
                        self.assertEqual(result['module']['observation']['metrics'] or {},expected['observation']['metrics'] or {})
                        self.assertEqual(result['module']['capability_status'],expected['capability_status'])
                self.assertEqual(adapted['results']['ai']['module']['state'],'NOT_CONFIGURED')
                self.assertEqual(app.state.product.kernel.modules(),before)
                with closing(app.state.product.connect()) as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM product_jobs').fetchone()[0],0)


if __name__ == '__main__':
    unittest.main()
