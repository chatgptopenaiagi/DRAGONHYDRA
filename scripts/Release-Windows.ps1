#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SourceRoot,
    [Parameter(Mandatory)][string]$WorkspaceRoot,
    [Parameter(Mandatory)][string]$WorkRoot,
    [Parameter(Mandatory)][string]$AssetRoot,
    [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory)][string]$BuilderPackages,
    [Parameter(Mandatory)][string]$BuildInfoFile,
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{40}$')][string]$SourceSha,
    [Parameter(Mandatory)][ValidatePattern('^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$')][string]$Version,
    [ValidateSet('all','desktop','server')][string]$Target='all'
)
$ErrorActionPreference='Stop'
$SourceRoot=[IO.Path]::GetFullPath($SourceRoot)
$WorkspaceRoot=[IO.Path]::GetFullPath($WorkspaceRoot)
$WorkRoot=[IO.Path]::GetFullPath($WorkRoot)
$AssetRoot=[IO.Path]::GetFullPath($AssetRoot)
$BuildInfoFile=[IO.Path]::GetFullPath($BuildInfoFile)
$workspaceBoundary=$WorkspaceRoot.TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
foreach($path in @($SourceRoot,$WorkRoot,$AssetRoot,$BuildInfoFile)){
    if(-not $path.StartsWith($workspaceBoundary,[StringComparison]::OrdinalIgnoreCase)){throw "Release path is outside the authorized workspace: $path"}
}
$buildInfo=Get-Content -LiteralPath $BuildInfoFile -Raw|ConvertFrom-Json
if($buildInfo.source_sha -ne $SourceSha -or $buildInfo.version -ne $Version){throw 'Build metadata does not identify this release candidate.'}
if(-not(Test-Path -LiteralPath $Python -PathType Leaf)){throw 'Verified Python executable is unavailable.'}
New-Item -ItemType Directory -Path $WorkRoot,$AssetRoot -Force|Out-Null
$commands=[Collections.Generic.List[object]]::new()
$artifacts=[Collections.Generic.List[object]]::new()
$failures=[Collections.Generic.List[object]]::new()
$record=[ordered]@{schema_version=1;source_sha=$SourceSha;version=$Version;source_root=$SourceRoot;started_at=[DateTime]::UtcNow.ToString('o');commands=$commands;artifacts=$artifacts;failures=$failures;status='running'}
$recordFile=Join-Path $WorkRoot 'windows-build.json'
if(Test-Path -LiteralPath (Join-Path $SourceRoot '.git')){
    $observedSha=(& 'C:\Program Files\Git\cmd\git.exe' -C $SourceRoot rev-parse HEAD).Trim()
    if($LASTEXITCODE -ne 0 -or $observedSha -ne $SourceSha){throw 'Frozen Windows source HEAD differs from the release commit.'}
    & 'C:\Program Files\Git\cmd\git.exe' -C $SourceRoot diff --quiet HEAD --
    if($LASTEXITCODE -ne 0){throw 'Frozen Windows tracked source has changes before the build.'}
    $record.source_check='Detached source HEAD and clean tracked content verified'
}else{$record.source_check='Exported snapshot supplied by coordinator; snapshot integrity must be verified by release orchestrator'}
function Save-Record {$record|ConvertTo-Json -Depth 9|Set-Content -LiteralPath $recordFile -Encoding utf8}
function Run-Native([string]$Name,[string]$Executable,[string[]]$Arguments,[string]$Directory){
    $log=Join-Path $WorkRoot ($Name+'.log')
    $started=[DateTime]::UtcNow
    Push-Location -LiteralPath $Directory
    try{& $Executable @Arguments 2>&1|Tee-Object -LiteralPath $log|ForEach-Object { Write-Host $_ };$code=$LASTEXITCODE}
    finally{Pop-Location}
    $commands.Add(@{name=$Name;executable=$Executable;arguments=$Arguments;cwd=$Directory;started_at=$started.ToString('o');duration_seconds=([DateTime]::UtcNow-$started).TotalSeconds;exit_code=$code;log=$log})
    Save-Record
    if($code -ne 0){throw "$Name failed with native exit code $code"}
}
function Artifact([string]$Path,[string]$Role){
    $signature=if($Path.EndsWith('.exe')){Get-AuthenticodeSignature -LiteralPath $Path}else{$null}
    $artifacts.Add(@{path=$Path;filename=[IO.Path]::GetFileName($Path);role=$Role;bytes=(Get-Item -LiteralPath $Path).Length;sha256=(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant();built=$true;source_sha=$SourceSha;version=$Version;signing=if($signature){[string]$signature.Status}else{'unsigned archive'};signer=if($signature -and $signature.SignerCertificate){$signature.SignerCertificate.Subject}else{$null}})
}
$oldPythonPath=$env:PYTHONPATH
$oldBuildInfo=$env:DRAGONHYDRA_BUILD_INFO
$oldSourceSha=$env:DRAGONHYDRA_SOURCE_SHA
$oldCargoTarget=$env:CARGO_TARGET_DIR
$oldCargoOffline=$env:CARGO_NET_OFFLINE
$oldNpmCache=$env:npm_config_cache
try{
    $env:DRAGONHYDRA_BUILD_INFO=$BuildInfoFile
    $env:DRAGONHYDRA_SOURCE_SHA=$SourceSha
    $env:PYTHONPATH=(Join-Path $SourceRoot 'src')+[IO.Path]::PathSeparator+$BuilderPackages
    if($Target -in @('all','server')){
        try{
            $serverDist=Join-Path $WorkRoot 'server-dist'
            Run-Native 'server-pyinstaller' $Python @('-B','-m','PyInstaller','--noconfirm','--distpath',$serverDist,'--workpath',(Join-Path $WorkRoot 'pyinstaller'),(Join-Path $SourceRoot 'packaging\windows\product-server.spec')) $SourceRoot
            $serverDirectory=Join-Path $serverDist 'DRAGONHYDRA-Server-x64'
            if(-not(Test-Path -LiteralPath (Join-Path $serverDirectory 'DRAGONHYDRA-Server.exe'))){throw 'PyInstaller did not produce the required onedir server.'}
            Copy-Item -LiteralPath $BuildInfoFile -Destination (Join-Path $serverDirectory 'BUILD-INFO.json')
            Copy-Item -LiteralPath (Join-Path $SourceRoot 'packaging\genesis2\THIRD-PARTY-NOTICES.txt') -Destination (Join-Path $serverDirectory 'THIRD-PARTY-NOTICES.txt')
            $archive=Join-Path $AssetRoot ('DRAGONHYDRA-'+$Version+'-Server-win-x64.zip')
            if(Test-Path -LiteralPath $archive){throw 'Server release asset already exists; do not overwrite verified bytes.'}
            $zipScript=Join-Path $SourceRoot 'tests\installation\release_zip.py'
            Run-Native 'server-package-zip' $Python @('-B',$zipScript,'--source',$serverDirectory,'--output',$archive) $WorkRoot
            Artifact $archive 'Windows x64 private-runtime server ZIP'
            $record.server_directory=$serverDirectory
        }catch{$failures.Add(@{target='server';error=$_.Exception.Message})}
    }
    if($Target -in @('all','desktop')){
        try{
            $desktop=Join-Path $SourceRoot 'client\desktop'
            $tauri=Get-Content -LiteralPath (Join-Path $desktop 'src-tauri\tauri.conf.json') -Raw|ConvertFrom-Json
            if($tauri.version -ne $Version){throw 'Tauri source version differs from selected release mapping.'}
            $env:CARGO_TARGET_DIR=Join-Path $WorkRoot 'tauri'
            $env:CARGO_NET_OFFLINE='true'
            $env:npm_config_cache=Join-Path $WorkspaceRoot 'runtime\scratch\npm-cache'
            # Reuse cached locked tarballs when present; a scoped cache miss may
            # retrieve the exact integrity-locked build dependency from npm.
            Run-Native 'desktop-npm-ci' 'C:\Program Files\nodejs\npm.cmd' @('ci','--prefer-offline','--fetch-retries=2','--fetch-timeout=30000','--no-audit','--no-fund') $desktop
            # A resource outside the source snapshot is an explicit controlled build
            # input, not a mutation to source or an uncontrolled live configuration.
            $resourceMap=@{};$resourceMap[$BuildInfoFile.Replace('\','/')]='BUILD-INFO.json'
            $overlay=@{bundle=@{resources=$resourceMap}}
            $overlayPath=Join-Path $WorkRoot 'tauri-release-overlay.json'
            $overlay|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $overlayPath -Encoding utf8NoBOM
            Run-Native 'desktop-tauri-build' 'C:\Program Files\nodejs\npm.cmd' @('run','build','--','--target','x86_64-pc-windows-msvc','--config',$overlayPath,'--','--locked','--offline') $desktop
            $release=Join-Path $env:CARGO_TARGET_DIR 'x86_64-pc-windows-msvc\release'
            $binary=Join-Path $release 'dragonhydra-desktop.exe'
            $setup=Join-Path $release ('bundle\nsis\DRAGONHYDRA Client_'+$Version+'_x64-setup.exe')
            if(-not(Test-Path -LiteralPath $binary) -or -not(Test-Path -LiteralPath $setup)){throw 'Tauri did not produce both expected desktop outputs.'}
            $destination=Join-Path $AssetRoot ('DRAGONHYDRA-'+$Version+'-Desktop-win-x64-Setup.exe')
            if(Test-Path -LiteralPath $destination){throw 'Desktop release asset already exists; do not overwrite verified bytes.'}
            Copy-Item -LiteralPath $setup -Destination $destination
            Artifact $destination 'Windows x64 desktop-only NSIS installer'
            $record.desktop_binary=$binary
            $record.desktop_file_version=(Get-Item -LiteralPath $binary).VersionInfo.FileVersion
            $fileInfo=(Get-Item -LiteralPath $binary).VersionInfo
            $record.desktop_numeric_file_version=@($fileInfo.FileMajorPart,$fileInfo.FileMinorPart,$fileInfo.FileBuildPart,$fileInfo.FilePrivatePart)-join '.'
            $record.desktop_product_version=(Get-Item -LiteralPath $binary).VersionInfo.ProductVersion
            $record.desktop_setup_file_version=(Get-Item -LiteralPath $destination).VersionInfo.FileVersion
        }catch{$failures.Add(@{target='desktop';error=$_.Exception.Message})}
    }
    $record.finished_at=[DateTime]::UtcNow.ToString('o')
    if(Test-Path -LiteralPath (Join-Path $SourceRoot '.git')){
        & 'C:\Program Files\Git\cmd\git.exe' -C $SourceRoot diff --quiet HEAD --
        if($LASTEXITCODE -ne 0){$failures.Add(@{target='source';error='Tracked frozen source changed during Windows build'})}
    }
    $record.status=if($failures.Count){'build_failed'}else{'built_unverified'}
    Save-Record
    if($failures.Count){throw 'One or more Windows target builds failed; see windows-build.json. Independent built outputs are retained.'}
    $record|ConvertTo-Json -Depth 9
}finally{
    $env:PYTHONPATH=$oldPythonPath;$env:DRAGONHYDRA_BUILD_INFO=$oldBuildInfo;$env:DRAGONHYDRA_SOURCE_SHA=$oldSourceSha
    $env:CARGO_TARGET_DIR=$oldCargoTarget;$env:CARGO_NET_OFFLINE=$oldCargoOffline;$env:npm_config_cache=$oldNpmCache
    Save-Record
}
