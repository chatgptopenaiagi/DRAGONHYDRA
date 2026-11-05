#requires -Version 5.1
[CmdletBinding()]
param([string]$EvidenceRoot='C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\release-evolution-20261105\dev7-acl-recovery')
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -eq 5){$env:PSModulePath=Join-Path $PSHOME 'Modules'}
. (Join-Path $PSScriptRoot '..\..\packaging\windows\workstation\CoreNextProfile.ps1')
$fixture=Join-Path ([IO.Path]::GetFullPath($EvidenceRoot)) ('profile-path-tests-'+[guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path $fixture
$checks=[Collections.Generic.List[object]]::new()
function Check([string]$Name,[scriptblock]$Action){
    try{& $Action;$checks.Add([pscustomobject]@{name=$Name;result='PASS'})}
    catch{$checks.Add([pscustomobject]@{name=$Name;result='FAIL';error=$_.Exception.Message})}
}
function Reject([scriptblock]$Action,[string]$Code){
    $caught=$null;try{& $Action|Out-Null}catch{$caught=$_}
    if(-not $caught -or -not $caught.Exception.Message.StartsWith($Code,[StringComparison]::Ordinal)){throw "Expected rejection: $Code; observed: $caught"}
    $caught
}
$junction=Join-Path $fixture 'junction'
$denied=Join-Path $fixture 'denied-profile.json'
$savedAcl=$null
try{
    $ordinary=Join-Path $fixture 'ordinary';$null=New-Item -ItemType Directory -Path $ordinary
    $leaf=Join-Path $ordinary 'profile.json';[IO.File]::WriteAllText($leaf,'{}')
    Check 'ORDINARY_PATH' {if((Assert-CoreNextOrdinaryPath $leaf $fixture) -cne $leaf){throw 'Path changed'}}
    Check 'PARENT_DIRECTORY_TRAVERSAL' {$null=Assert-CoreNextOrdinaryPath $leaf $fixture}
    Check 'MISSING_FUTURE_LEAF' {$null=Assert-CoreNextOrdinaryPath (Join-Path $ordinary 'missing.json') $fixture}
    Check 'MISSING_FUTURE_DIRECTORY' {$null=Assert-CoreNextOrdinaryPath (Join-Path $ordinary 'missing\leaf.json') $fixture}
    Check 'RELATIVE_PATH_REJECTION' {$null=Reject {Assert-CoreNextOrdinaryPath 'relative\leaf' $fixture} 'CORE_NEXT_ABSOLUTE_ORDINARY_PATH_REQUIRED'}
    Check 'DOTDOT_REJECTION' {$null=Reject {Assert-CoreNextOrdinaryPath ($ordinary+'\..\outside') $fixture} 'CORE_NEXT_ABSOLUTE_ORDINARY_PATH_REQUIRED'}
    Check 'OUTSIDE_BOUNDARY_REJECTION' {$null=Reject {Assert-CoreNextOrdinaryPath ($fixture+'-sibling\leaf') $fixture} 'CORE_NEXT_PATH_OUTSIDE_LAB'}
    $null=New-Item -ItemType Junction -Path $junction -Target $ordinary
    Check 'REPARSE_POINT_REJECTION' {$null=Reject {Assert-CoreNextOrdinaryPath $junction $fixture} 'CORE_NEXT_REPARSE_PATH_REJECTED'}
    Check 'REPARSE_PARENT_REJECTION' {$null=Reject {Assert-CoreNextOrdinaryPath (Join-Path $junction 'missing.json') $fixture} 'CORE_NEXT_REPARSE_PATH_REJECTED'}
    $profile=New-CoreNextProfileObject -SourceCommit ('a'*40) -Version '0.5.0-dev.7' -LabRoot $fixture
    Check 'VALID_GENERATED_PROFILE' {$null=Assert-CoreNextProfile $profile -LabRoot $fixture}
    Check 'INVALID_INSTALLATION_ID' {
        $copy=$profile|ConvertTo-Json -Depth 8|ConvertFrom-Json;$copy.installation_id='core-next-invalid'
        $null=Reject {Assert-CoreNextProfile $copy -LabRoot $fixture} 'CORE_NEXT_PROFILE_IDENTITY_REQUIRED'
    }
    Check 'INCORRECT_SERVICE_IDENTITY' {
        $copy=$profile|ConvertTo-Json -Depth 8|ConvertFrom-Json;$copy.service_name='DragonhydraCoreNextcandidatewrong'
        $null=Reject {Assert-CoreNextProfile $copy -LabRoot $fixture} 'CORE_NEXT_SERVICE_OR_SHELL_IDENTITY_MISMATCH'
    }
    Check 'UNAUTHORIZED_INSTALLATION_DIRECTORY' {
        $copy=$profile|ConvertTo-Json -Depth 8|ConvertFrom-Json;$copy.install_root=Join-Path $fixture 'other\application'
        $null=Reject {Assert-CoreNextProfile $copy -LabRoot $fixture} 'CORE_NEXT_PROFILE_PATH_IDENTITY_MISMATCH'
    }
    # Provider errors are injected at the provider boundary. This proves that
    # Continue cannot turn PermissionDenied into successful path validation.
    Check 'ACCESS_DENIED_DIAGNOSTICS_CONTINUE' {
        $deniedPath=Join-Path $ordinary 'provider-denied'
        function Get-Item {
            [CmdletBinding()]param([string]$LiteralPath,[switch]$Force)
            if($LiteralPath -ceq $deniedPath){Write-Error -Exception ([UnauthorizedAccessException]::new('fixture denial')) -Category PermissionDenied;return}
            Microsoft.PowerShell.Management\Get-Item -LiteralPath $LiteralPath -Force:$Force -ErrorAction Stop
        }
        $oldPreference=$ErrorActionPreference;$ErrorActionPreference='Continue'
        try{
            $errorRecord=Reject {Assert-CoreNextOrdinaryPath $deniedPath $fixture} ('CORE_NEXT_PATH_ACCESS_DENIED: '+$deniedPath)
            if($errorRecord.Exception -isnot [UnauthorizedAccessException]){throw 'Typed denial lost'}
        }finally{$ErrorActionPreference=$oldPreference;Remove-Item Function:\Get-Item}
    }
    Check 'UNKNOWN_PROVIDER_ERROR_FAILS_CLOSED' {
        function Get-Item {[CmdletBinding()]param([string]$LiteralPath,[switch]$Force);throw 'UNEXPECTED_PROVIDER_FAILURE'}
        try{$null=Reject {Assert-CoreNextOrdinaryPath $leaf $fixture} 'UNEXPECTED_PROVIDER_FAILURE'}finally{Remove-Item Function:\Get-Item}
    }
    [IO.File]::WriteAllText($denied,'{}');$before=(Get-FileHash -LiteralPath $denied -Algorithm SHA256).Hash
    $savedAcl=Get-Acl -LiteralPath $denied
    $denyAcl=Get-Acl -LiteralPath $denied
    $denyAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.WindowsIdentity]::GetCurrent().User,'ReadData','Deny'))
    Set-Acl -LiteralPath $denied -AclObject $denyAcl
    Check 'ACTUAL_NTFS_PROFILE_READ_DENIAL' {
        $oldPreference=$ErrorActionPreference;$ErrorActionPreference='Continue'
        try{$null=Reject {Read-CoreNextProfile $denied} ('CORE_NEXT_PROFILE_READ_ACCESS_DENIED: '+$denied)}finally{$ErrorActionPreference=$oldPreference}
    }
    Set-Acl -LiteralPath $denied -AclObject $savedAcl;$savedAcl=$null
    Check 'PROFILE_HASH_PRESERVATION' {if((Get-FileHash -LiteralPath $denied -Algorithm SHA256).Hash -cne $before){throw 'Profile bytes changed'}}
}finally{
    if($savedAcl){Set-Acl -LiteralPath $denied -AclObject $savedAcl}
    # Remove the link itself before cleaning the verified disposable fixture.
    if(Test-Path -LiteralPath $junction){[IO.Directory]::Delete($junction)}
    $resolved=[IO.Path]::GetFullPath($fixture)
    $boundary=[IO.Path]::GetFullPath($EvidenceRoot).TrimEnd('\')+'\profile-path-tests-'
    if(-not $resolved.StartsWith($boundary,[StringComparison]::OrdinalIgnoreCase)){throw 'TEST_CLEANUP_BOUNDARY_REJECTED'}
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
$result=[pscustomobject]@{schema_version='core-next.profile-path-regression/1';checks=$checks.ToArray();passed=(@($checks|Where-Object result -ne 'PASS').Count -eq 0);scope='Disposable path, provider-error and actual NTFS profile read checks; no service-token acceptance implied'}
$result|ConvertTo-Json -Depth 6
if(-not $result.passed){exit 1}
