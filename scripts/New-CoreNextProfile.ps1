#requires -Version 7.0
[CmdletBinding()]
param([Parameter(Mandatory)][ValidateSet('baseline','candidate')][string]$Environment,
      [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{40}$')][string]$SourceCommit,
      [string]$Version='0.5.0-dev.1',[string]$BuildId=('core-next-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')))
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '..\packaging\windows\workstation\CoreNextProfile.ps1')
$created=New-CoreNextInstallationProfile -Environment $Environment -SourceCommit $SourceCommit -Version $Version -BuildId $BuildId
$profile=$created.profile
[pscustomobject]@{profile_path=$created.profile_path;installation_id=$profile.installation_id;environment_id=$Environment;install_root=$profile.install_root;state_root=$profile.state_root;service_name=$profile.service_name;ports=$profile.ports}|ConvertTo-Json -Depth 5
