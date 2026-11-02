"""CORE NEXT Joomla typed workflow, identity, permissions and retained rendering fixtures."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
PHP=Path(os.environ.get('DRAGONHYDRA_TEST_PHP','C:/xampp/php/php.exe'))
COMPONENT=ROOT/'server/joomla/com_dragonhydra'
SERVICE=COMPONENT/'admin/src/Service/ControlWorkflow.php'
MODEL=COMPONENT/'admin/src/Model/ControlCenterModel.php'
IDENTITY={'product':'DRAGONHYDRA CORE NEXT','installation_id':'core-next-fixture'}


def fixtures():
    match={'id':'a'*64,'status':'scheduled','home':{'name':'Synthetic home'},'away':{'name':'Synthetic away'},'competition':'Synthetic league','event_date':'2099-01-01'}
    history={'schema_version':'core-next.workflow/1','installation':IDENTITY,'match_id':'a'*64,'source_id':'synthetic-source',
        'fixture_key':'synthetic-fixture','target_evidence_id':'synthetic-target','cutoff':'2026-11-02T00:00:00Z',
        'records':{'models':[{'record_id':'synthetic-model','model_name':'frequency','model_version':'synthetic-only',
            'data_cutoff':'2026-11-01T00:00:00Z','input_evidence_ids':['synthetic-input'],
            'parameters':{'private_token':'PRIVATE_FIXTURE_VALUE','workflow':{'generated_at':'2026-11-02T00:00:00Z',
                'build':IDENTITY|{'build_id':'fixture-build','source_commit':'b'*40,'version':'0.5.0-dev.2'},
                'uncertainty':{'items':['Synthetic uncertainty; no skill proof.']},'adaptation':{'reason':'INSUFFICIENT_COMPARABLE_OPERATIONAL_EVALUATIONS','minimum_cases':20,'evidence_ids':[]}}}}],
            'predictions':[{'record_id':'synthetic-prediction','model_run_id':'synthetic-model','probabilities':{'home':'0.4','draw':'0.3','away':'0.3'}}],
            'outcomes':[],'evaluations':[]},'present_knowledge_holdout':{'available':False,'reason':'EXPLICIT_DIAGNOSTIC_NOT_REQUESTED'},'limitations':['Synthetic fixture only.']}
    return match,history


@unittest.skipUnless(PHP.is_file(),'Existing matching PHP runtime required')
class CoreNextControlWorkflowTests(unittest.TestCase):
    def php(self,body,prefix=''):
        code=prefix+'namespace{define("_JEXEC",1);require '+json.dumps(str(SERVICE))+';require '+json.dumps(str(MODEL))+';use Dragonhydra\\Component\\Dragonhydra\\Administrator\\Service\\ControlWorkflow as W;'+body+'}'
        run=subprocess.run([str(PHP),'-n'],input='<?php '+code,capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertNotIn('Warning:',run.stdout)
        return run.stdout

    def loaded(self,identity=None):
        match,history=fixtures()
        if identity is not None: history['installation']=identity
        body='$m=json_decode('+json.dumps(json.dumps(match))+',true);$h=json_decode('+json.dumps(json.dumps(history))+',true);$paths=[];'
        body+='$read=function($path)use($m,$h,&$paths){$paths[]=$path;return str_ends_with($path,"/cognition-history")?$h:$m;};'
        body+='try{$r=W::load($read,str_repeat("a",64),"core-next-fixture");echo json_encode(["result"=>$r,"paths"=>$paths]);}catch(\\RuntimeException $e){echo json_encode(["rejected"=>true,"paths"=>$paths]);}'
        return json.loads(self.php(body))

    def test_history_is_same_instance_read_only_and_projects_retained_provenance(self):
        got=self.loaded()
        self.assertEqual(got['paths'],['/matches/'+'a'*64,'/matches/'+'a'*64+'/cognition-history'])
        result=got['result']
        self.assertEqual(result['models'][0]['build']['build_id'],'fixture-build')
        self.assertEqual(result['models'][0]['build']['source_commit'],'b'*40)
        self.assertEqual(result['predictions'][0]['probabilities']['home'],'0.4')
        self.assertEqual(result['counts'],{'models':1,'predictions':1,'outcomes':0,'evaluations':0})
        self.assertNotIn('PRIVATE_FIXTURE_VALUE',json.dumps(result))
        self.assertTrue(self.loaded(IDENTITY|{'installation_id':'old-original-profile'})['rejected'])
        self.assertTrue(self.loaded(IDENTITY|{'product':'DRAGONHYDRA'})['rejected'])

    def test_commands_are_typed_empty_body_and_session_keys_replay(self):
        body='$app=new class{public $s=[];function getUserState($k,$d){return $this->s[$k]??$d;}function setUserState($k,$v){$this->s[$k]=$v;}};'
        body+='$key=W::formKey($app,str_repeat("a",64),"forecasts");$same=W::formKey($app,str_repeat("a",64),"forecasts");$other=W::formKey($app,str_repeat("a",64),"evaluations");$calls=[];'
        body+='$send=function($m,$p,$b,$k)use(&$calls){$calls[]=[$m,$p,$b,$k];return ["id"=>str_repeat("b",32)];};'
        body+='W::submit($send,str_repeat("a",64),"forecasts",$key,$same);$denied=0;foreach(["../unsafe","observe"] as $op){try{W::submit($send,str_repeat("a",64),$op,$key,$same);}catch(\\RuntimeException $e){$denied++;}}'
        body+='try{W::submit($send,str_repeat("a",64),"evaluations",$key,$other);}catch(\\RuntimeException $e){$denied++;}echo json_encode([$same===$key,$other!==$key,count($calls),$calls[0][0],$calls[0][1],$calls[0][2],$denied]);'
        self.assertEqual(json.loads(self.php(body)),[True,True,1,'POST','/matches/'+'a'*64+'/forecasts',[],3])

    def test_public_actions_require_csrf_component_and_import_permission_before_bridge(self):
        controller=COMPONENT/'admin/src/Controller/ActionsController.php'
        for action in ('forecast','evaluate','observe'):
            for csrf,manage,importer in ((False,True,True),(True,False,True),(True,True,False)):
                prefix='namespace Joomla\\CMS\\MVC\\Controller{class BaseController{public $app;}}namespace Joomla\\CMS\\Session{class Session{static function checkToken($method){return '+str(csrf).lower()+';}}}'
                body='require '+json.dumps(str(controller))+';$c=new \\Dragonhydra\\Component\\Dragonhydra\\Administrator\\Controller\\ActionsController();'
                body+='$c->app=new class{function getIdentity(){return new class{function authorise($action,$component){return $action==="core.manage"?'+str(manage).lower()+':'+str(importer).lower()+';}};}};'
                body+='try{$c->'+action+'();echo "accepted";}catch(\\RuntimeException $e){echo $e->getCode();}'
                self.assertEqual(self.php(body,prefix),'403')

    def test_narrow_idempotency_transport_rejects_local_checks_and_arbitrary_paths(self):
        body='require '+json.dumps(str(COMPONENT/'admin/src/Service/ApiClient.php'))+';'
        body+='$c=new \\Dragonhydra\\Component\\Dragonhydra\\Administrator\\Service\\ApiClient("http://127.0.0.1:18821/dragon/api/v1",str_repeat("x",32),"joomla:47","admin");$denied=0;'
        body+='foreach([["POST","/modules/observe"],["GET","/modules?scope=all"],["POST","/connections/openfootball/sync"]] as $args){try{$c->request($args[0],$args[1],[],str_repeat("c",32));}catch(\\RuntimeException $e){$denied++;}}echo $denied;'
        self.assertEqual(self.php(body),'3')

    def test_explicit_local_check_completion_busy_and_disabled_messages_keep_their_scope(self):
        controller=COMPONENT/'admin/src/Controller/ActionsController.php'
        prefix=r'''namespace Joomla\CMS\MVC\Controller{class BaseController{public $app;function setRedirect($url,$message,$type="message"){$GLOBALS['redirect']=[$url,$message,$type];}}}
namespace Joomla\CMS\Session{class Session{static function checkToken($method){return true;}}}
namespace Joomla\CMS\Router{class Route{static function _($url,$x=false){return $url;}}}
namespace Joomla\CMS\Component{class ComponentHelper{static function getParams($name){return new class{function get($key,$default){return "core-next-fixture";}};}}}
namespace Dragonhydra\Component\Dragonhydra\Administrator\Service{class Kernel{static function client(){return new class{function request($method,$path,$payload=null){$GLOBALS['calls'][]=[$method,$path,$payload];return $path==="/modules"?$GLOBALS['registry']:$GLOBALS['observation'];}};}}}
'''
        for state,text in [('completed','Local checks completed'),('busy','Another local check is already running'),('disabled','Local checks are disabled')]:
            with self.subTest(state=state):
                body='$GLOBALS["registry"]=["installation"=>json_decode('+json.dumps(json.dumps(IDENTITY))+',true)];'
                body+='$GLOBALS["observation"]=["schema_version"=>"core-next.local-observation/1","installation"=>$GLOBALS["registry"]["installation"],"status"=>'+json.dumps(state)+'];$GLOBALS["calls"]=[];'
                body+='require '+json.dumps(str(controller))+';$c=new \\Dragonhydra\\Component\\Dragonhydra\\Administrator\\Controller\\ActionsController();'
                body+='$c->app=new class{function getIdentity(){return new class{function authorise($a,$c){return true;}};}};$c->observe();echo json_encode([$GLOBALS["calls"],$GLOBALS["redirect"]]);'
                calls,redirect=json.loads(self.php(body,prefix))
                self.assertEqual(calls,[['GET','/modules',None],['POST','/modules/observe',[]]])
                self.assertIn(text,redirect[1])
                self.assertEqual(redirect[2],'message')

    def test_history_schema_and_other_instance_are_rejected_before_workflow_render(self):
        match,history=fixtures()
        history['schema_version']='other-product/1'
        body='$m=json_decode('+json.dumps(json.dumps(match))+',true);$h=json_decode('+json.dumps(json.dumps(history))+',true);'
        body+='try{W::load(function($p)use($m,$h){return str_ends_with($p,"/cognition-history")?$h:$m;},str_repeat("a",64),"core-next-fixture");echo "accepted";}catch(\\RuntimeException $e){echo "rejected";}'
        self.assertEqual(self.php(body),'rejected')

    def render(self,workflow,can_import=True):
        prefix='namespace Joomla\\CMS\\HTML{class HTMLHelper{static function _($name){return "<input type=hidden name=synthetic_csrf value=1>";}}}namespace Joomla\\CMS\\Language{class Text{static function _($key){return $key;}}}namespace Joomla\\CMS\\Router{class Route{static function _($url,$x=false){return $url;}}}'
        body='$v=new class{public $section="prediction",$center=[],$error=null,$jobId="",$data=[],$probe=[],$canImport=false,$dashboardUrl="",$workflowMatchId="",$workflowKeys=[];function render($path){ob_start();require $path;return ob_get_clean();}};'
        body+='$v->center=["installation"=>["installation_id"=>"core-next-fixture"],"modules"=>[],"workflow"=>json_decode('+json.dumps(json.dumps(workflow))+',true)];'
        body+='$v->workflowMatchId=str_repeat("a",64);$v->workflowKeys=["forecasts"=>str_repeat("f",32),"evaluations"=>str_repeat("e",32)];$v->canImport='+str(can_import).lower()+';echo $v->render('+json.dumps(str(COMPONENT/'admin/tmpl/dashboard/default.php'))+');'
        return self.php(body,prefix)

    def test_real_template_shows_retained_ids_and_uncertainty_with_honest_pending(self):
        workflow=self.loaded()['result']
        rendered=self.render(workflow)
        for value in ('synthetic-model','synthetic-prediction','synthetic-target','fixture-build','40.00%','Synthetic uncertainty',
                      'No eligible later outcome is attached','Pending is not accuracy','task=actions.forecast','task=actions.evaluate','synthetic_csrf'):
            self.assertIn(value,rendered)
        self.assertNotIn('PRIVATE_FIXTURE_VALUE',rendered)
        workflow['match']['status']='finished';workflow['forecast_available']=False
        finished=self.render(workflow)
        self.assertNotIn('task=actions.forecast',finished)
        self.assertIn('Finished results cannot become historical prospective forecasts',finished)
        reader=self.render(workflow,False)
        self.assertNotIn('task=actions.evaluate',reader)


if __name__=='__main__':unittest.main()
