"""Extracted PowerShell functions and SQL driver doubles only; never SCM/SQL/UI."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKSTATION = ROOT / 'packaging/windows/workstation/Workstation.ps1'
HELPER = ROOT / 'packaging/windows/workstation/Configure-CoreNextSqlResearch.ps1'
PROFILE = ROOT / 'packaging/windows/workstation/CoreNextProfile.ps1'
SCHEMA = ROOT / 'src/dragonhydra/research_storage/schema_sqlserver.sql'
HOSTS = [Path(r'C:\Program Files\PowerShell\7\pwsh.exe'),
         Path(r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe')]


def quote(path): return "'" + str(path).replace("'", "''") + "'"


class SqlServiceMaintenanceTests(unittest.TestCase):
    def run_ps(self, body):
        # Only AST-extracted definitions are evaluated; no script top-level runs.
        setup = r'''
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -eq 5){$env:PSModulePath=Join-Path $PSHOME 'Modules'}
function Load-Definition([string]$Path,[string[]]$Names){
 $tokens=$null;$errors=$null;$ast=[Management.Automation.Language.Parser]::ParseFile($Path,[ref]$tokens,[ref]$errors)
 if($errors.Count){throw 'SOURCE_PARSE_FAILED'}
 foreach($name in $Names){
  $found=@($ast.FindAll({param($node)$node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -ceq $name},$true))
  if($found.Count -ne 1){throw 'EXACT_FUNCTION_REQUIRED'}
  . ([scriptblock]::Create($found[0].Extent.Text))
  Set-Item -Path ('Function:global:'+$name) -Value (Get-Item ('Function:'+$name)).ScriptBlock
 }
}
function Require($Value,[string]$Message){if(-not $Value){throw $Message}}
function Reject([scriptblock]$Action,[string]$Code){
 $caught=$false;try{& $Action}catch{$caught=$_.Exception.Message -ceq $Code}
 Require $caught ('EXPECTED_REJECTION_'+$Code)
}
'''
        script = setup + '\n. ' + quote(PROFILE) + '\n' + body
        results = []
        with tempfile.TemporaryDirectory(prefix='dh-sql-service-static-') as temporary:
            path = Path(temporary) / 'fixture.ps1'
            path.write_text(script, encoding='utf-8-sig')
            for host in HOSTS:
                with self.subTest(host=host.name):
                    self.assertTrue(host.is_file())
                    completed = subprocess.run([str(host), '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(path)],
                        capture_output=True, text=True, timeout=25)
                    self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
                    results.append(json.loads(completed.stdout.strip()))
        return results

    def test_both_powershell_hosts_parse_all_owned_scripts(self):
        body = '\n'.join('$tokens=$null;$errors=$null;$null=[Management.Automation.Language.Parser]::ParseFile(' + quote(path) + ',[ref]$tokens,[ref]$errors);Require ($errors.Count -eq 0) "SCRIPT_PARSE_FAILED"' for path in [WORKSTATION, HELPER])
        self.run_ps(body + '\n@{passed=$true;scripts=2;executed=$false}|ConvertTo-Json -Compress')

    def test_new_sid_and_repair_guards_use_fake_scm_only_and_preserve_legacy(self):
        body = 'Load-Definition ' + quote(WORKSTATION) + " @('Set-CoreNextOwnedServiceSid')\n" + r'''
$p=New-CoreNextProfileObject -SourceCommit ('a'*40) -Version '0.5.0-dev.7' -BuildId 'SYNTHETIC-static'
function Quote([string]$Value){'"'+$Value+'"'}
$expected=(Quote (Join-Path $p.install_root 'workstation\DragonhydraService.exe'))+' --state '+(Quote $p.state_root)+' --name '+$p.service_name
$script:fake=[pscustomobject]@{Name=$p.service_name;PathName=$expected;StartName='NT AUTHORITY\LocalService';State='Stopped'}
$script:sidType='NONE';$script:writes=0;$script:queries=0;$script:reported=$p.service_name;$script:ignoreSet=$false
function Get-CimInstance {param($ClassName,$Filter);Require ($ClassName -ceq 'Win32_Service') 'SCM_CLASS';return $script:fake}
function Native {param($Exe,[string[]]$Arguments)
 if($Arguments[0] -ceq 'qsidtype'){$script:queries++;return @(('SERVICE_NAME: '+$script:reported),('SERVICE_SID_TYPE: '+$script:sidType))}
 if($Arguments[0] -ceq 'sidtype'){Require ($Arguments[1] -ceq $p.service_name -and $Arguments[2] -ceq 'unrestricted') 'WRONG_SID_TARGET';$script:writes++;if(-not $script:ignoreSet){$script:sidType='UNRESTRICTED'};return}
 throw 'NO_ACTUAL_NATIVE_OPERATIONS_ALLOWED'
}
$fresh=Set-CoreNextOwnedServiceSid -Profile $p -CreatedNow -Policy 'unrestricted'
Require ($fresh.changed -and $script:writes -eq 1 -and $fresh.sid_type -ceq 'UNRESTRICTED') 'FRESH_SID_FAILED'
$script:writes=0;$repair=Set-CoreNextOwnedServiceSid -Profile $p -Policy 'unrestricted'
Require (-not $repair.changed -and $script:writes -eq 0) 'REPAIR_CHANGED_SECURITY'
$script:sidType='NONE';$script:queries=0;$script:fake.State='Running'
$legacy=Set-CoreNextOwnedServiceSid -Profile $p
Require ($legacy.sid_type -ceq 'LEGACY_NOT_REQUIRED' -and $script:queries -eq 0 -and $script:writes -eq 0) 'LEGACY_REPAIR_CHANGED'
Reject {Set-CoreNextOwnedServiceSid -Profile $p -SqlEnabled} 'CORE_NEXT_SQL_SERVICE_SID_POLICY_REQUIRED'
Reject {Set-CoreNextOwnedServiceSid -Profile $p -CreatedNow -Policy 'unrestricted'} 'CORE_NEXT_NEW_SERVICE_MUST_BE_STOPPED'
$script:fake.State='Stopped'
Reject {Set-CoreNextOwnedServiceSid -Profile $p -Policy 'unrestricted'} 'CORE_NEXT_EXISTING_SERVICE_SID_UNVERIFIED'
$script:fake.StartName='LocalSystem'
Reject {Set-CoreNextOwnedServiceSid -Profile $p -CreatedNow -Policy 'unrestricted'} 'CORE_NEXT_SERVICE_SID_OWNERSHIP_MISMATCH'
$script:fake.StartName='NT AUTHORITY\LocalService';$script:fake.PathName='SYNTHETIC-foreign-image'
Reject {Set-CoreNextOwnedServiceSid -Profile $p -CreatedNow -Policy 'unrestricted'} 'CORE_NEXT_SERVICE_SID_OWNERSHIP_MISMATCH'
$script:fake.PathName=$expected;$script:reported='SYNTHETIC-other-service'
Reject {Set-CoreNextOwnedServiceSid -Profile $p -CreatedNow -Policy 'unrestricted'} 'CORE_NEXT_SERVICE_SID_QUERY_UNVERIFIED'
$script:reported=$p.service_name;$script:ignoreSet=$true
Reject {Set-CoreNextOwnedServiceSid -Profile $p -CreatedNow -Policy 'unrestricted'} 'CORE_NEXT_SERVICE_SID_CONFIGURATION_FAILED'
@{passed=$true;actual_service_calls=0;actual_native_calls=0;legacy_unchanged=$true}|ConvertTo-Json -Compress
'''
        self.run_ps(body)

    def test_grants_are_exact_objects_with_no_audit_insert_or_server_roles(self):
        body = 'Load-Definition ' + quote(HELPER) + " @('New-CoreNextSqlGrantPlan')\n" + r'''
$tables=@('dh_research_owner','dh_research_migrations','dh_research_archives','dh_research_models','dh_research_predictions','dh_research_inputs','dh_research_notes','dh_research_note_audit')
$principal='NT SERVICE\DragonhydraCoreNextcandidateabcdef123456'
$grants=@(New-CoreNextSqlGrantPlan $principal $tables)
Require ($grants.Count -eq 15) 'EXACT_15_GRANTS_REQUIRED'
Require (@($grants|Where-Object permission -CEQ 'SELECT').Count -eq 8) 'SELECT_SET'
Require (@($grants|Where-Object permission -CEQ 'INSERT').Count -eq 5) 'INSERT_SET'
Require (@($grants|Where-Object {$_.permission -ceq 'UPDATE' -and $_.object -ceq 'dh_research_notes'}).Count -eq 1) 'UPDATE_SET'
Require (-not @($grants|Where-Object {$_.permission -ceq 'INSERT' -and $_.object -ceq 'dh_research_note_audit'})) 'AUDIT_INSERT_FORBIDDEN'
Require (-not @($grants|Where-Object {$_.sql -match 'sysadmin|dbcreator|CREATE|ALTER|VIEW SERVER|VIEW ANY|LOCAL SERVICE'})) 'BROAD_PERMISSION_FORBIDDEN'
Reject {New-CoreNextSqlGrantPlan 'NT AUTHORITY\LocalService' $tables} 'CORE_NEXT_SQL_EXACT_SERVICE_PRINCIPAL_REQUIRED'
Reject {New-CoreNextSqlGrantPlan ($principal+'];other') $tables} 'CORE_NEXT_SQL_EXACT_SERVICE_PRINCIPAL_REQUIRED'
Reject {New-CoreNextSqlGrantPlan $principal ($tables+@('foreign'))} 'CORE_NEXT_SQL_TABLE_ALLOWLIST_REQUIRED'
@{passed=$true;grants=$grants.Count;sql_executions=0}|ConvertTo-Json -Compress
'''
        self.run_ps(body)

    def test_database_name_is_profile_bound_and_baseline_is_rejected(self):
        body = 'Load-Definition ' + quote(HELPER) + " @('Get-CoreNextSqlNames')\n" + r'''
$p=New-CoreNextProfileObject -SourceCommit ('a'*40) -Version '0.5.0-dev.7' -BuildId 'SYNTHETIC-static'
$n=Get-CoreNextSqlNames $p
$suffix=$p.installation_id.Substring($p.installation_id.Length-12)
Require ($n.database -ceq ('DRAGONHYDRA_CORE_NEXT_SQL_'+$suffix.ToUpperInvariant())) 'DATABASE_NOT_BOUND'
Require ($n.principal -ceq ('NT SERVICE\'+$p.service_name)) 'PRINCIPAL_NOT_BOUND'
$b=New-CoreNextProfileObject -Environment baseline -SourceCommit ('a'*40) -Version '0.5.0-dev.7' -BuildId 'SYNTHETIC-static'
Reject {Get-CoreNextSqlNames $b} 'CORE_NEXT_SQL_CANDIDATE_REQUIRED'
@{passed=$true;profiles_written=0}|ConvertTo-Json -Compress
'''
        self.run_ps(body)

    def test_schema_is_canonical_hash_bound_and_only_parsed(self):
        body = 'Load-Definition ' + quote(HELPER) + " @('Get-CoreNextSqlHash','Get-CoreNextSqlSchemaPlan')\n"
        body += '$schema=Get-CoreNextSqlSchemaPlan ' + quote(SCHEMA) + " '" + hashlib.sha256(SCHEMA.read_bytes()).hexdigest() + "'\n"
        body += 'Require ($schema.tables.Count -eq 8 -and $schema.triggers.Count -eq 9 -and $schema.batches.Count -eq 10) "SCHEMA_SET"\n'
        body += 'Reject {Get-CoreNextSqlSchemaPlan ' + quote(SCHEMA) + " ('0'*64)} 'CORE_NEXT_SQL_SCHEMA_HASH_MISMATCH'\n"
        self.run_ps(body + '@{passed=$true;sql_executions=0}|ConvertTo-Json -Compress')

    def test_existing_settings_require_exact_types_and_no_credentials_or_extra_fields(self):
        body = 'Load-Definition ' + quote(HELPER) + " @('Assert-CoreNextSqlSettings')\n" + r'''
$expected=[ordered]@{schema_version=1;provider='sqlserver';sqlserver=[ordered]@{server='lpc:localhost';database='SYNTHETIC';driver='ODBC Driver 18 for SQL Server';authentication='windows_integrated';encrypt=$true;trust_server_certificate=$false;connection_timeout_seconds=5;query_timeout_seconds=10}}
function Copy-Expected {$expected|ConvertTo-Json -Depth 5|ConvertFrom-Json}
Assert-CoreNextSqlSettings (Copy-Expected) $expected
$bad=Copy-Expected;$bad.sqlserver.encrypt='true';Reject {Assert-CoreNextSqlSettings $bad $expected} 'CORE_NEXT_SQL_EXISTING_CONFIGURATION_CONFLICT'
$bad=Copy-Expected;$bad.sqlserver.connection_timeout_seconds=5.0;Reject {Assert-CoreNextSqlSettings $bad $expected} 'CORE_NEXT_SQL_EXISTING_CONFIGURATION_CONFLICT'
$bad=Copy-Expected;$bad.schema_version='1';Reject {Assert-CoreNextSqlSettings $bad $expected} 'CORE_NEXT_SQL_EXISTING_CONFIGURATION_CONFLICT'
$bad=Copy-Expected;$bad.sqlserver|Add-Member -NotePropertyName password -NotePropertyValue 'SYNTHETIC-canary';Reject {Assert-CoreNextSqlSettings $bad $expected} 'CORE_NEXT_SQL_EXISTING_CONFIGURATION_CONFLICT'
@{passed=$true;sql_executions=0;configuration_writes=0}|ConvertTo-Json -Compress
'''
        self.run_ps(body)

    def test_final_configuration_gate_validates_and_hashes_current_bytes(self):
        body = 'Load-Definition ' + quote(HELPER) + " @('Get-CoreNextSqlHex','Assert-CoreNextSqlSettings','Get-CoreNextSqlValidatedSettingsHash')\n" + r'''
$expected=[ordered]@{schema_version=1;provider='sqlserver';sqlserver=[ordered]@{server='lpc:localhost';database='SYNTHETIC';driver='ODBC Driver 18 for SQL Server';authentication='windows_integrated';encrypt=$true;trust_server_certificate=$false;connection_timeout_seconds=5;query_timeout_seconds=10}}
$root=Join-Path $PSScriptRoot ([Guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path $root
$path=Join-Path $root 'research-storage.json'
[IO.File]::WriteAllText($path,($expected|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
$hash=Get-CoreNextSqlValidatedSettingsHash $path $root $expected
Require ($hash -ceq (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()) 'VALIDATED_BYTES_HASH_MISMATCH'
# A conflicting file appearing/changed during the owner SQL phase must not pass.
$other=$expected|ConvertTo-Json -Depth 5|ConvertFrom-Json;$other.sqlserver.server='lpc:SYNTHETIC-foreign'
[IO.File]::WriteAllText($path,($other|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
$before=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
Reject {Get-CoreNextSqlValidatedSettingsHash $path $root $expected} 'CORE_NEXT_SQL_EXISTING_CONFIGURATION_CONFLICT'
Require ($before -ceq (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash) 'CONFLICTING_CONFIGURATION_WAS_MODIFIED'
@{passed=$true;sql_executions=0;conflict_preserved=$true}|ConvertTo-Json -Compress
'''
        self.run_ps(body)
        source = HELPER.read_text()
        final = source.index('$record.configuration_sha256=Get-CoreNextSqlValidatedSettingsHash')
        self.assertGreater(final, source.index('[IO.File]::Move($temporary,$settingsPath)'))
        self.assertLess(final, source.index("$record.passed=$true;$record.stage='configured_restart_required'"))

    def test_descendant_paths_reject_junction_before_configuration_read_or_write(self):
        body = 'Load-Definition ' + quote(HELPER) + " @('Get-CoreNextSqlValidatedSettingsHash','Save-CoreNextSqlReceipt')\n" + r'''
$root=Join-Path $PSScriptRoot ([Guid]::NewGuid().ToString('N'))
$outside=Join-Path $PSScriptRoot ([Guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path $root
$null=New-Item -ItemType Directory -Path $outside
$junction=Join-Path $root 'kernel'
$null=New-Item -ItemType Junction -Path $junction -Target $outside
try{
 $redirected=Join-Path $junction 'research-storage.json'
 Reject {Get-CoreNextSqlValidatedSettingsHash $redirected $root @{}} 'CORE_NEXT_REPARSE_PATH_REJECTED'
 Reject {Save-CoreNextSqlReceipt @{passed=$true} (Join-Path $junction 'receipt.json') $root} 'CORE_NEXT_REPARSE_PATH_REJECTED'
 Require (@(Get-ChildItem -LiteralPath $outside -Force).Count -eq 0) 'REDIRECTED_WRITE_OCCURRED'
}finally{Remove-Item -LiteralPath $junction -Force}
@{passed=$true;sql_executions=0;redirected_writes=0}|ConvertTo-Json -Compress
'''
        self.run_ps(body)
        source = HELPER.read_text()
        for variable, boundary in [('configPath', 'state_root'), ('serverExe', 'install_root'),
                                   ('serverInfoPath', 'install_root'), ('settingsPath', 'state_root'),
                                   ('temporary', 'state_root')]:
            self.assertIn('$null=Assert-CoreNextOrdinaryPath $' + variable + ' $profile.' + boundary, source)
        self.assertIn("$temporary=Assert-CoreNextOrdinaryPath ($Path+'.tmp') $LabRoot", source)
        self.assertIn("$lockPath=Assert-CoreNextOrdinaryPath ($ReceiptPath+'.started.lock') $profile.lab_root", source)
        self.assertIn('database=$Database;server=$SqlServer;', source)

    def test_install_sets_policy_and_verifies_sid_before_start_without_legacy_defaults(self):
        source = WORKSTATION.read_text(encoding='utf-8-sig')
        call = source.index('$sidEvidence=Set-CoreNextOwnedServiceSid')
        self.assertLess(call, source.index("Start-Service $ServiceName", call))
        self.assertIn("-NotePropertyName service_sid_policy -NotePropertyValue 'unrestricted'", source)
        self.assertIn('product_version=$coreProfile.version', source)
        self.assertIn('if($script:cfg.product_version -cne $coreProfile.version)', source)
        self.assertIn("if(-not $Policy -and -not $CreatedNow -and -not $SqlEnabled)", source)

    def test_owner_wrapper_has_no_service_mutation_restart_or_windows_admin_requirement(self):
        source = HELPER.read_text()
        self.assertNotIn('WindowsBuiltInRole', source)
        self.assertIn("if($PSVersionTable.PSVersion.Major -eq 5){$env:PSModulePath=Join-Path $PSHOME 'Modules'}", source)
        self.assertNotIn('-Verb RunAs', source)
        self.assertNotIn('Start-Service', source)
        self.assertNotIn('Stop-Service', source)
        self.assertNotIn("'sidtype'", source)
        self.assertLess(source.index('if(-not $Apply)'), source.index("$master=Open-CoreNextSqlOwnerConnection 'master'"))
        self.assertIn("$identity.User.Value -cne $config.owner_sid", source)
        self.assertIn('CORE_NEXT_SQL_EXISTING_CONFIGURATION_CONFLICT', source)
        self.assertNotIn('DROP DATABASE', source)


if __name__ == '__main__': unittest.main()
