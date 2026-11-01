"""Typed cognition workflow, real administrator guards and actual retained-history templates."""
import hashlib
import hmac
import http.server
import json
from pathlib import Path
import subprocess
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'server/joomla/com_dragonhydra'
PHP = ROOT / 'build/workstation/test-install/application files/web/php/php.exe'
ADAPTER = COMPONENT / 'admin/src/Service/SystemWorkflow.php'
CONTROLLER = COMPONENT / 'admin/src/Controller/ActionsController.php'
FIXTURE = ROOT / 'tests/installation/joomla_control_render_fixture.php'


def history():
    match_id = 'a' * 64
    match = {'id': match_id, 'status': 'scheduled', 'home': {'name': 'Synthetic home'},
             'away': {'name': 'Synthetic away'}, 'competition': 'Synthetic league', 'event_date': '2099-01-01'}
    data = {'match_id': match_id, 'cutoff': '2026-11-01T00:00:00Z', 'source_id': 'synthetic-source',
            'target_evidence_id': 'synthetic-target', 'fixture_key': 'synthetic-fixture',
            'records': {'models': [{'record_id': 'synthetic-model', 'model_name': 'frequency', 'model_version': 'fixture-only',
                                    'data_cutoff': '2026-11-01T00:00:00Z', 'parameters': {'secret': 'PRIVATE_FIXTURE_SECRET',
                                    'workflow': {'generated_at': '2026-11-01T00:00:01Z',
                                                 'uncertainty': {'items': ['Synthetic uncertainty']},
                                                 'adaptation': {'reason': 'INSUFFICIENT_COMPARABLE_OPERATIONAL_EVALUATIONS',
                                                                'minimum_cases': 20, 'evidence_ids': []}}}}],
                        'predictions': [{'record_id': 'synthetic-prediction', 'model_run_id': 'synthetic-model',
                                         'probabilities': {'home': '0.4', 'draw': '0.3', 'away': '0.3'}}],
                        'outcomes': [], 'evaluations': []},
            'present_knowledge_holdout': {'available': False, 'reason': 'EXPLICIT_DIAGNOSTIC_NOT_REQUESTED'},
            'secret': 'PRIVATE_FIXTURE_SECRET'}
    return match, data


