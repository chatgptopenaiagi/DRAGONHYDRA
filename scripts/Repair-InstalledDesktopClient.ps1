#requires -Version 7.0
[CmdletBinding()]
param(
    [string]$ClientBuildRoot,
    [string]$ExpectedClientManifestSha256,
    [string]$BackupRoot,
    [switch]$Apply
)

function Get-RepairFileHash([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
}

function Write-RepairJson($Value,[string]$Path) {
    [IO.File]::WriteAllText($Path,($Value | ConvertTo-Json -Depth 30),[Text.UTF8Encoding]::new($false))
}

function Get-RepairAccessPolicy([string]$Path) {
    $acl = Get-Acl -LiteralPath $Path
    # ReplaceFile can normalize the informational DACL auto-inherited flag.
    # Compare the actual owner/group, inheritance protection and ordered ACEs.
    $rules = @($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]) | ForEach-Object {
        [ordered]@{sid=$_.IdentityReference.Value;rights=[long]$_.FileSystemRights;type=[int]$_.AccessControlType;
            inherited=$_.IsInherited;inheritance=[int]$_.InheritanceFlags;propagation=[int]$_.PropagationFlags}
    })
    [ordered]@{owner=$acl.GetOwner([Security.Principal.SecurityIdentifier]).Value;
        group=$acl.GetGroup([Security.Principal.SecurityIdentifier]).Value;protected=$acl.AreAccessRulesProtected;rules=$rules} | ConvertTo-Json -Depth 5 -Compress
}

function Get-RepairServices {
    $names = @('DragonhydraProvidersA2Test','DragonhydraWorkstation','DragonhydraWorkstationTest')
    $services = @(Get-CimInstance Win32_Service -ErrorAction Stop | Where-Object {$_.Name -in $names} | Sort-Object Name | Select-Object Name,State,ProcessId,PathName)
    if ($services.Count -ne $names.Count) { throw 'EXPECTED_SERVICE_OBSERVATION_UNAVAILABLE' }
    $services
}

function Assert-NoInstalledDesktopProcess([string]$InstallRoot) {
    $target = Join-Path $InstallRoot 'client\DRAGONHYDRA-Client.exe'
    foreach ($process in @(Get-CimInstance Win32_Process -Filter "Name='DRAGONHYDRA-Client.exe'" -ErrorAction Stop)) {
        if (-not $process.ExecutablePath) { throw 'CLIENT_PROCESS_OWNERSHIP_UNAVAILABLE' }
        if ([IO.Path]::GetFullPath($process.ExecutablePath) -eq $target) { throw 'CLOSE_INSTALLED_CLIENT_BEFORE_REPAIR' }
    }
}

function Set-RepairFileAtomic([string]$Source,[string]$Destination) {
    $temporary = Join-Path (Split-Path -Path $Destination -Parent) ('.desktop-repair-'+[Guid]::NewGuid().ToString('N')+'.tmp')
    try {
        [IO.File]::Copy($Source,$temporary,$false)
        [IO.File]::Replace($temporary,$Destination,[System.Management.Automation.Language.NullString]::Value)
    } finally {
        if (Test-Path -LiteralPath $temporary -PathType Leaf) { Remove-Item -LiteralPath $temporary -Force }
    }
}

