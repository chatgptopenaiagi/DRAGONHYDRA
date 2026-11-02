# Pure same-profile metadata transition. Installer identity guards stay strict.
function New-CoreNextUpgradeMetadata {
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Profile,[Parameter(Mandatory)]$Config,
          [Parameter(Mandatory)][string]$ExpectedInstallationId,
          [Parameter(Mandatory)][string]$FromSource,[Parameter(Mandatory)][string]$FromVersion,
          [Parameter(Mandatory)][string]$ToSource,[Parameter(Mandatory)][string]$ToVersion,
          [Parameter(Mandatory)][string]$BuildId)
    $null=Assert-CoreNextProfile $Profile
    Assert-CoreNextConfig $Config $Profile
    if($Profile.environment_id -cne 'candidate' -or $Profile.installation_id -cne $ExpectedInstallationId){throw 'CORE_NEXT_UPGRADE_TARGET_MISMATCH'}
    if($FromSource -cnotmatch '^[a-f0-9]{40}$' -or $ToSource -cnotmatch '^[a-f0-9]{40}$' -or $FromSource -ceq $ToSource){throw 'CORE_NEXT_UPGRADE_SOURCE_REQUIRED'}
    if($FromVersion -cnotmatch '^(\d+)\.(\d+)\.(\d+)-dev\.(\d+)$'){throw 'CORE_NEXT_UPGRADE_DEVELOPMENT_VERSION_REQUIRED'}
    $oldNumbers=@([int]$Matches[1],[int]$Matches[2],[int]$Matches[3],[int]$Matches[4])
    if($ToVersion -cnotmatch '^(\d+)\.(\d+)\.(\d+)-dev\.(\d+)$'){throw 'CORE_NEXT_UPGRADE_DEVELOPMENT_VERSION_REQUIRED'}
    $newNumbers=@([int]$Matches[1],[int]$Matches[2],[int]$Matches[3],[int]$Matches[4])
    if($oldNumbers[0] -ne $newNumbers[0] -or $oldNumbers[1] -ne $newNumbers[1] -or $oldNumbers[2] -ne $newNumbers[2] -or $newNumbers[3] -ne $oldNumbers[3]+1){throw 'CORE_NEXT_UPGRADE_NEXT_INCREMENT_REQUIRED'}
    if($Profile.source_commit -cne $FromSource -or $Profile.version -cne $FromVersion -or $Config.source_commit -cne $FromSource -or $Config.version -cne $FromVersion -or $Config.product_version -cne $FromVersion){throw 'CORE_NEXT_UPGRADE_OLD_BINDING_MISMATCH'}
    if($BuildId -cnotmatch '^[A-Za-z0-9._-]{1,100}$'){throw 'CORE_NEXT_UPGRADE_BUILD_ID_REQUIRED'}
    $nextProfile=$Profile|ConvertTo-Json -Depth 30|ConvertFrom-Json
    $nextConfig=$Config|ConvertTo-Json -Depth 30|ConvertFrom-Json
    foreach($value in @($nextProfile,$nextConfig)){$value.source_commit=$ToSource;$value.version=$ToVersion;$value.build_id=$BuildId}
    $nextConfig.product_version=$ToVersion
    $null=Assert-CoreNextProfile $nextProfile
    Assert-CoreNextConfig $nextConfig $nextProfile
    [pscustomobject]@{profile=$nextProfile;config=$nextConfig;
        original_profile_fingerprint=(Get-CoreNextMetadataFingerprint $Profile);
        original_config_fingerprint=(Get-CoreNextMetadataFingerprint $Config)}
}

