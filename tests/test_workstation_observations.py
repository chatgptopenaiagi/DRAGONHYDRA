"""Execute the actual supervisor observation functions without controlling services."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=r'''
$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($Source,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'PARSE_ERROR'}
foreach($name in @('Status','Module-Observation','Read-OnlyHttp','Runtime-Observations')){
 $node=$ast.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst]},$true)|Where-Object Name -eq $name
 . ([scriptblock]::Create($node.Extent.Text))
}
$script:cfg=[pscustomobject]@{service_name='DragonhydraObservationFixture';api_port=18744;web_port=18740;database_port=1;admin_password='SYNTHETIC_PRIVATE_CANARY'}
$StateRoot='C:\SYNTHETIC_STATE';$script:runtimeObservations=@{};$script:requests=@();$script:apiFail=$false
$script:children=@([pscustomobject]@{Role='kernel';Process=[pscustomobject]@{Id=4101;HasExited=$false}})
function Save-Json($value,[string]$path){$script:captured=$value}
function Read-Json([string]$path){if($path.EndsWith('local-session.json')){return @{token='SYNTHETIC_TOKEN_CANARY'}};return @{pid=4101;url='http://127.0.0.1:18744'}}
function Invoke-WebRequest {
 param($Uri,$Method,$Headers,$WebSession,$MaximumRedirection,$TimeoutSec,[switch]$UseBasicParsing)
 if($Method -ne 'Get' -or $MaximumRedirection -ne 0 -or $TimeoutSec -gt 2){throw 'UNBOUNDED_OR_MUTATING_PROBE'}
 $script:requests+=@{url=$Uri;method=$Method}
 if($Uri.EndsWith('/health/ready')){if($script:apiFail){throw 'SYNTHETIC_PRIVATE_CANARY'};return @{StatusCode=200;Content='{"status":"ready","backend":"sqlite"}'}}
 if($Headers.ContainsKey('Authorization')){throw 'CREDENTIAL_LEFT_API_ORIGIN'}
 return @{StatusCode=200;Content=$(if($Uri.EndsWith('/administrator/')){'mod-login-username'}else{'dragonhydra-workspace'})}
}
$denied=0
try{$null=Read-OnlyHttp 'https://provider.invalid/'}catch{$denied++}
try{$null=Read-OnlyHttp 'http://127.0.0.1:18740/' $true}catch{$denied++}
if($denied -ne 2 -or $script:requests.Count){throw 'ALLOWLIST_BYPASS'}
$listener=New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback,0);$listener.Start()
try{
 $script:cfg.database_port=$listener.LocalEndpoint.Port
 $script:runtimeObservations=Runtime-Observations
 if($script:runtimeObservations.api_server.runtime_state -ne 'ready' -or $script:runtimeObservations.storage_mariadb.runtime_state -ne 'ready'){throw 'HEALTHY_PROBES_NOT_READY'}
 Status 'ready'
 $first=$script:captured
 if($first.observer -ne 'workstation-supervisor' -or $first.observations.api_server.sanitized_metrics.pid -ne 4101){throw 'IDENTITY_MISSING'}
 $expiry=([DateTime]::Parse($first.evidence_expires_at)-[DateTime]::Parse($first.observed_at)).TotalSeconds
 if($expiry -ne 30){throw 'EVIDENCE_NOT_EXPIRING'}
 $script:apiFail=$true;$second=Runtime-Observations
 if($second.api_server.runtime_state -eq 'ready' -or $second.api_server.last_success_at){throw 'FAILED_PROBE_REPORTED_SUCCESS'}
 if($second.website.runtime_state -ne 'ready'){throw 'UNRELATED_MODULE_WAS_DEGRADED'}
 $json=$first|ConvertTo-Json -Depth 12
 if($json -match 'SYNTHETIC_PRIVATE_CANARY|SYNTHETIC_TOKEN_CANARY|admin_password'){throw 'SECRET_IN_OBSERVATION'}
 @{passed=$true;healthy_modules=$first.observations.Count;failed_api_is_degraded=$true;unrelated_website_ready=$true;expiry_seconds=$expiry;private_values_excluded=$true;allowlist_guards=$denied;requests=$script:requests.Count}|ConvertTo-Json -Compress
}finally{$listener.Stop()}
'''

class WorkstationObservationTests(unittest.TestCase):
    def run_shell(self,executable):
        with tempfile.TemporaryDirectory(prefix='dragonhydra-observations-') as work:
            script=Path(work)/'probe.ps1'
            script.write_text('param([string]$Source)\n'+FIXTURE,encoding='utf-8-sig')
            result=subprocess.run([executable,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),'-Source',str(ROOT/'packaging/windows/workstation/Workstation.ps1')],capture_output=True,text=True,timeout=25)
            self.assertEqual(result.returncode,0,result.stderr)
            proof=json.loads(result.stdout);self.assertTrue(proof['passed']);self.assertEqual(proof['healthy_modules'],6)
    def test_powershell7_observation_safety_and_expiry(self):
        self.run_shell(r'C:\Program Files\PowerShell\7\pwsh.exe')
    def test_service_powershell51_observation_safety_and_expiry(self):
        self.run_shell(r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe')

if __name__=='__main__':unittest.main()
