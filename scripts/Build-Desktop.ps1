#requires -Version 7.0
[CmdletBinding()]
param([Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{40}$')][string]$SourceSha,
      [Parameter(Mandatory)][string]$WorkRoot,[Parameter(Mandatory)][string]$OutputRoot,
      [string]$CargoCacheRoot,[string]$CargoCacheManifest,
      [string]$NodeModulesSource='C:\xampp\DRAGONHYDRA\client\desktop\node_modules')
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $project 'packaging\windows\workstation\CoreNextProfile.ps1')
$lab='C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB'
$work=Assert-CoreNextOrdinaryPath $WorkRoot $lab;$output=Assert-CoreNextOrdinaryPath $OutputRoot $lab
if(Test-Path -LiteralPath $output){throw 'CORE_NEXT_FRESH_DESKTOP_OUTPUT_REQUIRED'}
$head=(& 'C:\Program Files\Git\cmd\git.exe' -C $project rev-parse HEAD).Trim()
if($LASTEXITCODE -ne 0 -or $head -cne $SourceSha){throw 'CORE_NEXT_FROZEN_DESKTOP_SOURCE_REQUIRED'}
& 'C:\Program Files\Git\cmd\git.exe' -C $project diff --quiet HEAD --
if($LASTEXITCODE){throw 'CORE_NEXT_CLEAN_DESKTOP_SOURCE_REQUIRED'}
$desktop=Join-Path $project 'client\desktop'
$config=Get-Content -LiteralPath (Join-Path $desktop 'src-tauri\tauri.conf.json') -Raw|ConvertFrom-Json
if($config.identifier -cne 'ai.dragonhydra.corenext.desktop' -or $config.version -cne '0.5.0-dev.1'){throw 'CORE_NEXT_DESKTOP_IDENTITY_REQUIRED'}
$cache=Join-Path $lab 'tools\desktop-node_modules'
if(-not(Test-Path -LiteralPath $cache)){
    if($NodeModulesSource -ine (Join-Path $desktop 'node_modules') -and $NodeModulesSource -ine 'C:\xampp\DRAGONHYDRA\client\desktop\node_modules'){throw 'CORE_NEXT_UNREVIEWED_NODE_MODULE_SOURCE'}
    $metadata=Get-Content -LiteralPath (Join-Path $NodeModulesSource '@tauri-apps\cli\package.json') -Raw|ConvertFrom-Json
    if($metadata.version -cne '2.12.4'){throw 'CORE_NEXT_LOCKED_TAURI_CLI_REQUIRED'}
    New-Item -ItemType Directory -Force -Path (Split-Path $cache -Parent)|Out-Null
    Copy-Item -LiteralPath $NodeModulesSource -Destination $cache -Recurse
}
$cli=Join-Path $cache '@tauri-apps\cli\tauri.js'
if(-not(Test-Path -LiteralPath $cli)){throw 'CORE_NEXT_EXISTING_TAURI_CLI_UNAVAILABLE'}
New-Item -ItemType Directory -Force -Path $work,$output|Out-Null
if($CargoCacheRoot){
    $CargoCacheRoot=Assert-CoreNextOrdinaryPath $CargoCacheRoot $lab
    if(-not $CargoCacheManifest){$CargoCacheManifest=Join-Path (Split-Path $CargoCacheRoot -Parent) 'cargo-dependency-cache.json'}
    $CargoCacheManifest=Assert-CoreNextOrdinaryPath $CargoCacheManifest $lab
    & (Join-Path $lab 'tools-env\Scripts\python.exe') -B (Join-Path $PSScriptRoot 'core_next_cargo_cache.py') copy --root $CargoCacheRoot --manifest $CargoCacheManifest --desktop $desktop --destination (Join-Path $work 'cargo-target')
    if($LASTEXITCODE){throw 'CORE_NEXT_DEPENDENCY_CACHE_REUSE_REJECTED'}
}
$inputs=@('src-tauri/src/main.rs','src-tauri/src/client_state.rs','src-tauri/src/external_target.rs','src-tauri/tauri.conf.json','src-tauri/Cargo.toml','src-tauri/Cargo.lock','web/app.js','web/index.html','web/style.css','web/favicon.svg')
$bindings=@($inputs|ForEach-Object {$p=Join-Path $desktop $_;[ordered]@{path=$_;sha256=(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}})
$sourceText=$bindings|ConvertTo-Json -Depth 4 -Compress
$sourceHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($sourceText))).ToLowerInvariant()
$values=@{CARGO_TARGET_DIR=(Join-Path $work 'cargo-target');CARGO_NET_OFFLINE='true';npm_config_cache=(Join-Path $lab 'cache\npm');NODE_PATH=$cache;DRAGONHYDRA_SOURCE_SHA=$SourceSha;DRAGONHYDRA_SOURCE_CONTENT_SHA256=$sourceHash}
$previous=@{};foreach($key in $values.Keys){$previous[$key]=[Environment]::GetEnvironmentVariable($key,'Process');[Environment]::SetEnvironmentVariable($key,$values[$key],'Process')}
try{
    $vcvars='C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
    foreach($path in @($desktop,$cli,$vcvars)){if($path.IndexOfAny([char[]]'"%!&^|<>') -ge 0){throw 'CORE_NEXT_ORDINARY_BUILD_PATH_REQUIRED'}}
    $runner=Join-Path $work 'build-desktop.cmd'
    @('@echo off',('call "'+$vcvars+'" >nul'),'if errorlevel 1 exit /b %errorlevel%',('cd /d "'+$desktop+'"'),('"C:\Program Files\nodejs\node.exe" "'+$cli+'" build --no-bundle --target x86_64-pc-windows-msvc -- --locked --offline'),'exit /b %errorlevel%')|Set-Content -LiteralPath $runner -Encoding ascii
    & 'C:\Windows\System32\cmd.exe' /d /c $runner 2>&1|Tee-Object -LiteralPath (Join-Path $work 'desktop-build.log')
    if($LASTEXITCODE){throw 'CORE_NEXT_NATIVE_DESKTOP_BUILD_FAILED'}
    $native=Join-Path $env:CARGO_TARGET_DIR 'x86_64-pc-windows-msvc\release\dragonhydra-desktop.exe'
    $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$native;$start.ArgumentList.Add('--build-info');$start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    $probe=[Diagnostics.Process]::new();$probe.StartInfo=$start;$null=$probe.Start();$stdout=$probe.StandardOutput.ReadToEndAsync();$stderr=$probe.StandardError.ReadToEndAsync()
    if(-not $probe.WaitForExit(15000)){$probe.Kill();throw 'CORE_NEXT_METADATA_PROBE_TIMEOUT'}
    $embedded=$stdout.GetAwaiter().GetResult()|ConvertFrom-Json
    $probeError=$stderr.GetAwaiter().GetResult()
    if($probe.ExitCode -ne 0 -or $embedded.product -cne 'DRAGONHYDRA CORE NEXT' -or $embedded.source_sha -cne $SourceSha -or $embedded.source_content_sha256 -cne $sourceHash -or $embedded.version -cne $config.version){throw 'CORE_NEXT_EMBEDDED_DESKTOP_IDENTITY_MISMATCH'}
    Copy-Item -LiteralPath $native -Destination (Join-Path $output 'DRAGONHYDRA-Client.exe')
    $embedded|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $output 'BUILD-INFO.json') -Encoding utf8
    Get-Content -LiteralPath (Join-Path $project 'packaging\genesis2\THIRD-PARTY-NOTICES.txt'),(Join-Path $desktop 'THIRD-PARTY-OPENER-NOTICES.txt')|Set-Content -LiteralPath (Join-Path $output 'THIRD-PARTY-NOTICES.txt') -Encoding utf8
    $files=@(Get-ChildItem -LiteralPath $output -File|ForEach-Object {@{path=$_.Name;bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}})
    @{schema_version=1;product='DRAGONHYDRA CORE NEXT';version=$config.version;source_sha=$SourceSha;files=$files}|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $output 'PAYLOAD-MANIFEST.json') -Encoding utf8
    @{status='BUILT_METADATA_VERIFIED';compilation='PASS';source_sha=$SourceSha;source_content_sha256=$sourceHash;source_files=$bindings;files=$files;output=$output;metadata_probe='Bounded redirected ProcessStartInfo wait';metadata_stderr=$probeError;node_path=$cache;cargo_cache_source=$CargoCacheRoot;native_gui_acceptance='NOT_RUN';original_installation_mutated=$false}|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $work 'desktop-build.json') -Encoding utf8
    $output
}finally{foreach($key in $previous.Keys){[Environment]::SetEnvironmentVariable($key,$previous[$key],'Process')}}
