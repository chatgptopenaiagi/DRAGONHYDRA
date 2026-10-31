#requires -Version 7.0
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Installer,[Parameter(Mandatory)][string]$InstallRoot,[Parameter(Mandatory)][string]$StateRoot,[string]$ServiceName='DragonhydraWorkstationTest',[Parameter(Mandatory)][string]$Output)
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$InstallRoot=[IO.Path]::GetFullPath($InstallRoot).TrimEnd('\');$StateRoot=[IO.Path]::GetFullPath($StateRoot).TrimEnd('\');$Output=[IO.Path]::GetFullPath($Output)
foreach($path in @($InstallRoot,$StateRoot)){if(-not $path.StartsWith((Join-Path $project 'build\workstation\test-install')+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Lifecycle testing is restricted to the owned isolated installation.'}}
if(-not $Output.StartsWith((Join-Path $project 'build\workstation\evidence')+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Output must stay in workstation evidence.'}
if($ServiceName -notmatch '^Dragonhydra[A-Za-z0-9_-]{0,60}$'){throw 'Invalid service name.'}
$cfg=Get-Content -LiteralPath (Join-Path $StateRoot 'workstation.json') -Raw|ConvertFrom-Json
$expected='"'+(Join-Path $InstallRoot 'workstation\DragonhydraService.exe')+'" --state "'+$StateRoot+'" --name '+$ServiceName
$service=Get-CimInstance Win32_Service -Filter "Name='$ServiceName'"
if(-not $service -or $service.PathName -cne $expected -or $cfg.install_root -ne $InstallRoot -or $cfg.state_root -ne $StateRoot){throw 'Exact test installation ownership did not match.'}
function Snapshot {
    $token=(Get-Content -LiteralPath (Join-Path $StateRoot 'client\local-session.json') -Raw|ConvertFrom-Json).token
    $page=Invoke-RestMethod -Uri ('http://127.0.0.1:'+$cfg.api_port+'/dragon/api/v1/matches?limit=1') -Headers @{Authorization=('Bearer '+$token)} -TimeoutSec 15
    $hasher=[Security.Cryptography.SHA256]::Create()
    try{$tokenHash=[Convert]::ToHexString($hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($token)))}finally{$hasher.Dispose()}
    return [ordered]@{count=$page.total;match_id=$page.items[0].id;evidence_version=$page.items[0].version;pairing_fingerprint=$tokenHash;joomla_configuration_sha256=(Get-FileHash -LiteralPath (Join-Path $StateRoot 'site\configuration.php') -Algorithm SHA256).Hash;sqlite_exists=(Test-Path -LiteralPath (Join-Path $StateRoot 'kernel\core.sqlite3'));mariadb_exists=(Test-Path -LiteralPath (Join-Path $StateRoot 'mysql-data\mysql'))}
}
$record=[ordered]@{schema_version=1;started_at=[DateTime]::UtcNow.ToString('o');passed=$false;installer_sha256=(Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash;install_root=$InstallRoot;state_root=$StateRoot;service_name=$ServiceName;scope='Uninstall only this owned test product, retain every data file, reinstall the same final EXE and compare committed records'}
try{
    $before=Snapshot;$record.before=$before
    $uninstaller=Join-Path $InstallRoot 'Uninstall-Workstation.exe'
    if(-not(Test-Path -LiteralPath $uninstaller)){throw 'The installed uninstaller is missing.'}
    $uninstall=Start-Process -FilePath $uninstaller -ArgumentList '/S' -PassThru
    $null=$uninstall.Handle
    if(-not $uninstall.WaitForExit(120000)){throw 'Owned uninstaller did not exit before deadline.'}
    $record.uninstaller_exit_code=$uninstall.ExitCode
    if($uninstall.ExitCode -ne 0){throw 'Owned uninstaller returned failure.'}
    $deadline=[DateTime]::UtcNow.AddSeconds(90)
    do{
        $remaining=Get-CimInstance Win32_Service -Filter "Name='$ServiceName'"
        if(-not $remaining -and -not(Test-Path -LiteralPath $InstallRoot)){break}
        Start-Sleep -Milliseconds 500
    }while([DateTime]::UtcNow -lt $deadline)
    if($remaining -or (Test-Path -LiteralPath $InstallRoot)){throw 'Owned binaries or service remain after uninstall; data was not deleted.'}
    foreach($relative in @('kernel\core.sqlite3','mysql-data\mysql','site\configuration.php','workstation.json','client\local-session.json')){if(-not(Test-Path -LiteralPath (Join-Path $StateRoot $relative))){throw "Uninstall removed retained data: $relative"}}
    $record.uninstall_retained_all_required_data=$true
    Write-Output 'Owned uninstall passed: service/binaries removed, SQLite/MariaDB/Joomla/config/pairing retained.'
    $arguments='/S /STATE="'+$StateRoot+'" /SERVICE='+$ServiceName+' /D='+$InstallRoot
    $install=Start-Process -FilePath $Installer -ArgumentList $arguments -PassThru
    $null=$install.Handle
    if(-not $install.WaitForExit(300000)){throw 'Same-byte reinstall timed out; retained data was not removed.'}
    $record.installer_exit_code=$install.ExitCode
    if($install.ExitCode -ne 0){throw 'Same-byte reinstall returned failure.'}
    $status=Get-Content -LiteralPath (Join-Path $StateRoot 'status.json') -Raw|ConvertFrom-Json
    $current=Get-CimInstance Win32_Service -Filter "Name='$ServiceName'"
    if($status.stage -ne 'ready' -or $current.State -ne 'Running' -or $current.PathName -cne $expected){throw 'Reinstalled product did not become ready under the expected service binding.'}
    $after=Snapshot;$record.after=$after
    foreach($key in @('count','match_id','evidence_version','pairing_fingerprint','joomla_configuration_sha256')){if($before[$key] -ne $after[$key]){throw "Retained state changed unexpectedly: $key"}}
    $record.passed=$true
    Write-Output ('Same-byte reinstall passed: installer exit0, service Running, records '+$before.count+' -> '+$after.count+', pairing/evidence/Joomla configuration unchanged.')
}catch{$record.error=$_.Exception.Message;throw}
finally{
    $record.finished_at=[DateTime]::UtcNow.ToString('o')
    $record|ConvertTo-Json -Depth 10|Set-Content -LiteralPath $Output -Encoding utf8
}
