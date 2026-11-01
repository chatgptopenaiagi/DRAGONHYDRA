#requires -Version 5.1
param([ValidateSet('SelectProfile','Validate','ValidateUninstall','RemoveShortcuts')][string]$Action='Validate',[string]$ProfilePath,[string]$InstallRoot,[string]$StateRoot,[string]$ServiceName,[string]$ReleaseVersion,[string]$ReleaseSourceCommit,[string]$OutputBindings)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -eq 5){$env:PSModulePath=Join-Path $PSHOME 'Modules'}
. (Join-Path $PSScriptRoot 'CoreNextProfile.ps1')
if($Action -eq 'SelectProfile'){
    if(-not $ProfilePath){$created=New-CoreNextInstallationProfile -SourceCommit $ReleaseSourceCommit -Version $ReleaseVersion;$ProfilePath=$created.profile_path}
}
$profile=Read-CoreNextProfile $ProfilePath -CheckService
Assert-CoreNextReleaseBinding $profile $ReleaseVersion $ReleaseSourceCommit
if($Action -eq 'SelectProfile'){
    if(-not $ReleaseVersion -or -not $ReleaseSourceCommit){throw 'CORE_NEXT_RELEASE_IDENTITY_REQUIRED'}
    $bindings=[IO.Path]::GetFullPath($OutputBindings)
    if([IO.Path]::GetFileName($bindings) -cne 'core-next-selected.ini'){throw 'CORE_NEXT_SELECTION_BINDINGS_NAME_REQUIRED'}
    $lab='C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB';$temp=[IO.Path]::GetTempPath().TrimEnd('\')
    if($bindings.StartsWith($lab+'\',[StringComparison]::OrdinalIgnoreCase)){$null=Assert-CoreNextOrdinaryPath $bindings $lab}
    elseif($bindings.StartsWith($temp+'\',[StringComparison]::OrdinalIgnoreCase)){$null=Assert-CoreNextOrdinaryPath $bindings $temp}
    else{throw 'CORE_NEXT_SELECTION_BINDINGS_LOCATION_REQUIRED'}
    if(Test-Path -LiteralPath $bindings){throw 'CORE_NEXT_FRESH_SELECTION_BINDINGS_REQUIRED'}
    $text="[Profile]`r`nIdentity=DRAGONHYDRA CORE NEXT selection v1`r`nProfilePath=$ProfilePath`r`nInstallRoot=$($profile.install_root)`r`nStateRoot=$($profile.state_root)`r`nServiceName=$($profile.service_name)`r`nShortcutName=$($profile.shortcut_name)`r`nUninstallId=$($profile.uninstall_id)`r`nInstallationId=$($profile.installation_id)`r`n"
    [IO.File]::WriteAllText($bindings,$text,[Text.Encoding]::Unicode)
    Write-Output 'CORE NEXT profile selected; no binaries or services were installed.'
    return
}
if($InstallRoot -ine $profile.install_root -or $StateRoot -ine $profile.state_root -or $ServiceName -cne $profile.service_name){throw 'CORE_NEXT_INSTALLER_ARGUMENT_BINDING_MISMATCH'}
$marker=Join-Path $InstallRoot 'workstation\installer.ini';$owned=$false
if(Test-Path -LiteralPath $marker){
    $ini=@{};foreach($line in Get-Content -LiteralPath $marker){if($line -match '^([^=]+)=(.*)$'){$ini[$matches[1]]=$matches[2]}}
    Assert-CoreNextInstallerMarker $ini $profile $ProfilePath
    $owned=$true
}
if((Test-Path -LiteralPath $InstallRoot) -and @(Get-ChildItem -LiteralPath $InstallRoot -Force).Count -and -not $owned){throw 'CORE_NEXT_UNOWNED_NONEMPTY_BINARY_DIRECTORY'}
if($Action -ne 'Validate' -and -not $owned){throw 'CORE_NEXT_OWNED_UNINSTALL_MARKER_REQUIRED'}
$config=Join-Path $StateRoot 'workstation.json'
if(Test-Path -LiteralPath $config){Assert-CoreNextConfig (Get-Content -LiteralPath $config -Raw|ConvertFrom-Json) $profile}
elseif((Test-Path -LiteralPath $StateRoot) -and @(Get-ChildItem -LiteralPath $StateRoot -Force).Count){throw 'CORE_NEXT_UNOWNED_NONEMPTY_STATE_DIRECTORY'}
$runtimeMarker=Join-Path $InstallRoot 'workstation-installed.json'
if(Test-Path -LiteralPath $runtimeMarker){$value=Get-Content -LiteralPath $runtimeMarker -Raw|ConvertFrom-Json;if($value.product -cne $profile.product -or $value.installation_id -cne $profile.installation_id -or $value.install_root -ine $InstallRoot -or $value.state_root -ine $StateRoot -or $value.service_name -cne $ServiceName){throw 'CORE_NEXT_RUNTIME_MARKER_NOT_OWNED'}}
elseif($Action -ne 'Validate'){throw 'CORE_NEXT_RUNTIME_MARKER_REQUIRED'}
$folder=Join-Path ([Environment]::GetFolderPath('CommonPrograms')) $profile.shortcut_name
$links=@((Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) ($profile.shortcut_name+'.lnk')),(Join-Path $folder 'DRAGONHYDRA CORE NEXT.lnk'),(Join-Path $folder 'DRAGONHYDRA CORE NEXT Administration.lnk'))
$shell=New-Object -ComObject WScript.Shell;$target=Join-Path $InstallRoot 'workstation\DragonhydraLauncher.exe'
foreach($link in $links){if(Test-Path -LiteralPath $link){$existing=$shell.CreateShortcut($link);if($existing.TargetPath -ine $target -or -not $existing.Arguments.Contains($StateRoot)){throw 'CORE_NEXT_SHORTCUT_NOT_OWNED'};if($Action -eq 'RemoveShortcuts'){Remove-Item -LiteralPath $link}}}
if($Action -eq 'RemoveShortcuts' -and (Test-Path -LiteralPath $folder) -and -not @(Get-ChildItem -LiteralPath $folder -Force).Count){Remove-Item -LiteralPath $folder}
Write-Output 'CORE NEXT profile, paths, service, database and shell ownership checks passed.'
