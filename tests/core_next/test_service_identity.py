"""Synthetic service binding and extracted supervisor functions; no live services."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import json,os,subprocess,tempfile,unittest
from pathlib import Path

from dragonhydra.kernel.contracts import KernelConfig,ServiceIdentity,sanitized_metrics
from dragonhydra.kernel.ports import ApplicationContext,StoragePort
from dragonhydra.kernel.supporting import SupportingObservations,definitions
from dragonhydra.kernel.registry import ModuleRegistry
from dragonhydra.kernel.local_observer import LocalObserver

ROOT=Path(__file__).resolve().parents[2]
LAB=ROOT.parent/(ROOT.name+'-LAB')
SHELLS=[Path('C:/Program Files/PowerShell/7/pwsh.exe'),Path('C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe')]
SCOPE='BOUND_SUPERVISOR_SERVICE_IDENTITY_ONLY'


class ServiceIdentityTests(unittest.TestCase):
    def setUp(self):
        (LAB/'tests').mkdir(exist_ok=True)
        t=tempfile.TemporaryDirectory(dir=LAB/'tests',prefix='service-identity-');self.addCleanup(t.cleanup)
        self.root=Path(t.name);self.state=self.root/'state/kernel';self.state.mkdir(parents=True)
        self.at=datetime(2026,11,2,tzinfo=timezone.utc)
        self.config=KernelConfig('core-next-'+'a'*32,source_commit='b'*40,build_id='synthetic-build')
        self.cfg={'product':'DRAGONHYDRA CORE NEXT','installation_id':self.config.installation_id,
            'source_commit':self.config.source_commit,'build_id':self.config.build_id,
            'state_root':str(self.state.parent),'install_root':str(self.root/'application'),
            'service_name':'DragonhydraCoreNextSynthetic','api_port':18891,'web_port':18892,'database_port':18893,
            'admin_password':'SYNTHETIC_PRIVATE_CANARY_NOT_A_CREDENTIAL'}
        self.cfgpath=self.state.parent/'workstation.json';self.cfgpath.write_text(json.dumps(self.cfg))
        self.receipt_path=self.state.parent/'runtime-observations.json'
        def forbidden():raise AssertionError('No write connection permitted')
        context=ApplicationContext(StoragePort(self.state,self.state/'core.sqlite3',ROOT,self.state/'exports',forbidden),None,lambda:self.at.isoformat())
        self.source=SupportingObservations(context,self.config,lambda:self.at)
        definition=next(d for d in definitions('fixture') if d.id=='runtime_supervisor')
        self.registry=ModuleRegistry((definition,),{},supporting={'runtime_supervisor':self.source.bindings()['runtime_supervisor']},
            ttl_seconds=300,clock=lambda:self.at,installation_id=self.config.installation_id,
            build_identity=self.config.build_id+':'+self.config.source_commit,source_commit=self.config.source_commit)

    def receipt(self,*,identity=True,changes=None,identity_changes=None):
        data={'schema_version':2,'observer':'core-next.supervisor',
            **{k:self.cfg[k] for k in ('installation_id','source_commit','build_id','service_name')},
            'api_pid':os.getpid(),'supervisor_pid':1234,'api_verified':True,
            'observed_at':self.at.isoformat(),'last_success_at':self.at.isoformat(),
            'expires_at':(self.at+timedelta(seconds=45)).isoformat(),'checks':{}}
        if identity:
            data['service_identity']={'schema_version':1,'service_name':self.cfg['service_name'],
                'service_process_id':4321,'supervisor_process_id':1234,'observed_at':self.at.isoformat(),
                'verification_scope':'SCM_RUNNING_SERVICE_AND_SUPERVISOR_PARENT_ONLY'}
            data['service_identity'].update(identity_changes or {})
        data.update(changes or {});self.receipt_path.write_text(json.dumps(data));return data

    def item(self):
        self.registry.refresh('runtime_supervisor');return self.registry.item('runtime_supervisor')

    def assertAbsent(self,item):
        self.assertNotIn('service_identity',item);self.assertNotIn('service_identity',item['observation'])
        self.assertNotIn('SYNTHETIC_PRIVATE_CANARY',json.dumps(item))

    def test_configured_name_without_scm_evidence_is_never_public_identity(self):
        self.receipt(identity=False);item=self.item()
        self.assertEqual(item['state'],'READY');self.assertAbsent(item)
        self.assertNotIn('service_name',item['sanitized_metrics'])

    def test_bound_identity_has_exact_public_shape_and_read_does_not_probe_or_renew(self):
        self.receipt();item=self.item();identity=item['service_identity']
        self.assertEqual(identity,item['observation']['service_identity'])
        self.assertEqual(set(identity),{'service_name','installation_id','source_commit','build_id','observed_at','evidence_expires_at','verification_scope'})
        self.assertEqual(identity['verification_scope'],SCOPE);self.assertEqual(identity['build_id'],self.config.build_id)
        self.assertEqual(identity['observed_at'],'2026-11-02T00:00:00.000000Z')
        self.assertEqual(identity['evidence_expires_at'],'2026-11-02T00:00:45.000000Z')
        self.source.observe=lambda unused:(_ for _ in ()).throw(AssertionError('Cached GET must not probe'))
        self.at+=timedelta(seconds=20);again=self.registry.item('runtime_supervisor')
        self.assertEqual(again['service_identity'],identity)
        self.assertEqual(again['observation']['observed_at'],item['observation']['observed_at'])

    def test_malformed_or_non_scm_identity_is_omitted_without_discarding_other_status(self):
        variants=[{'schema_version':2},{'schema_version':True},{'schema_version':1.0},{'service_name':'DragonhydraOther'},
            {'verification_scope':'CONFIGURED_NAME_ONLY'},{'service_process_id':None},
            {'service_process_id':True},{'service_process_id':0},{'service_process_id':1234},{'service_process_id':2**32},
            {'supervisor_process_id':4321},{'supervisor_process_id':True},
            {'private_password':'SYNTHETIC_PRIVATE_CANARY_NOT_A_CREDENTIAL'}]
        for fields in variants:
            with self.subTest(fields=tuple(fields)):
                self.receipt(identity_changes=fields);item=self.item();self.assertEqual(item['state'],'READY');self.assertAbsent(item)
        for name in ['Dragonhydra\nInjected','Dragonhydra'+('x'*61),'https://SYNTHETIC_PRIVATE_CANARY','OtherService']:
            with self.subTest(name_length=len(name)):
                self.cfg['service_name']=name;self.cfgpath.write_text(json.dumps(self.cfg));self.receipt();self.assertAbsent(self.item())

    def test_foreign_profile_source_build_or_process_receipts_never_supply_identity(self):
        for fields in [{'installation_id':'core-next-'+'c'*32},{'source_commit':'d'*40},{'build_id':'other-build'},
                {'api_pid':os.getpid()+1},{'supervisor_pid':9999},{'api_verified':False},{'observer':'unknown'},{'schema_version':2.0}]:
            with self.subTest(fields=tuple(fields)):
                self.receipt(changes=fields);self.assertAbsent(self.item())

    def test_missing_future_stale_naive_or_upstream_expired_clocks_omit_identity(self):
        for value in [None,'not-a-clock',self.at.replace(tzinfo=None).isoformat(),
                (self.at+timedelta(seconds=1)).isoformat(),(self.at-timedelta(seconds=91)).isoformat()]:
            with self.subTest(value=value):
                self.receipt(identity_changes={'observed_at':value});self.assertAbsent(self.item())
        self.receipt();self.registry.refresh('runtime_supervisor');self.at+=timedelta(seconds=45)
        self.assertAbsent(self.registry.item('runtime_supervisor'))
        self.assertEqual(self.registry.item('runtime_supervisor')['runtime_state'],'EXPIRED')

    def test_scm_sample_expiry_can_be_earlier_but_never_later_than_upstream(self):
        self.receipt(identity_changes={'observed_at':(self.at-timedelta(seconds=80)).isoformat()})
        item=self.item();self.assertEqual(item['service_identity']['evidence_expires_at'],'2026-11-02T00:00:10.000000Z')
        self.at+=timedelta(seconds=10);self.assertAbsent(self.registry.item('runtime_supervisor'))
        self.assertEqual(self.registry.item('runtime_supervisor')['runtime_state'],'READY') # Service identity expired before heartbeat status.

    def test_registry_projection_rejects_wrong_enclosing_identity_build_or_expected_source(self):
        self.receipt();self.registry.refresh('runtime_supervisor');proof=self.registry.observations['runtime_supervisor']
        for fields in [{'installation_id':'foreign'},{'module_id':'web_server'},{'build_identity':'foreign-build'}]:
            with self.subTest(fields=fields):
                # Corruption cannot be constructed through the typed Observation contract.
                with self.assertRaises(ValueError):replace(proof,**fields)
        self.registry.source_commit='c'*40;self.assertAbsent(self.registry.item('runtime_supervisor'))

    def test_typed_scope_and_metrics_remain_separate(self):
        self.receipt();identity=self.source.observe('runtime_supervisor')['service_identity']
        for fields in [{'verification_scope':'ADMINISTRATOR_ACCESS'},{'service_name':'Dragonhydra\nsecret'},
                {'evidence_expires_at':self.at},{'source_commit':'not-source'}]:
            with self.subTest(fields=tuple(fields)):
                with self.assertRaises(ValueError):replace(identity,**fields)
        self.assertEqual(sanitized_metrics({'service_name':'SYNTHETIC_PRIVATE_CANARY'}),{})
        for metric in ['configured','process_id']:
            with self.assertRaises(ValueError):sanitized_metrics({metric:'SYNTHETIC_PRIVATE_CANARY'})

    def test_local_observer_carries_identity_but_history_does_not_restore_it(self):
        self.receipt();observer=LocalObserver(self.registry,self.source,self.state,self.config.identity(),interval=30,clock=lambda:self.at)
        observer.start();self.addCleanup(observer.stop)
        self.assertIn('service_identity',self.registry.item('runtime_supervisor'))
        cache=json.loads(observer.path.read_text());self.assertNotIn('service_identity',json.dumps(cache))
        self.registry.observations.clear();observer._load_history()
        self.assertAbsent(self.registry.item('runtime_supervisor'))
        self.assertEqual(self.registry.item('runtime_supervisor')['runtime_state'],'UNVERIFIED')


@unittest.skipUnless(os.name=='nt' and all(p.is_file() for p in SHELLS),'Existing Windows PowerShell5.1 and7 required')
class ServiceProducerTests(unittest.TestCase):
    def invoke(self,shell,mode='reader'):
        (LAB/'tests').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=LAB/'tests',prefix='service-producer-') as scratch:
            runner=Path(scratch)/'fixture.ps1'
            runner.write_text(r'''param($Source,$Mode)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
$tokens=$null;$errors=$null;$ast=[Management.Automation.Language.Parser]::ParseFile($Source,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'SOURCE_PARSE_FAILED'}
foreach($fn in $ast.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst]},$false)){
 if($fn.Name -in @('Read-CoreNextHeartbeatServiceEvidence','Get-CoreNextHeartbeatServiceIdentity')){Invoke-Expression $fn.Extent.Text}
}
$script:cfg=@{service_name='DragonhydraCoreNextSynthetic';install_root='C:\synthetic\application';state_root='C:\synthetic\state'}
if($Mode -eq 'deadline'){
 ${function:Read-CoreNextHeartbeatServiceEvidence}={param($Name,$ExpectedImage,$SupervisorId) [Threading.Thread]::Sleep(5000);return @{service_name=$Name;supervisor_process_id=$SupervisorId}}
 $clock=[Diagnostics.Stopwatch]::StartNew();$one=Get-CoreNextHeartbeatServiceIdentity;$elapsed=$clock.ElapsedMilliseconds
 $pending=$script:coreNextServiceQuery.handle
 $two=Get-CoreNextHeartbeatServiceIdentity;$same=[object]::ReferenceEquals($pending,$script:coreNextServiceQuery.handle)
 $null=$pending.AsyncWaitHandle.WaitOne(8000);$three=Get-CoreNextHeartbeatServiceIdentity
 @{first_ms=$elapsed;first_absent=($null -eq $one);second_absent=($null -eq $two);same_request=$same;completed=($three.service_name -ceq $script:cfg.service_name);disposed=($null -eq $script:coreNextServiceQuery)}|ConvertTo-Json -Compress
 return
}
$script:calls=@();$script:case='valid'
function Get-CimInstance {
 param($ClassName,$Filter,$OperationTimeoutSec,$ErrorAction)
 $script:calls+=@{class=$ClassName;filter=$Filter;timeout=$OperationTimeoutSec}
 if($script:case -eq 'denied'){throw 'SYNTHETIC_PRIVATE_ERROR_NOT_FOR_OUTPUT'}
 if($ClassName -ceq 'Win32_Service'){
  if($script:case -eq 'missing'){return}
  return [pscustomobject]@{Name=$(if($script:case -eq 'foreign'){'DragonhydraOther'}else{'DragonhydraCoreNextSynthetic'});State=$(if($script:case -eq 'stopped'){'Stopped'}else{'Running'});ProcessId=4321;PathName=$(if($script:case -eq 'path'){'wrong'}else{'synthetic exact image'})}
 }
 return [pscustomobject]@{ProcessId=1234;ParentProcessId=$(if($script:case -eq 'parent'){9999}else{4321})}
}
$rows=@()
foreach($case in @('valid','stopped','missing','foreign','path','parent','denied')){
 $script:case=$case;$script:calls=@();$got=Read-CoreNextHeartbeatServiceEvidence 'DragonhydraCoreNextSynthetic' 'synthetic exact image' 1234
 $rows+=@{case=$case;present=($null -ne $got);scope=$(if($got){$got.verification_scope}else{$null});calls=$script:calls}
}
$script:calls=@();$bad=Read-CoreNextHeartbeatServiceEvidence 'DragonhydraInjected''Name' 'image' 1234
$newline=Read-CoreNextHeartbeatServiceEvidence "DragonhydraInjected`n" 'image' 1234
@{rows=$rows;invalid_name_absent=($null -eq $bad -and $null -eq $newline);invalid_name_calls=$script:calls.Count}|ConvertTo-Json -Depth 8 -Compress
''',encoding='utf-8')
            quote=lambda value:"'"+str(value).replace("'","''")+"'"
            bootstrap='& ([ScriptBlock]::Create([IO.File]::ReadAllText('+quote(runner)+'))) -Source '+quote(ROOT/'packaging/windows/workstation/Workstation.ps1')+' -Mode '+quote(mode)
            result=subprocess.run([str(shell),'-NoProfile','-Command',bootstrap],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertNotIn('SYNTHETIC_PRIVATE_ERROR',result.stdout)
            return json.loads(result.stdout)

    def test_exact_running_service_and_supervisor_parent_are_required_on_both_hosts(self):
        for shell in SHELLS:
            with self.subTest(host=str(shell)):
                result=self.invoke(shell)
                for row in result['rows']:
                    self.assertEqual(row['present'],row['case']=='valid',row)
                    for call in row['calls']:
                        self.assertEqual(call['timeout'],1)
                        self.assertIn(call['filter'],["Name='DragonhydraCoreNextSynthetic'",'ProcessId=1234'])
                self.assertEqual(result['rows'][0]['scope'],'SCM_RUNNING_SERVICE_AND_SUPERVISOR_PARENT_ONLY')
                self.assertTrue(result['invalid_name_absent']);self.assertEqual(result['invalid_name_calls'],0)

    def test_stalled_query_has_bounded_wait_and_only_one_inflight_runspace(self):
        for shell in SHELLS:
            with self.subTest(host=str(shell)):
                result=self.invoke(shell,'deadline')
                self.assertTrue(result['first_absent']);self.assertTrue(result['second_absent'])
                self.assertTrue(result['same_request']);self.assertTrue(result['completed']);self.assertTrue(result['disposed'])
                self.assertLess(result['first_ms'],2400,result)


if __name__=='__main__':unittest.main()
