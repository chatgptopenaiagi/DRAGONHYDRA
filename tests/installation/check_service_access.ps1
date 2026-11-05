#requires -Version 5.1
# Disposable NTFS fixtures and AST-extracted production functions only. No SCM,
# service start, application launch, SQL, credentials or existing profile writes.
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -eq 5){$env:PSModulePath=Join-Path $PSHOME 'Modules'}
$project=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
. (Join-Path $project 'packaging\windows\workstation\CoreNextProfile.ps1')
$tokens=$null;$parseErrors=$null
$sourcePath=Join-Path $project 'packaging\windows\workstation\Workstation.ps1'
$ast=[Management.Automation.Language.Parser]::ParseFile($sourcePath,[ref]$tokens,[ref]$parseErrors)
if($parseErrors.Count){throw 'SOURCE_PARSE_FAILED'}
foreach($name in @('Protect-Directory','Set-CoreNextServiceProfileAccess','Assert-CoreNextImmutableFiles','Test-CoreNextServiceProfileAccess')){
    $found=@($ast.FindAll({param($node)$node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -ceq $name},$true))
    if($found.Count -ne 1){throw 'EXACT_PRODUCTION_FUNCTION_REQUIRED'}
    . ([scriptblock]::Create($found[0].Extent.Text))
}
$results=New-Object Collections.Generic.List[object]
function Check([string]$Name,[bool]$Value){if(-not $Value){throw ('ASSERTION_FAILED_'+$Name)};$results.Add(@{check=$Name;result='PASS'})}
function Reject([string]$Name,[scriptblock]$Action,[string]$Code){
    $message='';try{& $Action|Out-Null}catch{$message=$_.Exception.Message}
    Check $Name ($message -ceq $Code)
}
function Quote([string]$Value){'"'+$Value+'"'}
# These are intentional test doubles. In particular, no real service identity
# is resolved or SCM queried; actual-token acceptance is a separate operation.
$testSid=[Security.Principal.SecurityIdentifier]::new('S-1-5-80-11-22-33-44-55')
function Resolve-CoreNextServiceSid([string]$ServiceName){$testSid}
function Get-CimInstance {param($ClassName,$Filter);if($ClassName -cne 'Win32_Service'){throw 'SCM_FORBIDDEN'};return $script:fakeService}
function Rules([string]$Path){(Get-Acl -LiteralPath $Path).GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])}
function Has-Grant([string]$Path,[string]$Sid,[Security.AccessControl.FileSystemRights]$Rights){
    @((Rules $Path)|Where-Object {$_.IdentityReference.Value -ceq $Sid -and $_.AccessControlType -eq 'Allow' -and ($_.FileSystemRights -band $Rights) -eq $Rights}).Count -gt 0
}
$p=New-CoreNextProfileObject -SourceCommit ('a'*40) -Version '0.5.0-dev.7' -BuildId 'disposable-acl-regression'
$p.created_utc='2026-11-05T19:02:00.1234560Z'
$root=Split-Path $p.install_root -Parent
if(Test-Path -LiteralPath $root){throw 'FRESH_DISPOSABLE_FIXTURE_REQUIRED'}
$profile=Join-Path $root 'installation-profile.json'
$owner=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
try{
    New-Item -ItemType Directory -Path $root,$p.install_root,$p.state_root|Out-Null
    Protect-Directory $root $owner -ServiceSpecific
    Protect-Directory $p.state_root $owner -ServiceSpecific
    [IO.File]::WriteAllText($profile,($p|ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
    $script:fakeService=[pscustomobject]@{Name=$p.service_name;PathName=((Quote (Join-Path $p.install_root 'workstation\DragonhydraService.exe'))+' --state '+(Quote $p.state_root)+' --name '+$p.service_name);StartName='NT AUTHORITY\LocalService';State='Stopped'}
    $sidEvidence=[pscustomobject]@{installation_id=$p.installation_id;service_name=$p.service_name;account='NT AUTHORITY\LocalService';sid_type='UNRESTRICTED'}
    $beforeHash=(Get-FileHash -LiteralPath $profile -Algorithm SHA256).Hash.ToLowerInvariant()
    $beforeOwner=(Get-Acl -LiteralPath $root).Owner
    Check 'MISSING_SERVICE_PERMISSIONS_DETECTED' (-not (Has-Grant $profile $testSid.Value 'Read'))
    $wrong=$sidEvidence.PSObject.Copy();$wrong.service_name+='wrong'
    Reject 'INCORRECT_SERVICE_IDENTITY' {Set-CoreNextServiceProfileAccess $p $profile $wrong} 'CORE_NEXT_SERVICE_ACL_IDENTITY_MISMATCH'
    Reject 'UNAUTHORIZED_PROFILE_DIRECTORY' {Set-CoreNextServiceProfileAccess $p (Join-Path $p.state_root 'installation-profile.json') $sidEvidence} 'CORE_NEXT_CANONICAL_PROFILE_PATH_REQUIRED'
    $bad=$p.PSObject.Copy();$bad.installation_id='invalid'
    Reject 'INVALID_INSTALLATION_ID' {Set-CoreNextServiceProfileAccess $bad $profile $sidEvidence} 'CORE_NEXT_PROFILE_IDENTITY_REQUIRED'
    $script:fakeService.StartName='LocalSystem'
    Reject 'INCORRECT_SERVICE_ACCOUNT' {Set-CoreNextServiceProfileAccess $p $profile $sidEvidence} 'CORE_NEXT_EXISTING_SERVICE_NOT_OWNED'
    $script:fakeService.StartName='NT AUTHORITY\LocalService'
    $changed=$p.PSObject.Copy();$changed.build_id='modified-profile'
    [IO.File]::WriteAllText($profile,($changed|ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
    Reject 'MODIFIED_PROFILE_REJECTED' {Set-CoreNextServiceProfileAccess $p $profile $sidEvidence} 'CORE_NEXT_SERVICE_ACL_PROFILE_BINDING_MISMATCH'
    [IO.File]::WriteAllText($profile,($p|ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
    $receipt=Set-CoreNextServiceProfileAccess $p $profile $sidEvidence
    Check 'PROFILE_TIMESTAMP_NORMALIZATION' ($receipt.status -ceq 'PROVISIONED')
    Check 'INSTALLATION_ROOT_ACL' (Has-Grant $root $testSid.Value 'ReadAndExecute')
    Check 'INSTALLATION_PROFILE_READ_ACCESS' (Has-Grant $profile $testSid.Value 'Read')
    Check 'APPLICATION_EXECUTE_ACCESS' (Has-Grant $p.install_root $testSid.Value 'ReadAndExecute')
    Check 'STATE_WRITE_ACCESS' (Has-Grant $p.state_root $testSid.Value 'Modify')
    Check 'NO_SHARED_ACCOUNT_STATE_GRANT' (-not (Has-Grant $p.state_root 'S-1-5-19' 'Write'))
    Check 'PROFILE_HASH_PRESERVATION' ($beforeHash -ceq $receipt.profile_sha256 -and $beforeHash -ceq (Get-FileHash -LiteralPath $profile -Algorithm SHA256).Hash.ToLowerInvariant())
    Check 'OWNER_PRESERVATION' ($beforeOwner -ceq (Get-Acl -LiteralPath $root).Owner)
    Check 'SYSTEM_ADMIN_PRESERVATION' ((Has-Grant $root 'S-1-5-18' 'FullControl') -and (Has-Grant $root 'S-1-5-32-544' 'FullControl'))
    Check 'PROVISIONING_IS_NOT_EFFECTIVE_ACCESS' ($receipt.effective_access_verified -eq $false)
    Reject 'ADMINISTRATOR_IS_NOT_SERVICE_TOKEN' {Test-CoreNextServiceProfileAccess $p $profile $receipt} 'CORE_NEXT_SERVICE_TOKEN_IDENTITY_MISMATCH'
    $rootRule=@((Rules $root)|Where-Object {$_.IdentityReference.Value -ceq $testSid.Value})[0]
    Check 'ROOT_GRANT_NOT_INHERITED_TO_SIBLINGS' ($rootRule.InheritanceFlags -eq 'None')
    $beforeSddl=(Get-Acl -LiteralPath $root).Sddl
    $null=Set-CoreNextServiceProfileAccess $p $profile $sidEvidence
    Check 'IDEMPOTENT_ACL_PROVISIONING' ($beforeSddl -ceq (Get-Acl -LiteralPath $root).Sddl)
    $acl=Get-Acl -LiteralPath $profile
    $deny=[Security.AccessControl.FileSystemAccessRule]::new($testSid,'Read','Deny')
    $acl.AddAccessRule($deny);Set-Acl -LiteralPath $profile -AclObject $acl
    Reject 'EXPLICIT_DENY_NOT_TREATED_AS_ACCESS' {Set-CoreNextServiceProfileAccess $p $profile $sidEvidence} 'CORE_NEXT_SERVICE_ACL_DENY_PRESENT'
    $legacy=$sidEvidence.PSObject.Copy();$legacy.sid_type='LEGACY_NOT_REQUIRED'
    $legacyBefore=(Get-Acl -LiteralPath $profile).Sddl
    $legacyReceipt=Set-CoreNextServiceProfileAccess $p $profile $legacy
    Check 'LEGACY_ACL_UNCHANGED' ($legacyReceipt.status -ceq 'LEGACY_UNCHANGED' -and $legacyBefore -ceq (Get-Acl -LiteralPath $profile).Sddl)
    $immutable=@($profile)
    foreach($relative in @('workstation\Workstation.ps1','workstation\CoreNextProfile.ps1','workstation\DragonhydraService.exe','server\DRAGONHYDRA-Server.exe')){
        $file=Join-Path $p.install_root $relative
        $null=New-Item -ItemType Directory -Path (Split-Path $file -Parent) -Force
        [IO.File]::WriteAllText($file,'disposable immutable fixture')
        $immutable+=$file
    }
    $hashes=@{};foreach($file in $immutable){$hashes[$file]=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash}
    $writeDeny=[Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.WindowsIdentity]::GetCurrent().User,'WriteData','Deny')
    foreach($file in $immutable){$acl=Get-Acl -LiteralPath $file;$acl.AddAccessRule($writeDeny);Set-Acl -LiteralPath $file -AclObject $acl}
    Assert-CoreNextImmutableFiles $immutable
    Check 'ALL_REQUIRED_FILES_WRITE_DENIED' $true
    foreach($file in $immutable){
        $acl=Get-Acl -LiteralPath $file;$acl.RemoveAccessRuleSpecific($writeDeny);Set-Acl -LiteralPath $file -AclObject $acl
        Reject ('WRITABLE_REQUIRED_FILE_REJECTED_'+[IO.Path]::GetFileName($file)) {Assert-CoreNextImmutableFiles $immutable} 'CORE_NEXT_SERVICE_IMMUTABLE_PATH_WRITABLE'
        $acl=Get-Acl -LiteralPath $file;$acl.AddAccessRule($writeDeny);Set-Acl -LiteralPath $file -AclObject $acl
    }
    Check 'IMMUTABLE_TEST_PRESERVES_ALL_BYTES' (@($immutable|Where-Object {(Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash -cne $hashes[$_]}).Count -eq 0)
    $source=Get-Content -LiteralPath $sourcePath -Raw
    $grantPosition=$source.IndexOf('$accessEvidence=Set-CoreNextServiceProfileAccess')
    $startPosition=$source.IndexOf("Start-Service `$ServiceName")
    $readyPosition=$source.IndexOf("if(`$status.stage -eq 'ready')")
    $recoveryPosition=$source.IndexOf("@('failure',`$ServiceName,'reset=','86400'")
    Check 'ACCESS_PROVISIONED_BEFORE_SERVICE_START' ($grantPosition -gt 0 -and $grantPosition -lt $startPosition)
    Check 'NEW_SERVICE_MANUAL_UNTIL_PROVISIONED' ($source.Contains("StartMode='Manual';StartName='NT AUTHORITY\LocalService'"))
    Check 'NEW_SERVICE_RECOVERY_AFTER_READINESS' ($recoveryPosition -gt $readyPosition -and $readyPosition -gt $startPosition)
    @{schema_version=1;passed=$true;scope='Disposable NTFS ACLs; synthetic service SID/SCM; no actual service-token or launch claims';checks=$results.ToArray();actual_service_calls=0;actual_native_calls=0}|ConvertTo-Json -Depth 8
}finally{
    $expected=Join-Path 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\profiles' $p.installation_id
    if([IO.Path]::GetFullPath($root) -ine $expected -or $p.installation_id -cnotmatch '^core-next-[a-f0-9]{32}$'){throw 'FIXTURE_CLEANUP_SCOPE_REJECTED'}
    if(Test-Path -LiteralPath $root){Remove-Item -LiteralPath $root -Recurse -Force}
}
