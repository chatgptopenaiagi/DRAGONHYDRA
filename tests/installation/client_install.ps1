#requires -Version 7.0
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$projectRoot=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$installer=Join-Path $projectRoot 'dist\DRAGONHYDRA-Client-0.3.0-windows-x64-setup.exe'
$target=[IO.Path]::GetFullPath((Join-Path $projectRoot ('runtime\scratch\client-install-'+[Guid]::NewGuid().ToString('N'))))
$testRoot=[IO.Path]::GetFullPath((Join-Path $projectRoot 'runtime\scratch'))+[IO.Path]::DirectorySeparatorChar
if(-not $target.StartsWith($testRoot,[StringComparison]::OrdinalIgnoreCase)){throw 'Install test target escaped the product scratch directory.'}
$existing=Get-ChildItem -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall' -ErrorAction SilentlyContinue|ForEach-Object{Get-ItemProperty -LiteralPath $_.PSPath -ErrorAction SilentlyContinue}|Where-Object {$_.DisplayName -eq 'DRAGONHYDRA Client'}
if($existing){throw 'A DRAGONHYDRA client is already registered; isolated install test will not overwrite it.'}
$evidence=Join-Path $projectRoot 'runtime\evidence\installation'
New-Item -ItemType Directory -Path $evidence -Force|Out-Null
$checks=[Collections.Generic.List[object]]::new()
$result=@{installer=$installer;sha256=(Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash;target=$target;scope='Client-only NSIS install, native UI, uninstall on current development Windows 11 x64; not a clean machine or full workstation installation';checks=$checks;passed=$false;clean_machine=$false;complete_workstation=$false}
$installed=$false
try{
    $setup=Start-Process -FilePath $installer -ArgumentList @('/S',('/D='+$target)) -PassThru -WindowStyle Hidden
    if(-not $setup.WaitForExit(45000)){throw 'Client installer exceeded its startup deadline.'}
    if($setup.ExitCode -ne 0){throw "Client installer failed: $($setup.ExitCode)"}
    $binary=Join-Path $target 'dragonhydra-desktop.exe'
    if(-not (Test-Path -LiteralPath $binary)){throw 'Installer did not create the client executable.'}
    $installed=$true
    $checks.Add(@{name='nsis-client-install';passed=$true;exit_code=$setup.ExitCode})
    if(-not(Test-Path -LiteralPath (Join-Path $target 'THIRD-PARTY-NOTICES.txt'))){throw 'Client payload is missing upstream notices.'}
    $checks.Add(@{name='upstream-notices-retained';passed=$true})
    & (Join-Path $projectRoot 'tests\installation\native_uia.ps1') -Binary $binary -Output (Join-Path $evidence 'installed-native-uia.json')|Out-Null
    $checks.Add(@{name='installed-native-interactions';passed=$true;evidence='installed-native-uia.json'})
    $uninstall=Join-Path $target 'uninstall.exe'
    if(-not(Test-Path -LiteralPath $uninstall)){throw 'Installer did not supply uninstall.exe.'}
    $remove=Start-Process -FilePath $uninstall -ArgumentList @('/S',('_?='+$target)) -PassThru -WindowStyle Hidden
    if(-not $remove.WaitForExit(30000)){throw 'Client uninstaller exceeded its deadline.'}
    if($remove.ExitCode -ne 0 -or (Test-Path -LiteralPath $binary)){throw 'Client uninstall did not remove its executable.'}
    $checks.Add(@{name='client-uninstall';passed=$true;exit_code=$remove.ExitCode})
    if(-not(Test-Path -LiteralPath (Join-Path $projectRoot 'runtime\product\local-session.json'))){throw 'Client uninstall removed the server pairing state.'}
    $checks.Add(@{name='server-state-retained';passed=$true})
    $result.passed=$true
}catch{$result.error=$_.Exception.Message;throw}
finally{
    $result|ConvertTo-Json -Depth 7|Set-Content -LiteralPath (Join-Path $evidence 'client-install.json') -Encoding utf8
    $result|ConvertTo-Json -Depth 7
}
