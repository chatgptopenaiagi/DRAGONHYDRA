#requires -Version 7.0
[CmdletBinding()]
param(
    [string]$WorkspaceRoot=(Split-Path $PSScriptRoot -Parent),
    [Parameter(Mandatory)][string]$SourceRoot,
    [Parameter(Mandatory)][string]$WorkRoot,
    [Parameter(Mandatory)][string]$ArtifactPath,
    [Parameter(Mandatory)][string]$Version,
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{40}$')][string]$SourceSha,
    [int]$VersionCode=4
)
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath($WorkspaceRoot)
$sourcePath=[IO.Path]::GetFullPath($SourceRoot)
$workPath=[IO.Path]::GetFullPath($WorkRoot)
$artifact=[IO.Path]::GetFullPath($ArtifactPath)
$allowedRoot=[IO.Path]::GetFullPath($projectRoot)+[IO.Path]::DirectorySeparatorChar
foreach($path in @($sourcePath,$workPath,$artifact)){
    if(-not $path.StartsWith($allowedRoot,[StringComparison]::OrdinalIgnoreCase)){throw 'Release work must remain within this project.'}
}
$flutter='C:\flutter\bin\flutter.bat'
$javaRoot='C:\Program Files\Android\openjdk\jdk-21.0.8'
$sdk='C:\Users\LOVE\AppData\Local\Android\Sdk'
$apksigner=Join-Path $sdk 'build-tools\36.0.0\apksigner.bat'
$aapt=Join-Path $sdk 'build-tools\36.0.0\aapt.exe'
$keystore=Join-Path $env:USERPROFILE '.android\debug.keystore'
$expectedSigner='d77e623706f0146bc495904affe310cb492d67277ecf70b28455d1f5e138e419'
foreach($file in @($flutter,$apksigner,$aapt,$keystore,(Join-Path $javaRoot 'bin\java.exe'))){
    if(-not(Test-Path -LiteralPath $file -PathType Leaf)){throw "Required existing Android build capability is unavailable: $file"}
}
$actualSha=(& git -C $sourcePath rev-parse HEAD).Trim()
if($LASTEXITCODE -ne 0 -or $actualSha -ne $SourceSha){throw 'Android source checkout does not match the frozen release commit.'}
$changes=& git -C $sourcePath status --porcelain --untracked-files=no
if($LASTEXITCODE -ne 0 -or $changes){throw 'Frozen release source has tracked changes.'}
$mobileSource=Join-Path $sourcePath 'android\dragonhydra_mobile'
$pubspec=Get-Content -LiteralPath (Join-Path $mobileSource 'pubspec.yaml') -Raw
if($pubspec -notmatch ('(?m)^version:\s*'+[regex]::Escape($Version)+'\+'+$VersionCode+'\s*$')){
    throw 'Android versionName/versionCode does not match the release version mapping.'
}
New-Item -ItemType Directory -Force -Path $workPath,(Split-Path $artifact -Parent) | Out-Null
$stage=Join-Path $workPath 'android-stage'
if(Test-Path -LiteralPath $stage){throw 'Use a fresh or explicitly reviewed Android work directory; existing staged source is preserved.'}
New-Item -ItemType Directory -Path $stage | Out-Null
# Copy only the clean frozen mobile sources; exclude developer build state.
foreach($name in @('lib','assets','test','android','pubspec.yaml','pubspec.lock','analysis_options.yaml','README.md')){
    $input=Join-Path $mobileSource $name
    if(Test-Path -LiteralPath $input){Copy-Item -LiteralPath $input -Destination $stage -Recurse}
}
$oldJava=$env:JAVA_HOME
$oldSdk=$env:ANDROID_HOME
$started=[DateTime]::UtcNow
try{
    $env:JAVA_HOME=$javaRoot
    $env:ANDROID_HOME=$sdk
    Push-Location $stage
    try{
        & $flutter pub get --offline 2>&1 | Tee-Object -LiteralPath (Join-Path $workPath 'pub-get.txt')
        if($LASTEXITCODE -ne 0){throw 'Flutter dependency restoration failed.'}
        & $flutter analyze --no-pub 2>&1 | Tee-Object -LiteralPath (Join-Path $workPath 'analyze.txt')
        if($LASTEXITCODE -ne 0){throw 'Flutter analysis failed.'}
        & $flutter test --no-pub 2>&1 | Tee-Object -LiteralPath (Join-Path $workPath 'flutter-tests.txt')
        if($LASTEXITCODE -ne 0){throw 'Flutter regression failed.'}
        & $flutter build apk --release --target-platform android-arm64 --no-pub --dart-define "DRAGONHYDRA_SOURCE_SHA=$SourceSha" --dart-define "DRAGONHYDRA_VERSION=$Version" 2>&1 | Tee-Object -LiteralPath (Join-Path $workPath 'build-apk.txt')
        if($LASTEXITCODE -ne 0){throw 'Android APK build failed.'}
    }finally{Pop-Location}
    $built=Join-Path $stage 'build\app\outputs\flutter-apk\app-release.apk'
    if(-not(Test-Path -LiteralPath $built)){throw 'Android build returned without its expected APK.'}
    $signature=& $apksigner verify --verbose --print-certs $built 2>&1
    if($LASTEXITCODE -ne 0){throw 'Android APK signature verification failed.'}
    $signature|Set-Content -LiteralPath (Join-Path $workPath 'apk-signature.txt')
    if(($signature -join "`n") -notmatch ('certificate SHA-256 digest:\s*'+$expectedSigner)){
        throw 'APK signer differs from the established earlier Android alpha; artifact rejected.'
    }
    $badging=& $aapt dump badging $built 2>&1
    if($LASTEXITCODE -ne 0){throw 'Android package metadata inspection failed.'}
    $badging|Set-Content -LiteralPath (Join-Path $workPath 'apk-badging.txt')
    $packageLine=@($badging|Where-Object {$_ -match '^package:'})[0]
    if($packageLine -notmatch "name='ai.dragonhydra.mobile'" -or $packageLine -notmatch "versionCode='$VersionCode'" -or $packageLine -notmatch ("versionName='"+[regex]::Escape($Version)+"'")){
        throw 'Final APK application/update identity or embedded version does not match the release.'
    }
    if(Test-Path -LiteralPath $artifact){throw 'An output APK already exists; refusing implicit replacement.'}
    Copy-Item -LiteralPath $built -Destination $artifact
    $result=[ordered]@{schema_version=1;status='BUILT_SIGNATURE_VERIFIED';source_sha=$SourceSha;version=$Version;version_code=$VersionCode;application_id='ai.dragonhydra.mobile';abi='arm64-v8a';build_mode='release-optimized';signing_status='development signed with existing Android Debug identity';certificate_sha256=$expectedSigner;production_signing_available=$false;artifact=$artifact;bytes=(Get-Item -LiteralPath $artifact).Length;sha256=(Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLowerInvariant();started_at=$started.ToString('o');finished_at=[DateTime]::UtcNow.ToString('o');install_test='required before publication';source_metadata_defines=@('DRAGONHYDRA_SOURCE_SHA','DRAGONHYDRA_VERSION')}
    $result|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $workPath 'android-build.json')
    $result|ConvertTo-Json -Depth 5
}finally{
    $env:JAVA_HOME=$oldJava
    $env:ANDROID_HOME=$oldSdk
}
