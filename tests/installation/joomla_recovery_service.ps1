#requires -Version 7.0
[CmdletBinding()]
param([switch]$Apply,[ValidateSet('r1','r2')][string]$Attempt='r2')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$targetState=Join-Path $projectRoot 'build\workstation\test-install\state data'
$targetInstall=Join-Path $projectRoot 'build\workstation\test-install\application files'
$recoveryRoot=Join-Path $projectRoot 'build\joomla-recovery-20261101'
$evidenceRoot=Join-Path $recoveryRoot 'evidence'
$privateRoot=Join-Path $recoveryRoot 'private-backup'
$output=Join-Path $evidenceRoot ('service-restart-'+$Attempt+'.json')
if(Test-Path -LiteralPath $output){throw 'Existing service receipt must remain preserved.'}
$targetService='DragonhydraWorkstationTest'
$protectedNames=@('DragonhydraWorkstation','DragonhydraProvidersA2Test','DragonhydraGenesisA8Test')
$record=[ordered]@{schema_version=1;passed=$false;started_at=[DateTime]::UtcNow.ToString('o');target_service=$targetService;restart_requested=[bool]$Apply;checks=@();credential_values_emitted=$false;configuration_modified=$false;database_repair_requested=$false}
function Save-Receipt {
    $temporary=$output+'.next'
    $record|ConvertTo-Json -Depth 12|Set-Content -LiteralPath $temporary -Encoding utf8NoBOM
    Move-Item -LiteralPath $temporary -Destination $output -Force
}
function Check([string]$name,[bool]$condition) {
    $record.checks+=@{name=$name;status=$(if($condition){'PASS'}else{'FAIL'})}
    Save-Receipt
    if(-not $condition){throw 'A scoped service verification gate failed.'}
}
function Services([string[]]$names) {
    @(foreach($name in $names){
        $service=Get-CimInstance Win32_Service -Filter "Name='$name'"
        if(-not $service){throw 'Expected workstation service is missing.'}
        [ordered]@{name=$service.Name;state=$service.State;pid=$service.ProcessId;account=$service.StartName;path=$service.PathName}
    })
}
function Process-Chain {
    $listeners=@(Get-NetTCPConnection -State Listen|Where-Object LocalPort -in @(18740,18741,18744))
    $result=@()
    foreach($listener in $listeners){
        $process=Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        $owner=Invoke-CimMethod -InputObject $process -MethodName GetOwner
        $parent=Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ParentProcessId)"
        $result+=@{port=$listener.LocalPort;address=$listener.LocalAddress;pid=$process.ProcessId;name=$process.Name;executable=$process.ExecutablePath;command_line=$process.CommandLine;owner=($owner.Domain+'\'+$owner.User);parent=@{pid=$parent.ProcessId;name=$parent.Name;executable=$parent.ExecutablePath;command_line=$parent.CommandLine}}
    }
    $result
}
function Ready {
    $session=Get-Content -LiteralPath (Join-Path $targetState 'client\local-session.json') -Raw|ConvertFrom-Json
    $health=Invoke-RestMethod -Uri 'http://127.0.0.1:18744/dragon/api/v1/health/ready' -Headers @{Authorization=('Bearer '+$session.token)} -TimeoutSec 5
    $joomla=Invoke-WebRequest -Uri 'http://127.0.0.1:18740/administrator/' -TimeoutSec 5
    @{health=$health;joomla_http_status=[int]$joomla.StatusCode;login_form_present=$joomla.Content.Contains('mod-login-username')}
}
try {
    $cfg=Get-Content -LiteralPath (Join-Path $targetState 'workstation.json') -Raw|ConvertFrom-Json
    Check 'fixed-profile-and-port-identity' ($cfg.service_name -eq $targetService -and $cfg.install_root -eq $targetInstall -and $cfg.state_root -eq $targetState -and $cfg.api_port -eq 18744 -and $cfg.web_port -eq 18740 -and $cfg.database_port -eq 18741)
    $principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    $record.elevated=$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    Check 'administrative-inspection-token' $record.elevated
    $backup=Get-Content -LiteralPath (Join-Path $evidenceRoot 'backup-r1.json') -Raw|ConvertFrom-Json
    $auth=Get-Content -LiteralPath (Join-Path $evidenceRoot 'authenticated-pre-restart-r3.json') -Raw|ConvertFrom-Json
    Check 'recoverable-backup-and-authenticated-acceptance-before-restart' ($backup.passed -and $auth.passed)
    $record.protected_services_before=Services $protectedNames
    $record.target_before=Services @($targetService)
    $record.processes_before=Process-Chain
    $record.before=Ready
    foreach($entry in $record.processes_before){
        if(-not $entry.executable -or -not ([IO.Path]::GetFullPath($entry.executable)).StartsWith($targetInstall+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Listener executable belongs to a different installation.'}
    }
    Check 'all-three-target-listeners-owned-by-expected-installation' ($record.processes_before.Count -eq 3)
    $bridge=Join-Path $targetState 'kernel\joomla-bridge.json'
    $bridgeInfo=Get-Item -LiteralPath $bridge
    $record.bridge_before=@{path=$bridge;bytes=$bridgeInfo.Length;last_write_utc=$bridgeInfo.LastWriteTimeUtc.ToString('o');content_read=$false;source_acl_modified=$false;backup_required_for_content_change=$false;reason='No bridge/configuration change is requested; existing LocalService-only credential protection is preserved.'}
    Check 'protected-bridge-present-without-opening-secret-or-changing-acl' ($bridgeInfo.Length -gt 32)
    $apache=Join-Path $targetInstall 'web\apache\bin\httpd.exe'
    $nativeOutput=& $apache -t -f (Join-Path $targetState 'web-config\httpd.conf') 2>&1
    $record.apache_config_test=@{exit_code=$LASTEXITCODE;syntax_ok=([string]$nativeOutput).Contains('Syntax OK')}
    Check 'actual-apache-configuration-syntax' ($record.apache_config_test.exit_code -eq 0)
    if(-not $Apply){throw 'Service operation requires explicit -Apply.'}
    Stop-Service -Name $targetService -ErrorAction Stop
    (Get-Service -Name $targetService).WaitForStatus('Stopped',[TimeSpan]::FromSeconds(55))
    Start-Service -Name $targetService -ErrorAction Stop
    $deadline=[DateTime]::UtcNow.AddSeconds(180)
    $ready=$false
    while([DateTime]::UtcNow -lt $deadline){
        try{$record.after=Ready;$ready=($record.after.health.status -eq 'ready' -and $record.after.joomla_http_status -eq 200 -and $record.after.login_form_present);if($ready){break}}catch{}
        Start-Sleep -Milliseconds 800
    }
    Check 'target-service-restarted-api-and-joomla-ready' $ready
    $record.target_after=Services @($targetService)
    $record.protected_services_after=Services $protectedNames
    $record.processes_after=Process-Chain
    Check 'unrelated-three-services-retain-state-pid-and-image' (($record.protected_services_before|ConvertTo-Json -Depth 5 -Compress) -eq ($record.protected_services_after|ConvertTo-Json -Depth 5 -Compress))
    $bridgeInfoAfter=Get-Item -LiteralPath $bridge
    Check 'existing-bridge-file-size-and-timestamp-preserved' ($record.bridge_before.bytes -eq $bridgeInfoAfter.Length -and $record.bridge_before.last_write_utc -eq $bridgeInfoAfter.LastWriteTimeUtc.ToString('o'))
    $record.passed=$true
}catch{
    $record.failure_class=$_.Exception.GetType().FullName
    $record.failure_stage='See the last recorded check; raw messages omitted to avoid secrets.'
}finally{
    $record.finished_at=[DateTime]::UtcNow.ToString('o')
    Save-Receipt
}
[pscustomobject]@{passed=$record.passed;checks=$record.checks.Count;receipt=$output}|ConvertTo-Json
if(-not $record.passed){exit 1}