function Invoke-DesktopClientRepairTransaction {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$InstallRoot,[Parameter(Mandatory)]$ClientBuild,
          [Parameter(Mandatory)][string]$BackupRoot,[switch]$Apply)
    $ErrorActionPreference = 'Stop'
    $payloadNames = @('client/BUILD-INFO.json','client/DRAGONHYDRA-Client.exe','client/THIRD-PARTY-NOTICES.txt')
    $metadataNames = @('WORKSTATION-BUILD.json','PAYLOAD-MANIFEST.json')
    $names = $payloadNames + $metadataNames
    $result = [ordered]@{schema_version=1;passed=$false;applied=$false;phase='preflight';target=$InstallRoot;
        source_manifest_sha256=$ClientBuild.manifest_sha256;backup_root=$BackupRoot;
        services_controlled=$false;state_data_or_vault_accessed=$false;files_replaced=@();rollback=$null}
    $replaced = [Collections.Generic.List[string]]::new()
    $originals = @{}
    $originalAcls = @{}
    try {
        if (Test-Path -LiteralPath $BackupRoot) { throw 'FRESH_BACKUP_ROOT_REQUIRED' }
        Assert-NoInstalledDesktopProcess $InstallRoot
        $beforeServices = @(Get-RepairServices)
        $result.services_before = $beforeServices
        $inventoryPath = Join-Path $InstallRoot 'PAYLOAD-MANIFEST.json'
        $inventory = Get-Content -LiteralPath $inventoryPath -Raw | ConvertFrom-Json
        $buildInfo = Get-Content -LiteralPath (Join-Path $InstallRoot 'WORKSTATION-BUILD.json') -Raw | ConvertFrom-Json
        if ($inventory.schema_version -ne 1 -or $inventory.version -ne '0.4.1-dev.1' -or $buildInfo.product -ne 'DRAGONHYDRA Workstation' -or $buildInfo.version -ne $inventory.version -or $buildInfo.api_namespace -ne '/dragon/api/v1' -or $buildInfo.kernel_schema_version -ne 1) { throw 'INSTALLED_WORKSTATION_IDENTITY_MISMATCH' }
        $changedManifestNames = $payloadNames + @('WORKSTATION-BUILD.json')
        foreach ($name in $names) {
            $file = Join-Path $InstallRoot $name
            $item = Get-Item -LiteralPath $file -Force
            if ($item.PSIsContainer -or $item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'INSTALLED_REPAIR_FILE_IS_NOT_ORDINARY' }
            $originals[$name] = [ordered]@{bytes=$item.Length;sha256=(Get-RepairFileHash $file)}
            $originalAcls[$name] = Get-RepairAccessPolicy $file
            if ($name -ne 'PAYLOAD-MANIFEST.json') {
                $entries = @($inventory.files | Where-Object path -CEQ $name)
                if ($entries.Count -ne 1 -or $entries[0].bytes -ne $item.Length -or $entries[0].sha256 -ne $originals[$name].sha256) { throw ('INSTALLED_MANIFEST_INTEGRITY_FAILED: '+$name) }
            }
        }
        $result.original_files = $originals
        $result.source_content_sha256 = $ClientBuild.manifest.source_content_sha256
        if (-not $Apply) {
            $result.passed = $true
            $result.status = 'validated_not_applied'
            return [pscustomobject]$result
        }
        New-Item -ItemType Directory -Path $BackupRoot | Out-Null
        $backup = Join-Path $BackupRoot 'original'
        $prepared = Join-Path $BackupRoot 'prepared'
        New-Item -ItemType Directory -Path (Join-Path $backup 'client'),(Join-Path $prepared 'client') -Force | Out-Null
        foreach ($name in $names) {
            Copy-Item -LiteralPath (Join-Path $InstallRoot $name) -Destination (Join-Path $backup $name)
            if ((Get-RepairFileHash (Join-Path $backup $name)) -ne $originals[$name].sha256) { throw 'BACKUP_VERIFICATION_FAILED' }
        }
        foreach ($entry in $ClientBuild.manifest.files) {
            $preparedFile = Join-Path $prepared ('client/'+$entry.path)
            Copy-Item -LiteralPath (Join-Path $ClientBuild.root $entry.path) -Destination $preparedFile
            if ((Get-RepairFileHash $preparedFile) -ne $entry.sha256 -or (Get-Item -LiteralPath $preparedFile).Length -ne $entry.bytes) { throw 'CLIENT_SOURCE_CHANGED_DURING_PREPARATION' }
        }
        $override = [ordered]@{version=$ClientBuild.manifest.version;architecture=$ClientBuild.manifest.architecture;
            source_content_sha256=$ClientBuild.manifest.source_content_sha256;
            binary_sha256=(Get-RepairFileHash (Join-Path $prepared 'client/DRAGONHYDRA-Client.exe'));
            build_manifest_sha256=$ClientBuild.manifest_sha256;
            verification='Verified desktop client-only repair; existing server, services and application state preserved';
            installed_at=[DateTime]::UtcNow.ToString('o');backup_root=$BackupRoot}
        $buildInfo | Add-Member -NotePropertyName client_override -NotePropertyValue $override -Force
        foreach ($component in $buildInfo.inner_components) {
            if ($component.filename.EndsWith('-Desktop-win-x64-Setup.exe')) {
                $component | Add-Member -NotePropertyName installed_payload -NotePropertyValue $false -Force
                $component | Add-Member -NotePropertyName role -NotePropertyValue 'Immutable baseline input; installed desktop replaced by verified client_override' -Force
            }
        }
        Write-RepairJson $buildInfo (Join-Path $prepared 'WORKSTATION-BUILD.json')
        foreach ($name in $changedManifestNames) {
            $entry = @($inventory.files | Where-Object path -CEQ $name)[0]
            $entry.bytes = (Get-Item -LiteralPath (Join-Path $prepared $name)).Length
            $entry.sha256 = Get-RepairFileHash (Join-Path $prepared $name)
        }
        Write-RepairJson $inventory (Join-Path $prepared 'PAYLOAD-MANIFEST.json')
        # Recheck immediately before the first write; no process is terminated.
        Assert-NoInstalledDesktopProcess $InstallRoot
        $result.phase = 'apply'
        foreach ($name in $names) {
            $destination = Join-Path $InstallRoot $name
            if ((Get-RepairFileHash $destination) -ne $originals[$name].sha256) { throw 'INSTALLED_FILE_CHANGED_CONCURRENTLY' }
            Set-RepairFileAtomic -Source (Join-Path $prepared $name) -Destination $destination
            $replaced.Add($name)
            $actualHash = Get-RepairFileHash $destination
            $expectedHash = Get-RepairFileHash (Join-Path $prepared $name)
            $actualAcl = Get-RepairAccessPolicy $destination
            if ($actualHash -ne $expectedHash -or $actualAcl -ne $originalAcls[$name]) {
                $result.replacement_failure = [ordered]@{path=$name;hash_matches=($actualHash -eq $expectedHash);acl_matches=($actualAcl -eq $originalAcls[$name]);original_acl=$originalAcls[$name];actual_acl=$actualAcl}
                throw 'INSTALLED_REPLACEMENT_VERIFICATION_FAILED'
            }
        }
        $afterServices = @(Get-RepairServices)
        $result.services_after = $afterServices
        if (($beforeServices | ConvertTo-Json -Depth 5 -Compress) -ne ($afterServices | ConvertTo-Json -Depth 5 -Compress)) { throw 'SERVICE_STATE_CHANGED_DURING_REPAIR' }
        $result.files_replaced = @($replaced)
        $result.passed = $true
        $result.applied = $true
        $result.status = 'client_repaired_services_unchanged'
    } catch {
        $result.error = $_.Exception.Message
        $result.files_replaced = @($replaced)
        if ($replaced.Count) {
            $rollbackErrors = [Collections.Generic.List[string]]::new()
            for ($index=$replaced.Count-1;$index -ge 0;$index--) {
                $name = $replaced[$index]
                try {
                    Set-RepairFileAtomic -Source (Join-Path (Join-Path $BackupRoot 'original') $name) -Destination (Join-Path $InstallRoot $name)
                    if ((Get-RepairFileHash (Join-Path $InstallRoot $name)) -ne $originals[$name].sha256 -or (Get-RepairAccessPolicy (Join-Path $InstallRoot $name)) -ne $originalAcls[$name]) { throw 'Rollback verification failed' }
                } catch { $rollbackErrors.Add($name+': '+$_.Exception.Message) }
            }
            $result.rollback = [ordered]@{attempted=$true;passed=($rollbackErrors.Count -eq 0);errors=@($rollbackErrors)}
        }
        $result.status = 'repair_failed'
    }
    if (Test-Path -LiteralPath $BackupRoot -PathType Container) { Write-RepairJson $result (Join-Path $BackupRoot 'repair-result.json') }
    [pscustomobject]$result
}