function Get-CoreNextBytesFingerprint([byte[]]$Bytes) {
    $algorithm=[Security.Cryptography.SHA256]::Create()
    try{([BitConverter]::ToString($algorithm.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant()}
    finally{$algorithm.Dispose()}
}

function Get-CoreNextMetadataFingerprint($Value) {
    Get-CoreNextBytesFingerprint ([Text.Encoding]::UTF8.GetBytes(($Value|ConvertTo-Json -Depth 30 -Compress)))
}

function Assert-CoreNextUpgradeSnapshot {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$ProfilePath,[Parameter(Mandatory)][string]$ConfigPath,
          [Parameter(Mandatory)]$Transition)
    $null=Assert-CoreNextOrdinaryPath $ProfilePath 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB'
    $null=Assert-CoreNextOrdinaryPath $ConfigPath 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB'
    if($Transition.original_profile_fingerprint -cnotmatch '^[a-f0-9]{64}$' -or $Transition.original_config_fingerprint -cnotmatch '^[a-f0-9]{64}$'){throw 'CORE_NEXT_UPGRADE_ORIGINAL_SNAPSHOT_REQUIRED'}
    $currentProfile=Get-CoreNextMetadataFingerprint ([IO.File]::ReadAllText($ProfilePath)|ConvertFrom-Json)
    $currentConfig=Get-CoreNextMetadataFingerprint ([IO.File]::ReadAllText($ConfigPath)|ConvertFrom-Json)
    if($currentProfile -cne $Transition.original_profile_fingerprint -or $currentConfig -cne $Transition.original_config_fingerprint){throw 'CORE_NEXT_UPGRADE_METADATA_CHANGED_SINCE_PLAN'}
}

function Get-CoreNextFileSecuritySignature($Security) {
    $identity=[Security.Principal.SecurityIdentifier]
    [ordered]@{owner=$Security.GetOwner($identity).Value;group=$Security.GetGroup($identity).Value;
        protected=$Security.AreAccessRulesProtected;rules=@($Security.GetAccessRules($true,$true,$identity)|ForEach-Object{
            '{0}|{1}|{2}|{3}|{4}|{5}' -f $_.IdentityReference.Value,[int64]$_.FileSystemRights,[int]$_.AccessControlType,$_.IsInherited,[int]$_.InheritanceFlags,[int]$_.PropagationFlags
        }|Sort-Object)}|ConvertTo-Json -Depth 5 -Compress
}

function Write-CoreNextAtomicBytes {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path,[Parameter(Mandatory)][byte[]]$Bytes,
          [Parameter(Mandatory)][string]$BackupFile,[string]$ExpectedCurrentSha256)
    $null=Assert-CoreNextOrdinaryPath $Path 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB'
    $null=Assert-CoreNextOrdinaryPath $BackupFile 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB'
    if(-not(Test-Path -LiteralPath $Path -PathType Leaf) -or (Test-Path -LiteralPath $BackupFile)){throw 'CORE_NEXT_UPGRADE_ATOMIC_TARGET_REQUIRED'}
    $security=Get-Acl -LiteralPath $Path
    $signature=Get-CoreNextFileSecuritySignature $security
    $oldBytes=[IO.File]::ReadAllBytes($Path);$replaced=$false
    if($ExpectedCurrentSha256 -and (Get-CoreNextBytesFingerprint $oldBytes) -cne $ExpectedCurrentSha256){throw 'CORE_NEXT_UPGRADE_ATOMIC_TARGET_CHANGED'}
    $temporary=$Path+'.upgrade-'+[Guid]::NewGuid().ToString('N')+'.tmp'
    try{
        [IO.File]::WriteAllBytes($temporary,$Bytes)
        if($ExpectedCurrentSha256 -and (Get-CoreNextBytesFingerprint ([IO.File]::ReadAllBytes($Path))) -cne $ExpectedCurrentSha256){throw 'CORE_NEXT_UPGRADE_ATOMIC_TARGET_CHANGED'}
        [IO.File]::Replace($temporary,$Path,$BackupFile);$replaced=$true
        # Windows can normalize D: to D:AI while retaining the same owner,
        # protection and ACEs. Compare permissions rather than that control bit.
        if((Get-CoreNextFileSecuritySignature (Get-Acl -LiteralPath $Path)) -cne $signature){Set-Acl -LiteralPath $Path -AclObject $security}
        if((Get-CoreNextFileSecuritySignature (Get-Acl -LiteralPath $Path)) -cne $signature){throw 'CORE_NEXT_UPGRADE_FILE_SECURITY_NOT_PRESERVED'}
    }catch{
        if($replaced){
            if([Convert]::ToBase64String([IO.File]::ReadAllBytes($Path)) -cne [Convert]::ToBase64String($Bytes)){throw 'CORE_NEXT_UPGRADE_ATOMIC_FILE_RECONCILIATION_REQUIRED'}
            [IO.File]::WriteAllBytes($temporary,$oldBytes);[IO.File]::Replace($temporary,$Path,($BackupFile+'.failed-new'));Set-Acl -LiteralPath $Path -AclObject $security
        }
        throw
    }
    finally{if(Test-Path -LiteralPath $temporary){Remove-Item -LiteralPath $temporary -Force}}
}

