"""Exercise the actual site PHP adapter against isolated API doubles, no live state."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
PHP = ROOT / 'build/workstation/test-install/application files/web/php/php.exe'
MODEL = ROOT / 'server/joomla/com_dragonhydra/site/src/Model/WorkspaceModel.php'
KERNEL = ROOT / 'server/joomla/com_dragonhydra/site/src/Service/Kernel.php'


@unittest.skipUnless(os.name == 'nt' and PHP.is_file(), 'Existing matching private PHP required')
class JoomlaFrontendModelTests(unittest.TestCase):
    def php(self, body):
        source = ('namespace Joomla\\CMS\\MVC\\Model { class BaseDatabaseModel {} } '
                  'namespace { define("_JEXEC",1); require ' + json.dumps(str(MODEL))
                  + '; require ' + json.dumps(str(KERNEL)) + '; '
                  'use Dragonhydra\\Component\\Dragonhydra\\Site\\Model\\WorkspaceModel as W; '
                  'use Dragonhydra\\Component\\Dragonhydra\\Site\\Service\\Kernel as K; '
                  + body + ' }')
        result = subprocess.run([str(PHP), '-n', '-r', source], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_anonymous_workspace_never_reads_backend_or_private_data(self):
        result = self.php('$called=0;$m=new W();$r=$m->build([],false,function($p)use(&$called){$called++;return ["items"=>[["private"=>true]]];});'
                          'echo json_encode(["called"=>$called,"workspace"=>$r]);')
        self.assertEqual(result['called'], 0)
        self.assertFalse(result['workspace']['authenticated'])
        self.assertIsNone(result['workspace']['summary']['total_matches'])
        self.assertEqual(result['workspace']['matches']['items'], [])

    def test_real_site_identity_and_acl_both_required(self):
        result = self.php('class U {function __construct(public $id,public $guest,public $allowed){}'
                          'function authorise($a,$c){return $this->allowed && $a==="core.manage" && $c==="com_dragonhydra";}}'
                          'echo json_encode([K::canRead(new U(0,true,true)),K::canRead(new U(5,false,false)),K::canRead(new U(5,false,true))]);')
        self.assertEqual(result, [False, False, True])

    def test_empty_backend_is_zero_records_and_not_fake_unavailability(self):
        result = self.php('$m=new W();$r=$m->build([],true,function($p){'
                          'if($p==="/health/ready")return ["status"=>"ready"];'
                          'return ["items"=>[],"total"=>0];});echo json_encode($r);')
        self.assertIsNone(result['error'])
        self.assertEqual(result['summary']['total_matches'], 0)
        self.assertEqual(result['summary']['total_teams'], 0)
        self.assertEqual(result['summary']['upcoming'], [])

    def test_backend_exception_is_useful_and_omits_private_error_details(self):
        result = self.php('$m=new W();echo json_encode($m->build([],true,function($p){throw new \\RuntimeException("PRIVATE_RUNTIME_DETAIL");}));')
        self.assertIsNone(result['health'])
        self.assertIsNone(result['summary']['total_matches'])
        self.assertIn('temporarily unavailable', result['error'])
        self.assertNotIn('PRIVATE_RUNTIME_DETAIL', json.dumps(result))

    def test_unavailable_record_does_not_falsely_mark_healthy_backend_offline(self):
        result = self.php('$m=new W();echo json_encode($m->build(["section"=>"matches","match_id"=>str_repeat("a",64)],true,function($p){'
                          'if($p==="/health/ready")return ["status"=>"ready"];'
                          'if($p==="/teams" || $p==="/competitions")return ["items"=>[]];'
                          'throw new \\RuntimeException("MATCH_NOT_FOUND");}));')
        self.assertEqual(result['health']['status'], 'ready')
        self.assertIn('not available', result['error'])

    def test_team_filter_retains_source_scope_and_pages_filtered_records(self):
        result = self.php('$f=W::filters(["q"=>"Albion","competition"=>str_repeat("c",64),"status"=>"finished","limit"=>10,"offset"=>0]);'
                          '$row=["id"=>str_repeat("a",64),"competition_id"=>str_repeat("c",64),"status"=>"finished","event_date"=>"2026-01-01","home"=>["name"=>"Albion"],"away"=>["name"=>"Visitors"]];'
                          '$other=$row;$other["competition_id"]=str_repeat("d",64);$scheduled=$row;$scheduled["status"]="scheduled";'
                          'echo json_encode(W::filterTeamMatches([$other,$scheduled,$row],$f));')
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['items'][0]['competition_id'], 'c' * 64)
        self.assertEqual(result['items'][0]['status'], 'finished')

    def test_search_is_encoded_and_no_arbitrary_proxy_path_is_accepted(self):
        result = self.php('$paths=[];$m=new W();$r=$m->build(["section"=>"matches","q"=>"Alpha & Beta"],true,function($p)use(&$paths){$paths[]=$p;return ["items"=>[],"total"=>0,"status"=>"ready"];});'
                          'try{W::filters(["match_id"=>"../../administrator"]);$invalid=false;}catch(\\InvalidArgumentException $e){$invalid=true;}'
                          'echo json_encode(["paths"=>$paths,"invalid_rejected"=>$invalid]);')
        self.assertIn('/matches?search=Alpha%20%26%20Beta&limit=25&offset=0', result['paths'])
        self.assertTrue(result['invalid_rejected'])

    def test_overview_performs_no_analysis_inference_or_mutation_operation(self):
        result = self.php('$paths=[];$m=new W();$r=$m->build([],true,function($p)use(&$paths){$paths[]=$p;return ["items"=>[],"total"=>0,"status"=>"ready"];});echo json_encode($paths);')
        self.assertFalse(any('prediction' in path or 'analysis' in path or 'export' in path or '/test' in path or '/sync' in path for path in result))

    def test_inconsistent_pagination_stops_instead_of_loading_forever(self):
        result = self.php('$called=0;$m=new W();$r=$m->build([],true,function($p)use(&$called){$called++;'
                          'if(str_starts_with($p,"/matches?status=scheduled"))return ["items"=>[],"total"=>1];'
                          'return ["items"=>[],"total"=>0,"status"=>"ready"];});echo json_encode(["workspace"=>$r,"calls"=>$called]);')
        self.assertLess(result['calls'], 10)
        self.assertIsNotNone(result['workspace']['error'])

    def test_report_page_rejects_non_export_job_and_preserves_backend_health(self):
        result = self.php('$m=new W();echo json_encode($m->build(["section"=>"reports","job_id"=>str_repeat("a",32)],true,function($p){'
                          'if(str_starts_with($p,"/jobs/"))return ["kind"=>"import_public","status"=>"succeeded"];'
                          'return ["items"=>[],"total"=>0,"status"=>"ready"];}));')
        self.assertIsNone(result['job'])
        self.assertIsNotNone(result['error'])
        self.assertEqual(result['health']['status'], 'ready')


if __name__ == '__main__':
    unittest.main()
