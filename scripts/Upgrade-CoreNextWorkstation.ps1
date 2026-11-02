#requires -Version 7.0
[CmdletBinding()]
param([Parameter(Mandatory)][string]$ProfilePath,
      [Parameter(Mandatory)][string]$ExpectedInstallationId,
      [Parameter(Mandatory)][string]$Installer,
      [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{64}$')][string]$ExpectedInstallerSha256,
      [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{40}$')][string]$NewSourceCommit,
      [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{64}$')][string]$ExpectedNewServerSha256,
      [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{64}$')][string]$ExpectedNewClientSha256,
      [string]$FromSourceCommit='953b67fa50dfa9d705f060f97b8a1af5d317c001',
      [string]$FromVersion='0.5.0-dev.1',[string]$ToVersion='0.5.0-dev.2',
      [string]$BackupRoot,[switch]$Apply)
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$lab='C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB'
. (Join-Path $project 'packaging\windows\workstation\CoreNextProfile.ps1')
. (Join-Path $project 'packaging\windows\workstation\CoreNextUpgrade.ps1')
function Hash([string]$path){(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Json([string]$path){Get-Content -LiteralPath $path -Raw|ConvertFrom-Json}
function Save($value,[string]$path){[IO.File]::WriteAllText($path,($value|ConvertTo-Json -Depth 30),[Text.UTF8Encoding]::new($false))}
function Assert-OwnedListeners($p,[int]$ServicePid){
    foreach($port in @($p.ports.api,$p.ports.web,$p.ports.database)){
        $listeners=@(Get-NetTCPConnection -LocalPort $port -State Listen)
        if($listeners.Count -ne 1 -or $listeners[0].LocalAddress -cne '127.0.0.1'){throw 'CORE_NEXT_UPGRADE_LOOPBACK_LISTENER_REQUIRED'}
        $next=[int]$listeners[0].OwningProcess;$bound=$false
        for($i=0;$i -lt 8 -and $next -gt 0;$i++){if($next -eq $ServicePid){$bound=$true;break};$proc=Get-CimInstance Win32_Process -Filter ('ProcessId='+$next);if(-not$proc){break};$next=[int]$proc.ParentProcessId}
        if(-not$bound){throw 'CORE_NEXT_UPGRADE_LISTENER_NOT_OWNED'}
    }
}
function Read-DataSnapshot($p){
    $session=Json (Join-Path $p.state_root 'client\local-session.json')
    $headers=@{Authorization=('Bearer '+$session.token)};$base='http://127.0.0.1:'+$p.ports.api+'/dragon/api/v1'
    $health=Invoke-RestMethod -Uri ($base+'/health/ready') -Headers $headers -TimeoutSec 15
    if($health.status -cne 'ready' -or $health.source_sha -cne $p.source_commit){throw 'CORE_NEXT_UPGRADE_AUTHENTICATED_SOURCE_MISMATCH'}
    $registry=Invoke-RestMethod -Uri ($base+'/modules') -Headers $headers -TimeoutSec 15
    if($registry.schema_version -cne 'core-next.modules/1' -or $registry.installation.installation_id -cne $p.installation_id){throw 'CORE_NEXT_UPGRADE_AUTHENTICATED_INSTALLATION_MISMATCH'}
    $records=@();$offset=0;$expectedTotal=$null
    do{$page=Invoke-RestMethod -Uri ($base+'/matches?limit=200&offset='+$offset) -Headers $headers -TimeoutSec 15;if($null -eq $expectedTotal){$expectedTotal=[int]$page.total};if($page.total -ne $expectedTotal){throw 'CORE_NEXT_UPGRADE_CONCURRENT_RETAINED_DATA_CHANGE'};$batch=@($page.items);if(-not$batch.Count -and $offset -lt $page.total){throw 'CORE_NEXT_UPGRADE_MATCH_PAGE_INCOMPLETE'};$records+=@($batch|ForEach-Object{[pscustomobject][ordered]@{id=$_.id;version=$_.version}});$offset+=$batch.Count;if($offset -gt 20000){throw 'CORE_NEXT_UPGRADE_MATCH_SNAPSHOT_BOUND_EXCEEDED'}}while($offset -lt $page.total)
    if($records.Count -ne $expectedTotal -or @($records.id|Sort-Object -Unique).Count -ne $expectedTotal){throw 'CORE_NEXT_UPGRADE_CONCURRENT_RETAINED_DATA_CHANGE'}
    [ordered]@{records=@($records|Sort-Object id);count=$records.Count}
}
function Vault-Fingerprints($p){$root=Join-Path $p.state_root 'kernel\vault';if(Test-Path -LiteralPath $root){Get-ChildItem -LiteralPath $root -Recurse -File|Sort-Object FullName|ForEach-Object{[pscustomobject][ordered]@{path=[IO.Path]::GetRelativePath($root,$_.FullName);sha256=(Hash $_.FullName)}}}}
$profile=Read-CoreNextProfile $ProfilePath -CheckService
$configPath=Join-Path $profile.state_root 'workstation.json';$config=Json $configPath
$transition=New-CoreNextUpgradeMetadata -Profile $profile -Config $config -ExpectedInstallationId $ExpectedInstallationId -FromSource $FromSourceCommit -FromVersion $FromVersion -ToSource $NewSourceCommit -ToVersion $ToVersion -BuildId ('upgrade-'+$NewSourceCommit.Substring(0,12))
$null=Assert-CoreNextOrdinaryPath $Installer $lab
$null=Assert-CoreNextOrdinaryPath (Join-Path (Split-Path $Installer -Parent) 'WORKSTATION-BUILD.json') $lab
$build=Json (Join-Path (Split-Path $Installer -Parent) 'WORKSTATION-BUILD.json')
if($build.product -cne 'DRAGONHYDRA CORE NEXT' -or $build.status -cne 'BUILT' -or $build.installed -ne $false -or $build.source_sha -cne $NewSourceCommit -or $build.version -cne $ToVersion -or $build.sha256 -cne $ExpectedInstallerSha256 -or (Hash $Installer) -cne $ExpectedInstallerSha256 -or (Get-Item -LiteralPath $Installer).Length -ne $build.bytes -or [IO.Path]::GetFullPath($build.artifact) -ine [IO.Path]::GetFullPath($Installer)){throw 'CORE_NEXT_UPGRADE_NEW_PACKAGE_PROVENANCE_MISMATCH'}
$installed=Json (Join-Path $profile.install_root 'WORKSTATION-BUILD.json')
$serverInfo=Json (Join-Path $profile.install_root 'server\BUILD-INFO.json')
if($installed.product -cne $profile.product -or $installed.version -cne $FromVersion -or $installed.source_sha -cne $FromSourceCommit -or $serverInfo.version -cne $FromVersion -or $serverInfo.source_sha -cne $FromSourceCommit -or (Hash (Join-Path $profile.install_root 'server\DRAGONHYDRA-Server.exe')) -cne '31d85b96121aa8685d58fb8808a972b89a0aeaac93c0fcb4e4a67ef476dd9f38'){throw 'CORE_NEXT_UPGRADE_OLD_INSTALLED_SOURCE_MISMATCH'}
$oldValidator=Join-Path $profile.install_root 'workstation\Installer-Checks.ps1'
& (Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe') -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $oldValidator -Action Validate -ProfilePath $ProfilePath -InstallRoot $profile.install_root -StateRoot $profile.state_root -ServiceName $profile.service_name -ReleaseVersion $FromVersion -ReleaseSourceCommit $FromSourceCommit *> $null
if($LASTEXITCODE){throw 'CORE_NEXT_UPGRADE_OLD_OWNERSHIP_VALIDATION_FAILED'}
$protectedNames=@('DragonhydraWorkstationTest','DragonhydraWorkstation','DragonhydraProvidersA2Test','DragonhydraGenesisA8Test')
$protected=@(foreach($name in $protectedNames){$s=Get-CimInstance Win32_Service -Filter ("Name='"+$name+"'");if(-not$s){throw 'CORE_NEXT_PROTECTED_SERVICE_MISSING'};[ordered]@{name=$s.Name;state=$s.State;pid=[int]$s.ProcessId;binding=$s.PathName}})
$service=Get-CimInstance Win32_Service -Filter ("Name='"+$profile.service_name+"'")
if(-not$service -or $service.State -cne 'Running'){throw 'CORE_NEXT_UPGRADE_RUNNING_OWNED_SERVICE_REQUIRED'}
Assert-OwnedListeners $profile $service.ProcessId
$elevated=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$plan=[ordered]@{schema_version=1;mode=$(if($Apply){'apply'}else{'preview'});installation_id=$profile.installation_id;service_name=$profile.service_name;service_pid=$service.ProcessId;ports=$profile.ports;from_source=$FromSourceCommit;from_version=$FromVersion;to_source=$NewSourceCommit;to_version=$ToVersion;installer_sha256=$ExpectedInstallerSha256;expected_new_server_sha256=$ExpectedNewServerSha256;expected_new_client_sha256=$ExpectedNewClientSha256;elevated=$elevated;protected_backup_required_before_stop=$true;metadata_fields_only=@('source_commit','version','build_id','product_version');protected_original_services=@($protected|ForEach-Object{@{name=$_.name;state=$_.state;pid=$_.pid}});installed=$false;phase='preflight_passed'}
if(-not$Apply){$plan|ConvertTo-Json -Depth 8;return}
if(-not$elevated){throw 'CORE_NEXT_UPGRADE_OWNER_WINDOWS_ELEVATION_REQUIRED'}
if(-not$BackupRoot){throw 'CORE_NEXT_UPGRADE_FRESH_PRIVATE_BACKUP_REQUIRED'}
$BackupRoot=Assert-CoreNextOrdinaryPath $BackupRoot $lab
$profileRoot=Split-Path $profile.install_root -Parent
if((Test-Path -LiteralPath $BackupRoot) -or $BackupRoot.StartsWith($profileRoot+'\',[StringComparison]::OrdinalIgnoreCase) -or $profileRoot.StartsWith($BackupRoot+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'CORE_NEXT_UPGRADE_FRESH_EXTERNAL_BACKUP_REQUIRED'}
New-Item -ItemType Directory -Path $BackupRoot|Out-Null
$owner=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& (Join-Path $env:WINDIR 'System32\icacls.exe') $BackupRoot /inheritance:r /grant:r ('*'+$owner+':(OI)(CI)F') ('*'+$config.owner_sid+':(OI)(CI)F') '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' *> $null
if($LASTEXITCODE -or -not(Get-Acl -LiteralPath $BackupRoot).AreAccessRulesProtected){throw 'CORE_NEXT_UPGRADE_PRIVATE_BACKUP_ACL_FAILED'}
$receiptPath=Join-Path $BackupRoot 'upgrade-receipt.json';$setupStarted=$false
function Phase([string]$name){$plan.phase=$name;$plan['observed_at']=[DateTime]::UtcNow.ToString('o');Save $plan $receiptPath}
function Check-ProtectedServices {foreach($row in $protected){$s=Get-CimInstance Win32_Service -Filter ("Name='"+$row.name+"'");if($s.State -cne $row.state -or $s.ProcessId -ne $row.pid -or $s.PathName -cne $row.binding){throw 'CORE_NEXT_PROTECTED_SERVICE_CHANGED_RECONCILE'}}}
try{
    Phase 'backing_up_before_service_stop'
    $dataBefore=Read-DataSnapshot $profile
    Save $dataBefore (Join-Path $BackupRoot 'match-identifiers-before.json')
    $vaultBefore=Vault-Fingerprints $profile
    Save $vaultBefore (Join-Path $BackupRoot 'private-vault-fingerprints-before.json')
    $privateStateHashes=@{}
    $backupModeReceipts=@()
    foreach($item in Get-ChildItem -LiteralPath $profile.install_root -Recurse -Force){if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'CORE_NEXT_UPGRADE_LINKED_RUNTIME_REJECTED'}}
    Copy-Item -LiteralPath $profile.install_root -Destination (Join-Path $BackupRoot 'application-before') -Recurse
    $runtimeInventory=@(Get-ChildItem -LiteralPath $profile.install_root -Recurse -File|ForEach-Object{$relative=[IO.Path]::GetRelativePath($profile.install_root,$_.FullName);$copy=Join-Path (Join-Path $BackupRoot 'application-before') $relative;if((Hash $copy) -cne (Hash $_.FullName)){throw 'CORE_NEXT_UPGRADE_RUNTIME_BACKUP_MISMATCH'};@{path=$relative;bytes=$_.Length;sha256=(Hash $copy)}})
    Copy-Item -LiteralPath $ProfilePath -Destination (Join-Path $BackupRoot 'original-profile.json')
    foreach($relative in @('workstation.json','first-run.json','launcher.json','site\configuration.php','web-config\httpd.conf','web-config\php.ini','web-config\my.ini','kernel\local-session.json','kernel\joomla-bridge.json','kernel\local-ai.json','kernel\product.json','client\local-session.json')){
        $path=Join-Path $profile.state_root $relative
        if(Test-Path -LiteralPath $path){
            $null=Assert-CoreNextOrdinaryPath $path $lab;$target=Join-Path (Join-Path $BackupRoot 'state-files') $relative;New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent)|Out-Null
            try{Copy-Item -LiteralPath $path -Destination $target;if((Hash $path) -cne (Hash $target)){throw 'CORE_NEXT_UPGRADE_PRIVATE_FILE_BACKUP_MISMATCH'}}
            catch{if($relative -cnotin @('kernel\local-session.json','kernel\joomla-bridge.json','kernel\local-ai.json') -or ($_.CategoryInfo.Category -ne 'PermissionDenied' -and $_.Exception -isnot [UnauthorizedAccessException])){throw};$backupModeReceipts+=Copy-CoreNextProtectedBackup -StateRoot $profile.state_root -BackupRoot $BackupRoot -RelativePath $relative -OwnerSid $config.owner_sid}
            $privateStateHashes[$relative]=Hash $target
        }
    }
    foreach($relative in @('kernel\raw','kernel\exports','kernel\vault')){ $path=Join-Path $profile.state_root $relative;if(Test-Path -LiteralPath $path){$null=Assert-CoreNextOrdinaryPath $path $lab;foreach($entry in Get-ChildItem -LiteralPath $path -Recurse -Force){if($entry.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'CORE_NEXT_UPGRADE_LINKED_STATE_BACKUP_REJECTED'}};$target=Join-Path (Join-Path $BackupRoot 'state-trees') $relative;New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent)|Out-Null;Copy-Item -LiteralPath $path -Destination $target -Recurse}}
    Save @{files=$runtimeInventory} (Join-Path $BackupRoot 'runtime-backup-manifest.json')
    $python=Join-Path $lab 'tools-env\Scripts\python.exe'
    $null=Assert-CoreNextOrdinaryPath (Join-Path $profile.state_root 'kernel\core.sqlite3') $lab
    $sqliteCode='import sqlite3,sys,json;from pathlib import Path;source=sqlite3.connect(Path(sys.argv[1]).resolve().as_uri()+"?mode=ro",uri=True);copy=sqlite3.connect(sys.argv[2]);source.backup(copy);assert copy.execute("PRAGMA integrity_check").fetchone()[0]=="ok";copy.close();source.close();print("SQLITE_BACKUP_OK")'
    & $python -I -c $sqliteCode (Join-Path $profile.state_root 'kernel\core.sqlite3') (Join-Path $BackupRoot 'core.sqlite3') *> (Join-Path $BackupRoot 'sqlite-backup.log')
    if($LASTEXITCODE){throw 'CORE_NEXT_UPGRADE_SQLITE_ONLINE_BACKUP_FAILED'}
    $providerCode='import sqlite3,sys,json;from pathlib import Path;db=sqlite3.connect(Path(sys.argv[1]).resolve().as_uri()+"?mode=ro",uri=True);columns=[r[1] for r in db.execute("PRAGMA table_info(connector_settings)")];assert columns;rows=db.execute("SELECT * FROM connector_settings ORDER BY provider").fetchall();Path(sys.argv[2]).write_text(json.dumps({"columns":columns,"rows":rows},sort_keys=True,separators=(",",":")),encoding="utf-8");db.close()'
    & $python -I -c $providerCode (Join-Path $BackupRoot 'core.sqlite3') (Join-Path $BackupRoot 'private-provider-settings-before.json') *> (Join-Path $BackupRoot 'provider-backup.log')
    if($LASTEXITCODE){throw 'CORE_NEXT_UPGRADE_PROVIDER_SETTINGS_BACKUP_FAILED'}
    $defaults=Join-Path $BackupRoot 'dump-client.cnf'
    $password=$config.root_password.Replace('\','\\').Replace('"','\"').Replace("`r",'\r').Replace("`n",'\n')
    [IO.File]::WriteAllText($defaults,("[client]`nhost=127.0.0.1`nport="+$profile.ports.database+"`nuser=root`npassword=`""+$password+"`"`n"),[Text.UTF8Encoding]::new($false))
    try{
        $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=Join-Path $profile.install_root 'web\mariadb\bin\mysqldump.exe';$start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
        foreach($arg in @(('--defaults-extra-file='+$defaults),'--lock-all-tables','--hex-blob','--routines','--triggers','--events','--databases',$config.db_name,$config.core_db_name)){$start.ArgumentList.Add($arg)}
        $dump=[Diagnostics.Process]::new();$dump.StartInfo=$start;$null=$dump.Start();$errorTask=$dump.StandardError.ReadToEndAsync();$sql=Join-Path $BackupRoot 'joomla-and-reserved-core.sql';$stream=[IO.File]::Open($sql,[IO.FileMode]::CreateNew);try{$copyTask=$dump.StandardOutput.BaseStream.CopyToAsync($stream);if(-not$dump.WaitForExit(90000)){$dump.Kill();throw 'CORE_NEXT_UPGRADE_DATABASE_DUMP_TIMEOUT'};$copyTask.GetAwaiter().GetResult()}finally{$stream.Dispose()}
        [IO.File]::WriteAllText((Join-Path $BackupRoot 'database-dump.stderr'),$errorTask.GetAwaiter().GetResult());if($dump.ExitCode -ne 0 -or (Get-Item -LiteralPath $sql).Length -lt 1000){throw 'CORE_NEXT_UPGRADE_DATABASE_DUMP_FAILED'}
    }finally{if(Test-Path -LiteralPath $defaults){Remove-Item -LiteralPath $defaults -Force}}
    Save @{runtime_manifest_sha256=(Hash (Join-Path $BackupRoot 'runtime-backup-manifest.json'));sqlite_sha256=(Hash (Join-Path $BackupRoot 'core.sqlite3'));sql_sha256=(Hash $sql);profile_sha256=(Hash (Join-Path $BackupRoot 'original-profile.json'));configuration_sha256=(Hash (Join-Path $BackupRoot 'state-files\workstation.json'))} (Join-Path $BackupRoot 'private-backup-integrity.json')
    Save $privateStateHashes (Join-Path $BackupRoot 'private-state-file-fingerprints.json')
    Save $backupModeReceipts (Join-Path $BackupRoot 'private-backup-mode-receipts.json')
    if(($dataBefore|ConvertTo-Json -Depth 10 -Compress) -cne ((Read-DataSnapshot $profile)|ConvertTo-Json -Depth 10 -Compress)){throw 'CORE_NEXT_UPGRADE_CONCURRENT_RETAINED_DATA_CHANGE'}
    Phase 'backup_complete_before_service_stop';Check-ProtectedServices
    Assert-CoreNextUpgradeSnapshot -ProfilePath $ProfilePath -ConfigPath $configPath -Transition $transition
    $oldController=Join-Path $profile.install_root 'workstation\Workstation.ps1'
    & (Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe') -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $oldController -Action Stop -ProfilePath $ProfilePath *> (Join-Path $BackupRoot 'owned-stop.log')
    if($LASTEXITCODE -or (Get-Service -Name $profile.service_name).Status -ne 'Stopped'){throw 'CORE_NEXT_UPGRADE_OWNED_STOP_FAILED'}
    Phase 'owned_service_stopped'
    $null=Set-CoreNextUpgradeMetadata -ProfilePath $ProfilePath -ConfigPath $configPath -Transition $transition -BackupRoot $BackupRoot
    Phase 'metadata_transition_committed'
    $setup=Start-Process -FilePath $Installer -ArgumentList @('/S',('/PROFILE="'+$ProfilePath+'"')) -PassThru -WindowStyle Hidden
    $setupStarted=$true;$plan['installer_pid']=$setup.Id;Phase 'installer_running_no_retry'
    if(-not$setup.WaitForExit(900000)){throw 'CORE_NEXT_UPGRADE_INSTALLER_RUNNING_RECONCILE_NO_RETRY'}
    $setup.Refresh();$plan['installer_exit_code']=$setup.ExitCode
    if($setup.ExitCode -ne 0){throw 'CORE_NEXT_UPGRADE_INSTALLER_FAILED_RECONCILE_NO_RETRY'}
    if((Hash (Join-Path $profile.install_root 'server\DRAGONHYDRA-Server.exe')) -cne $ExpectedNewServerSha256 -or (Hash (Join-Path $profile.install_root 'client\DRAGONHYDRA-Client.exe')) -cne $ExpectedNewClientSha256){throw 'CORE_NEXT_UPGRADE_INSTALLED_BYTES_MISMATCH'}
    $current=Read-CoreNextProfile $ProfilePath -CheckService;Assert-CoreNextConfig (Json $configPath) $current
    Assert-CoreNextReleaseBinding $current $ToVersion $NewSourceCommit
    $newService=Get-CimInstance Win32_Service -Filter ("Name='"+$profile.service_name+"'")
    if($newService.State -cne 'Running'){throw 'CORE_NEXT_UPGRADE_NEW_OWNED_SERVICE_NOT_RUNNING'}
    Assert-OwnedListeners $current $newService.ProcessId
    $dataAfter=Read-DataSnapshot $current
    if(($dataBefore|ConvertTo-Json -Depth 10 -Compress) -cne ($dataAfter|ConvertTo-Json -Depth 10 -Compress)){throw 'CORE_NEXT_UPGRADE_RETAINED_MATCH_IDENTITIES_CHANGED'}
    $newConfig=Json $configPath
    & $python -I -c $providerCode (Join-Path $profile.state_root 'kernel\core.sqlite3') (Join-Path $BackupRoot 'private-provider-settings-after.json') *> (Join-Path $BackupRoot 'provider-after.log')
    if($LASTEXITCODE -or (Hash (Join-Path $BackupRoot 'private-provider-settings-before.json')) -cne (Hash (Join-Path $BackupRoot 'private-provider-settings-after.json'))){throw 'CORE_NEXT_UPGRADE_PROVIDER_CONFIGURATION_CHANGED'}
    if(($vaultBefore|ConvertTo-Json -Depth 10 -Compress) -cne ((Vault-Fingerprints $current)|ConvertTo-Json -Depth 10 -Compress)){throw 'CORE_NEXT_UPGRADE_PROTECTED_VAULT_CHANGED'}
    foreach($property in $config.PSObject.Properties){if($property.Name -notin @('source_commit','version','build_id','product_version')){if($property.Name -notin $newConfig.PSObject.Properties.Name -or ($property.Value|ConvertTo-Json -Depth 30 -Compress) -cne ($newConfig.($property.Name)|ConvertTo-Json -Depth 30 -Compress)){throw 'CORE_NEXT_UPGRADE_RETAINED_CONFIGURATION_CHANGED'}}}
    foreach($relative in @('kernel\local-session.json','kernel\joomla-bridge.json','kernel\local-ai.json','client\local-session.json','site\configuration.php')){
        if(-not$privateStateHashes.ContainsKey($relative)){continue}
        $currentHash=$null
        try{$currentHash=Hash (Join-Path $profile.state_root $relative)}catch{
            if($relative -cnotin @('kernel\local-session.json','kernel\joomla-bridge.json','kernel\local-ai.json') -or ($_.CategoryInfo.Category -ne 'PermissionDenied' -and $_.Exception -isnot [UnauthorizedAccessException])){throw}
            $verifyRoot=Join-Path $BackupRoot 'post-upgrade-protected-verification'
            if(-not(Test-Path -LiteralPath $verifyRoot)){New-Item -ItemType Directory -Path $verifyRoot|Out-Null;Set-Acl -LiteralPath $verifyRoot -AclObject (Get-Acl -LiteralPath $BackupRoot)}
            $proof=Copy-CoreNextProtectedBackup -StateRoot $profile.state_root -BackupRoot $verifyRoot -RelativePath $relative -OwnerSid $config.owner_sid
            $currentHash=$proof.backup_sha256
        }
        if($currentHash -cne $privateStateHashes[$relative]){throw 'CORE_NEXT_UPGRADE_PRIVATE_CONFIGURATION_CHANGED'}
    }
    $plan['retained_records_preserved']=$dataAfter.count;$plan['pairing_configuration_preserved']=$true;$plan['new_service_pid']=$newService.ProcessId
    Check-ProtectedServices
    $plan.installed=$true;Phase 'installed_bytes_verified_acceptance_pending'
    $plan|ConvertTo-Json -Depth 8
}catch{
    $plan['error_code']=$(if($_.Exception.Message -cmatch '^CORE_NEXT_[A-Z0-9_]+$'){$_.Exception.Message}else{'CORE_NEXT_UPGRADE_OPERATION_FAILED_PRIVATE_EVIDENCE_REQUIRED'})
    $plan['installer_started']=$setupStarted;$plan['automatic_retry_performed']=$false
    $plan['rollback']='Do not rerun Setup blindly. Reconcile the recorded installer PID/status first. With only this owning service stopped, restore matched application-before and original-profile/config backups; database restore is a separate reviewed step if migration writes occurred. Never restore another profile or overwrite concurrent imports.'
    Phase 'failed_reconciliation_required'
    $plan|Select-Object phase,error_code,installer_started,automatic_retry_performed,rollback|ConvertTo-Json -Depth 4
    throw $plan.error_code
}
