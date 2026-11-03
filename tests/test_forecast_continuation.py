"""Synthetic guard mutations of sanitized proof copies. No API/lifecycle calls."""
import ast,copy,importlib.util,json,os,stat,tempfile,unittest,io
from contextlib import redirect_stdout
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).parent/'installation/forecast_continuation'
EVIDENCE=Path(__file__).resolve().parents[1]/'docs/reconciliation/evidence/forecast-preservation-20261103'
s=importlib.util.spec_from_file_location('contract',HERE/'continuation_contract.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
PROPOSAL=c.ROOT/'proposals/continuation'
FILES={'root_cause':'ROOT-CAUSE.json','repair_verification':'REPAIR-VERIFICATION.json','original_audit':'ORIGINAL-SNAPSHOT-AUDIT.json','contract_tests':'FOCUSED-TESTS.json','isolated_reproduction':'ISOLATED-RUNTIME.json','installed_identity':'INSTALLED-READBACK.json','preapproval_live_readback':'INSTALLED-JOOMLA.json'}
class Guards(unittest.TestCase):
    def setUp(self):
        self.b={k:json.loads((EVIDENCE/v).read_text(encoding='utf-8-sig')) for k,v in FILES.items()}
        self.r=json.loads((PROPOSAL/'ReconciliationReceipt.example.json').read_text());self.a=json.loads((PROPOSAL/'CoordinatorApproval.example.json').read_text())
        self.r.update(status='VERIFIED',verdict='EXPECTED_WORKFLOW_DELTA_VERIFIED',operation_root=str(c.OP),original_operation_root=str(c.OLD));self.r['corrected_contract'].update(sha256=c.AUDITOR,exact_schema_objects_sha256=self.b['original_audit']['schema_contract_sha256']);self.a['approved']=True;self.a['operation_root']=str(c.OP)
    def valid(self):c.common(self.r,self.a);c.proof_semantics(self.r,self.b)
    def rejects(self):
        with self.assertRaises(c.Refused):self.valid()
    def test_01_current_root_final_proofs_semantics_positive(self):self.valid()
    def test_02_pending_root_cause_rejected(self):self.b['root_cause']['status']='PENDING';self.rejects()
    def test_03_failed_root_cause_not_positive(self):self.b['root_cause']['status']='FAILED';self.rejects()
    def test_04_repair_wrapper_pass_without_source_rejected(self):self.b['repair_verification']={'passed':True};self.rejects()
    def test_05_old_proposal_auditor_not_integrated_rejected(self):self.b['original_audit']['auditor_sha256']='36a446f5563c12f1deb1263382665c4fbf6f8cf44491289317cf0b51dde4a725';self.rejects()
    def test_06_wrong_original_snapshot_rejected(self):self.b['original_audit']['before_sha256']='f'*64;self.rejects()
    def test_07_wrong_original_counts_rejected(self):self.b['original_audit']['counts']['protected_retained_rows']=759;self.rejects()
    def test_08_failed_focused_test_rejected(self):self.b['contract_tests']['failed']=1;self.rejects()
    def test_09_duplicate_case_ids_rejected(self):self.b['contract_tests']['case_ids'][-1]=self.b['contract_tests']['case_ids'][0];self.rejects()
    def test_10_reproduction_using_original_instance_rejected(self):self.b['isolated_reproduction']['installation_id']=c.ID;self.rejects()
    def test_11_reproduction_wrapper_without_real_checks_rejected(self):self.b['isolated_reproduction']['checks']=[];self.rejects()
    def test_12_duplicate_named_check_cannot_hide_failure(self):self.b['isolated_reproduction']['checks'].insert(0,{'name':self.b['isolated_reproduction']['checks'][0]['name'],'status':'FAIL'});self.rejects()
    def test_13_restart_new_records_rejected(self):self.b['isolated_reproduction']['restart_audit']['counts']['new_cognitive_records']=1;self.rejects()
    def test_14_old_false_failure_not_reproduced_rejected(self):self.b['isolated_reproduction']['old_comparison_reproduction']['passed']=True;self.rejects()
    def test_15_installed_wrapper_without_rich_baseline_rejected(self):self.b['preapproval_live_readback']['database_after']={};self.rejects()
    def test_16_installed_other_jobs_rejected(self):self.b['installed_identity']['workflow']['forecast_job_id']='a'*32;self.rejects()
    def test_17_original_forecast_cannot_be_promoted(self):self.r['original_forecast_status']='PASS';self.rejects()
    def test_18_boolean_lookalike_approval_rejected(self):self.a['approved']='true';self.rejects()
    def test_19_original_operation_cannot_be_reused(self):self.r['operation_root']=str(c.OLD);self.rejects()
    def test_20_source_and_setup_foreign_rejected(self):self.a['source_commit']='a'*40;self.rejects()
    def test_21_reader_only_two_phases_and_literal_get(self):
        tree=ast.parse((HERE/'Read-Continuation.py').read_text());phases=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PHASES' for t in n.targets));self.assertEqual(phases,{'reconcile':None,'backup':'reconcile'})
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='Request'];self.assertGreater(len(calls),0)
        for call in calls:self.assertEqual(next(ast.literal_eval(k.value) for k in call.keywords if k.arg=='method'),'GET')
    def test_22_full_ancestor_reparse_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);parent=root/'parent';parent.mkdir();file=parent/'x';file.write_text('fixture');real=Path.lstat
            def fake(p,*a,**k):
                value=real(p,*a,**k)
                if p==parent:
                    class S:st_mode=value.st_mode;st_file_attributes=0x400
                    return S()
                return value
            with patch.object(Path,'lstat',fake):
                with self.assertRaises(c.Refused):c.ordinary(file,root)
    def test_23_outside_and_traversal_rejected(self):
        with self.assertRaises(c.Refused):c.ordinary(c.OLD/'phase-Forecast.json',c.OP)
        with self.assertRaises(c.Refused):c.ordinary(c.OP/'..'/'x',c.OP,False)
    def test_24_noninteger_audit_count_rejected(self):self.b['original_audit']['counts']['new_jobs']=2.0;self.rejects()
    @unittest.skipUnless(os.name=='nt' and (c.ROOT/'installed-joomla-history-r1/read_history.py').is_file() and (c.ROOT.parents[1]/'verify_disposable_workstation_dev5.py').is_file() and (c.ROOT.parents[1]/'profiles'/c.ID/'installation-profile.json').is_file(), 'Requires the original Windows LAB definitions/profile for the mock-GET reader adapter; no live requests')
    def test_25_full_reader_validate_only_creates_no_output_with_mock_gets(self):
        spec=importlib.util.spec_from_file_location('reader_fixture',HERE/'Read-Continuation.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
        profile=json.loads((r.LAB/'profiles'/c.ID/'installation-profile.json').read_text())
        cfg={'installation_id':c.ID,'source_commit':c.SOURCE,'version':c.VERSION,'api_port':18860,'web_port':18861,'database_port':18862}
        records={'models':[{'record_id':'fixture-model-'+str(i)} for i in range(5)],'predictions':[{'record_id':'fixture-prediction-'+str(i)} for i in range(5)],'outcomes':[],'evaluations':[]}
        projected={'schema_sha256':'a'*64,'protected_tables':{'fixture_'+str(i):{'rows':0,'sha256':'b'*64} for i in range(20)},'job_count':3,'integrity_check':'ok'};configuration={'fixture':'c'*64};baseline={'database_after':projected,'configuration_fingerprints':configuration}
        now=datetime.now(timezone.utc);identity={k:profile[k] for k in ('service_name','installation_id','source_commit','build_id')};identity.update(observed_at=(now-timedelta(seconds=1)).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),evidence_expires_at=(now+timedelta(seconds=40)).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),verification_scope='BOUND_SUPERVISOR_SERVICE_IDENTITY_ONLY')
        payloads={'/health/ready':{'source_sha':c.SOURCE,'version':c.VERSION},'/system':{'installation':{'installation_id':c.ID,'source_commit':c.SOURCE}},'/modules?scope=all':{'items':[{'id':'runtime_supervisor','runtime_state':'READY','service_identity':identity,'observation':{'service_identity':identity}}]},'/matches/'+c.TARGET+'/cognition-history':{'installation':{'installation_id':c.ID},'records':records,'counts':{k:len(v) for k,v in records.items()}}}
        for jid,kind in ((c.FORECAST,'forecast'),(c.EVALUATION,'evaluation')):payloads['/jobs/'+jid]={'kind':kind,'status':'succeeded','payload':{'match_id':c.TARGET},'result':{'status':'pending' if kind=='evaluation' else 'persisted'}}
        class Response:
            status=200
            def __init__(self,p):self.p=p
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,*args):return c.canonical(self.p)
        class Opener:
            def open(self,req,timeout):
                self_outer.assertEqual(req.get_method(),'GET');return Response(payloads[req.full_url.split('/dragon/api/v1',1)[1]])
        self_outer=self;real_read=Path.read_text;real_imports=r.imports
        def reads(p,*args,**kw):
            if p==r.STATE/'workstation.json':return json.dumps(cfg)
            if p==r.STATE/'client/local-session.json':return '{"token":"synthetic-fixture-token"}'
            return real_read(p,*args,**kw)
        def imports():
            real_imports();r.configuration=lambda:configuration;r.validate_state_inputs=lambda:None;r.live_projection=lambda:copy.deepcopy(projected)
            r.db_snapshot=lambda *_:self.fail('ValidateOnly created snapshot output')
        # Never bind a synthetic output to a completed historical operation.
        # Create the fixture before forbidding writes, and leave its output absent.
        with tempfile.TemporaryDirectory() as temporary:
            fixture_op=Path(temporary)/'operation-not-created'
            args=SimpleNamespace(phase='reconcile',receipt='fixture',receipt_sha256='d'*64,approval='fixture',approval_sha256='e'*64,output=str(fixture_op/'acceptance/reconcile'),previous=None,validate_only=True)
            output=io.StringIO()
            with patch.object(r.cc,'OP',fixture_op),patch.object(r.cc,'validate',return_value=({},baseline)),patch.object(r.cc,'HISTORY',c.sha(c.canonical(records))),patch.object(r,'imports',side_effect=imports),patch.object(r,'build_opener',return_value=Opener()),patch.object(Path,'read_text',reads),patch.object(Path,'mkdir',side_effect=AssertionError('OUTPUT_DIRECTORY_CREATED')),patch.object(Path,'write_text',side_effect=AssertionError('OUTPUT_FILE_CREATED')),redirect_stdout(output):
                self.assertEqual(r.run(args),0)
            self.assertFalse(fixture_op.exists())
        value=json.loads(output.getvalue());self.assertTrue(value['passed']);self.assertTrue(value['validate_only']);self.assertFalse(value['output_created']);self.assertTrue(all(x['method']=='GET' for x in value['requests']))
    def test_26_existing_output_rejected_before_imports_or_requests(self):
        spec=importlib.util.spec_from_file_location('reader_existing_output',HERE/'Read-Continuation.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
        with tempfile.TemporaryDirectory() as temporary:
            fixture_op=Path(temporary);output=fixture_op/'acceptance/reconcile';output.mkdir(parents=True)
            args=SimpleNamespace(phase='reconcile',receipt='fixture',receipt_sha256='d'*64,approval='fixture',approval_sha256='e'*64,output=str(output),previous=None,validate_only=True)
            with patch.object(r.cc,'OP',fixture_op),patch.object(r.cc,'validate',return_value=({},{})),patch.object(r,'imports',side_effect=AssertionError('IMPORTS_AFTER_USED_OUTPUT')),patch.object(r,'build_opener',side_effect=AssertionError('REQUEST_AFTER_USED_OUTPUT')):
                with self.assertRaisesRegex(r.cc.Refused,'EXACT_FRESH_ACCEPTANCE_OUTPUT_REQUIRED'):r.run(args)
if __name__=='__main__':unittest.main(verbosity=2)
