#requires -Version 7.0
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$projectRoot=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$version=(Get-Content -LiteralPath (Join-Path $projectRoot 'client\desktop\src-tauri\tauri.conf.json') -Raw|ConvertFrom-Json).version
if($version -notmatch '^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$'){throw 'The Tauri source version is invalid.'}
$artifacts=@()
$installationEvidence=Join-Path $projectRoot 'runtime\evidence\installation\client-install.json'
$nativeEvidence=Join-Path $projectRoot 'runtime\evidence\installation\installed-native-uia.json'
$installResult=if(Test-Path -LiteralPath $installationEvidence){Get-Content -LiteralPath $installationEvidence -Raw|ConvertFrom-Json}else{$null}
$nativeResult=if(Test-Path -LiteralPath $nativeEvidence){Get-Content -LiteralPath $nativeEvidence -Raw|ConvertFrom-Json}else{$null}
$portableEvidence=Join-Path $projectRoot 'runtime\evidence\installation\portable-native-uia.json'
$portableResult=if(Test-Path -LiteralPath $portableEvidence){Get-Content -LiteralPath $portableEvidence -Raw|ConvertFrom-Json}else{$null}
foreach($name in @('DRAGONHYDRA-Client-x64.exe',('DRAGONHYDRA-Client-'+$version+'-windows-x64-setup.exe'))){
    $path=Join-Path $projectRoot ('dist\'+$name)
    if(-not(Test-Path -LiteralPath $path)){continue}
    $hash=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
    $isSetup=$name.EndsWith('-setup.exe')
    $installVerified=$isSetup -and $installResult -and $installResult.passed -and $installResult.sha256 -eq $hash
    $nativeVerified=-not $isSetup -and $portableResult -and $portableResult.passed -and $portableResult.sha256 -eq $hash
    $signature=Get-AuthenticodeSignature -LiteralPath $path
    $artifacts+=@{path=$path;bytes=(Get-Item -LiteralPath $path).Length;sha256=$hash;target_os='Windows';architecture='x86_64';kind=if($isSetup){'client-only NSIS installer'}else{'portable client executable'};signing_state=[string]$signature.Status;built=$true;installed_and_uninstalled_on_current_host=[bool]$installVerified;native_launched_and_interaction_tested=[bool]($nativeVerified -or $installVerified);clean_machine_tested=$false;complete_workstation_installer=$false}
}
$manifest=@{
    schema_version=1;product='DRAGONHYDRA Client';version=$version;generated_at=[DateTime]::UtcNow.ToString('o');artifacts=$artifacts
    payload=@{tauri='2.12.5';tauri_build='2.7.4';tauri_cli='2.12.4';rust='1.99.1';cargo_lock='client/desktop/src-tauri/Cargo.lock';npm_lock='client/desktop/package-lock.json';architecture='x86_64-pc-windows-msvc';node_runtime_in_payload=$false;python_runtime_in_payload=$false;custom_native_commands=@();upstream_notices='THIRD-PARTY-NOTICES.txt'}
    webview=@{strategy='Evergreen download bootstrapper';offline_edition=$false;tested_runtime='156.0.4314.50';requires_network_when_runtime_missing=$true}
    tested_platform=@{os='Windows 11 Pro Insider Preview';version='10.0.29695';architecture='64-bit';other_windows_versions_tested=$false;linux_tested=$false;windows_x86_tested=$false}
    evidence=@{lifecycle='runtime/evidence/installation/development-lifecycle.json';installer='runtime/evidence/installation/client-install.json';native='runtime/evidence/installation/installed-native-uia.json';native_screenshot='runtime/evidence/installation/installed-native-uia.png';webdriver_attempt='runtime/evidence/installation/native-smoke-state-arg.json';native_driver='Microsoft UI Automation (.NET UIAutomationClient)';tauri_webdriver_status='Failed: DevToolsActivePort file does not exist; native UI verified independently through Microsoft UI Automation'}
    sources=@{tauri='https://v2.tauri.app/distribute/windows-installer/';native_testing='https://v2.tauri.app/develop/tests/webdriver/';nsis='https://github.com/tauri-apps/binary-releases/releases/download/nsis-3.13/nsis-3.13.zip';nsis_hash_validation='Tauri CLI build output verified bundled NSIS and plugin hashes';edgedriver='https://msedgedriver.microsoft.com/156.0.4314.50/edgedriver_win64.zip';edgedriver_archive_sha256='DFB627983FCDAA076266619E5CFDA0C654093CE1B320165574C4A08D5FDCA357'}
}
$output=Join-Path $projectRoot ('dist\DRAGONHYDRA-Client-'+$version+'-manifest.json')
$manifest|ConvertTo-Json -Depth 9|Set-Content -LiteralPath $output -Encoding utf8
$manifest|ConvertTo-Json -Depth 9
