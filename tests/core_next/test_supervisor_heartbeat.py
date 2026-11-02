"""Extracted passive supervisor functions; synthetic local servers, never Workstation actions."""
from datetime import datetime
import http.server
import json
import os
from pathlib import Path
import socketserver
import subprocess
import tempfile
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]
LAB=ROOT.parent/(ROOT.name+'-LAB')
SHELLS=[Path('C:/Program Files/PowerShell/7/pwsh.exe'),Path('C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe')]
TOKEN='SYNTHETIC_HEARTBEAT_FIXTURE_ONLY_0123456789'
IDENTITY={'product':'DRAGONHYDRA CORE NEXT','edition':'CORE NEXT','installation_id':'core-next-'+'a'*32,
          'source_commit':'b'*40,'build_id':'synthetic-heartbeat-build','version':'0.5.0-dev.2'}


class LocalHTTP(http.server.ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,kind,case):
        self.kind,self.case,self.seen=kind,case,[]
        super().__init__(('127.0.0.1',0),Handler)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        self.server.seen.append(self.path)
        case=self.server.case
        if self.server.kind=='api':
            if self.headers.get('Authorization')!='Bearer '+TOKEN:
                self.send_response(401);self.end_headers();return
            if self.path.endswith('/health/live'):
                identity=IDENTITY|({'source_commit':'c'*40} if case=='wrong_build' else {})
                body=json.dumps({'installation':identity}).encode()
            else: body=json.dumps({'status':'ready','version':IDENTITY['version'],'source_sha':IDENTITY['source_commit']}).encode()
        elif self.path=='/administrator/':
            body=b'<html><form><input id="mod-login-username"></form></html>'
            if case=='admin_error':
                self.send_response(500);self.end_headers();self.wfile.write(b'PRIVATE_FIXTURE_BODY');return
        else:
            body=b'<html>DRAGONHYDRA <main data-dragonhydra-workspace>Public sign-in shell</main></html>'
            if case=='redirect':
                self.send_response(302);self.send_header('Location','/forbidden-redirect');self.end_headers();return
            if case=='oversize': body=b'x'*16385
            if case=='slow': time.sleep(1.3)
        self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass


class TCPHandler(socketserver.BaseRequestHandler):
    def handle(self):pass


