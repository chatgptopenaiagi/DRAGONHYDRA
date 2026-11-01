#requires -Version 7.0
# Read-only validation and scoped staging of a verified desktop build payload.
function Get-VerifiedClientStagingCopy {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Root,[Parameter(Mandatory)][string]$ProjectRoot)
    $ErrorActionPreference = 'Stop'
    $rootPath = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $boundary = Join-Path ([IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')) 'build\connections'
    if (-not $rootPath.StartsWith($boundary+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Client repair staging must remain under build/connections.' }
    $proofFile = Join-Path $rootPath 'CLIENT-REPAIR-STAGING.json'
    if ((Get-Item -LiteralPath $proofFile -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Staging-copy provenance cannot be a link.' }
    $proof = Get-Content -LiteralPath $proofFile -Raw | ConvertFrom-Json
    if ($proof.schema_version -ne 1 -or $proof.purpose -ne 'desktop-client-repair' -or -not [IO.Path]::IsPathRooted($proof.source_build_root) -or $proof.payload_manifest_sha256 -notmatch '^[a-f0-9]{64}$') { throw 'Explicit client staging-copy provenance is required.' }
    $source = [IO.Path]::GetFullPath($proof.source_build_root).TrimEnd('\')
    if (-not $source.StartsWith($boundary+'\',[StringComparison]::OrdinalIgnoreCase) -or $source -eq $rootPath -or $source.StartsWith($rootPath+'\',[StringComparison]::OrdinalIgnoreCase) -or $rootPath.StartsWith($source+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Client repair must use a new separate staging copy.' }
    foreach ($candidate in @((Join-Path $source 'stage\PAYLOAD-MANIFEST.json'),(Join-Path $rootPath 'stage\PAYLOAD-MANIFEST.json'))) {
        if ((Get-Item -LiteralPath $candidate -Force).Attributes -band [IO.FileAttributes]::ReparsePoint -or (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant() -ne $proof.payload_manifest_sha256) { throw 'Client repair staging differs from its recorded original manifest.' }
    }
    $proof
}

function Get-VerifiedClientBuild {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][string]$ProjectRoot,
        [Parameter(Mandatory)][string]$StagingRoot
    )
    $ErrorActionPreference = 'Stop'
    $rootPath = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $projectPath = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
    $stagingPath = [IO.Path]::GetFullPath($StagingRoot).TrimEnd('\')
    $boundary = Join-Path $projectPath 'build\connections'
    if (-not $rootPath.StartsWith($boundary+'\',[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Client build must be a dedicated child of build/connections.'
    }
    if ($rootPath -eq $stagingPath -or $rootPath.StartsWith($stagingPath+'\',[StringComparison]::OrdinalIgnoreCase) -or $stagingPath.StartsWith($rootPath+'\',[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Client build and workstation staging must be separate.'
    }
    $walk = $rootPath
    while ($walk.StartsWith($projectPath+'\',[StringComparison]::OrdinalIgnoreCase)) {
        if (-not (Test-Path -LiteralPath $walk -PathType Container) -or (Get-Item -LiteralPath $walk -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'Client build requires ordinary existing project directories.'
        }
        $walk = Split-Path -Path $walk -Parent
    }
    $manifestFile = Join-Path $rootPath 'CLIENT-BUILD.json'
    if ((Get-Item -LiteralPath $manifestFile -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Client manifest cannot be a link.' }
    $manifest = Get-Content -LiteralPath $manifestFile -Raw | ConvertFrom-Json
    if ($manifest.schema_version -ne 1 -or $manifest.product -ne 'DRAGONHYDRA Client' -or $manifest.version -ne '0.4.0-alpha.1' -or $manifest.architecture -ne 'x86_64-pc-windows-msvc' -or $manifest.api_namespace -ne '/dragon/api/v1' -or $manifest.kernel_schema_version -ne 1 -or $manifest.status -ne 'verified_current_host' -or $manifest.verification.passed -ne $true -or $manifest.source_content_sha256 -notmatch '^[a-f0-9]{64}$') {
        throw 'Client build identity or current-host verification is incompatible.'
    }
    $expected = @('BUILD-INFO.json','DRAGONHYDRA-Client.exe','THIRD-PARTY-NOTICES.txt')
    $entries = @($manifest.files)
    if ($entries.Count -ne $expected.Count -or @($entries.path | Sort-Object -Unique).Count -ne $expected.Count) {
        throw 'Client build must enumerate exactly the three required payload files.'
    }
    foreach ($entry in $entries) {
        if ($entry.path -cnotin $expected -or $entry.sha256 -notmatch '^[a-f0-9]{64}$' -or $entry.bytes -le 0) {
            throw 'Client payload manifest contains an unsupported path or integrity entry.'
        }
        $file = Join-Path $rootPath $entry.path
        $item = Get-Item -LiteralPath $file -Force
        if ($item.PSIsContainer -or $item.Attributes -band [IO.FileAttributes]::ReparsePoint -or $item.Length -ne $entry.bytes -or (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256) {
            throw ('Client payload integrity failed: '+$entry.path)
        }
    }
    if (@(Get-ChildItem -LiteralPath $rootPath -Force).Count -ne 4) { throw 'Unexpected files or directories exist in the client build payload.' }
    $identity = Get-Content -LiteralPath (Join-Path $rootPath 'BUILD-INFO.json') -Raw | ConvertFrom-Json
    if ($identity.version -ne $manifest.version -or $identity.api_namespace -ne $manifest.api_namespace -or $identity.schema_version -ne $manifest.kernel_schema_version -or $identity.architecture -ne $manifest.architecture -or $identity.source_content_sha256 -ne $manifest.source_content_sha256) {
        throw 'Client embedded metadata sidecar differs from its verified build identity.'
    }
    [pscustomobject]@{root=$rootPath;manifest=$manifest;manifest_sha256=(Get-FileHash -LiteralPath $manifestFile -Algorithm SHA256).Hash.ToLowerInvariant();identity=$identity;
        project_root=$projectPath;staging_root=$stagingPath;staging_was_new=(-not (Test-Path -LiteralPath $stagingPath))}
}

function Set-VerifiedClientPayload {
    [CmdletBinding()]
    param([Parameter(Mandatory)]$ClientBuild,[Parameter(Mandatory)][string]$BuildRoot,
          [Parameter(Mandatory)][string]$Stage,[switch]$RepackageOnly)
    $ErrorActionPreference = 'Stop'
    $buildPath = [IO.Path]::GetFullPath($BuildRoot).TrimEnd('\')
    $stagePath = [IO.Path]::GetFullPath($Stage).TrimEnd('\')
    $projectPath = [IO.Path]::GetFullPath($ClientBuild.project_root).TrimEnd('\')
    $boundary = Join-Path $projectPath 'build\connections'
    $clientTarget = Join-Path $stagePath 'client'
    if (-not $buildPath.StartsWith($boundary+'\',[StringComparison]::OrdinalIgnoreCase) -or $buildPath -ne $ClientBuild.staging_root -or $stagePath -ne (Join-Path $buildPath 'stage')) { throw 'Client payload staging must target its exact owned build/connections stage.' }
    $stagingCopy = $null
    if ($RepackageOnly) {
        $stagingCopy = Get-VerifiedClientStagingCopy -Root $buildPath -ProjectRoot $projectPath
    } elseif (-not $ClientBuild.staging_was_new) {
        throw 'Fresh client staging requires a new build root validated before creation.'
    }
    # Fresh workstation preparation can take time. Recheck the immutable source
    # receipt and all three payload files immediately before replacing bytes.
    $currentBuild = Get-VerifiedClientBuild -Root $ClientBuild.root -ProjectRoot $projectPath -StagingRoot $buildPath
    if ($currentBuild.manifest_sha256 -ne $ClientBuild.manifest_sha256) { throw 'Client build receipt changed after its initial validation.' }
    $walk = $clientTarget
    while ($walk.StartsWith($projectPath+'\',[StringComparison]::OrdinalIgnoreCase)) {
        if (-not (Test-Path -LiteralPath $walk -PathType Container) -or (Get-Item -LiteralPath $walk -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'The verified client staging directory is unavailable or linked.' }
        $walk = Split-Path -Path $walk -Parent
    }
    foreach ($entry in $ClientBuild.manifest.files) {
        $targetFile = Join-Path $clientTarget $entry.path
        if ((Test-Path -LiteralPath $targetFile) -and ((Get-Item -LiteralPath $targetFile -Force).Attributes -band [IO.FileAttributes]::ReparsePoint -or (Get-Item -LiteralPath $targetFile -Force).PSIsContainer)) { throw 'A client staging target is linked or not a file.' }
        Copy-Item -LiteralPath (Join-Path $ClientBuild.root $entry.path) -Destination $targetFile -Force
        if ((Get-FileHash -LiteralPath $targetFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256 -or (Get-Item -LiteralPath $targetFile).Length -ne $entry.bytes) { throw 'Client payload changed during staging.' }
    }
    [ordered]@{version=$ClientBuild.manifest.version;architecture=$ClientBuild.manifest.architecture;
        source_content_sha256=$ClientBuild.manifest.source_content_sha256;
        binary_sha256=(Get-FileHash -LiteralPath (Join-Path $clientTarget 'DRAGONHYDRA-Client.exe') -Algorithm SHA256).Hash.ToLowerInvariant();
        build_manifest_sha256=$ClientBuild.manifest_sha256;
        baseline_staging=$(if($stagingCopy){$stagingCopy.source_build_root}else{$null});
        baseline_payload_manifest_sha256=$(if($stagingCopy){$stagingCopy.payload_manifest_sha256}else{$null});
        staging_mode=$(if($RepackageOnly){'verified_repackage_copy'}else{'fresh_owned_build'});
        verification='Verified current-host desktop payload; exact source/payload hashes in CLIENT-BUILD.json; no clean-machine claim'}
}