@unittest.skipUnless(PHP.is_file(), 'Existing matching private Windows PHP runtime required')
class JoomlaControlWorkflowTests(unittest.TestCase):
    def php(self, code):
        result = subprocess.run([str(PHP), '-n', '-r', code], capture_output=True, text=True,
                                encoding='utf-8', timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('Warning:', result.stdout)
        return result.stdout

    def prelude(self):
        return 'define("_JEXEC",1);require ' + json.dumps(str(ADAPTER)) + ';use Dragonhydra\\Component\\Dragonhydra\\Administrator\\Service\\SystemWorkflow as W;'

    def render(self, scenario):
        result = subprocess.run([str(PHP), '-n', str(FIXTURE), scenario], capture_output=True,
                                text=True, encoding='utf-8', timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('Warning:', result.stdout)
        return result.stdout

    def test_history_reads_exact_match_and_history_routes_without_inference_or_write(self):
        match, data = history()
        code = self.prelude() + '$m=json_decode(' + json.dumps(json.dumps(match)) + ',true);$h=json_decode(' + json.dumps(json.dumps(data)) + ',true);'
        code += '$paths=[];$r=W::load(function($path)use(&$paths,$m,$h){$paths[]=$path;return str_ends_with($path,"/cognition-history")?$h:$m;},str_repeat("a",64));echo json_encode([$paths,$r]);'
        paths, result = json.loads(self.php(code))
        self.assertEqual(paths, ['/matches/' + 'a' * 64, '/matches/' + 'a' * 64 + '/cognition-history'])
        self.assertEqual(result['predictions'][0]['probabilities']['home'], '0.4')
        self.assertEqual(result['models'][0]['record_id'], 'synthetic-model')
        self.assertEqual(result['models'][0]['adaptation_minimum_cases'], 20)
        self.assertFalse(result['holdout_available'])
        self.assertNotIn('PRIVATE_FIXTURE_SECRET', json.dumps(result))

    def test_non_numeric_probability_and_unavailable_evaluation_are_not_invented(self):
        match, data = history()
        data['records']['predictions'][0]['probabilities'] = {'home': 'NaN', 'draw': True, 'away': '99'}
        code = self.prelude() + 'echo json_encode(W::project(json_decode(' + json.dumps(json.dumps(match)) + ',true),json_decode(' + json.dumps(json.dumps(data)) + ',true)));'
        result = json.loads(self.php(code))
        self.assertEqual(result['predictions'][0]['probabilities'], {'home': None, 'draw': None, 'away': None})
        self.assertEqual(result['evaluations'], [])
        self.assertEqual(result['counts']['evaluations'], 0)

    def test_session_command_keys_are_stable_and_operation_scoped(self):
        code = self.prelude() + '$app=new class{public array $s=[];function getUserState($k,$d){return $this->s[$k]??$d;}function setUserState($k,$v){$this->s[$k]=$v;}};'
        code += '$a=W::formKey($app,str_repeat("a",64),"forecasts");$b=W::formKey($app,str_repeat("a",64),"forecasts");$c=W::formKey($app,str_repeat("a",64),"evaluations");echo json_encode([$a===$b,$a!==$c,(bool)preg_match("/^[a-f0-9]{32}$/D",$a)]);'
        self.assertEqual(json.loads(self.php(code)), [True, True, True])

    def test_command_is_typed_empty_input_and_invalid_requests_never_reach_backend(self):
        code = self.prelude() + '$calls=[];$send=function($m,$p,$b,$k)use(&$calls){$calls[]=[$m,$p,$b,$k];return ["id"=>str_repeat("b",32)];};'
        code += '$job=W::submit($send,str_repeat("a",64),"forecasts",str_repeat("c",32),str_repeat("c",32));$denied=0;'
        code += 'foreach([["../bad","forecasts",str_repeat("c",32),str_repeat("c",32)],[str_repeat("a",64),"arbitrary",str_repeat("c",32),str_repeat("c",32)],[str_repeat("a",64),"evaluations",str_repeat("d",32),str_repeat("c",32)]] as $args){try{W::submit($send,...$args);}catch(\\RuntimeException $e){$denied++;}}echo json_encode([$calls,$job,$denied]);'
        calls, job, denied = json.loads(self.php(code))
        self.assertEqual(calls, [['POST', '/matches/' + 'a' * 64 + '/forecasts', [], 'c' * 32]])
        self.assertEqual(job, {'id': 'b' * 32})
        self.assertEqual(denied, 3)

    def test_actual_public_actions_reject_missing_csrf_or_component_or_import_permission(self):
        for csrf, manage, importer in ((False, True, True), (True, False, True), (True, True, False)):
            for action in ('forecast', 'evaluate'):
                code = ('namespace Joomla\\CMS\\MVC\\Controller{class BaseController{public $app;public $input;}}'
                        'namespace Joomla\\CMS\\Session{class Session{static function checkToken($method){return '
                        + str(csrf).lower() + ';}}}namespace{define("_JEXEC",1);require ' + json.dumps(str(CONTROLLER)) + ';'
                        '$c=new \\Dragonhydra\\Component\\Dragonhydra\\Administrator\\Controller\\ActionsController();'
                        '$c->app=new class{function getIdentity(){return new class{function authorise($action,$component){return $component==="com_dragonhydra" && ($action==="core.manage"?'
                        + str(manage).lower() + ':' + str(importer).lower() + ');}};}};'
                        'try{$c->' + action + '();echo "accepted";}catch(\\RuntimeException $e){echo $e->getCode();}}')
                self.assertEqual(self.php(code), '403')

    def test_actual_workflow_template_displays_retained_ids_probabilities_and_pending_honestly(self):
        rendered = self.render('workflow')
        for text in ('synthetic-model-record', 'synthetic-prediction-record', 'synthetic-target-evidence',
                     'Synthetic fixture uncertainty only.', '40.00%', '30.00%', 'fixture_csrf_only',
                     'task=actions.forecast', 'task=actions.evaluate', 'No eligible later outcome is attached',
                     'No operational evaluation metrics have been persisted', 'EXPLICIT_DIAGNOSTIC_NOT_REQUESTED'):
            self.assertIn(text, rendered)
        self.assertNotIn('PRIVATE_FIXTURE_SECRET', rendered)

    def test_actual_finished_and_reader_templates_do_not_offer_forbidden_commands(self):
        finished = self.render('finished')
        self.assertNotIn('task=actions.forecast', finished)
        self.assertIn('Finished results cannot be turned into historical prospective forecasts', finished)
        reader = self.render('reader')
        self.assertNotIn('task=actions.forecast', reader)
        self.assertNotIn('task=actions.evaluate', reader)
        self.assertIn('requires the existing Import and synchronize', reader)
        self.assertIn('Retained workflow history is not available', self.render('workflow_error'))

    def test_completed_pending_evaluation_job_is_not_reported_as_evaluated(self):
        rendered = self.render('pending_job')
        self.assertIn('Retained workflow job', rendered)
        self.assertIn('LATER_RETAINED_OUTCOME_UNAVAILABLE', rendered)
        self.assertIn('Pending is not a successful evaluation', rendered)
        self.assertIn('Read persisted workflow history', rendered)
        self.assertNotIn('View imported matches', rendered)

    def test_failed_workflow_job_displays_safe_code_without_raw_exception(self):
        rendered = self.render('failed_job')
        self.assertIn('FIXTURE_WORKFLOW_FAILED', rendered)
        self.assertIn('This workflow job could not complete', rendered)
        self.assertNotIn('PRIVATE_FIXTURE_SECRET', rendered)

    @unittest.skipUnless(Path('C:/xampp/php/php.exe').is_file(), 'Existing PHP cURL runtime required')
    def test_actual_transport_signs_empty_body_and_passes_narrow_idempotency_header(self):
        seen = []
        secret = 'isolated-transport-fixture-secret-00000000'

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers['Content-Length']))
                fields = ['POST', self.path, self.headers['X-Dragon-Time'], self.headers['X-Dragon-Nonce'],
                          self.headers['X-Dragon-User'], self.headers['X-Dragon-Roles'], hashlib.sha256(raw).hexdigest()]
                valid = hmac.compare_digest(self.headers['X-Dragon-Signature'],
                    hmac.new(secret.encode(), '\n'.join(fields).encode(), 'sha256').hexdigest())
                seen.append([raw.decode(), self.headers.get('Idempotency-Key'), valid])
                payload = json.dumps({'id': 'b' * 32, 'status': 'queued'}).encode()
                self.send_response(202); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload))); self.end_headers(); self.wfile.write(payload)

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            code = 'define("_JEXEC",1);require ' + json.dumps(str(COMPONENT / 'admin/src/Service/ApiClient.php')) + ';'
            code += '$c=new \\Dragonhydra\\Component\\Dragonhydra\\Administrator\\Service\\ApiClient(' + ','.join(map(json.dumps, [f'http://127.0.0.1:{server.server_port}/dragon/api/v1', secret, 'joomla:42', 'admin'])) + ');'
            code += '$c->request("POST","/matches/".str_repeat("a",64)."/forecasts",[],str_repeat("c",32));'
            code += '$denied=0;foreach([["GET","/system/modules"],["POST","/connections/openfootball/sync"]] as $args){try{$c->request($args[0],$args[1],[],str_repeat("c",32));}catch(\\RuntimeException $e){$denied++;}}echo $denied;'
            result = subprocess.run(['C:/xampp/php/php.exe', '-r', code], capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout, '2')
            self.assertEqual(seen, [['{}', 'c' * 32, True]])
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
