"""Production SID resolver under real PS5.1/PS7 with synthetic SCM/native data.

No actual service query, account-name lookup, service/ACL/SQL change or product
launch is permitted. Only the transport test redirects one AST-proven executable
assignment to a disposable cmd fixture; production receives no injection flag.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAB = Path(r'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB')
PROFILE = ROOT/'packaging/windows/workstation/CoreNextProfile.ps1'
WORKSTATION = ROOT/'packaging/windows/workstation/Workstation.ps1'
SQL = ROOT/'packaging/windows/workstation/Configure-CoreNextSqlResearch.ps1'
HOSTS = [Path(r'C:\Program Files\PowerShell\7\pwsh.exe'),
         Path(r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe')]


def quote(value):
    return "'"+str(value).replace("'", "''")+"'"


@unittest.skipUnless(os.name == 'nt' and all(host.is_file() for host in HOSTS),
                     'Native Windows PowerShell5.1 and existing PowerShell7 required')
class ServiceSidHostTests(unittest.TestCase):
    def run_ps(self, body):
        scratch=LAB/'tests';scratch.mkdir(exist_ok=True)
        for host in HOSTS:
            with self.subTest(host=str(host)), tempfile.TemporaryDirectory(
                    prefix='service-sid-',dir=scratch) as directory:
                fixture=Path(directory)
                self.assertEqual(fixture.parent.resolve(),scratch.resolve())
                setup=r'''
$ErrorActionPreference='Stop'
$OutputEncoding=[Text.UTF8Encoding]::new($false);[Console]::OutputEncoding=$OutputEncoding
if($PSVersionTable.PSVersion.Major -eq 5){$env:PSModulePath=Join-Path $PSHOME 'Modules'}
function Require($Value,[string]$Code){if(-not $Value){throw $Code}}
function Reject([scriptblock]$Body,[string]$Code){
 $caught=$null;try{& $Body|Out-Null}catch{$caught=$_}
 Require ($caught -and $caught.Exception.Message.Contains($Code)) ('EXPECTED_'+$Code)
}
'''
                setup+='\n$fixture='+quote(fixture)+'\n$source='+quote(PROFILE)+'\n. $source\n'
                setup+=r'''
$id='core-next-'+[Guid]::NewGuid().ToString('N');$suffix=$id.Substring($id.Length-12)
$lab='C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB';$base=Join-Path $lab ('profiles\'+$id)
$p=[pscustomobject]@{schema_version=1;product='DRAGONHYDRA CORE NEXT';edition='CORE NEXT';installation_id=$id;environment_id='candidate';lab_root=$lab;
 install_root=(Join-Path $base 'application');state_root=(Join-Path $base 'state');browser_user_data=(Join-Path $base 'browser');service_name=('DragonhydraCoreNextcandidate'+$suffix);
 shortcut_name=('DRAGONHYDRA CORE NEXT candidate '+$suffix);uninstall_id=('DRAGONHYDRA-CORE-NEXT-'+$id);ports=@{api=19940;web=19941;database=19942};
 database=@{admin_schema=('dhcn_admin_'+$suffix);admin_user=('dhcn_admin_'+$suffix);core_schema=('dhcn_core_'+$suffix);core_user=('dhcn_core_'+$suffix)};
 cookie_name=('dhcn_'+$suffix);joomla_session_suffix=$id;provider_schedules='disabled';copy_credentials=$false;api_namespace='/dragon/api/v1';kernel_schema_version=1;
 source_commit=('a'*40);build_id='synthetic-sid-resolver-only';version='0.5.0-dev.8'}
$image='"'+(Join-Path $p.install_root 'workstation\DragonhydraService.exe')+'" --state "'+$p.state_root+'" --name '+$p.service_name
$script:service=[pscustomobject]@{Name=$p.service_name;PathName=$image;StartName='NT AUTHORITY\LocalService';State='Stopped'}
$script:services=@($script:service);$script:cimCalls=0;$script:queries=New-Object Collections.Generic.List[string]
$script:sid='S-1-5-80-11-22-33-44-55'
$script:typeText=@('[SC] QueryServiceConfig2 SUCCESS','',('SERVICE_NAME: '+$p.service_name),'SERVICE_SID_TYPE:  UNRESTRICTED')
$script:sidText=@('',('NAME: '+$p.service_name),('SERVICE SID: '+$script:sid),'STATUS: Active')
$script:failQuery=$null
function Get-CimInstance {
 [CmdletBinding()]param($ClassName,$Filter)
 Require ($ClassName -ceq 'Win32_Service' -and $Filter -ceq ("Name='"+$p.service_name+"'")) 'UNEXPECTED_SCM_QUERY'
 $script:cimCalls++;$script:services
}
function Invoke-CoreNextServiceSidQuery {
 param($ServiceName,$Query)
 Require ($ServiceName -ceq $p.service_name -and $Query -cin @('qsidtype','showsid')) 'UNEXPECTED_NATIVE_QUERY'
 $script:queries.Add($Query+'|'+$ServiceName)
 if($script:failQuery -ceq $Query){throw 'CORE_NEXT_SERVICE_SID_NATIVE_QUERY_FAILED'}
 if($Query -ceq 'qsidtype'){$script:typeText}else{$script:sidText}
}
function Resolve-CoreNextServiceSid {throw 'OLD_ACCOUNT_NAME_LOOKUP_FORBIDDEN'}
'''
                runner=fixture/'fixture.ps1';runner.write_text(setup+'\n'+body,encoding='utf-8-sig')
                result=subprocess.run([str(host),'-NoLogo','-NoProfile','-NonInteractive',
                    '-ExecutionPolicy','RemoteSigned','-File',str(runner)],capture_output=True,
                    text=True,encoding='utf-8',errors='replace',timeout=35)
                self.assertEqual(result.returncode,0,result.stdout[-1200:]+result.stderr[-3000:])
                doc=json.loads(result.stdout.strip())
                self.assertIs(doc['passed'],True)
                self.assertEqual(doc['actual_SCM_SQL_ACL_app_actions'],0)

    def test_recorded_sc_header_and_bare_format_return_typed_sid_without_lookup(self):
        self.run_ps(r'''
$value=Get-CoreNextServiceSid -Profile $p
Require ($value -is [Security.Principal.SecurityIdentifier] -and $value.Value -ceq $script:sid) 'TYPED_SID_REQUIRED'
Require (($script:queries -join '|') -ceq ('qsidtype|'+$p.service_name+'|showsid|'+$p.service_name) -and $script:cimCalls -eq 1) 'EXACT_QUERIES_REQUIRED'
$script:typeText=$script:typeText[2..3];$script:queries.Clear();$script:service.State='Running'
$value=Get-CoreNextServiceSid -Profile $p
Require ($value.Value -ceq $script:sid -and $script:queries.Count -eq 2) 'BARE_QUERY_FORMAT_FAILED'
@{passed=$true;actual_SCM_SQL_ACL_app_actions=0;query_pairs=2;name_lookup_calls=0}|ConvertTo-Json -Compress
''')

    def test_owned_profile_scm_name_image_account_and_single_result_required(self):
        self.run_ps(r'''
$original=$script:service
foreach($field in @('Name','PathName','StartName')){
 $bad=$original.PSObject.Copy();$bad.$field=if($field -ceq 'StartName'){'LocalSystem'}else{'wrong'};$script:services=@($bad);$script:queries.Clear()
 Reject {Get-CoreNextServiceSid -Profile $p} 'CORE_NEXT_SERVICE_SID_OWNERSHIP_MISMATCH'
 Require ($script:queries.Count -eq 0) 'UNOWNED_SERVICE_WAS_QUERIED'
}
foreach($count in @(0,2)){
 $script:services=if($count -eq 0){@()}else{@($original,$original)};$script:queries.Clear()
 Reject {Get-CoreNextServiceSid -Profile $p} 'CORE_NEXT_SERVICE_SID_OWNERSHIP_MISMATCH';Require ($script:queries.Count -eq 0) 'AMBIGUOUS_SERVICE_WAS_QUERIED'
}
$script:services=@($original);$before=$script:cimCalls;$bad=$p.PSObject.Copy();$bad.installation_id='invalid'
Reject {Get-CoreNextServiceSid -Profile $bad} 'CORE_NEXT_PROFILE_IDENTITY_REQUIRED';Require ($script:cimCalls -eq $before) 'INVALID_PROFILE_REACHED_SCM'
@{passed=$true;actual_SCM_SQL_ACL_app_actions=0}|ConvertTo-Json -Compress
''')

    def test_sid_type_rejects_wrong_name_type_order_extra_or_duplicate_header(self):
        self.run_ps(r'''
$name='SERVICE_NAME: '+$p.service_name;$type='SERVICE_SID_TYPE: UNRESTRICTED'
$variants=@(@('SERVICE_NAME: wrong',$type),@($name,'SERVICE_SID_TYPE: NONE'),@($name,'SERVICE_SID_TYPE: RESTRICTED'),@($type,$name),@($name,$type,'unexpected'),@('[SC] QueryServiceConfig2 FAILED',$name,$type),@('[SC] QueryServiceConfig2 SUCCESS','[SC] QueryServiceConfig2 SUCCESS',$name,$type),@($name,$name),@())
foreach($variant in $variants){$script:typeText=$variant;$script:queries.Clear();Reject {Get-CoreNextServiceSid -Profile $p} 'CORE_NEXT_SERVICE_SID_QUERY_UNVERIFIED';Require ($script:queries.Count -eq 1) 'SID_TYPE_FAILURE_REACHED_SHOWSID'}
@{passed=$true;actual_SCM_SQL_ACL_app_actions=0;negative_formats=$variants.Count}|ConvertTo-Json -Compress
''')

    def test_showsid_requires_exact_name_active_and_canonical_service_sid(self):
        self.run_ps(r'''
$name='NAME: '+$p.service_name;$sid='SERVICE SID: '+$script:sid;$status='STATUS: Active'
$variants=@(@('NAME: wrong',$sid,$status),@($name,$sid,'STATUS: Inactive'),@($name,$sid,'STATUS: active'),@($sid,$name,$status),@($name,$sid,$status,'extra'),@($name,'SERVICE SID: S-1-5-19',$status),@($name,'SERVICE SID: S-1-5-81-11-22-33-44-55',$status),@($name,'SERVICE SID: S-1-5-80-11-22-33-44',$status),@($name,'SERVICE SID: S-1-5-80-11-22-33-44-4294967296',$status),@($name,'SERVICE SID: S-1-5-80-011-22-33-44-55',$status),@($name,$sid,$sid))
foreach($variant in $variants){$script:sidText=$variant;$script:queries.Clear();Reject {Get-CoreNextServiceSid -Profile $p} 'CORE_NEXT_SERVICE_SID_QUERY_UNVERIFIED';Require ($script:queries.Count -eq 2) 'SHOWSID_FAILURE_RETRIED'}
@{passed=$true;actual_SCM_SQL_ACL_app_actions=0;negative_formats=$variants.Count}|ConvertTo-Json -Compress
''')

    def test_native_query_failures_propagate_once_without_fallback_or_retry(self):
        self.run_ps(r'''
foreach($query in @('qsidtype','showsid')){$script:failQuery=$query;$script:queries.Clear();Reject {Get-CoreNextServiceSid -Profile $p} 'CORE_NEXT_SERVICE_SID_NATIVE_QUERY_FAILED';Require ($script:queries.Count -eq $(if($query -ceq 'qsidtype'){1}else{2})) 'NATIVE_FAILURE_RETRIED'}
@{passed=$true;actual_SCM_SQL_ACL_app_actions=0}|ConvertTo-Json -Compress
''')

    def test_production_native_transport_handles_exit_stderr_and_restores_preference(self):
        self.run_ps(r"""
