#requires -Version 7.0
<# Refresh only the original profile's verified immutable Joomla inputs.
   No database action, service operation, credential readout or ACL modification. #>
[CmdletBinding()]
param(
    [switch]$Apply,
    [ValidateSet('r1','r2')][string]$PreflightAttempt='r2',
    [ValidatePattern('^[a-f0-9]{64}$')][string]$ExpectedWebManifestSha256='f54572ad63f2f6a7b8467a4fc96c8fad72d203357e57d958641fca517b884304',
    [ValidatePattern('^[a-f0-9]{64}$')][string]$ExpectedPackageSha256='8b639f154d086af6616d04ddbec40ad280d772577a0e7fba176cb8958c502a49'
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$Project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\')
$InstallRoot=Join-Path $Project 'build\workstation\test-install\application files'
$StateRoot=Join-Path $Project 'build\workstation\test-install\state data'
$WorkRoot=Join-Path $Project 'build\joomla-frontend-20261101'
$SourceRoot=Join-Path $WorkRoot 'web-payload'
$PrivateParent=Join-Path $WorkRoot 'private-backup'
$BackupRoot=Join-Path $PrivateParent 'installed-web-inputs-r1'
$EvidenceRoot=Join-Path $WorkRoot 'evidence'
$ReportPath=Join-Path $EvidenceRoot $(if($Apply){'installed-web-update-r1.json'}else{'installed-web-preflight-'+$PreflightAttempt+'.json'})
$ServiceNames=@('DragonhydraWorkstation','DragonhydraWorkstationTest','DragonhydraProvidersA2Test','DragonhydraGenesisA8Test')
$WebNames=@('extension.zip','manage.php','README.md','payload-manifest.json')
$RelativeTargets=@('web/extension.zip','web/manage.php','web/README.md','web/payload-manifest.json','WORKSTATION-BUILD.json','PAYLOAD-MANIFEST.json')
$Checks=[Collections.Generic.List[object]]::new()
$Report=[ordered]@{schema_version=1;passed=$false;applied=$false;preflight_only=(-not [bool]$Apply);started_at=[DateTime]::UtcNow.ToString('o');phase='initializing';checks=$Checks;
    service_name='DragonhydraWorkstationTest';install_root=$InstallRoot;source_web_payload=$SourceRoot;
    services_restarted=$false;database_mutations_requested=$false;acl_changes_requested=$false;credentials_emitted=$false;
    windows_installer_built=$false;scope='Original installed component/web-input refresh only; no new Windows Setup or fresh-install claim'}
$MutationsStarted=$false
$TemporaryFiles=[Collections.Generic.List[string]]::new()
$BeforeFiles=[Collections.Generic.List[object]]::new()

function Hash([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function ReadJson([string]$Path){Get-Content -LiteralPath $Path -Raw|ConvertFrom-Json}
function Save-Report {
    $text=$Report|ConvertTo-Json -Depth 20
    $temporary=$ReportPath+'.next'
    [IO.File]::WriteAllText($temporary,$text,[Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $ReportPath -Force
}
function Gate([string]$Name,[bool]$Condition){
    $Checks.Add([ordered]@{name=$Name;status=$(if($Condition){'PASS'}else{'FAIL'})})
    Save-Report
    if(-not $Condition){throw 'SCOPED_INSTALLED_WEB_GATE_FAILED'}
}
function Ordinary-Path([string]$Path){
    $walk=[IO.Path]::GetFullPath($Path)
    while($walk){
        if(Test-Path -LiteralPath $walk){
            if((Get-Item -LiteralPath $walk -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'FILESYSTEM_LINK_DENIED'}
        }
        $parent=Split-Path $walk -Parent
        if($parent -eq $walk){break}
        $walk=$parent
    }
}
function Target-Path([string]$Relative){
    if($Relative -notin $RelativeTargets){throw 'TARGET_NOT_ALLOWLISTED'}
    $path=[IO.Path]::GetFullPath((Join-Path $InstallRoot $Relative.Replace('/','\')))
    if(-not $path.StartsWith($InstallRoot+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'TARGET_OUTSIDE_FIXED_INSTALLATION'}
    Ordinary-Path $path
    return $path
}
function Services {
    @(foreach($name in $ServiceNames){
        $service=Get-CimInstance Win32_Service -Filter "Name='$name'"
        if(-not $service){throw 'EXPECTED_SERVICE_MISSING'}
        [ordered]@{name=$service.Name;state=$service.State;pid=$service.ProcessId;account=$service.StartName;path=$service.PathName}
    })
}
function One-Row($Manifest,[string]$Relative){
    $rows=@($Manifest.files|Where-Object path -CEQ $Relative)
    if($rows.Count -ne 1){throw 'MANIFEST_TARGET_ROW_NOT_UNIQUE'}
    return $rows[0]
}
function Restricted-Directory([string]$Path){
    $broad=@('S-1-1-0','S-1-5-11','S-1-5-32-545')
    foreach($entry in (Get-Acl -LiteralPath $Path).Access){
        if($entry.AccessControlType -eq 'Allow' -and $entry.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -in $broad){return $false}
    }
    return $true
}
function Stage-Bytes([string]$Target,[byte[]]$Bytes){
    $temporary=$Target+'.joomla-frontend.'+[Guid]::NewGuid().ToString('N')+'.next'
    if(-not ([IO.Path]::GetDirectoryName($temporary)).Equals([IO.Path]::GetDirectoryName($Target),[StringComparison]::OrdinalIgnoreCase)){throw 'ATOMIC_SIBLING_MISMATCH'}
    $stream=[IO.FileStream]::new($temporary,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None,4096,[IO.FileOptions]::WriteThrough)
    try{$stream.Write($Bytes,0,$Bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
    $TemporaryFiles.Add($temporary)
    return $temporary
}
function Commit-Bytes([string]$Target,[byte[]]$Bytes,[string]$ExpectedHash){
    $temporary=Stage-Bytes $Target $Bytes
    if((Hash $temporary) -cne $ExpectedHash){throw 'STAGED_BYTES_HASH_MISMATCH'}
    [Dragonhydra.Workstation.AtomicFile]::Commit($temporary,$Target)
    if((Hash $Target) -cne $ExpectedHash){throw 'COMMITTED_BYTES_HASH_MISMATCH'}
}

if(Test-Path -LiteralPath $ReportPath){throw 'Existing installed-web receipt must remain preserved.'}
if(-not(Test-Path -LiteralPath $EvidenceRoot -PathType Container)){throw 'Expected frontend evidence directory is missing.'}
try {
    $Report.phase='validate-profile-and-artifacts'
    foreach($directory in @($InstallRoot,$StateRoot,$SourceRoot,$PrivateParent)){Ordinary-Path $directory;if(-not(Test-Path -LiteralPath $directory -PathType Container)){throw 'FIXED_WORKSPACE_DIRECTORY_MISSING'}}
    $cfg=ReadJson (Join-Path $StateRoot 'workstation.json')
    $expectedService='"'+(Join-Path $InstallRoot 'workstation\DragonhydraService.exe')+'" --state "'+$StateRoot+'" --name DragonhydraWorkstationTest'
    Gate 'exact-original-profile-and-ports' ($cfg.service_name -eq 'DragonhydraWorkstationTest' -and $cfg.install_root -eq $InstallRoot -and $cfg.state_root -eq $StateRoot -and $cfg.web_port -eq 18740 -and $cfg.api_port -eq 18744 -and $cfg.database_port -eq 18741)
    $Report.services_before=Services
    $owner=@($Report.services_before|Where-Object name -EQ 'DragonhydraWorkstationTest')
    Gate 'all-four-services-running-and-owning-controller-matches' ($owner.Count -eq 1 -and $owner[0].path -eq $expectedService -and @($Report.services_before|Where-Object state -NE 'Running').Count -eq 0)
    $sourceManifestPath=Join-Path $SourceRoot 'payload-manifest.json'
    $sourceManifest=ReadJson $sourceManifestPath
    $oldWebPath=Target-Path 'web/payload-manifest.json'
    $oldWeb=ReadJson $oldWebPath
    $outerPath=Target-Path 'PAYLOAD-MANIFEST.json'
    $outer=ReadJson $outerPath
    $buildPath=Target-Path 'WORKSTATION-BUILD.json'
    $build=ReadJson $buildPath
    Gate 'new-web-manifest-and-installed-baseline-identities' ((Hash $sourceManifestPath) -ceq $ExpectedWebManifestSha256 -and (Hash $oldWebPath) -ceq $sourceManifest.frontend_refresh.baseline_manifest_sha256 -and $sourceManifest.architecture -eq 'x64' -and $sourceManifest.platform -eq 'windows' -and $sourceManifest.source_sha -ceq $oldWeb.source_sha -and $sourceManifest.product_version -ceq $oldWeb.product_version)
    Gate 'new-package-version-and-hash' ($sourceManifest.components.joomla_extension.version -eq '0.4.1-dev.2' -and $sourceManifest.components.joomla_extension.child_template -eq 'cassiopeia_dragonhydra' -and $sourceManifest.components.joomla_extension.sha256 -ceq $ExpectedPackageSha256 -and (Hash (Join-Path $SourceRoot 'extension.zip')) -ceq $ExpectedPackageSha256)
    $unchanged=0
    $sourceRows=[Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
    foreach($entry in $sourceManifest.files){
        if($sourceRows.ContainsKey([string]$entry.path)){throw 'SOURCE_MANIFEST_PATH_DUPLICATE'}
        $sourceRows.Add([string]$entry.path,$entry)
    }
    foreach($entry in $oldWeb.files){
        if(-not $sourceRows.ContainsKey([string]$entry.path)){throw 'SOURCE_MANIFEST_PATH_MISSING'}
        $new=$sourceRows[[string]$entry.path]
        if($entry.path -notin @('extension.zip','manage.php','README.md')){
            if($new.sha256 -cne $entry.sha256 -or $new.bytes -ne $entry.bytes){throw 'UNEXPECTED_RUNTIME_MANIFEST_CHANGE'}
            $unchanged++
        }
    }
    Gate 'only-three-presentation-inputs-differ-in-runtime-manifest' ($sourceManifest.files.Count -eq $oldWeb.files.Count -and $unchanged -eq $sourceManifest.frontend_refresh.reused_runtime_files -and (@($sourceManifest.frontend_refresh.changed_files|Sort-Object)|ConvertTo-Json -Compress) -ceq (@('README.md','extension.zip','manage.php')|Sort-Object|ConvertTo-Json -Compress))
    $Report.unchanged_runtime_manifest_entries=$unchanged
    foreach($relative in $RelativeTargets){
        $path=Target-Path $relative
        if(-not(Test-Path -LiteralPath $path -PathType Leaf)){throw 'EXISTING_TARGET_MISSING'}
        $hash=Hash $path
        if($relative -ne 'PAYLOAD-MANIFEST.json'){
            $row=One-Row $outer $relative
            if($row.sha256 -cne $hash -or $row.bytes -ne (Get-Item -LiteralPath $path).Length){throw 'INSTALLED_OUTER_MANIFEST_TARGET_MISMATCH'}
        }
        if($relative -in @('web/extension.zip','web/manage.php','web/README.md')){
            $row=One-Row $oldWeb $relative.Substring(4)
            if($row.sha256 -cne $hash -or $row.bytes -ne (Get-Item -LiteralPath $path).Length){throw 'INSTALLED_WEB_TARGET_MISMATCH'}
        }
        $BeforeFiles.Add([ordered]@{relative_path=$relative;bytes=(Get-Item -LiteralPath $path).Length;sha256=$hash;acl_sddl=(Get-Acl -LiteralPath $path).Sddl})
    }
    foreach($name in $WebNames){
        $source=Join-Path $SourceRoot $name
        Ordinary-Path $source
        $hash=Hash $source
        if($name -ne 'payload-manifest.json'){
            $row=One-Row $sourceManifest $name
            if($row.sha256 -cne $hash -or $row.bytes -ne (Get-Item -LiteralPath $source).Length){throw 'NEW_WEB_TARGET_MISMATCH'}
        }
    }
    Gate 'six-existing-targets-and-four-new-inputs-verified' ($BeforeFiles.Count -eq 6)
    Gate 'original-workstation-manifest-shape' ($build.product -eq 'DRAGONHYDRA Workstation' -and $build.version -eq '0.4.1-dev.1' -and $outer.version -eq '0.4.1-dev.1' -and $outer.schema_version -eq 1)
    $Report.before_files=@($BeforeFiles|ForEach-Object{[ordered]@{relative_path=$_.relative_path;bytes=$_.bytes;sha256=$_.sha256}})
    $Report.critical_binaries_before=@(foreach($relative in @('server/DRAGONHYDRA-Server.exe','client/DRAGONHYDRA-Client.exe')){
        $path=[IO.Path]::GetFullPath((Join-Path $InstallRoot $relative.Replace('/','\')))
        Ordinary-Path $path
        $row=One-Row $outer $relative
        $hash=Hash $path
        $length=(Get-Item -LiteralPath $path).Length
        if($hash -cne $row.sha256 -or $length -ne $row.bytes){throw 'INDEPENDENT_CRITICAL_BINARY_MISMATCH'}
        [ordered]@{relative_path=$relative;bytes=$length;sha256=$hash}
    })
    Gate 'existing-server-and-client-binaries-match-their-outer-manifest' ($Report.critical_binaries_before.Count -eq 2)
    if(-not $Apply){$Report.passed=$true;$Report.phase='preflight-complete'}
    else {
        $principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
        Gate 'explicit-apply-with-administrative-token' $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        Gate 'existing-private-backup-parent-is-restricted' (Restricted-Directory $PrivateParent)
        if(Test-Path -LiteralPath $BackupRoot){throw 'Do not overwrite a previous installed-input backup.'}
        New-Item -ItemType Directory -Path $BackupRoot|Out-Null
        foreach($before in $BeforeFiles){
            $backup=Join-Path $BackupRoot $before.relative_path.Replace('/','\')
            $parent=Split-Path $backup -Parent
            if(-not(Test-Path -LiteralPath $parent)){New-Item -ItemType Directory -Path $parent|Out-Null}
            Copy-Item -LiteralPath (Target-Path $before.relative_path) -Destination $backup
            if((Hash $backup) -cne $before.sha256 -or -not(Restricted-Directory $backup)){throw 'PRIVATE_BACKUP_VERIFICATION_FAILED'}
        }
        Gate 'all-six-targets-backed-up-before-any-change' $true
        $Report.private_backup_directory=$BackupRoot
        $atomicPath=Join-Path $InstallRoot 'workstation\DragonhydraAtomicFile.dll'
        $atomicEntry=One-Row $outer 'workstation/DragonhydraAtomicFile.dll'
        if((Hash $atomicPath) -cne $atomicEntry.sha256){throw 'INSTALLED_ATOMIC_HELPER_IDENTITY_MISMATCH'}
        if(-not('Dragonhydra.Workstation.AtomicFile' -as [type])){Add-Type -Path $atomicPath}
        $build|Add-Member -NotePropertyName joomla_frontend_override -NotePropertyValue ([ordered]@{version='0.4.1-dev.2';package_sha256=$ExpectedPackageSha256;source_sha='55997de0a3997a10d12c6271795289a5d147e1ab';web_manifest_sha256=$ExpectedWebManifestSha256;runtime_binaries_unchanged=$true;installed_web_input_refresh=$true;new_windows_installer_built=$false;recorded_at=[DateTime]::UtcNow.ToString('o')}) -Force
        foreach($component in $build.inner_components){
            if($component.filename -like 'pkg_dragonhydra-*'){
                $component|Add-Member -NotePropertyName installed_payload -NotePropertyValue $false -Force
                $component|Add-Member -NotePropertyName role -NotePropertyValue 'Immutable baseline input; installed Joomla package replaced by recorded joomla_frontend_override' -Force
            }
        }
        $utf8=[Text.UTF8Encoding]::new($false)
        $newBytes=@{}
        foreach($name in $WebNames){$newBytes['web/'+$name]=[IO.File]::ReadAllBytes((Join-Path $SourceRoot $name))}
        $newBytes['WORKSTATION-BUILD.json']=$utf8.GetBytes(($build|ConvertTo-Json -Depth 24))
        foreach($relative in @($WebNames|ForEach-Object{'web/'+$_})+@('WORKSTATION-BUILD.json')){
            $row=One-Row $outer $relative
            $row.bytes=$newBytes[$relative].Length
            $row.sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([byte[]]$newBytes[$relative])).ToLowerInvariant()
        }
        $newBytes['PAYLOAD-MANIFEST.json']=$utf8.GetBytes(($outer|ConvertTo-Json -Depth 24))
        Gate 'all-four-service-identities-still-match-before-commit' (($Report.services_before|ConvertTo-Json -Depth 5 -Compress) -ceq ((Services)|ConvertTo-Json -Depth 5 -Compress))
        $Report.phase='atomic-file-commits'
        $MutationsStarted=$true
        foreach($relative in $RelativeTargets){
            $target=Target-Path $relative
            $expected=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([byte[]]$newBytes[$relative])).ToLowerInvariant()
            Commit-Bytes $target $newBytes[$relative] $expected
            $before=@($BeforeFiles|Where-Object relative_path -CEQ $relative)[0]
            if((Get-Acl -LiteralPath $target).Sddl -cne $before.acl_sddl){throw 'TARGET_ACL_CHANGED'}
        }
        $Report.applied=$true
        $Report.after_files=@(foreach($relative in $RelativeTargets){$path=Target-Path $relative;[ordered]@{relative_path=$relative;bytes=(Get-Item -LiteralPath $path).Length;sha256=(Hash $path)}})
        Gate 'installed-four-inputs-and-two-outer-manifests-verified' ((Hash (Target-Path 'web/payload-manifest.json')) -ceq $ExpectedWebManifestSha256 -and (Hash (Target-Path 'web/extension.zip')) -ceq $ExpectedPackageSha256)
        $Report.critical_binaries_after=@(foreach($before in $Report.critical_binaries_before){
            $path=Join-Path $InstallRoot $before.relative_path.Replace('/','\')
            [ordered]@{relative_path=$before.relative_path;bytes=(Get-Item -LiteralPath $path).Length;sha256=(Hash $path)}
        })
        Gate 'server-and-client-binaries-byte-identical-after-web-input-refresh' (($Report.critical_binaries_before|ConvertTo-Json -Depth 4 -Compress) -ceq ($Report.critical_binaries_after|ConvertTo-Json -Depth 4 -Compress))
        $Report.services_after=Services
        Gate 'all-four-services-retain-original-state-pid-and-controller' (($Report.services_before|ConvertTo-Json -Depth 5 -Compress) -ceq ($Report.services_after|ConvertTo-Json -Depth 5 -Compress))
        $Report.passed=$true
        $Report.phase='installed-input-refresh-complete'
    }
}catch{
    $Report.failure_class=$_.Exception.GetType().FullName
    $Report.failure_stage=$Report.phase
    $Report.vendor_message_omitted=$true
    if($MutationsStarted){
        $Report.rollback_attempted=$true
        try{
            foreach($relative in $RelativeTargets){
                $target=Target-Path $relative
                $backup=Join-Path $BackupRoot $relative.Replace('/','\')
                $before=@($BeforeFiles|Where-Object relative_path -CEQ $relative)[0]
                if((Hash $backup) -cne $before.sha256){throw 'ROLLBACK_BACKUP_MISMATCH'}
                Commit-Bytes $target ([IO.File]::ReadAllBytes($backup)) $before.sha256
                if((Get-Acl -LiteralPath $target).Sddl -cne $before.acl_sddl){throw 'ROLLBACK_ACL_VERIFICATION_FAILED'}
            }
            $Report.rollback_verified=$true;$Report.applied=$false
        }catch{$Report.rollback_verified=$false;$Report.rollback_failure_class=$_.Exception.GetType().FullName}
    }
}finally{
    foreach($temporary in $TemporaryFiles){
        if(Test-Path -LiteralPath $temporary){
            if(-not $temporary.StartsWith($InstallRoot+'\',[StringComparison]::OrdinalIgnoreCase) -or $temporary -notmatch '\.joomla-frontend\.[a-f0-9]{32}\.next$'){throw 'TEMPORARY_CLEANUP_SCOPE_DENIED'}
            Remove-Item -LiteralPath $temporary -Force
        }
    }
    $Report.finished_at=[DateTime]::UtcNow.ToString('o')
    Save-Report
}
[ordered]@{passed=$Report.passed;applied=$Report.applied;checks=$Checks.Count;receipt=$ReportPath}|ConvertTo-Json
if(-not $Report.passed){exit 1}