@unittest.skipUnless(os.name=='nt' and all(p.is_file() for p in SHELLS),'Existing Windows PowerShell5.1 and7 required')
class SupervisorHeartbeatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch=LAB/'tests';scratch.mkdir(exist_ok=True)
        cls.temp=tempfile.TemporaryDirectory(prefix='passive-supervisor-',dir=scratch)
        cls.base=Path(cls.temp.name)
        cls.runner=cls.base/'fixture.ps1'
        cls.runner.write_text(r'''param($Source,$ProfileSource,$AtomicSource)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if($PSVersionTable.PSVersion.Major -eq 5){$env:PSModulePath=Join-Path $PSHOME 'Modules'}
$fixture=[Console]::In.ReadToEnd()|ConvertFrom-Json
$StateRoot=$fixture.state
$script:cfg=$fixture.cfg
$script:children=@()
$utf8=New-Object Text.UTF8Encoding($false)
foreach($role in @('kernel','apache','database')){
  $relative=@{kernel='server\DRAGONHYDRA-Server.exe';apache='web\apache\bin\httpd.exe';database='web\mariadb\bin\mysqld.exe'}[$role]
  $script:children+=@{Role=$role;Executable=(Join-Path $fixture.cfg.install_root $relative);Process=[pscustomobject]@{Id=$fixture.process_id;HasExited=($fixture.dead_role -eq $role)}}
}
function Start-Process {throw 'HOST_MUTATION_FORBIDDEN'}
function Start-Service {throw 'HOST_MUTATION_FORBIDDEN'}
function Stop-Service {throw 'HOST_MUTATION_FORBIDDEN'}
function Stop-Process {throw 'HOST_MUTATION_FORBIDDEN'}
function Invoke-WebRequest {throw 'UNBOUNDED_HTTP_FORBIDDEN'}
function Invoke-RestMethod {throw 'UNBOUNDED_HTTP_FORBIDDEN'}
Add-Type -Path $AtomicSource
foreach($file in @($Source,$ProfileSource)){
  $tokens=$null;$errors=$null;$ast=[Management.Automation.Language.Parser]::ParseFile($file,[ref]$tokens,[ref]$errors)
  if($errors.Count){throw 'SOURCE_PARSE_FAILED'}
  foreach($fn in $ast.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst]},$false)){
    if($fn.Name -eq 'Assert-CoreNextOrdinaryPath' -or $fn.Name -match '^(Initialize|Get|Read|Invoke|Test|Save|Write)-CoreNext(Heartbeat|Passive)'){
      Invoke-Expression $fn.Extent.Text
    }
  }
}
$clock=[Diagnostics.Stopwatch]::StartNew()
if($fixture.mode -eq 'api'){
  $token=(Read-CoreNextHeartbeatJson (Join-Path $StateRoot 'kernel\local-session.json')).token
  $live=Invoke-CoreNextHeartbeatHttp $fixture.cfg.api_port '/dragon/api/v1/health/live' $token
  $ready=Invoke-CoreNextHeartbeatHttp $fixture.cfg.api_port '/dragon/api/v1/health/ready' $token
  $out=@{live_ok=$live.ok;live_status=$live.status;ready_ok=$ready.ok;ready_status=$ready.status;live_body_length=$live.body.Length;ready_body_length=$ready.body.Length}
}elseif($fixture.mode -eq 'http'){
  $response=Invoke-CoreNextHeartbeatHttp $fixture.cfg.web_port '/'
  $out=@{ok=$response.ok;status=$response.status;body_length=$response.body.Length}
}elseif($fixture.mode -eq 'tcp'){
  Initialize-CoreNextPassiveSockets
  $out=@{matching=(Test-CoreNextHeartbeatTcp $fixture.cfg.database_port $fixture.process_id);foreign=(Test-CoreNextHeartbeatTcp $fixture.cfg.database_port ($fixture.process_id+100000))}
}elseif($fixture.mode -eq 'writer'){
  $out=@{written=$false}
  try{Save-CoreNextHeartbeatReceipt @{schema_version=2;observer='synthetic-only';sequence=1};Save-CoreNextHeartbeatReceipt @{schema_version=2;observer='synthetic-only';sequence=2};$out.written=$true}catch{$out.rejected=$true}
}elseif($fixture.mode -in @('proof','api_proof','history')){
  $at=[DateTime]::UtcNow;$current=$at.ToString('o');$success=$null
  if($fixture.case -eq 'future'){$success=$at.AddSeconds(120).ToString('o')}
  if($fixture.case -eq 'stale'){$success=$at.AddSeconds(-120).ToString('o')}
  $checks=[ordered]@{web_server=@{state='READY';reason='SYNTHETIC_CHECK';metrics=@{};scope='SYNTHETIC';observed_at=$current}}
  if($fixture.case -ne 'missing'){$checks.web_server.last_success_at=$success}
  if($fixture.mode -eq 'history'){
    $old=$at.AddSeconds(-120).ToString('o')
    Save-CoreNextHeartbeatReceipt @{schema_version=2;observer='core-next.supervisor';installation_id=$script:cfg.installation_id;source_commit=$script:cfg.source_commit;build_id=$script:cfg.build_id;service_name=$script:cfg.service_name;api_pid=$fixture.process_id;supervisor_pid=$PID;api_verified=$true;last_success_at=$old;observed_at=$at.AddSeconds(-119).ToString('o');expires_at=$at.AddSeconds(-74).ToString('o');checks=@{web_server=@{last_success_at=$old;observed_at=$at.AddSeconds(-119).ToString('o')}}}
    $checks.web_server.state='UNAVAILABLE';$checks.web_server.last_success_at=$null
    Save-CoreNextHeartbeatSnapshot $fixture.process_id $true $current $checks
  }elseif($fixture.mode -eq 'api_proof'){Save-CoreNextHeartbeatSnapshot $fixture.process_id $true $success $checks}
  else{Save-CoreNextHeartbeatSnapshot $fixture.process_id $true $current $checks}
  $out=@{receipt=(Get-Content -LiteralPath (Join-Path $StateRoot 'runtime-observations.json') -Raw|ConvertFrom-Json)}
}else{
  $ok=Write-CoreNextHeartbeat
  $target=Join-Path $StateRoot 'runtime-observations.json'
  $out=@{written=$ok;receipt=$null}
  if(Test-Path -LiteralPath $target){$out.receipt=Get-Content -LiteralPath $target -Raw|ConvertFrom-Json}
}
$out.elapsed_ms=$clock.ElapsedMilliseconds
$out.powershell=$PSVersionTable.PSVersion.ToString()
$out|ConvertTo-Json -Depth 12 -Compress
''',encoding='utf-8')

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def invoke(self,shell,*,case='normal',mode='heartbeat',dead_role='',wrong_pid=False):
        api=LocalHTTP('api',case);web=LocalHTTP('web',case)
        database=socketserver.ThreadingTCPServer(('127.0.0.1',0),TCPHandler);database.daemon_threads=True
        servers=[api,web,database]
        for server in servers: threading.Thread(target=server.serve_forever,daemon=True).start()
        directory=Path(tempfile.mkdtemp(prefix='cycle-',dir=self.base));state=directory/'state';(state/'kernel').mkdir(parents=True)
        cfg=IDENTITY|{'service_name':'DragonhydraCoreNextSynthetic','state_root':str(state),'install_root':str(directory/'application'),
            'api_port':api.server_port,'web_port':web.server_port,'database_port':database.server_address[1]}
        actual_pid=os.getpid();pid=actual_pid+100000 if wrong_pid else actual_pid
        (state/'kernel/endpoint.json').write_text(json.dumps({'url':'http://127.0.0.1:'+str(api.server_port),'pid':pid}))
        (state/'kernel/local-session.json').write_text(json.dumps({'token':TOKEN}))
        (state/'status.json').write_text(json.dumps({'stage':'ready','legacy_fixture_field':'retained'}))
        if case=='junction':
            link=directory/'state-junction'
            quote=lambda value: "'"+str(value).replace("'","''")+"'"
            made=subprocess.run([str(SHELLS[0]),'-NoProfile','-Command','New-Item -ItemType Junction -Path '+quote(link)+' -Target '+quote(state)+' | Out-Null'],capture_output=True,text=True,timeout=15)
            self.assertEqual(made.returncode,0)
            self.addCleanup(lambda:os.rmdir(link) if link.exists() else None)
            cfg['state_root']=str(link)
            fixture_state=link
        else:fixture_state=state
        fixture={'state':str(fixture_state),'cfg':cfg,'process_id':actual_pid,'dead_role':dead_role,'mode':mode,'case':case}
        env=os.environ.copy();env['TEMP']=str(directory);env['TMP']=str(directory)
        try:
            quote=lambda value: "'"+str(value).replace("'","''")+"'"
            bootstrap='& ([ScriptBlock]::Create([IO.File]::ReadAllText('+quote(self.runner)+'))) -Source '+quote(ROOT/'packaging/windows/workstation/Workstation.ps1')+' -ProfileSource '+quote(ROOT/'packaging/windows/workstation/CoreNextProfile.ps1')+' -AtomicSource '+quote(ROOT/'packaging/windows/workstation/DragonhydraAtomicFile.cs')
            run=subprocess.run([str(shell),'-NoProfile','-Command',bootstrap],
                input=json.dumps(fixture),capture_output=True,text=True,encoding='utf-8',timeout=35,env=env)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertNotIn(TOKEN,run.stdout)
            self.assertNotIn('PRIVATE_FIXTURE_BODY',run.stdout)
            return json.loads(run.stdout),api.seen,web.seen,state
        finally:
            for server in servers:server.shutdown();server.server_close()

    def test_bound_receipt_distinguishes_anonymous_login_and_preserves_schema_on_both_hosts(self):
        for shell in SHELLS:
            with self.subTest(shell=shell.name):
                got,api,web,state=self.invoke(shell)
                self.assertTrue(got['written'],{'result':got,'api_paths':api,'web_paths':web})
                receipt=got['receipt'];self.assertEqual(receipt['schema_version'],2)
                self.assertEqual(receipt['installation_id'],IDENTITY['installation_id'])
                self.assertEqual(receipt['api_pid'],os.getpid())
                self.assertEqual(receipt['source_commit'],IDENTITY['source_commit'])
                self.assertTrue(receipt['api_verified'])
                self.assertIsNotNone(receipt['last_success_at'])
                observed=datetime.fromisoformat(receipt['observed_at'])
                self.assertLessEqual(datetime.fromisoformat(receipt['last_success_at']),observed)
                self.assertLessEqual((observed-datetime.fromisoformat(receipt['last_success_at'])).total_seconds(),90)
                self.assertEqual((datetime.fromisoformat(receipt['expires_at'])-datetime.fromisoformat(receipt['observed_at'])).total_seconds(),45)
                self.assertEqual(receipt['checks']['web_server']['state'],'READY')
                self.assertEqual(receipt['checks']['joomla_administration']['state'],'DEGRADED')
                self.assertEqual(receipt['checks']['joomla_administration']['reason'],'LOCAL_LOGIN_BOOTSTRAP_ONLY')
                self.assertIn('authentication not tested',receipt['checks']['joomla_administration']['scope'])
                self.assertEqual(receipt['checks']['joomla_website']['state'],'READY')
                self.assertEqual(receipt['checks']['mariadb_storage']['state'],'READY')
                self.assertIn('no direct SQL',receipt['checks']['mariadb_storage']['scope'])
                self.assertEqual(api,['/dragon/api/v1/health/live','/dragon/api/v1/health/ready'])
                self.assertEqual(web,['/','/administrator/'])
                self.assertEqual(list(state.glob('*.tmp')),[])
                self.assertEqual(json.loads((state/'status.json').read_text()),{'stage':'ready','legacy_fixture_field':'retained'})

    def test_wrong_build_pid_and_exited_child_never_renew_receipt(self):
        for kwargs in ({'case':'wrong_build'},{'wrong_pid':True},{'dead_role':'apache'}):
            with self.subTest(kwargs=kwargs):
                got,_,_,state=self.invoke(SHELLS[0],**kwargs)
                self.assertFalse(got['written'])
                self.assertFalse(got['receipt']['api_verified'])
                self.assertIsNone(got['receipt']['last_success_at'])
                self.assertTrue(all(check['state']=='UNVERIFIED' for check in got['receipt']['checks'].values()))

    def test_native_listener_requires_the_exact_process_and_connects_only_the_own_port(self):
        got,api,web,_=self.invoke(SHELLS[0],mode='tcp')
        self.assertEqual(got['matching'],'READY')
        self.assertEqual(got['foreign'],'UNVERIFIED')
        self.assertEqual(api+web,[])

    def test_http_refuses_redirects_oversize_and_slow_response_without_credentials(self):
        for case in ('redirect','oversize','slow'):
            with self.subTest(case=case):
                got,_,seen,_=self.invoke(SHELLS[0],case=case,mode='http')
                self.assertFalse(got['ok'])
                self.assertEqual(got['body_length'],0)
                self.assertLess(got['elapsed_ms'],2300)
                self.assertNotIn('/forbidden-redirect',seen)

    def test_failed_joomla_bootstrap_does_not_assert_administrator_or_sql_readiness(self):
        got,_,_,_=self.invoke(SHELLS[0],case='admin_error')
        self.assertTrue(got['written'],got)
        self.assertEqual(got['receipt']['checks']['joomla_administration']['state'],'UNAVAILABLE')
        self.assertEqual(got['receipt']['checks']['joomla_administration']['metrics']['http_status'],500)
        self.assertEqual(got['receipt']['checks']['mariadb_storage']['state'],'UNVERIFIED')

    def test_atomic_writer_replaces_owned_receipt_and_refuses_junction_ancestor(self):
        good,api,web,state=self.invoke(SHELLS[0],mode='writer')
        self.assertTrue(good['written'])
        self.assertEqual(json.loads((state/'runtime-observations.json').read_text())['sequence'],2)
        self.assertEqual(list(state.glob('*.tmp')),[])
        self.assertEqual(api+web,[])
        denied,api,web,state=self.invoke(SHELLS[0],mode='writer',case='junction')
        self.assertFalse(denied['written'])
        self.assertTrue(denied['rejected'])
        self.assertFalse((state/'runtime-observations.json').exists())
        self.assertEqual(api+web,[])

    def test_missing_null_future_or_stale_success_can_never_be_ready(self):
        for case in ('missing','null','future','stale'):
            with self.subTest(case=case):
                got,api,web,_=self.invoke(SHELLS[0],mode='proof',case=case)
                self.assertEqual(got['receipt']['checks']['web_server']['state'],'UNVERIFIED')
                self.assertIsNone(got['receipt']['checks']['web_server']['last_success_at'])
                self.assertEqual(api+web,[])
                got,api,web,_=self.invoke(SHELLS[0],mode='api_proof',case=case)
                self.assertFalse(got['receipt']['api_verified'])
                self.assertEqual(got['receipt']['checks']['web_server']['state'],'UNVERIFIED')

    def test_failed_check_preserves_historical_success_without_renewing_it(self):
        got,api,web,_=self.invoke(SHELLS[0],mode='history')
        receipt=got['receipt'];check=receipt['checks']['web_server']
        self.assertEqual(check['state'],'UNAVAILABLE')
        self.assertGreater((datetime.fromisoformat(check['observed_at'])-datetime.fromisoformat(check['last_success_at'])).total_seconds(),110)
        self.assertTrue(receipt['api_verified'])
        self.assertEqual(api+web,[])


if __name__=='__main__':unittest.main()
