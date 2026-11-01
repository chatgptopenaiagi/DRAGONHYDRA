#requires -Version 7.0
# Validate existing build receipts and stage an explicitly selected private kernel.
# Validation never executes a binary, submits HTTP, or operates a service.
function Get-KernelFileHash([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Assert-KernelOrdinaryPath([string]$Path,[string]$Boundary) {
    $walk = [IO.Path]::GetFullPath($Path)
    $boundaryPath = [IO.Path]::GetFullPath($Boundary).TrimEnd('\')
    if (-not $walk.StartsWith($boundaryPath+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Kernel input escaped its owned boundary.' }
    while ($walk.StartsWith($boundaryPath+'\',[StringComparison]::OrdinalIgnoreCase)) {
        if ((Test-Path -LiteralPath $walk) -and ((Get-Item -LiteralPath $walk -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Kernel inputs and staging paths cannot contain reparse points.' }
        $walk = Split-Path -Path $walk -Parent
    }
}
function Read-KernelBuildJson([string]$Path,[string]$Boundary,[long]$Limit=8388608) {
    Assert-KernelOrdinaryPath $Path $Boundary
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.PSIsContainer -or $item.Length -gt $Limit) { throw 'Kernel build receipt is missing, oversized or not a file.' }
    Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}
function Get-VerifiedKernelBuild {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Root,[Parameter(Mandatory)][string]$ProjectRoot,
          [Parameter(Mandatory)][string]$StagingRoot)
    $ErrorActionPreference = 'Stop'
    $rootPath = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $projectPath = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
    $stagingPath = [IO.Path]::GetFullPath($StagingRoot).TrimEnd('\')
    if (-not $rootPath.StartsWith($projectPath+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'The verified kernel build must remain inside the project.' }
    if (-not $stagingPath.StartsWith((Join-Path $projectPath 'build\connections')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Kernel staging must remain in a dedicated build/connections directory.' }
    if ($rootPath -eq $stagingPath -or $rootPath.StartsWith($stagingPath+'\',[StringComparison]::OrdinalIgnoreCase) -or $stagingPath.StartsWith($rootPath+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Kernel build and workstation staging must be separate.' }
    Assert-KernelOrdinaryPath $rootPath $projectPath
    Assert-KernelOrdinaryPath $stagingPath $projectPath
    $report = Read-KernelBuildJson (Join-Path $rootPath 'BUILD-REPORT.json') $rootPath
    $inventoryPath = Join-Path $rootPath 'PAYLOAD-MANIFEST.json'
    $inventory = Read-KernelBuildJson $inventoryPath $rootPath
    $payload = [IO.Path]::GetFullPath($report.payload).TrimEnd('\')
    if ($report.schema_version -ne 1 -or $inventory.schema_version -ne 1 -or $report.status -ne 'verified_current_host' -or -not $payload.StartsWith($rootPath+'\',[StringComparison]::OrdinalIgnoreCase) -or $report.source_content_sha256 -notmatch '^[a-f0-9]{64}$') { throw 'The kernel override is not a verified, owned private-runtime distribution.' }
    Assert-KernelOrdinaryPath $payload $rootPath
    $entries = @($inventory.files)
    if (-not $entries.Count -or @($entries.path | Sort-Object -Unique).Count -ne $entries.Count) { throw 'The kernel inventory is empty or contains duplicate paths.' }
    foreach ($entry in $entries) {
        if (-not $entry.path -or [IO.Path]::IsPathRooted($entry.path) -or $entry.path -match '(^|[/\\])\.\.([/\\]|$)|[:\r\n]' -or $entry.sha256 -notmatch '^[a-f0-9]{64}$' -or $entry.bytes -lt 0) { throw 'The kernel inventory contains an unsupported path or integrity entry.' }
        $file = [IO.Path]::GetFullPath((Join-Path $payload $entry.path))
        Assert-KernelOrdinaryPath $file $payload
        $item = Get-Item -LiteralPath $file -Force
        if ($item.PSIsContainer -or (Get-KernelFileHash $file) -ne $entry.sha256 -or $item.Length -ne $entry.bytes) { throw "Kernel payload integrity failed: $($entry.path)" }
    }
    if (@(Get-ChildItem -LiteralPath $payload -File -Recurse -Force).Count -ne $entries.Count) { throw 'The private kernel contains unexpected files.' }
    foreach ($name in @('DRAGONHYDRA-Server.exe','BUILD-INFO.json','SOURCE-MANIFEST.json')) {
        if (@($entries | Where-Object path -CEQ $name).Count -ne 1) { throw "The verified kernel inventory is missing $name." }
    }
    $metadata = Read-KernelBuildJson (Join-Path $payload 'BUILD-INFO.json') $payload
    $source = Read-KernelBuildJson (Join-Path $payload 'SOURCE-MANIFEST.json') $payload
    $binary = Join-Path $payload 'DRAGONHYDRA-Server.exe'
    if ($metadata.api_namespace -ne '/dragon/api/v1' -or $metadata.schema_version -ne 1 -or $metadata.source_content_sha256 -ne $report.source_content_sha256 -or $source.schema_version -ne 1 -or $source.content_sha256 -ne $report.source_content_sha256 -or $report.binary_sha256 -ne (Get-KernelFileHash $binary)) { throw 'The kernel metadata has an incompatible API, binary or source identity.' }
    [pscustomobject]@{root=$rootPath;payload=$payload;report=$report;inventory=$inventory;staging_root=$stagingPath;
        metadata=$metadata;binary=$binary;manifest_sha256=(Get-KernelFileHash $inventoryPath)}
}
function Assert-FrontendKernelCompatibility {
    [CmdletBinding()]
    param([AllowNull()][string]$FrontendVersion,[AllowNull()]$KernelBuild,
          [AllowNull()]$InheritedOverride,[string]$Stage,[string]$ProjectRoot,[string]$StagingRoot)
    $ErrorActionPreference = 'Stop'
    if (-not $FrontendVersion -or $FrontendVersion -in @('0.4.0-alpha.1','0.4.1-dev.1','0.4.1-dev.2')) { return $null }
    if ($FrontendVersion -ne '0.4.1-dev.3') { throw 'Unknown Joomla frontend/kernel compatibility contract.' }
    if (-not $KernelBuild) {
        if (-not $InheritedOverride -or -not ($InheritedOverride.PSObject.Properties.Name -contains 'registry_verification') -or -not $InheritedOverride.registry_verification) { throw 'Joomla 0.4.1-dev.3 requires an explicit verified registry-capable -KernelBuildRoot or a matching persisted staged proof.' }
        $recorded = $InheritedOverride.registry_verification
        if (-not ($recorded.PSObject.Properties.Name -contains 'kernel_build_root')) { throw 'Inherited kernel verification is missing its bound build root.' }
        $verified = Get-VerifiedKernelBuild -Root $recorded.kernel_build_root -ProjectRoot $ProjectRoot -StagingRoot $StagingRoot
        $current = Assert-FrontendKernelCompatibility -FrontendVersion $FrontendVersion -KernelBuild $verified
        foreach ($key in @('schema_version','proof','proof_sha256','binary_sha256','source_content_sha256','module_count','payload_manifest_sha256')) {
            if (-not ($recorded.PSObject.Properties.Name -contains $key) -or $recorded.$key -ne $current[$key]) { throw 'Inherited kernel registry proof differs from its current bound receipt.' }
        }
        $stagePath = [IO.Path]::GetFullPath($Stage).TrimEnd('\')
        if ($stagePath -ne (Join-Path ([IO.Path]::GetFullPath($StagingRoot).TrimEnd('\')) 'stage')) { throw 'Inherited kernel staging path is not the exact owned stage.' }
        foreach ($entry in $verified.inventory.files) {
            $file = [IO.Path]::GetFullPath((Join-Path (Join-Path $stagePath 'server') $entry.path))
            Assert-KernelOrdinaryPath $file $stagePath
            if ((Get-KernelFileHash $file) -ne $entry.sha256 -or (Get-Item -LiteralPath $file).Length -ne $entry.bytes) { throw 'Inherited staged kernel differs from its registry-capable verified payload.' }
        }
        if ($InheritedOverride.binary_sha256 -ne $current.binary_sha256 -or $InheritedOverride.source_content_sha256 -ne $current.source_content_sha256) { throw 'Inherited kernel override identity differs from its proof.' }
        return $current
    }
    $proofPath = Join-Path $KernelBuild.root 'system-control-check\system-control-frozen.json'
    $proof = Read-KernelBuildJson $proofPath $KernelBuild.root 1048576
    if ($proof.schema_version -ne 1 -or $proof.passed -isnot [bool] -or -not $proof.passed -or $proof.source_content_sha256 -ne $KernelBuild.metadata.source_content_sha256 -or $proof.binary_sha256 -ne (Get-KernelFileHash $KernelBuild.binary) -or [IO.Path]::GetFullPath($proof.binary) -ne $KernelBuild.binary) { throw 'Registry-capable kernel proof has incompatible verification, schema, binary or source identity.' }
    $checks = @($proof.checks | Where-Object id -CEQ 'authenticated-passive-registry-before-memory')
    if ($checks.Count -ne 1 -or $checks[0].status -cne 'PASS' -or $checks[0].modules -ne 18) { throw 'Registry-capable kernel proof must verify exactly 18 authenticated passive modules.' }
    [ordered]@{schema_version=1;proof='system-control-check/system-control-frozen.json';
        proof_sha256=(Get-KernelFileHash $proofPath);binary_sha256=$proof.binary_sha256;
        source_content_sha256=$proof.source_content_sha256;module_count=18;
        kernel_build_root=$KernelBuild.root;payload_manifest_sha256=$KernelBuild.manifest_sha256;
        verification='Existing frozen-binary receipt verified; package builder did not execute software or HTTP checks'}
}
function Set-VerifiedKernelPayload {
    [CmdletBinding()]
    param([Parameter(Mandatory)]$KernelBuild,[Parameter(Mandatory)][string]$BuildRoot,
          [Parameter(Mandatory)][string]$Stage,[AllowNull()]$RegistryProof)
    $ErrorActionPreference = 'Stop'
    $buildPath = [IO.Path]::GetFullPath($BuildRoot).TrimEnd('\')
    $stagePath = [IO.Path]::GetFullPath($Stage).TrimEnd('\')
    $target = [IO.Path]::GetFullPath((Join-Path $stagePath 'server'))
    if ($buildPath -ne $KernelBuild.staging_root -or $stagePath -ne (Join-Path $buildPath 'stage') -or $target -ne ($stagePath+'\server') -or -not $target.StartsWith($buildPath+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'The owned server staging path escaped its verified build directory.' }
    Assert-KernelOrdinaryPath $target $buildPath
    foreach ($entry in Get-ChildItem -LiteralPath $target -Recurse -Force) {
        if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'The existing server staging tree contains a reparse point.' }
    }
    $noticeBytes = $null
    $noticeSource = Join-Path $target 'THIRD-PARTY-NOTICES.txt'
    if (-not (Test-Path -LiteralPath (Join-Path $KernelBuild.payload 'THIRD-PARTY-NOTICES.txt'))) {
        if (-not (Test-Path -LiteralPath $noticeSource -PathType Leaf)) { throw 'The verified baseline runtime notices are missing.' }
        $noticeBytes = [IO.File]::ReadAllBytes($noticeSource)
    }
    # The exact absolute target above is checked before this scoped replacement.
    Remove-Item -LiteralPath $target -Recurse -Force
    Copy-Item -LiteralPath $KernelBuild.payload -Destination $target -Recurse
    if ($noticeBytes) { [IO.File]::WriteAllBytes((Join-Path $target 'THIRD-PARTY-NOTICES.txt'),$noticeBytes) }
    foreach ($entry in $KernelBuild.inventory.files) {
        $file = Join-Path $target $entry.path
        if ((Get-KernelFileHash $file) -ne $entry.sha256 -or (Get-Item -LiteralPath $file).Length -ne $entry.bytes) { throw 'Kernel payload changed during staging.' }
    }
    $metadata = $KernelBuild.metadata
    [ordered]@{version=$metadata.version;build_kind=$metadata.build_kind;source_sha=$metadata.source_sha;
        source_content_sha256=$metadata.source_content_sha256;binary_sha256=(Get-KernelFileHash (Join-Path $target 'DRAGONHYDRA-Server.exe'));
        payload_manifest_sha256=$KernelBuild.manifest_sha256;source_manifest='server/SOURCE-MANIFEST.json';
        upstream_notices_sha256=(Get-KernelFileHash (Join-Path $target 'THIRD-PARTY-NOTICES.txt'));
        registry_verification=$RegistryProof;verification='private-runtime current-host smoke checks; no clean-machine claim'}
}