function Set-CoreNextUpgradeMetadata {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$ProfilePath,[Parameter(Mandatory)][string]$ConfigPath,
          [Parameter(Mandatory)]$Transition,[Parameter(Mandatory)][string]$BackupRoot)
    # Two files cannot be atomically swapped together. The owning service must
    # already be stopped; restore only our exact partial metadata before Setup.
    $null=Assert-CoreNextOrdinaryPath $BackupRoot 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB'
    $null=Assert-CoreNextOrdinaryPath $ProfilePath 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB'
    $null=Assert-CoreNextOrdinaryPath $ConfigPath 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB'
    $profileRoot=Split-Path -Path $Transition.profile.install_root -Parent
    if([IO.Path]::GetFullPath($ProfilePath) -ine (Join-Path $profileRoot 'installation-profile.json') -or [IO.Path]::GetFullPath($ConfigPath) -ine (Join-Path $Transition.profile.state_root 'workstation.json')){throw 'CORE_NEXT_UPGRADE_METADATA_PATH_MISMATCH'}
    if($BackupRoot.StartsWith($profileRoot+'\',[StringComparison]::OrdinalIgnoreCase) -or $profileRoot.StartsWith($BackupRoot+'\',[StringComparison]::OrdinalIgnoreCase) -or $BackupRoot -ieq $profileRoot){throw 'CORE_NEXT_UPGRADE_BACKUP_OVERLAPS_PROFILE'}
    Assert-CoreNextUpgradeSnapshot -ProfilePath $ProfilePath -ConfigPath $ConfigPath -Transition $Transition
    $oldProfile=[IO.File]::ReadAllBytes($ProfilePath);$oldConfig=[IO.File]::ReadAllBytes($ConfigPath)
    if((Get-CoreNextMetadataFingerprint ([Text.Encoding]::UTF8.GetString($oldProfile).TrimStart([char]0xfeff)|ConvertFrom-Json)) -cne $Transition.original_profile_fingerprint -or (Get-CoreNextMetadataFingerprint ([Text.Encoding]::UTF8.GetString($oldConfig).TrimStart([char]0xfeff)|ConvertFrom-Json)) -cne $Transition.original_config_fingerprint){throw 'CORE_NEXT_UPGRADE_METADATA_CHANGED_SINCE_PLAN'}
    $encoding=[Text.UTF8Encoding]::new($false)
    $newProfile=$encoding.GetBytes(($Transition.profile|ConvertTo-Json -Depth 30))
    $newConfig=$encoding.GetBytes(($Transition.config|ConvertTo-Json -Depth 30))
    $profileDone=$false;$configDone=$false
    try{
        Write-CoreNextAtomicBytes -Path $ProfilePath -Bytes $newProfile -BackupFile (Join-Path $BackupRoot 'profile-before-transition.json') -ExpectedCurrentSha256 (Get-CoreNextBytesFingerprint $oldProfile)
        $profileDone=$true
        Write-CoreNextAtomicBytes -Path $ConfigPath -Bytes $newConfig -BackupFile (Join-Path $BackupRoot 'config-before-transition.json') -ExpectedCurrentSha256 (Get-CoreNextBytesFingerprint $oldConfig)
        $configDone=$true
    }catch{
        if($profileDone -and -not $configDone){
            if([Convert]::ToBase64String([IO.File]::ReadAllBytes($ProfilePath)) -cne [Convert]::ToBase64String($newProfile) -or [Convert]::ToBase64String([IO.File]::ReadAllBytes($ConfigPath)) -cne [Convert]::ToBase64String($oldConfig)){throw 'CORE_NEXT_UPGRADE_PARTIAL_METADATA_RECONCILIATION_REQUIRED'}
            Write-CoreNextAtomicBytes -Path $ProfilePath -Bytes $oldProfile -BackupFile (Join-Path $BackupRoot 'rolled-back-new-profile.json') -ExpectedCurrentSha256 (Get-CoreNextBytesFingerprint $newProfile)
        }
        throw
    }
    [pscustomobject]@{profile_updated=$profileDone;config_updated=$configDone;credentials_or_identity_changed=$false}
}

function Invoke-CoreNextBackupCopy([string]$SourceDirectory,[string]$DestinationDirectory,[string]$FileName,[string]$LogPath) {
    if(-not([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'CORE_NEXT_UPGRADE_BACKUP_MODE_ELEVATION_REQUIRED'}
    & (Join-Path $env:WINDIR 'System32\robocopy.exe') $SourceDirectory $DestinationDirectory $FileName /B /R:0 /W:0 /COPY:DAT /NFL /NDL /NJH /NJS /NP *> $LogPath
    $LASTEXITCODE
}

function Copy-CoreNextProtectedBackup {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$StateRoot,[Parameter(Mandatory)][string]$BackupRoot,
          [Parameter(Mandatory)][string]$RelativePath,[Parameter(Mandatory)][string]$OwnerSid)
    $allowed=@('kernel\local-session.json','kernel\joomla-bridge.json','kernel\local-ai.json')
    if($RelativePath -cnotin $allowed){throw 'CORE_NEXT_UPGRADE_BACKUP_MODE_EXACT_FILE_REQUIRED'}
    $lab='C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB'
    $state=Assert-CoreNextOrdinaryPath $StateRoot $lab
    $private=Assert-CoreNextOrdinaryPath $BackupRoot $lab
    if($private.StartsWith($state+'\',[StringComparison]::OrdinalIgnoreCase) -or $state.StartsWith($private+'\',[StringComparison]::OrdinalIgnoreCase) -or $state -ieq $private){throw 'CORE_NEXT_UPGRADE_BACKUP_MODE_PATH_OVERLAP'}
    $acl=Get-Acl -LiteralPath $private
    $allowedSids=@($OwnerSid,[Security.Principal.WindowsIdentity]::GetCurrent().User.Value,'S-1-5-18','S-1-5-32-544')
    $rules=@($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]))
    if(-not$acl.AreAccessRulesProtected -or @($rules|Where-Object {$_.AccessControlType -ne 'Allow' -or $_.IdentityReference.Value -notin $allowedSids}).Count){throw 'CORE_NEXT_UPGRADE_BACKUP_MODE_PRIVATE_ACL_REQUIRED'}
    $source=Assert-CoreNextOrdinaryPath (Join-Path $state $RelativePath) $lab
    $destination=Assert-CoreNextOrdinaryPath (Join-Path (Join-Path $private 'state-files') $RelativePath) $lab
    if(-not(Test-Path -LiteralPath $source -PathType Leaf)){throw 'CORE_NEXT_UPGRADE_PROTECTED_SOURCE_MISSING'}
    New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent)|Out-Null
    $log=Join-Path $private ('backup-mode-'+[IO.Path]::GetFileName($source)+'.log')
    $code=Invoke-CoreNextBackupCopy -SourceDirectory (Split-Path $source -Parent) -DestinationDirectory (Split-Path $destination -Parent) -FileName ([IO.Path]::GetFileName($source)) -LogPath $log
    if($code -ge 8 -or $code -lt 0 -or -not(Test-Path -LiteralPath $destination -PathType Leaf) -or (Get-Item -LiteralPath $destination).Length -le 0){throw 'CORE_NEXT_UPGRADE_PROTECTED_BACKUP_COPY_FAILED'}
    $backupHash=(Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
    $sourceHash=$null
    try{$sourceHash=(Get-FileHash -LiteralPath $source -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()}catch{if($_.CategoryInfo.Category -ne 'PermissionDenied' -and $_.Exception -isnot [UnauthorizedAccessException]){throw};$sourceHash=$null}
    if($sourceHash -and $sourceHash -cne $backupHash){throw 'CORE_NEXT_UPGRADE_PROTECTED_BACKUP_HASH_MISMATCH'}
    [ordered]@{path=$RelativePath;method='Windows robocopy backup-mode /B /COPY:DAT; no source ACL changes';exit_code=[int]$code;
        backup_sha256=$backupHash;bytes=(Get-Item -LiteralPath $destination).Length;copied_at=[DateTime]::UtcNow.ToString('o');
        source_sha256=$sourceHash;source_hash_available=[bool]$sourceHash;source_hash_comparison=$(if($sourceHash){'MATCH'}else{'UNAVAILABLE_SOURCE_ACL; backup payload hashed; OS backup-copy semantics recorded'})}
}