$tokens=$null;$errors=$null;$ast=[Management.Automation.Language.Parser]::ParseFile($source,[ref]$tokens,[ref]$errors)
Require ($errors.Count -eq 0) 'SOURCE_PARSE_FAILED'
$definitions=@($ast.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq 'Invoke-CoreNextServiceSidQuery'},$true));Require ($definitions.Count -eq 1) 'EXACT_NATIVE_TRANSPORT_REQUIRED'
$assignments=@($definitions[0].FindAll({param($n)$n -is [Management.Automation.Language.AssignmentStatementAst] -and $n.Left.Extent.Text -ceq '$sc'},$true));Require ($assignments.Count -eq 1 -and $assignments[0].Extent.Text -ceq '$sc=Join-Path $env:WINDIR ''System32\sc.exe''') 'EXACT_FIXED_EXECUTABLE_SEAM_REQUIRED'
$native=Join-Path $fixture 'native query fixture.cmd'
$text=$definitions[0].Extent.Text.Replace($assignments[0].Extent.Text,('$sc='+("'"+$native.Replace("'","''")+"'")))
. ([scriptblock]::Create($text))
[IO.File]::WriteAllText($native,('@echo off'+"`r`n"+'echo QUERY:%1'+"`r`n"+'echo SERVICE:%2'+"`r`n"+'exit /b 0'+"`r`n"))
$output=@(Invoke-CoreNextServiceSidQuery -ServiceName $p.service_name -Query showsid)
Require (($output -join '|') -ceq ('QUERY:showsid|SERVICE:'+$p.service_name)) 'NATIVE_ARGUMENT_IDENTITY_CHANGED'
Require ($ErrorActionPreference -ceq 'Stop') 'PREFERENCE_NOT_RESTORED_AFTER_SUCCESS'
[IO.File]::WriteAllText($native,('@echo off'+"`r`n"+'echo NATIVE_STDERR 1>&2'+"`r`n"+'exit /b 17'+"`r`n"))
Reject {Invoke-CoreNextServiceSidQuery -ServiceName $p.service_name -Query qsidtype} 'CORE_NEXT_SERVICE_SID_NATIVE_QUERY_FAILED'
Require ($ErrorActionPreference -ceq 'Stop') 'PREFERENCE_NOT_RESTORED_AFTER_FAILURE'
Reject {Invoke-CoreNextServiceSidQuery -ServiceName 'DragonhydraWorkstation' -Query showsid} 'ServiceName'
Reject {Invoke-CoreNextServiceSidQuery -ServiceName $p.service_name -Query 'sidtype'} 'Query'
Remove-Item -LiteralPath $native
Reject {Invoke-CoreNextServiceSidQuery -ServiceName $p.service_name -Query showsid} 'CORE_NEXT_SERVICE_SID_QUERY_UNAVAILABLE'
@{passed=$true;actual_SCM_SQL_ACL_app_actions=0;native_processes='Disposable command only'}|ConvertTo-Json -Compress
""")


class ServiceSidSourceGuards(unittest.TestCase):
    def test_all_three_call_sites_use_shared_resolver_and_never_account_translation(self):
        workstation=WORKSTATION.read_text(encoding='utf-8-sig')
        sql=SQL.read_text(encoding='utf-8-sig')
        profile=PROFILE.read_text(encoding='utf-8-sig')
        self.assertEqual(workstation.count('Get-CoreNextServiceSid -Profile $Profile'),2)
        self.assertEqual(sql.count('Get-CoreNextServiceSid -Profile $profile'),1)
        for text in (workstation,sql,profile):
            self.assertNotIn('Resolve-CoreNextServiceSid',text)
            self.assertNotIn('NTAccount',text)
            self.assertNotRegex(text,r'\.Translate\s*\(')
        self.assertIn("[ValidateSet('qsidtype','showsid')]",profile)
        self.assertIn("$sc=Join-Path $env:WINDIR 'System32\\sc.exe'",profile)
        self.assertIn('actual token',profile)


if __name__=='__main__':
    unittest.main()
