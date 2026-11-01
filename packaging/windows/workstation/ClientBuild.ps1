#requires -Version 7.0
# Read-only validation of an explicitly verified replacement desktop payload.
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
    [pscustomobject]@{root=$rootPath;manifest=$manifest;manifest_sha256=(Get-FileHash -LiteralPath $manifestFile -Algorithm SHA256).Hash.ToLowerInvariant();identity=$identity}
}
