#requires -Version 7.0
[CmdletBinding()]
param([switch]$NoBundle)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$desktop=Join-Path $projectRoot 'client\desktop'
$version=(Get-Content -LiteralPath (Join-Path $desktop 'src-tauri\tauri.conf.json') -Raw|ConvertFrom-Json).version
if($version -notmatch '^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$'){throw 'The Tauri source version is invalid.'}
$cargoTarget=Join-Path $projectRoot 'build\tauri'
$oldTarget=$env:CARGO_TARGET_DIR
$oldNpmCache=$env:npm_config_cache
try {
    $env:CARGO_TARGET_DIR=$cargoTarget
    $env:npm_config_cache=Join-Path $projectRoot 'runtime\scratch\npm-cache'
    New-Item -ItemType Directory -Path (Join-Path $projectRoot 'dist') -Force | Out-Null
    Push-Location $desktop
    try {
        & npm.cmd ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Pinned Tauri CLI installation failed.' }
        $buildArguments=@('run','build','--','--target','x86_64-pc-windows-msvc')
        if($NoBundle){$buildArguments+='--no-bundle'}
        $buildArguments+=@('--','--locked')
        & npm.cmd @buildArguments
        if ($LASTEXITCODE -ne 0) { throw 'Native Tauri build failed.' }
    } finally { Pop-Location }
    $native=Join-Path $cargoTarget 'x86_64-pc-windows-msvc\release\dragonhydra-desktop.exe'
    Copy-Item -LiteralPath $native -Destination (Join-Path $projectRoot 'dist\DRAGONHYDRA-Client-x64.exe') -Force
    if(-not $NoBundle){
        $setup=Join-Path $cargoTarget ('x86_64-pc-windows-msvc\release\bundle\nsis\DRAGONHYDRA Client_'+$version+'_x64-setup.exe')
        Copy-Item -LiteralPath $setup -Destination (Join-Path $projectRoot ('dist\DRAGONHYDRA-Client-'+$version+'-windows-x64-setup.exe')) -Force
    }
    & (Join-Path $projectRoot 'packaging\genesis2\Write-ClientManifest.ps1')
} finally { $env:CARGO_TARGET_DIR=$oldTarget; $env:npm_config_cache=$oldNpmCache }
