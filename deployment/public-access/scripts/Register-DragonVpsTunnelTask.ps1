#requires -Version 7.0
[CmdletBinding()]
param(
    [string]$ConfigFile=(Join-Path $PSScriptRoot '..\vps\target.json'),
    [switch]$Install
)
$ErrorActionPreference='Stop'
$script=Join-Path $PSScriptRoot 'Start-DragonVpsTunnel.ps1'
$pwsh=Join-Path $PSHOME 'pwsh.exe'
$taskName='DRAGONHYDRA-VPS-Outbound-Tunnel'
if($ConfigFile -match '[\r\n"]'){throw 'Invalid configuration path'}
$validation=& $pwsh -NoLogo -NoProfile -NonInteractive -File $script -ConfigFile $ConfigFile
if($LASTEXITCODE -ne 0){throw 'VPS configuration validation failed'}
$proof=$validation | ConvertFrom-Json
if($proof.status -ne 'prepared') {
    [ordered]@{status='requires_configuration';task_registered=$false;missing=$proof.missing} | ConvertTo-Json -Depth 5
    if($Install){exit 2}else{exit 0}
}
$arguments='-NoLogo -NoProfile -NonInteractive -File "'+$script+'" -ConfigFile "'+([IO.Path]::GetFullPath($ConfigFile))+'" -Connect'
$action=New-ScheduledTaskAction -Execute $pwsh -Argument $arguments
$trigger=New-ScheduledTaskTrigger -AtStartup
$principal=New-ScheduledTaskPrincipal -UserId 'NT AUTHORITY\LOCAL SERVICE' -LogonType ServiceAccount -RunLevel Limited
$settings=New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
$task=New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'One outbound SSH remote forward to the existing DRAGONHYDRA public read-only gateway. Requires LOCAL SERVICE read permissions on its exact configuration, private key and independently verified known_hosts file.'
if($Install) {
    # No broad ACL grants or remote host changes. The deployment owner must
    # provision exact service-account read access and a headless usable key.
    Register-ScheduledTask -TaskName $taskName -InputObject $task -ErrorAction Stop | Out-Null
}
[ordered]@{status=if($Install){'registered_not_started'}else{'prepared_not_registered'};task_name=$taskName;identity='NT AUTHORITY\LOCAL SERVICE';restart_count=3;start_on_boot=$true;task_registered=[bool]$Install;connection_started=$false;prerequisite='Restricted LOCAL SERVICE read access to configured identity, known_hosts, target and script; no interactive passphrase prompt'} | ConvertTo-Json

