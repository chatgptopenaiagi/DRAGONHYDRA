"""Real PS7/PS5.1 receipt files and in-memory builders; no SQL/SCM/product calls."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAB = Path(r'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB')
HELPER = ROOT/'packaging/windows/workstation/Configure-CoreNextSqlResearch.ps1'
PROFILE = ROOT/'packaging/windows/workstation/CoreNextProfile.ps1'
LIBRARY = Path(os.environ.get('DRAGONHYDRA_ATOMIC_HELPER', str(
    LAB/'build/workstation-dev8-acl-r2/stage/workstation/DragonhydraAtomicFile.dll')))
HOSTS = [Path(r'C:\Program Files\PowerShell\7\pwsh.exe'),
         Path(r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe')]
GIT = Path(r'C:\Program Files\Git\cmd\git.exe')


def quote(value):
    return "'"+str(value).replace("'", "''")+"'"


@unittest.skipUnless(os.name == 'nt' and LIBRARY.is_file(),
                     'Windows and an existing prebuilt AtomicFile DLL required; no compiler fallback')
class SqlReceiptTests(unittest.TestCase):
    def run_ps(self, body, *, hosts=HOSTS, historical=False, library=True, checksum_baseline=False):
        scratch=LAB/'tests';scratch.mkdir(exist_ok=True)
        results=[]
        for host in hosts:
            with self.subTest(host=str(host)), tempfile.TemporaryDirectory(
                    prefix='sql receipts ', dir=scratch) as directory:
                fixture=Path(directory)
                if library:
                    shutil.copy2(LIBRARY,fixture/LIBRARY.name)
                    self.assertEqual(hashlib.sha256(LIBRARY.read_bytes()).digest(),
                                     hashlib.sha256((fixture/LIBRARY.name).read_bytes()).digest())
                helper=HELPER
                if historical:
                    helper=fixture/'historical.ps1'
                    helper.write_bytes(subprocess.check_output([
                        str(GIT),'-C',str(ROOT),'show',
                        '0e5df36704eeeaadbbf2380cc5352473fc2ebf0b:packaging/windows/workstation/Configure-CoreNextSqlResearch.ps1'],timeout=15))
                if checksum_baseline:
                    baseline=fixture/'checksum-baseline.ps1'
                    baseline.write_bytes(subprocess.check_output([
                        str(GIT),'-C',str(ROOT),'show',
                        '4a8177691bc272acb9258e256c7e9155baba76d3:packaging/windows/workstation/Configure-CoreNextSqlResearch.ps1'],timeout=15))
                setup=r'''
$ErrorActionPreference='Stop'
$OutputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=$OutputEncoding
if($PSVersionTable.PSVersion.Major -eq 5){$env:PSModulePath=Join-Path $PSHOME 'Modules'}
function Require($Value,[string]$Code){if(-not $Value){throw $Code}}
function Reject([scriptblock]$Body,[string]$Code){
    $caught=$null;try{& $Body}catch{$caught=$_}
    Require ($null -ne $caught -and $caught.Exception.Message -like ('*'+$Code+'*')) ('EXPECTED_'+$Code)
    $caught
}
'''
                setup+='\n$fixture='+quote(fixture)+'\n. '+quote(PROFILE)+'\n'
                if checksum_baseline:
                    setup+='$checksumBaseline='+quote(baseline)+'\n'
                setup+='$source='+quote(helper)+r'''
$tokens=$null;$errors=$null;$ast=[Management.Automation.Language.Parser]::ParseFile($source,[ref]$tokens,[ref]$errors)
Require ($errors.Count -eq 0) 'SOURCE_PARSE_FAILED'
$definitions=@($ast.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -in @('Save-CoreNextSqlReceipt','New-CoreNextSqlConnectionString','Convert-CoreNextSqlHash','Get-CoreNextSqlHex')},$true))
$functionFile=Join-Path $fixture 'receipt-functions.ps1'
[IO.File]::WriteAllText($functionFile,(($definitions|ForEach-Object {$_.Extent.Text}) -join "`r`n"),[Text.UTF8Encoding]::new($true))
. $functionFile
$receipt=Join-Path $fixture 'receipt.json'
$profilePath=Join-Path $fixture 'installation-profile.json'
[IO.File]::WriteAllText($profilePath,'{"installation_id":"SYNTHETIC_ONLY","provider_schedules":"disabled"}')
$profileBefore=(Get-FileHash -LiteralPath $profilePath -Algorithm SHA256).Hash
'''
                runner=fixture/'fixture.ps1'
                runner.write_text(setup+'\n'+body,encoding='utf-8-sig')
                # The owner approved Process RemoteSigned. No policy writes,
                # elevation, fallback transport or weaker child policy exists.
                completed=subprocess.run([str(host),'-NoLogo','-NoProfile','-NonInteractive',
                    '-ExecutionPolicy','RemoteSigned','-File',str(runner)],
                    capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
                self.assertEqual(completed.returncode,0,completed.stdout[-1000:]+completed.stderr[-2500:])
                results.append(json.loads(completed.stdout.strip()))
        return results

    def test_first_and_repeated_receipts_use_existing_typed_helper_and_preserve_profile(self):
        self.run_ps(r'''
for($n=0;$n -lt 20;$n++){
    $reader=$null
    if(Test-Path -LiteralPath $receipt){$reader=[IO.File]::Open($receipt,'Open','Read',([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))}
    try{Save-CoreNextSqlReceipt @{stage='validated';sequence=$n;label=('Fu'+[char]0x00df+'ball')} $receipt $fixture}finally{if($reader){$reader.Dispose()}}
    $value=[Dragonhydra.Workstation.AtomicFile]::Read($receipt)|ConvertFrom-Json
    Require ($value.sequence -eq $n -and $value.label -ceq ('Fu'+[char]0x00df+'ball')) 'REPEATED_RECEIPT_INVALID'
    Require (-not(Test-Path -LiteralPath ($receipt+'.tmp'))) 'SUCCESS_LEFT_PENDING_TEMP'
}
Require ((Get-FileHash -LiteralPath $profilePath -Algorithm SHA256).Hash -ceq $profileBefore) 'PROFILE_CHANGED'
Require ([Dragonhydra.Workstation.AtomicFile].Assembly.Location -ieq (Join-Path $fixture 'DragonhydraAtomicFile.dll')) 'EXISTING_SIBLING_HELPER_NOT_USED'
@{passed=$true;writes=20;profile_unchanged=$true;sql_calls=0}|ConvertTo-Json -Compress
''')

    def test_historical_native_writer_reproduces_failure_without_destroying_first_receipt(self):
        self.run_ps(r'''
Save-CoreNextSqlReceipt @{stage='validated';sequence=1} $receipt $fixture
$before=(Get-FileHash -LiteralPath $receipt -Algorithm SHA256).Hash
$caught=$null;try{Save-CoreNextSqlReceipt @{stage='failed_reconciliation_required';sequence=2} $receipt $fixture}catch{$caught=$_}
Require ($null -ne $caught) 'HISTORICAL_NATIVE_FAILURE_NOT_REPRODUCED'
Require ($caught.Exception.InnerException -is [ArgumentException]) 'HISTORICAL_NULL_BACKUP_ARGUMENT_EXCEPTION_REQUIRED'
Require ((Get-FileHash -LiteralPath $receipt -Algorithm SHA256).Hash -ceq $before) 'HISTORICAL_RECEIPT_DESTROYED'
Require (Test-Path -LiteralPath ($receipt+'.tmp')) 'HISTORICAL_PENDING_EVIDENCE_MISSING'
@{passed=$true;original_failed=$true;first_receipt_preserved=$true;pending_temp_preserved=$true;sql_calls=0}|ConvertTo-Json -Compress
''',hosts=[HOSTS[1]],historical=True)

    def test_existing_pending_temp_refuses_without_replacing_evidence(self):
        self.run_ps(r'''
Save-CoreNextSqlReceipt @{stage='validated'} $receipt $fixture
[IO.File]::WriteAllText(($receipt+'.tmp'),'original pending evidence')
$old=(Get-FileHash -LiteralPath $receipt -Algorithm SHA256).Hash
$temp=(Get-FileHash -LiteralPath ($receipt+'.tmp') -Algorithm SHA256).Hash
$null=Reject {Save-CoreNextSqlReceipt @{passed=$true} $receipt $fixture} 'CORE_NEXT_SQL_UNRECONCILED_RECEIPT_TEMP'
Require ((Get-FileHash -LiteralPath $receipt -Algorithm SHA256).Hash -ceq $old) 'COMMITTED_RECEIPT_CHANGED'
Require ((Get-FileHash -LiteralPath ($receipt+'.tmp') -Algorithm SHA256).Hash -ceq $temp) 'PENDING_RECEIPT_CHANGED'
@{passed=$true;sql_calls=0}|ConvertTo-Json -Compress
''')

    def test_locked_destination_preserves_old_receipt_and_pending_failure_bytes(self):
        self.run_ps(r'''
Save-CoreNextSqlReceipt @{stage='validated'} $receipt $fixture
$old=(Get-FileHash -LiteralPath $receipt -Algorithm SHA256).Hash
$stream=[IO.File]::Open($receipt,'Open','Read',[IO.FileShare]::None)
$watch=[Diagnostics.Stopwatch]::StartNew();$caught=$null
try{try{Save-CoreNextSqlReceipt @{stage='next'} $receipt $fixture}catch{$caught=$_}}finally{$stream.Dispose()}
Require ($null -ne $caught -and $watch.Elapsed.TotalSeconds -lt 5) 'BOUNDED_LOCK_FAILURE_REQUIRED'
Require ((Get-FileHash -LiteralPath $receipt -Algorithm SHA256).Hash -ceq $old) 'LOCK_FAILURE_CHANGED_COMMITTED_RECEIPT'
Require (([IO.File]::ReadAllText($receipt+'.tmp')|ConvertFrom-Json).stage -ceq 'next') 'LOCK_FAILURE_LOST_TEMP'
$null=Reject {Save-CoreNextSqlReceipt @{passed=$true} $receipt $fixture} 'CORE_NEXT_SQL_UNRECONCILED_RECEIPT_TEMP'
@{passed=$true;old_and_pending_preserved=$true;sql_calls=0}|ConvertTo-Json -Compress
''')

    def test_outside_and_junction_receipts_are_rejected_before_writes(self):
        self.run_ps(r'''
$outside=Join-Path (Split-Path $fixture -Parent) 'outside-receipt.json'
$null=Reject {Save-CoreNextSqlReceipt @{} $outside $fixture} 'CORE_NEXT_PATH_OUTSIDE_LAB'
$target=Join-Path $fixture 'target';$null=New-Item -ItemType Directory -Path $target
$link=Join-Path $fixture 'linked';$null=New-Item -ItemType Junction -Path $link -Target $target
try{
 $null=Reject {Save-CoreNextSqlReceipt @{} (Join-Path $link 'receipt.json') $fixture} 'CORE_NEXT_REPARSE_PATH_REJECTED'
 Require (-not(Test-Path -LiteralPath (Join-Path $target 'receipt.json'))) 'JUNCTION_TARGET_WRITTEN'
}finally{[IO.Directory]::Delete($link)}
Require ((Get-FileHash -LiteralPath $profilePath -Algorithm SHA256).Hash -ceq $profileBefore) 'PROFILE_CHANGED'
@{passed=$true;sql_calls=0}|ConvertTo-Json -Compress
''')

    def test_missing_existing_atomic_helper_refuses_before_temp_write(self):
        self.run_ps(r'''
$null=Reject {Save-CoreNextSqlReceipt @{} $receipt $fixture} 'CORE_NEXT_SQL_ATOMIC_HELPER_REQUIRED'
Require (-not(Test-Path -LiteralPath $receipt) -and -not(Test-Path -LiteralPath ($receipt+'.tmp'))) 'MISSING_LIBRARY_WROTE_RECEIPT'
@{passed=$true;sql_calls=0}|ConvertTo-Json -Compress
''',library=False)

    def test_primary_failure_survives_successful_and_failed_error_receipt_commits(self):
        self.run_ps(r'''
$outer=@($ast.FindAll({param($n)$n -is [Management.Automation.Language.TryStatementAst] -and $n.Body.Extent.Text.Contains("`$master=Open-CoreNextSqlOwnerConnection 'master'")},$true))
Require ($outer.Count -eq 1) 'EXACT_OWNER_FAILURE_HANDLER_REQUIRED'
$handler=[scriptblock]::Create("try {throw [ArgumentException]::new('SYNTHETIC_PRIMARY_FAILURE')} catch "+$outer[0].CatchClauses[0].Body.Extent.Text)
$record=[ordered]@{passed=$false;stage='validated'};$ReceiptPath=$receipt;$profile=@{lab_root=$fixture};$transaction=$null
Save-CoreNextSqlReceipt $record $receipt $fixture
$caught=$null;try{& $handler}catch{$caught=$_}
Require ($caught.Exception.InnerException -is [ArgumentException]) 'PRIMARY_FAILURE_NOT_PRESERVED'
$failed=[IO.File]::ReadAllText($receipt)|ConvertFrom-Json
Require ($failed.stage -ceq 'failed_reconciliation_required' -and $failed.failure_class -ceq 'ArgumentException' -and $failed.failure_line -gt 0 -and $failed.passed -eq $false) 'FAILED_RECEIPT_DIAGNOSTIC_LOST'
$hash=(Get-FileHash -LiteralPath $receipt -Algorithm SHA256).Hash
function Save-CoreNextSqlReceipt {throw [IO.IOException]::new('SYNTHETIC_SECONDARY_RECEIPT_FAILURE')}
$caught=$null;try{& $handler}catch{$caught=$_}
Require ($caught.Exception.InnerException -is [ArgumentException] -and $caught.Exception.InnerException.Message -ceq 'SYNTHETIC_PRIMARY_FAILURE') 'SECONDARY_FAILURE_MASKED_PRIMARY'
Require ($caught.Exception.Data['receipt_failure_class'] -ceq 'IOException') 'SECONDARY_FAILURE_DIAGNOSTIC_MISSING'
Require ((Get-FileHash -LiteralPath $receipt -Algorithm SHA256).Hash -ceq $hash) 'FAILED_RECEIPT_CHANGED_AFTER_SECONDARY_FAILURE'
@{passed=$true;primary_preserved=$true;sql_calls=0}|ConvertTo-Json -Compress
''')

    def test_canonical_builder_roundtrips_security_timeouts_and_identity_without_open(self):
        self.run_ps(r'''
foreach($trust in @($false,$true)){
 $text=New-CoreNextSqlConnectionString 'lpc:SYNTHETIC-LOCAL' 'SYNTHETIC_DATABASE' $trust
 $builder=New-Object System.Data.SqlClient.SqlConnectionStringBuilder($text)
 Require ($builder['Data Source'] -ceq 'lpc:SYNTHETIC-LOCAL' -and $builder['Initial Catalog'] -ceq 'SYNTHETIC_DATABASE') 'TARGET_CHANGED'
 Require ($builder['Integrated Security'] -eq $true -and $builder['Encrypt'] -eq $true -and $builder['TrustServerCertificate'] -eq $trust) 'AUTH_ENCRYPTION_CHANGED'
 Require ($builder['Connect Timeout'] -eq 5 -and $builder['Pooling'] -eq $false -and $builder['Application Name'] -ceq 'DRAGONHYDRA owned SQL provisioning') 'BOUNDS_OR_APP_ID_CHANGED'
 Require ($builder['User ID'] -ceq '' -and $builder['Password'] -ceq '') 'PASSWORD_AUTH_ADDED'
}
if($PSVersionTable.PSVersion.Major -eq 5){
 $old=New-Object System.Data.SqlClient.SqlConnectionStringBuilder
 $caught=$null;try{$old.DataSource='lpc:SYNTHETIC-LOCAL'}catch{$caught=$_}
 Require ($null -ne $caught) 'ORIGINAL_IDICTIONARY_SETTER_FAILURE_NOT_REPRODUCED'
 Require ($caught.Exception.Message -match 'DataSource' -and $caught.Exception -is [ArgumentException]) 'ORIGINAL_DATASOURCE_KEYWORD_ERROR_REQUIRED'
}
$pure=($definitions|Where-Object Name -CEQ 'New-CoreNextSqlConnectionString').Extent.Text
Require (-not $pure.Contains('.Open(') -and -not $pure.Contains('SqlConnection(')) 'PURE_BUILDER_OPENS_CONNECTION'
@{passed=$true;sql_connections=0;trust_variants=2}|ConvertTo-Json -Compress
''')


    def test_checksum_remains_one_byte_array_and_infers_varbinary_without_sql(self):
        schema=ROOT/'src/dragonhydra/research_storage/schema_sqlserver.sql'
        body='$schemaHash='+quote(hashlib.sha256(schema.read_bytes()).hexdigest())+'\n'+r'''
foreach($hex in @($schemaHash,('00'*32),('ff'*32),('0123456789ABCDEF'*4))){
 $checksum=Convert-CoreNextSqlHash $hex
 Require ($checksum.GetType().FullName -ceq 'System.Byte[]' -and $checksum.Length -eq 32) 'TYPED_BINARY_CHECKSUM_REQUIRED'
 Require ((Get-CoreNextSqlHex $checksum) -ceq $hex.ToLowerInvariant()) 'CHECKSUM_BYTES_CHANGED'
 $command=New-Object System.Data.SqlClient.SqlCommand
 try{
  $parameter=$command.Parameters.AddWithValue('@checksum',$checksum)
  Require ($parameter.Value.GetType().FullName -ceq 'System.Byte[]') 'PARAMETER_LOST_BINARY_TYPE'
  Require ($parameter.get_SqlDbType() -eq [Data.SqlDbType]::VarBinary -and $parameter.Size -eq 32) 'VARBINARY_32_REQUIRED'
  Require ((Get-CoreNextSqlHex $parameter.Value) -ceq $hex.ToLowerInvariant()) 'PARAMETER_BYTES_CHANGED'
 }finally{$command.Dispose()}
}
$tokens=$null;$errors=$null;$oldAst=[Management.Automation.Language.Parser]::ParseFile($checksumBaseline,[ref]$tokens,[ref]$errors)
Require ($errors.Count -eq 0) 'HISTORICAL_CHECKSUM_SOURCE_PARSE_FAILED'
$old=@($oldAst.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq 'Convert-CoreNextSqlHash'},$true))
Require ($old.Count -eq 1) 'EXACT_HISTORICAL_CHECKSUM_FUNCTION_REQUIRED'
. ([scriptblock]::Create($old[0].Extent.Text.Replace('function Convert-CoreNextSqlHash(','function Convert-HistoricalCoreNextSqlHash(')))
$oldChecksum=Convert-HistoricalCoreNextSqlHash $schemaHash
Require ($oldChecksum.GetType().FullName -ceq 'System.Object[]' -and $oldChecksum.Length -eq 32) 'HISTORICAL_ENUMERATION_FAILURE_NOT_REPRODUCED'
Require ((Get-CoreNextSqlHex ([byte[]]$oldChecksum)) -ceq $schemaHash) 'HISTORICAL_BINARY_CONTENT_DIFFERS'
$command=New-Object System.Data.SqlClient.SqlCommand
try{
 $parameter=$command.Parameters.AddWithValue('@checksum',$oldChecksum)
 $caught=$null;try{$null=$parameter.get_SqlDbType()}catch{$caught=$_}
 Require ($null -ne $caught) 'HISTORICAL_PROVIDER_MAPPING_FAILURE_NOT_REPRODUCED'
 $cause=$caught.Exception;$argument=$false
 while($cause){if($cause -is [ArgumentException] -and $cause.Message -match [regex]::Escape('System.Object[]')){$argument=$true};$cause=$cause.InnerException}
 Require $argument 'HISTORICAL_PROVIDER_ARGUMENT_EXCEPTION_REQUIRED'
}finally{$command.Dispose()}
Require ((Get-FileHash -LiteralPath $profilePath -Algorithm SHA256).Hash -ceq $profileBefore) 'PROFILE_CHANGED'
@{passed=$true;checksum_type='System.Byte[]';sql_db_type='VarBinary';bytes=32;vectors=4;historical_failure_reproduced=$true;sql_connections=0;sql_commands_executed=0}|ConvertTo-Json -Compress
'''
        self.run_ps(body,checksum_baseline=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
