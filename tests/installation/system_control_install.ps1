#requires -Version 7.0
[CmdletBinding()]
param(
    [ValidateSet('Verify','Restart','Upgrade')][string]$Phase='Verify',
    [Parameter(Mandatory)][string]$Installer,
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{64}$')][string]$ExpectedInstallerSha256,
    [Parameter(Mandatory)][string]$Output,
    [switch]$Apply,
    [switch]$NewPayload
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$Project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\')
$ProfileRoot=Join-Path $Project 'build\workstation\test-install'
$InstallRoot=Join-Path $ProfileRoot 'application files'
$StateRoot=Join-Path $ProfileRoot 'state data'
$ServiceName='DragonhydraWorkstationTest'
$ExpectedService='"'+(Join-Path $InstallRoot 'workstation\DragonhydraService.exe')+'" --state "'+$StateRoot+'" --name '+$ServiceName
$ProtectedNames=@('DragonhydraProvidersA2Test','DragonhydraWorkstation','DragonhydraGenesisA8Test')
$Checks=[Collections.Generic.List[object]]::new()
$CanWriteReceipt=$false
$Report=[ordered]@{schema_version=1;phase=$Phase;passed=$false;applied=$false;started_at=[DateTime]::UtcNow.ToString('o');
    install_root=$InstallRoot;state_root=$StateRoot;service_name=$ServiceName;checks=$Checks;
    scope='Existing fixed primary workstation on this host; not a clean-machine or reboot claim';
    unrelated_services_controlled=$false;credentials_printed=$false}

function Hash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function ReadJson([string]$Path) { Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json }
function AddCheck([string]$Name,$Details) { $Checks.Add([ordered]@{name=$Name;passed=$true;details=$Details}) }
function ProtectedServices {
    $services=@(Get-CimInstance Win32_Service | Where-Object {$_.Name -in $ProtectedNames} |
        Sort-Object Name | Select-Object Name,State,ProcessId,PathName)
    if($services.Count -ne 3){throw 'PROTECTED_SERVICE_OBSERVATION_INCOMPLETE'}
    $services
}
function AssertProtected($Before) {
    $after=@(ProtectedServices)
    $Report.protected_services_after=$after
    if(($Before | ConvertTo-Json -Depth 6 -Compress) -cne ($after | ConvertTo-Json -Depth 6 -Compress)){
        throw 'PROTECTED_SERVICE_STATE_OR_PID_CHANGED'
    }
}
function OrdinaryAncestors([string]$Path) {
    $walk=[IO.Path]::GetFullPath($Path).TrimEnd('\')
    while($walk.StartsWith($Project+'\',[StringComparison]::OrdinalIgnoreCase)){
        if(Test-Path -LiteralPath $walk){
            if((Get-Item -LiteralPath $walk -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'REPARSE_POINT_REJECTED'}
        }
        $walk=Split-Path -Path $walk -Parent
    }
}
function OwnedService {
    $service=Get-CimInstance Win32_Service -Filter "Name='$ServiceName'"
    if(-not $service -or $service.PathName -cne $ExpectedService -or $service.StartName -ine 'NT AUTHORITY\LocalService'){
        throw 'EXACT_PRIMARY_SERVICE_BINDING_REQUIRED'
    }
    $cfg=ReadJson (Join-Path $StateRoot 'workstation.json')
    if($cfg.install_root -cne $InstallRoot -or $cfg.state_root -cne $StateRoot -or $cfg.service_name -cne $ServiceName){
        throw 'EXACT_PRIMARY_STATE_OWNERSHIP_REQUIRED'
    }
    $ports=@([int]$cfg.api_port,[int]$cfg.web_port,[int]$cfg.database_port)
    if(@($ports | Sort-Object -Unique).Count -ne 3 -or @($ports | Where-Object {$_ -lt 1024 -or $_ -gt 65535}).Count){throw 'INVALID_ASSIGNED_PORTS'}
    [pscustomobject]@{service=$service;api_port=$ports[0];web_port=$ports[1];database_port=$ports[2]}
}
function Api($Owned,[string]$Path) {
    # Owner-readable pairing metadata only; values never enter logs/reports.
    $token=(ReadJson (Join-Path $StateRoot 'client\local-session.json')).token
    Invoke-RestMethod -Uri ('http://127.0.0.1:'+$Owned.api_port+'/dragon/api/v1'+$Path) -Headers @{Authorization=('Bearer '+$token)} -TimeoutSec 15
}
function Ready([int]$Timeout=360) {
    $deadline=[DateTime]::UtcNow.AddSeconds($Timeout)
    do{
        try{
            $owned=OwnedService
            $status=ReadJson (Join-Path $StateRoot 'status.json')
            if($status.stage -eq 'failed'){throw 'PRIMARY_SERVICE_REPORTED_FAILED'}
            if($owned.service.State -eq 'Running' -and $status.stage -eq 'ready'){
                $health=Api $owned '/health/ready'
                if($health.status -eq 'ready'){return $owned}
            }
        }catch{
            if($_.Exception.Message -eq 'PRIMARY_SERVICE_REPORTED_FAILED'){throw}
        }
        Start-Sleep -Milliseconds 500
    }while([DateTime]::UtcNow -lt $deadline)
    throw 'PRIMARY_READY_DEADLINE_EXPIRED_INSPECT_PRIVATE_STATUS'
}
function Snapshot($Owned) {
    $page=Api $Owned '/matches?limit=1'
    if($page.total -lt 1 -or @($page.items).Count -ne 1){throw 'NO_RETAINED_MATCH_AVAILABLE'}
    $allIds=@();$offset=0
    do{$batch=Api $Owned ('/matches?limit=200&offset='+$offset);$allIds+=@($batch.items|ForEach-Object {$_.id+':'+$_.version});$offset+=@($batch.items).Count;if($offset -lt $batch.total -and -not @($batch.items).Count){throw 'MATCH_PAGINATION_STALLED'}}while($offset -lt $batch.total)
    $bytes=[Text.Encoding]::UTF8.GetBytes((($allIds|Sort-Object)-join "`n"));$sha=[Security.Cryptography.SHA256]::Create();try{$allHash=([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
    $clientEndpoint=ReadJson (Join-Path $StateRoot 'client\endpoint.json')
    if($clientEndpoint.url -cne ('http://127.0.0.1:'+$Owned.api_port)){throw 'CLIENT_ENDPOINT_DIFFERS_FROM_CONFIGURED_API'}
    $clientPairing=Hash (Join-Path $StateRoot 'client\local-session.json')
    # The client copy is deliberately owner-readable; the kernel copy belongs
    # to LocalService/SYSTEM. Never require a kernel-token read or ACL takeover
    # for unelevated Verify. Successful authenticated API health proves this
    # client credential is accepted by its corresponding installed server.
    $joomla=Invoke-WebRequest -Uri ('http://127.0.0.1:'+$Owned.web_port+'/') -TimeoutSec 20
    if($joomla.StatusCode -ne 200){throw 'JOOMLA_HOME_NOT_READY'}
    foreach($relative in @('kernel\core.sqlite3','site\configuration.php','mysql-data\mysql')){
        if(-not(Test-Path -LiteralPath (Join-Path $StateRoot $relative))){throw 'REQUIRED_RETAINED_COMPONENT_MISSING'}
    }
    [ordered]@{records=[int]$page.total;all_match_id_versions_sha256=$allHash;match_id=$page.items[0].id;evidence_version=$page.items[0].version;
        pairing_file_sha256=$clientPairing;joomla_configuration_sha256=(Hash (Join-Path $StateRoot 'site\configuration.php'));
        api_url=$clientEndpoint.url;joomla_http_status=[int]$joomla.StatusCode;api_port=$Owned.api_port;web_port=$Owned.web_port;database_port=$Owned.database_port;
        service_pid=[int]$Owned.service.ProcessId}
}
function CompareRetained($Before,$After) {
    foreach($key in @('records','all_match_id_versions_sha256','match_id','evidence_version','pairing_file_sha256','joomla_configuration_sha256','api_port','web_port','database_port')){
        if($Before[$key] -cne $After[$key]){throw ('RETAINED_STATE_CHANGED_'+$key)}
    }
}
function ShortcutProof {
    $shell=New-Object -ComObject WScript.Shell
    $candidates=@(
        (Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) ('DRAGONHYDRA Workstation - '+$ServiceName+'.lnk')),
        (Join-Path ([Environment]::GetFolderPath('CommonPrograms')) ('DRAGONHYDRA Workstation - '+$ServiceName+'\DRAGONHYDRA Workstation.lnk')))
    $result=@()
    foreach($path in $candidates){
        if(-not(Test-Path -LiteralPath $path)){throw 'OFFICIAL_PRIMARY_SHORTCUT_MISSING'}
        $shortcut=$shell.CreateShortcut($path)
        if($shortcut.TargetPath -cne (Join-Path $InstallRoot 'workstation\DragonhydraLauncher.exe') -or $shortcut.Arguments -cne ('--state "'+$StateRoot+'"')){throw 'OFFICIAL_SHORTCUT_BINDING_DIFFERS'}
        $result+=@{path=$path;target=$shortcut.TargetPath;arguments=$shortcut.Arguments}
    }
    $result
}

try{
    $Installer=[IO.Path]::GetFullPath($Installer)
    $Output=[IO.Path]::GetFullPath($Output)
    if(-not $Installer.StartsWith((Join-Path $Project 'dist')+'\',[StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetExtension($Installer) -ine '.exe'){throw 'EXPLICIT_PROJECT_DIST_INSTALLER_REQUIRED'}
    if(-not $Output.StartsWith((Join-Path $Project 'build\system-control-center-20261101\evidence')+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'FRESH_OWNED_PRIMARY_EVIDENCE_REQUIRED'}
    OrdinaryAncestors $Output
    if(Test-Path -LiteralPath $Output){throw 'PRESERVE_EXISTING_RECEIPT'}
    $CanWriteReceipt=$true
    foreach($path in @($Installer,$InstallRoot,$StateRoot)){OrdinaryAncestors $path}
    if((Hash $Installer) -cne $ExpectedInstallerSha256){throw 'INSTALLER_HASH_MISMATCH'}
    $Report.installer=@{path=$Installer;bytes=(Get-Item -LiteralPath $Installer).Length;sha256=$ExpectedInstallerSha256}
    $beforeProtected=@(ProtectedServices)
    $Report.protected_services_before=$beforeProtected
    AddCheck 'verified-installer-and-protected-service-baseline' @{sha256=$ExpectedInstallerSha256}
    $isAdmin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    $Report.administrator_token=$isAdmin
    if($Phase -in @('Upgrade','Restart')){
        if(-not $Apply){throw 'EXPLICIT_APPLY_REQUIRED'}
        if(-not $isAdmin){throw 'ADMINISTRATOR_TOKEN_REQUIRED'}
    }
    if($Phase -eq 'Upgrade'){
        foreach($relative in @('joomla-and-core.sql','core-consistent.sqlite3','installed-inputs/server/DRAGONHYDRA-Server.exe','installed-inputs/client/DRAGONHYDRA-Client.exe')){
            $backup=Join-Path $Project ('build/system-control-center-20261101/private-backup/'+$relative)
            if(-not(Test-Path -LiteralPath $backup -PathType Leaf)){throw 'RECOVERABLE_PRIMARY_BACKUP_REQUIRED'}
        }
        AddCheck 'consistent-database-and-original-binary-backups-exist' @{scope='Fixed primary profile only; restricted private backup'}
    }
    if($Phase -in @('Upgrade','Restart')){
        $beforeOwned=Ready
        $beforeSnapshot=Snapshot $beforeOwned
        $Report.before=$beforeSnapshot
    }
    if($Phase -eq 'Upgrade'){
        $arguments='/S /STATE="'+$StateRoot+'" /SERVICE='+$ServiceName+' /D='+$InstallRoot
        $Report.installer_arguments=$arguments
        # The fixed service name and disjoint binary/data paths are the only
        # installation target. /D is deliberately last for NSIS path parsing.
        $process=Start-Process -FilePath $Installer -ArgumentList $arguments -WindowStyle Hidden -PassThru
        $null=$process.Handle
        $Report.installer_process_id=$process.Id
        if(-not $process.WaitForExit(900000)){throw 'INSTALLER_DEADLINE_EXPIRED_NO_RETRY_OR_KILL_PERFORMED'}
        $Report.installer_exit_code=$process.ExitCode
        if($process.ExitCode -ne 0){throw 'INSTALLER_RETURNED_FAILURE_INSPECT_PRIVATE_DIAGNOSTICS'}
        $Report.applied=$true
        AddCheck 'full-unified-installer-completed' @{exit_code=$process.ExitCode}
    }
    if($Phase -eq 'Restart'){
        $null=OwnedService
        Stop-Service -Name $ServiceName
        (Get-Service $ServiceName).WaitForStatus('Stopped',[TimeSpan]::FromSeconds(90))
        $null=OwnedService
        Start-Service -Name $ServiceName
        $Report.applied=$true
        AddCheck 'exact-owned-service-stop-start' @{service=$ServiceName}
    }
    if($Phase -in @('Verify','Upgrade','Restart')){
        $owned=Ready
        $afterSnapshot=Snapshot $owned
        $Report.after=$afterSnapshot
        $Report.shortcut_bindings=@(ShortcutProof)
        AddCheck 'localservice-api-joomla-mariadb-and-retained-data-ready' $afterSnapshot
        AddCheck 'official-shortcuts-target-corresponding-launcher-and-state' @{count=$Report.shortcut_bindings.Count}
        if($Phase -in @('Upgrade','Restart')){
            CompareRetained $beforeSnapshot $afterSnapshot
            AddCheck 'records-evidence-pairing-joomla-config-and-ports-persisted' @{records=$afterSnapshot.records}
        }
    }
    if($Phase -eq 'Upgrade' -or $NewPayload){
        foreach($pair in @(
            @('server/DRAGONHYDRA-Server.exe','3231c279aab1a3d8b3cbfe6c396dded8ced60e4fb15a42c0a04eb7144e2990a4'),
            @('client/DRAGONHYDRA-Client.exe','f4e8fbae68c4fdc3f52c7f9baaeb98f375df26e34dced3dc87c7988d9a4c0617'),
            @('web/extension.zip','d1c1fd8d35d281b20fc4ffef71fc18fd207b6608a90aa3df65bbe4cb7f671abc'),
            @('workstation/Workstation.ps1','bc184aae7f82acd72b62962ce94b1dbc69c97ae515ac011b34fd5339473ae5cc'))){
            if((Hash (Join-Path $InstallRoot $pair[0])) -cne $pair[1]){throw 'INSTALLED_NEW_PAYLOAD_HASH_MISMATCH'}
        }
        $system=Api $owned '/system';$registry=Api $owned '/system/modules'
        if($system.build.source_content_sha256 -cne 'fa51ebc8963b2dcdfb12a5eee13f3a41fc2b9147d11a8bdf3a78de21bf6c64bb' -or $registry.schema_version -ne 1 -or $registry.modules.Count -ne 18 -or $registry.core_state -ne 'ready'){throw 'INSTALLED_REGISTRY_IDENTITY_OR_CORE_NOT_READY'}
        $component=[xml](Get-Content -LiteralPath (Join-Path $StateRoot 'site/administrator/components/com_dragonhydra/dragonhydra.xml') -Raw)
        if($component.extension.version -cne '0.4.1-dev.3'){throw 'DEPLOYED_JOOMLA_COMPONENT_VERSION_MISMATCH'}
        AddCheck 'exact-new-installed-runtime-client-component-and-registry' @{source_content_sha256=$system.build.source_content_sha256;module_count=$registry.modules.Count;core_state=$registry.core_state;installation_id=$registry.installation_id;component_version='0.4.1-dev.3'}
    }
    AssertProtected $beforeProtected
    AddCheck 'all-three-existing-services-unchanged' @{services=$ProtectedNames}
    $Report.passed=$true
}catch{
    # These messages contain only named guards/component paths, never config
    # objects, HTTP headers, private installer logs, tokens or generated keys.
    $Report.error=@{type=$_.Exception.GetType().Name;message=$_.Exception.Message}
}finally{
    $Report.finished_at=[DateTime]::UtcNow.ToString('o')
    if($CanWriteReceipt -and -not(Test-Path -LiteralPath $Output)){
        try{
            # A rejected output must never become writable again through finally.
            # Recheck after creating parents and immediately before the final move.
            OrdinaryAncestors $Output
            $parent=Split-Path -Path $Output -Parent
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
            OrdinaryAncestors $Output
            $temporary=$Output+'.'+[Guid]::NewGuid().ToString('N')+'.tmp'
            OrdinaryAncestors $temporary
            $stream=[IO.FileStream]::new($temporary,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
            try{
                $bytes=[Text.UTF8Encoding]::new($false).GetBytes(($Report | ConvertTo-Json -Depth 12))
                $stream.Write($bytes,0,$bytes.Length)
                $stream.Flush($true)
            }finally{$stream.Dispose()}
            OrdinaryAncestors $Output
            [IO.File]::Move($temporary,$Output)
        }catch{
            $Report.receipt_write_error='SAFE_RECEIPT_WRITE_FAILED_NO_OVERWRITE'
            $Report.passed=$false
        }
    }
}
Write-Output ($Report | ConvertTo-Json -Depth 12)
if(-not $Report.passed){exit 1}