if ($MyInvocation.InvocationName -eq '.') { return }
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    $project = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
    if ($project -ne 'C:\xampp\DRAGONHYDRA') { throw 'EXACT_WORKSPACE_REQUIRED' }
    $target = Join-Path $project 'build\workstation\test-install\provider-a2\application files'
    if (-not $ClientBuildRoot -or $ExpectedClientManifestSha256 -notmatch '^[a-f0-9]{64}$' -or -not $BackupRoot) { throw 'EXPLICIT_SOURCE_MANIFEST_HASH_AND_FRESH_BACKUP_REQUIRED' }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $isAdmin = ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($Apply -and -not $isAdmin) { throw 'ADMINISTRATOR_TOKEN_REQUIRED_FOR_INSTALLED_CLIENT_REPAIR' }
    $BackupRoot = [IO.Path]::GetFullPath($BackupRoot).TrimEnd('\')
    if (-not $BackupRoot.StartsWith((Join-Path $project 'build\connections')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'BACKUP_MUST_BE_A_NEW_BUILD_CONNECTIONS_CHILD' }
    foreach ($directory in @($target,(Join-Path $target 'client'),(Split-Path -Path $BackupRoot -Parent))) {
        $walk = $directory
        while ($walk.StartsWith($project+'\',[StringComparison]::OrdinalIgnoreCase)) {
            if (-not (Test-Path -LiteralPath $walk -PathType Container) -or (Get-Item -LiteralPath $walk -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'ORDINARY_EXISTING_PROJECT_DIRECTORIES_REQUIRED' }
            $walk = Split-Path -Path $walk -Parent
        }
    }
    $marker = @{}
    foreach ($line in Get-Content -LiteralPath (Join-Path $target 'workstation\installer.ini')) { if ($line -match '^([^=]+)=(.*)$') { $marker[$matches[1]] = $matches[2] } }
    if ($marker.Identity -ne 'DRAGONHYDRA Workstation v1' -or $marker.InstallRoot -ne $target -or $marker.ServiceName -ne 'DragonhydraProvidersA2Test') { throw 'EXACT_INSTALLED_WORKSTATION_OWNERSHIP_REQUIRED' }
    . (Join-Path $project 'packaging\windows\workstation\ClientBuild.ps1')
    if ((Get-RepairFileHash (Join-Path $ClientBuildRoot 'CLIENT-BUILD.json')) -ne $ExpectedClientManifestSha256) { throw 'CLIENT_BUILD_MANIFEST_HASH_MISMATCH' }
    $source = Get-VerifiedClientBuild -Root $ClientBuildRoot -ProjectRoot $project -StagingRoot $target
    if ($BackupRoot -eq $source.root -or $BackupRoot.StartsWith($source.root+'\',[StringComparison]::OrdinalIgnoreCase) -or $source.root.StartsWith($BackupRoot+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'BACKUP_AND_CLIENT_SOURCE_MUST_BE_SEPARATE' }
    $result = Invoke-DesktopClientRepairTransaction -InstallRoot $target -ClientBuild $source -BackupRoot $BackupRoot -Apply:$Apply
    $result | Add-Member -NotePropertyName administrator_token -NotePropertyValue $isAdmin
    $result | ConvertTo-Json -Depth 30
    if (-not $result.passed) { exit 1 }
} catch {
    [ordered]@{passed=$false;applied=$false;error=$_.Exception.Message;services_controlled=$false;state_data_or_vault_accessed=$false} | ConvertTo-Json
    exit 1
}
