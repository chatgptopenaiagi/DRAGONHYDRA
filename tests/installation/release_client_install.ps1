#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Installer,
    [Parameter(Mandatory)][string]$State,
    [Parameter(Mandatory)][string]$Output,
    [Parameter(Mandatory)][string]$WorkRoot
)
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath($WorkRoot)
$target=Join-Path $root ('nsis-test-'+[Guid]::NewGuid().ToString('N'))
$existing=@(foreach($registryRoot in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall','HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall')){Get-ChildItem -LiteralPath $registryRoot -ErrorAction SilentlyContinue|ForEach-Object{Get-ItemProperty -LiteralPath $_.PSPath -ErrorAction SilentlyContinue}|Where-Object {$_.DisplayName -eq 'DRAGONHYDRA Client'}})
if($existing.Count){throw 'An existing client installation is registered; release tests will not replace or uninstall it.'}
$checks=[Collections.Generic.List[object]]::new()
$result=@{installer=$Installer;sha256=(Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant();target=$target;server_state=$State;checks=$checks;passed=$false;clean_machine_tested=$false;scope='Current-host isolated client-only NSIS installation; no working server or existing client uninstalled'}
$installed=$false
try{
    $setup=Start-Process -FilePath $Installer -ArgumentList @('/S',('/D='+$target)) -WindowStyle Hidden -PassThru
    if(-not $setup.WaitForExit(60000)){throw 'Client installer exceeded its deadline.'}
    if($setup.ExitCode -ne 0){throw "Installer failed with exit code $($setup.ExitCode)"}
    $binary=Join-Path $target 'dragonhydra-desktop.exe'
    if(-not(Test-Path -LiteralPath $binary)){throw 'NSIS installed no client executable.'}
    $installed=$true
    $checks.Add(@{name='exact-final-nsis-install';passed=$true;exit_code=$setup.ExitCode})
    foreach($name in 'THIRD-PARTY-NOTICES.txt','BUILD-INFO.json'){
        if(-not(Test-Path -LiteralPath (Join-Path $target $name))){throw "Installed payload lacks $name"}
    }
    $checks.Add(@{name='installed-notices-and-source-metadata';passed=$true})
    & (Join-Path $PSScriptRoot 'release_native_uia.ps1') -Binary $binary -State $State -Output (Join-Path $root 'installed-native.json') -Mode journey|Out-Null
    $native=Get-Content -LiteralPath (Join-Path $root 'installed-native.json') -Raw|ConvertFrom-Json
    if(-not $native.passed -or -not $native.clean_exit){throw 'Installed native interaction test failed.'}
    $checks.Add(@{name='installed-native-imported-match-context-analysis-export';passed=$true;evidence='installed-native.json'})
    $uninstall=Join-Path $target 'uninstall.exe'
    if(-not(Test-Path -LiteralPath $uninstall)){throw 'NSIS uninstaller absent.'}
    $remove=Start-Process -FilePath $uninstall -ArgumentList @('/S',('_?='+$target)) -WindowStyle Hidden -PassThru
    if(-not $remove.WaitForExit(45000)){throw 'Client uninstaller exceeded its deadline.'}
    if($remove.ExitCode -ne 0 -or (Test-Path -LiteralPath $binary)){throw 'Test client uninstall failed to remove its executable.'}
    $checks.Add(@{name='only-test-owned-client-uninstalled';passed=$true;exit_code=$remove.ExitCode})
    if(-not(Test-Path -LiteralPath (Join-Path $State 'core.sqlite3'))){throw 'Client uninstall altered the isolated server database.'}
    $checks.Add(@{name='isolated-server-database-and-pairing-retained';passed=$true})
    $result.passed=$true
}catch{$result.error=$_.Exception.Message;throw}
finally{
    # A failed test never broadens cleanup to any other installation. Keep its
    # explicit target/evidence for review rather than masking an upgrade issue.
    $result|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $Output -Encoding utf8
    $result|ConvertTo-Json -Depth 8
}
