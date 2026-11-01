#requires -Version 7.0
[CmdletBinding()]
param(
    [string]$Version = '0.4.1-dev.1',
    [string]$BuildRoot,
    [string]$OutputRoot,
    [string]$ReleaseRoot,
    [switch]$RepackageOnly,
    [switch]$RefreshRuntime,
    [switch]$RefreshWebHook,
    [string]$KernelBuildRoot,
    [string]$ClientBuildRoot,
    [string]$JoomlaPackagePath,
    [string]$SevenZip = 'C:\Program Files\7-Zip\7z.exe',
    [string]$MakeNsis = (Join-Path $env:LOCALAPPDATA 'tauri\NSIS\makensis.exe')
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($RefreshRuntime -and -not $RepackageOnly) { throw 'RefreshRuntime is an explicit repair step for an already verified staging tree.' }
if ($RefreshWebHook -and -not $RepackageOnly) { throw 'RefreshWebHook is an explicit repair step for an already verified staging tree.' }
$project = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if ($Version -ne '0.4.1-dev.1') { throw 'This development build has an explicit 0.4.1-dev.1 version contract.' }
if (-not $BuildRoot) { $BuildRoot = Join-Path $project ('build\workstation\'+$Version+'\'+(Get-Date -Format 'yyyyMMdd-HHmmss')) }
if (-not $OutputRoot) { $OutputRoot = Join-Path $project ('dist\workstation\'+$Version) }
if (-not $ReleaseRoot) { $ReleaseRoot = Join-Path $project 'dist\releases\v0.4.0-alpha.1\assets' }
$BuildRoot = [IO.Path]::GetFullPath($BuildRoot)
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
foreach ($path in @($BuildRoot,$OutputRoot)) {
    if (-not $path.StartsWith($project+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Build and output directories must remain inside the project.' }
    if ($path.StartsWith((Join-Path $project 'dist\releases')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Immutable release directories cannot be workstation outputs.' }
}
if ($KernelBuildRoot -or $ClientBuildRoot -or ($JoomlaPackagePath -and $RepackageOnly)) {
    if (-not $BuildRoot.StartsWith((Join-Path $project 'build\connections')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Provider kernel staging must be a new owned directory under build/connections; verified workstation staging is preserved.' }
    if (Test-Path -LiteralPath (Join-Path $OutputRoot ('DRAGONHYDRA-'+$Version+'-Workstation-win-x64-Setup.exe'))) { throw 'A provider-enabled candidate never overwrites a previous installer. Choose a fresh output directory.' }
    if ($KernelBuildRoot) {
        $KernelBuildRoot = [IO.Path]::GetFullPath($KernelBuildRoot)
        if (-not $KernelBuildRoot.StartsWith($project+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'The verified kernel build must remain inside the project.' }
    }
}
if ((Test-Path -LiteralPath $BuildRoot) -and -not $RepackageOnly) { throw 'Use a fresh build directory; previous evidence is retained.' }
if ($RepackageOnly -and -not (Test-Path -LiteralPath $BuildRoot)) { throw 'Repackaging requires an existing, verified staging directory.' }
foreach ($tool in @($SevenZip,$MakeNsis)) { if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) { throw "Existing required build tool is unavailable: $tool" } }
$stage = Join-Path $BuildRoot 'stage'
$started = [DateTime]::UtcNow
$attemptSuffix = if ($RepackageOnly) { '-repackage-'+(Get-Date -Format 'yyyyMMdd-HHmmss') } else { '' }
$steps = [Collections.Generic.List[object]]::new()
function Native([string]$Name,[string]$Executable,[string[]]$Arguments) {
    $time = [Diagnostics.Stopwatch]::StartNew()
    $log = Join-Path $BuildRoot ($Name+$attemptSuffix+'.log')
    & $Executable @Arguments 2>&1 | Tee-Object -FilePath $log
    $code = $LASTEXITCODE
    $time.Stop()
    $steps.Add([ordered]@{name=$Name;executable=$Executable;arguments=$Arguments;exit_code=$code;seconds=[Math]::Round($time.Elapsed.TotalSeconds,3);log=[IO.Path]::GetFileName($log)})
    if ($code -ne 0) { throw "$Name failed with exit code $code; inspect $log" }
}
function Hash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function WriteJson($Value,[string]$Path) { [IO.File]::WriteAllText($Path,($Value | ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false)) }
function Get-VerifiedFrontendPackage([string]$Path) {
    $Path = [IO.Path]::GetFullPath($Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw 'Build the canonical Joomla frontend package first using scripts/build_joomla.py, or provide -JoomlaPackagePath.' }
    $receiptPath = [IO.Path]::ChangeExtension($Path,'.manifest.json')
    if (-not (Test-Path -LiteralPath $receiptPath -PathType Leaf)) { throw 'The Joomla frontend package needs its matching builder manifest.' }
    $receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
    $expectedVersion = ([xml](Get-Content -LiteralPath (Join-Path $project 'server\joomla\pkg_dragonhydra.xml') -Raw)).extension.version
    if (-not $receipt.built -or $receipt.version -ne $expectedVersion -or -not ($receipt.PSObject.Properties.Name -contains 'frontend_setup') -or $receipt.child_template_files -lt 2 -or $receipt.sha256 -ne (Hash $Path) -or $receipt.bytes -ne (Get-Item -LiteralPath $Path).Length) { throw 'Joomla frontend artifact identity or SHA-256 does not match its builder manifest.' }
    [ordered]@{path=$Path;version=$receipt.version;package_sha256=$receipt.sha256;bytes=$receipt.bytes;source_sha=$receipt.source_sha;manifest_sha256=(Hash $receiptPath);frontend_setup=$receipt.frontend_setup;child_template='cassiopeia_dragonhydra';verification='Package input/hash verified; installation acceptance remains separate'}
}
$kernelOverride = $null
$clientOverride = $null
$joomlaOverride = $null
$kernelBuild = $null
$clientBuild = $null
$kernelRegistryProof = $null
. (Join-Path $project 'packaging\windows\workstation\ClientBuild.ps1')
. (Join-Path $project 'packaging\windows\workstation\KernelBuild.ps1')
if (-not $RepackageOnly -and -not $JoomlaPackagePath) {
    $joomlaVersion = ([xml](Get-Content -LiteralPath (Join-Path $project 'server\joomla\pkg_dragonhydra.xml') -Raw)).extension.version
    $JoomlaPackagePath = Join-Path $project ('dist\pkg_dragonhydra-'+$joomlaVersion+'.zip')
}
if ($JoomlaPackagePath) { $joomlaOverride = Get-VerifiedFrontendPackage $JoomlaPackagePath }
if ($KernelBuildRoot) { $kernelBuild = Get-VerifiedKernelBuild -Root $KernelBuildRoot -ProjectRoot $project -StagingRoot $BuildRoot }
if ($ClientBuildRoot) { $clientBuild = Get-VerifiedClientBuild -Root $ClientBuildRoot -ProjectRoot $project -StagingRoot $BuildRoot }
if (-not $RepackageOnly) {
    $kernelRegistryProof = Assert-FrontendKernelCompatibility -FrontendVersion $(if($joomlaOverride){$joomlaOverride.version}else{$null}) -KernelBuild $kernelBuild
}
$sourceSha = 'a1380545bd3bb225f400e7e328535ff692c0123a'
$manifest = Get-Content -LiteralPath (Join-Path $ReleaseRoot 'ARTIFACT-MANIFEST.json') -Raw | ConvertFrom-Json
if ($manifest.source_sha -ne $sourceSha) { throw 'The immutable inner-component source does not match the verified release.' }
$components = [Collections.Generic.List[object]]::new()
foreach ($filename in @('DRAGONHYDRA-0.4.0-alpha.1-Server-win-x64.zip','DRAGONHYDRA-0.4.0-alpha.1-Desktop-win-x64-Setup.exe','pkg_dragonhydra-0.4.0-alpha.1.zip')) {
    $entry = @($manifest.artifacts | Where-Object filename -EQ $filename)
    if ($entry.Count -ne 1) { throw "Missing explicit release manifest entry: $filename" }
    $file = Join-Path $ReleaseRoot $filename
    if ((Hash $file) -ne $entry[0].sha256 -or (Get-Item -LiteralPath $file).Length -ne $entry[0].bytes) { throw "Immutable input integrity failed: $filename" }
    $components.Add([ordered]@{filename=$filename;version='0.4.0-alpha.1';source_sha=$sourceSha;sha256=$entry[0].sha256;bytes=$entry[0].bytes})
}
if ($RepackageOnly) {
    $oldInfo = Get-Content -LiteralPath (Join-Path $stage 'WORKSTATION-BUILD.json') -Raw | ConvertFrom-Json
    if ($oldInfo.PSObject.Properties.Name -contains 'kernel_override') { $kernelOverride = $oldInfo.kernel_override }
    if ($oldInfo.PSObject.Properties.Name -contains 'client_override') { $clientOverride = $oldInfo.client_override }
    if (-not $joomlaOverride -and $oldInfo.PSObject.Properties.Name -contains 'joomla_frontend_override') { $joomlaOverride = $oldInfo.joomla_frontend_override }
    if ($RefreshWebHook -and -not $joomlaOverride) { throw 'The current frontend-aware provisioning hook requires the matching -JoomlaPackagePath when upgrading a pre-frontend staging copy.' }
    if ($oldInfo.product -ne 'DRAGONHYDRA Workstation' -or $oldInfo.version -ne $Version -or $oldInfo.inner_components[0].source_sha -ne $sourceSha) { throw 'Staging ownership/version does not match this build.' }
    $oldInventory = Get-Content -LiteralPath (Join-Path $stage 'PAYLOAD-MANIFEST.json') -Raw | ConvertFrom-Json
    foreach ($entry in $oldInventory.files) {
        $path = [IO.Path]::GetFullPath((Join-Path $stage $entry.path))
        if (-not $path.StartsWith($stage+'\',[StringComparison]::OrdinalIgnoreCase) -or (Hash $path) -ne $entry.sha256) { throw "Previously staged payload integrity failed: $($entry.path)" }
    }
    if (@(Get-ChildItem -LiteralPath $stage -File -Recurse).Count -ne $oldInventory.files.Count+1) { throw 'Unexpected files were added to the verified staging tree.' }
    if ($clientBuild) { $null = Get-VerifiedClientStagingCopy -Root $BuildRoot -ProjectRoot $project }
    $kernelRegistryProof = Assert-FrontendKernelCompatibility -FrontendVersion $(if($joomlaOverride){$joomlaOverride.version}else{$null}) -KernelBuild $kernelBuild -InheritedOverride $kernelOverride -Stage $stage -ProjectRoot $project -StagingRoot $BuildRoot
    if ($kernelOverride -and $kernelRegistryProof -and -not $kernelBuild) { $kernelOverride.registry_verification = $kernelRegistryProof }
    New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
    if ($RefreshRuntime) {
        $pwsh = (Get-Process -Id $PID).Path
        Native 'refresh-runtime' $pwsh @('-NoLogo','-NoProfile','-File',(Join-Path $project 'packaging\windows\workstation\Build-Runtime.ps1'),'-OutputRoot',(Join-Path $stage 'workstation'))
    }
    if ($RefreshWebHook -or $JoomlaPackagePath) {
        $webManifestPath = Join-Path $stage 'web\payload-manifest.json'
        $webManifest = Get-Content -LiteralPath $webManifestPath -Raw | ConvertFrom-Json
        if ($webManifest.source_sha -ne $sourceSha -or $webManifest.product_version -ne $Version -or $webManifest.architecture -ne 'x64') { throw 'The staged private web payload has incompatible provenance.' }
        $hookEntries = @($webManifest.files | Where-Object path -EQ 'manage.php')
        $hookPath = Join-Path $stage 'web\manage.php'
        if ($hookEntries.Count -ne 1 -or (Hash $hookPath) -ne $hookEntries[0].sha256) { throw 'The previously verified provisioning hook does not match the web manifest.' }
        Copy-Item -LiteralPath (Join-Path $project 'packaging\windows\workstation\web\manage.php') -Destination $hookPath -Force
        $hookEntries[0].sha256 = Hash $hookPath
        $hookEntries[0].bytes = (Get-Item -LiteralPath $hookPath).Length
        $webManifest | Add-Member -NotePropertyName provisioning_hook -NotePropertyValue ([ordered]@{path='manage.php';sha256=$hookEntries[0].sha256;source='workstation working-tree source recorded in WORKSTATION-BUILD.json';refresh='explicit verified hook-only repair; binary payload unchanged'}) -Force
        if ($JoomlaPackagePath) {
            $extensionEntries = @($webManifest.files | Where-Object path -EQ 'extension.zip')
            $extensionPath = Join-Path $stage 'web\extension.zip'
            if ($extensionEntries.Count -ne 1 -or (Hash $extensionPath) -ne $extensionEntries[0].sha256) { throw 'The prior Joomla extension does not match the verified private-web manifest.' }
            Copy-Item -LiteralPath $joomlaOverride.path -Destination $extensionPath -Force
            $extensionEntries[0].sha256 = Hash $extensionPath
            $extensionEntries[0].bytes = (Get-Item -LiteralPath $extensionPath).Length
            if ($extensionEntries[0].sha256 -ne $joomlaOverride.package_sha256) { throw 'Joomla frontend package changed while staging.' }
            $webManifest | Add-Member -NotePropertyName joomla_frontend_override -NotePropertyValue $joomlaOverride -Force
            $steps.Add([ordered]@{name='verified-joomla-frontend-package';exit_code=0;sha256=$joomlaOverride.package_sha256;bytes=$joomlaOverride.bytes;version=$joomlaOverride.version;full_web_payload_rebuilt=$false;server_or_client_rebuilt=$false})
        }
        WriteJson $webManifest $webManifestPath
        $steps.Add([ordered]@{name='refresh-web-hook';exit_code=0;path='web/manage.php';sha256=$hookEntries[0].sha256;bytes=$hookEntries[0].bytes;full_web_payload_rebuilt=$false})
    }
} else {
New-Item -ItemType Directory -Path $BuildRoot,$OutputRoot,$stage -Force | Out-Null
$serverExtract = Join-Path $BuildRoot 'server-extracted'
Native 'extract-server' $SevenZip @('x','-y',('-o'+$serverExtract),(Join-Path $ReleaseRoot 'DRAGONHYDRA-0.4.0-alpha.1-Server-win-x64.zip'))
$serverExe = @(Get-ChildItem -LiteralPath $serverExtract -Filter 'DRAGONHYDRA-Server.exe' -Recurse -File)
if ($serverExe.Count -ne 1) { throw 'The full private-runtime server directory could not be identified uniquely.' }
Copy-Item -LiteralPath $serverExe[0].Directory.FullName -Destination (Join-Path $stage 'server') -Recurse
$clientExtract = Join-Path $BuildRoot 'client-extracted'
Native 'extract-client' $SevenZip @('x','-y',('-o'+$clientExtract),(Join-Path $ReleaseRoot 'DRAGONHYDRA-0.4.0-alpha.1-Desktop-win-x64-Setup.exe'))
$client = Join-Path $clientExtract 'dragonhydra-desktop.exe'
if ((Hash $client) -ne '17b557c7a4f2524ace5769c3bace55583ce695a0f250771a3585ce954688f94b') { throw 'The extracted client does not match the previously verified release binary.' }
$clientMeta = Get-Content -LiteralPath (Join-Path $clientExtract 'BUILD-INFO.json') -Raw | ConvertFrom-Json
if ($clientMeta.source_sha -ne $sourceSha) { throw 'The client embeds a different source commit.' }
New-Item -ItemType Directory -Path (Join-Path $stage 'client') | Out-Null
Copy-Item -LiteralPath $client -Destination (Join-Path $stage 'client\DRAGONHYDRA-Client.exe')
foreach ($name in @('BUILD-INFO.json','THIRD-PARTY-NOTICES.txt')) { Copy-Item -LiteralPath (Join-Path $clientExtract $name) -Destination (Join-Path $stage 'client') }
$pwsh = (Get-Process -Id $PID).Path
Native 'build-runtime' $pwsh @('-NoLogo','-NoProfile','-File',(Join-Path $project 'packaging\windows\workstation\Build-Runtime.ps1'),'-OutputRoot',(Join-Path $stage 'workstation'))
Native 'build-web' $pwsh @('-NoLogo','-NoProfile','-File',(Join-Path $project 'packaging\windows\workstation\web\Build-WebPayload.ps1'),'-OutputRoot',(Join-Path $stage 'web'),'-ExtensionPath',$joomlaOverride.path,'-SourceSha',$sourceSha,'-Version',$Version)
}
if ($kernelBuild) {
    # Both a fresh extracted baseline and an integrity-checked repackage use
    # this one verified replacement path; immutable release inputs stay intact.
    $kernelOverride = Set-VerifiedKernelPayload -KernelBuild $kernelBuild -BuildRoot $BuildRoot -Stage $stage -RegistryProof $kernelRegistryProof
    $steps.Add([ordered]@{name='verified-provider-kernel';exit_code=0;source_content_sha256=$kernelOverride.source_content_sha256;binary_sha256=$kernelOverride.binary_sha256;files=$kernelBuild.inventory.files.Count})
}
if ($clientBuild) {
    # Preserve the legacy immutable extraction check above, then apply only an
    # explicitly verified desktop selection on either supported staging lane.
    $clientOverride = Set-VerifiedClientPayload -ClientBuild $clientBuild -BuildRoot $BuildRoot -Stage $stage -RepackageOnly:$RepackageOnly
    $steps.Add([ordered]@{name='verified-desktop-client';exit_code=0;source_content_sha256=$clientOverride.source_content_sha256;binary_sha256=$clientOverride.binary_sha256;files=$clientBuild.manifest.files.Count})
}

# This generated, PS5-compatible helper is extracted before copying any product files.
# It owns no services; the runtime performs the final exact service-binding check.
$checks = @'
#requires -Version 5.1
param([ValidateSet('Validate','ValidateUninstall','RemoveShortcuts')][string]$Action,[string]$InstallRoot,[string]$StateRoot,[string]$ServiceName)
$ErrorActionPreference='Stop'
try {
    Write-Output ('Preflight raw binary path=['+$InstallRoot+']; state path=['+$StateRoot+']; service=['+$ServiceName+']')
    foreach($name in @('InstallRoot','StateRoot')) {
        $value=Get-Variable -Name $name -ValueOnly
        if($value.Length -ge 2 -and $value.StartsWith('"') -and $value.EndsWith('"')) {Set-Variable -Name $name -Value $value.Substring(1,$value.Length-2)}
    }
    foreach($value in @($InstallRoot,$StateRoot)) { if(-not [IO.Path]::IsPathRooted($value) -or $value.IndexOfAny([char[]]"`"`r`n") -ge 0){throw 'An absolute, ordinary installation and state path is required.'} }
    $InstallRoot=[IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
    $StateRoot=[IO.Path]::GetFullPath($StateRoot).TrimEnd('\')
    foreach($path in @($InstallRoot,$StateRoot)) {
        if($path -eq [IO.Path]::GetPathRoot($path).TrimEnd('\') -or $path -eq $env:WINDIR -or $path -eq $env:ProgramFiles -or $path -eq $env:ProgramData){throw 'A dedicated product directory is required.'}
        $walk=$path
        while($walk -and (Split-Path -Path $walk -Parent)) {
            if(Test-Path -LiteralPath $walk) {if((Get-Item -LiteralPath $walk -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Reparse-point installation and state paths are not supported.'}}
            $walk=Split-Path -Path $walk -Parent
        }
    }
    if($InstallRoot -eq $StateRoot -or $StateRoot.StartsWith($InstallRoot+'\',[StringComparison]::OrdinalIgnoreCase) -or $InstallRoot.StartsWith($StateRoot+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Binary and retained-data directories must be separate.'}
    if($ServiceName -notmatch '^Dragonhydra[A-Za-z0-9_-]{0,60}$'){throw 'Invalid product service name.'}
    $marker=Join-Path $InstallRoot 'workstation\installer.ini'
    $owned=$false
    if(Test-Path -LiteralPath $marker) {
        $ini=@{}
        foreach($line in Get-Content -LiteralPath $marker){if($line -match '^([^=]+)=(.*)$'){$ini[$matches[1]]=$matches[2]}}
        $owned=$ini.Identity -eq 'DRAGONHYDRA Workstation v1' -and $ini.InstallRoot -eq $InstallRoot -and $ini.StateRoot -eq $StateRoot -and $ini.ServiceName -eq $ServiceName
        if(-not $owned){throw 'The existing installation marker belongs to a different deployment.'}
    }
    if($Action -eq 'Validate' -and (Test-Path -LiteralPath $InstallRoot) -and @(Get-ChildItem -LiteralPath $InstallRoot -Force).Count -and -not $owned){throw 'The binary directory is nonempty and is not owned by this workstation installer.'}
    if($Action -ne 'Validate' -and -not $owned){throw 'A matching installer ownership marker is required.'}
    $runtimeMarker=Join-Path $InstallRoot 'workstation-installed.json'
    if(Test-Path -LiteralPath $runtimeMarker){
        $cfg=Get-Content -LiteralPath $runtimeMarker -Raw|ConvertFrom-Json
        if($cfg.install_root -ne $InstallRoot -or $cfg.state_root -ne $StateRoot -or $cfg.service_name -ne $ServiceName -or $cfg.product -ne 'DRAGONHYDRA Workstation'){throw 'Runtime installation ownership does not match.'}
    } elseif($Action -eq 'ValidateUninstall'){throw 'The runtime ownership marker is missing.'}
    $stateConfig=Join-Path $StateRoot 'workstation.json'
    if(Test-Path -LiteralPath $stateConfig){
        $cfg=Get-Content -LiteralPath $stateConfig -Raw|ConvertFrom-Json
        if($cfg.install_root -ne $InstallRoot -or $cfg.state_root -ne $StateRoot -or $cfg.service_name -ne $ServiceName){throw 'Retained state belongs to a different installation.'}
    } elseif((Test-Path -LiteralPath $StateRoot) -and @(Get-ChildItem -LiteralPath $StateRoot -Force).Count){throw 'The retained-data directory is nonempty and unowned.'}
    $suffix=if($ServiceName -eq 'DragonhydraWorkstation'){''}else{' - '+$ServiceName}
    $folder=Join-Path ([Environment]::GetFolderPath('CommonPrograms')) ('DRAGONHYDRA Workstation'+$suffix)
    $links=@((Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) ('DRAGONHYDRA Workstation'+$suffix+'.lnk')),(Join-Path $folder 'DRAGONHYDRA Workstation.lnk'),(Join-Path $folder 'DRAGONHYDRA Administration.lnk'))
    $shell=New-Object -ComObject WScript.Shell
    $target=Join-Path $InstallRoot 'workstation\DragonhydraLauncher.exe'
    foreach($link in $links){if(Test-Path -LiteralPath $link){
        if($shell.CreateShortcut($link).TargetPath -ne $target){if($Action -ne 'RemoveShortcuts'){throw 'An existing shortcut belongs to another application and was not changed.'}}elseif($Action -eq 'RemoveShortcuts'){Remove-Item -LiteralPath $link -Force}
    }}
    if($Action -eq 'RemoveShortcuts' -and (Test-Path -LiteralPath $folder) -and -not @(Get-ChildItem -LiteralPath $folder -Force).Count){Remove-Item -LiteralPath $folder}
    Write-Output 'Workstation ownership and path checks passed.'
    exit 0
} catch {Write-Error $_.Exception.Message;exit 1}
'@
[IO.File]::WriteAllText((Join-Path $stage 'workstation\Installer-Checks.ps1'),$checks,[Text.UTF8Encoding]::new($false))

if (-not $RepackageOnly) {
$prerequisites = Join-Path $BuildRoot 'prerequisites'
New-Item -ItemType Directory -Path $prerequisites | Out-Null
$bootstrapper = Join-Path $prerequisites 'MicrosoftEdgeWebview2Setup.exe'
$bootstrapperUrl = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703'
Invoke-WebRequest -Uri $bootstrapperUrl -OutFile $bootstrapper -TimeoutSec 120
}
$prerequisites = Join-Path $BuildRoot 'prerequisites'
$bootstrapper = Join-Path $prerequisites 'MicrosoftEdgeWebview2Setup.exe'
$bootstrapperUrl = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703'
$signature = Get-AuthenticodeSignature -LiteralPath $bootstrapper
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') { throw 'The official WebView2 bootstrapper did not pass Microsoft Authenticode verification.' }
$sourceFiles = @('scripts\Build-Workstation.ps1','packaging\windows\workstation\KernelBuild.ps1','packaging\windows\workstation\ClientBuild.ps1','packaging\windows\workstation\installer.nsi','packaging\windows\workstation\README.md','packaging\windows\workstation\Workstation.ps1','packaging\windows\workstation\DragonhydraService.cs','packaging\windows\workstation\DragonhydraLauncher.cs','packaging\windows\workstation\DragonhydraAtomicFile.cs','packaging\windows\workstation\Build-Runtime.ps1','packaging\windows\workstation\web\Build-WebPayload.ps1','packaging\windows\workstation\web\prepare_payload.py','packaging\windows\workstation\web\manage.php')
$sourceInventory = @($sourceFiles | ForEach-Object { [ordered]@{path=$_.Replace('\','/');sha256=(Hash (Join-Path $project $_))} })
$buildInfo = [ordered]@{schema_version=1;product='DRAGONHYDRA Workstation';version=$Version;windows_file_version='0.4.1.1';release_state='unsigned_development_build_not_published';wrapper_source='working_tree_file_hashes';wrapper_source_files=$sourceInventory;inner_components=$components;api_namespace='/dragon/api/v1';kernel_schema_version=1;kernel_backend='sqlite';joomla_database='MariaDB';optional_local_ai='not_included';webview2_strategy='reuse existing runtime; official Microsoft online bootstrapper only when missing';webview2_bootstrapper=@{url=$bootstrapperUrl;sha256=(Hash $bootstrapper);bytes=(Get-Item $bootstrapper).Length;signature=$signature.Status.ToString();signer=$signature.SignerCertificate.Subject};platform='Windows 10 or later AMD64';prerequisites=@('.NET Framework 4.8','Internet only when WebView2 is missing')}
$buildInfo['kernel_override'] = $kernelOverride
$buildInfo['client_override'] = $clientOverride
$buildInfo['joomla_frontend_override'] = $joomlaOverride
if ($kernelOverride) {
    foreach ($component in $components) {
        $component['installed_payload'] = -not $component.filename.EndsWith('-Server-win-x64.zip')
        if (-not $component['installed_payload']) { $component['role'] = 'Immutable baseline input; installed server replaced by the separately verified kernel_override' }
    }
}
if ($clientOverride) {
    foreach ($component in $components) {
        if ($component.filename.EndsWith('-Desktop-win-x64-Setup.exe')) {
            $component['installed_payload'] = $false
            $component['role'] = 'Immutable baseline input; installed desktop replaced by the separately verified client_override'
        }
    }
}
if ($joomlaOverride) {
    foreach ($component in $components) {
        if ($component.filename.StartsWith('pkg_dragonhydra-')) {
            $component['installed_payload'] = $false
            $component['role'] = 'Immutable baseline input; installed Joomla replaced by separately identified joomla_frontend_override'
        }
    }
}
WriteJson $buildInfo (Join-Path $stage 'WORKSTATION-BUILD.json')
Copy-Item -LiteralPath (Join-Path $project 'packaging\windows\workstation\README.md') -Destination (Join-Path $stage 'INSTALLATION.md')
$inventory = @(Get-ChildItem -LiteralPath $stage -File -Recurse | Where-Object FullName -NE (Join-Path $stage 'PAYLOAD-MANIFEST.json') | Sort-Object FullName | ForEach-Object {[ordered]@{path=[IO.Path]::GetRelativePath($stage,$_.FullName).Replace('\','/');bytes=$_.Length;sha256=(Hash $_.FullName)}})
WriteJson ([ordered]@{schema_version=1;version=$Version;files=$inventory}) (Join-Path $stage 'PAYLOAD-MANIFEST.json')
$output = Join-Path $OutputRoot ('DRAGONHYDRA-'+$Version+'-Workstation-win-x64-Setup.exe')
if (Test-Path -LiteralPath $output) {
    if (-not $RepackageOnly) { throw 'An existing workstation EXE will not be overwritten. Use a new OutputRoot.' }
    $archive = Join-Path $BuildRoot 'candidates'
    New-Item -ItemType Directory -Path $archive -Force | Out-Null
    $oldHash = Hash $output
    $oldFile = Join-Path $archive ('Setup-'+$oldHash+'.exe')
    if (Test-Path -LiteralPath $oldFile) { throw 'The previous candidate is already archived; inspect the conflicting output before retrying.' }
    Move-Item -LiteralPath $output -Destination $oldFile
}
Native 'build-installer' $MakeNsis @('/V3',('/DSTAGE='+$stage),('/DOUTPUT='+$output),('/DPREREQUISITES='+$prerequisites),('/DVERSION='+$Version),'/DNUMERICVERSION=0.4.1.1',(Join-Path $project 'packaging\windows\workstation\installer.nsi'))
$finalSignature=Get-AuthenticodeSignature -LiteralPath $output
$payloadBytes=[long]0
foreach($entry in $inventory){$payloadBytes += [long]$entry.bytes}
$report=[ordered]@{schema_version=1;built=$true;installed=$false;launched=$false;installation_tested=$false;clean_machine_tested=$false;version=$Version;inner_release_sha=$sourceSha;reused_verified_payload=[bool]$RepackageOnly;refreshed_web_hook=[bool]$RefreshWebHook;started_at=$started.ToString('o');finished_at=[DateTime]::UtcNow.ToString('o');artifact=@{filename=[IO.Path]::GetFileName($output);path=$output;bytes=(Get-Item $output).Length;sha256=(Hash $output);signing_status=$finalSignature.Status.ToString()};source_files=$sourceInventory;payload_files=$inventory.Count;payload_bytes=$payloadBytes;steps=$steps}
$report['kernel_override'] = $kernelOverride
$report['client_override'] = $clientOverride
$report['joomla_frontend_override'] = $joomlaOverride
WriteJson $report (Join-Path $BuildRoot 'BUILD-REPORT.json')
Copy-Item -LiteralPath (Join-Path $BuildRoot 'BUILD-REPORT.json') -Destination (Join-Path $OutputRoot 'BUILD-REPORT.json')
Write-Output ($report|ConvertTo-Json -Depth 4)
