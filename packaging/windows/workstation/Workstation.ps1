#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('Install','Run','Stop','Uninstall','Status')][string]$Action,
    [string]$InstallRoot,
    [string]$StateRoot,
    [ValidatePattern('^Dragonhydra[A-Za-z0-9_-]{0,60}$')][string]$ServiceName,
    [string]$OwnerSid,
    [string]$ProfilePath,
    [string]$SeedSnapshot,
    [ValidatePattern('^[a-f0-9]{64}$')][string]$SeedSnapshotSha256,
    [int]$StartupTimeout=300
)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -eq 5){$env:PSModulePath=Join-Path $PSHOME 'Modules'}
. (Join-Path $PSScriptRoot 'CoreNextProfile.ps1')
if(-not $ProfilePath){if(-not $StateRoot){throw 'CORE_NEXT_EXPLICIT_PROFILE_REQUIRED'};$ProfilePath=Join-Path (Split-Path -Path $StateRoot -Parent) 'installation-profile.json'}
$coreProfile=Read-CoreNextProfile $ProfilePath -CheckService
foreach($key in @('InstallRoot','StateRoot','ServiceName')){
    $field=@{InstallRoot='install_root';StateRoot='state_root';ServiceName='service_name'}[$key]
    if($PSBoundParameters.ContainsKey($key) -and (Get-Variable $key -ValueOnly) -ine $coreProfile.$field){throw 'CORE_NEXT_EXPLICIT_BINDING_MISMATCH'}
    Set-Variable -Name $key -Value $coreProfile.$field
}
if($PSVersionTable.PSVersion.Major -eq 5){
    # An installer launched by PowerShell 7 inherits its PSModulePath, unlike a
    # direct powershell.exe invocation. Load only this host's Windows modules;
    # importing the PS7 Security manifest into PS5 duplicates ACL type data.
    # This change is process-local and also applies to our managed descendants.
    $env:PSModulePath=Join-Path $PSHOME 'Modules'
}
$StateRoot=[IO.Path]::GetFullPath($StateRoot).TrimEnd('\')
$configFile=Join-Path $StateRoot 'workstation.json'
$script:cfg=$null
$script:children=New-Object Collections.Generic.List[object]
$script:phase='initializing'
$utf8=New-Object Text.UTF8Encoding($false)
if($Action -eq 'Install'){
    Write-Output ('Workstation initialization: Windows PowerShell '+$PSVersionTable.PSVersion+'; 64-bit process='+[Environment]::Is64BitProcess)
    if(-not [Environment]::Is64BitProcess){throw 'The x64 workstation installer must invoke native 64-bit Windows PowerShell.'}
}
Add-Type -Path (Join-Path $PSScriptRoot 'DragonhydraAtomicFile.dll')
function Save-Json($value,[string]$path) {
    # A typed overload keeps the nullable backup argument out of PowerShell's
    # binder and handles both a new destination and repeated status updates.
    [Dragonhydra.Workstation.AtomicFile]::Write($path,($value|ConvertTo-Json -Depth 12))
}
function Read-Json([string]$path) { [Dragonhydra.Workstation.AtomicFile]::Read($path)|ConvertFrom-Json }
function Protect-Directory([string]$path,[string]$owner,[switch]$ServiceSpecific) {
    $acl=New-Object Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true,$false)
    $principals=@('S-1-5-18','S-1-5-32-544',$owner)
    # New profiles receive their own service SID after SCM registration. Keep
    # the shared account grant only for explicitly legacy profiles.
    if(-not $ServiceSpecific){$principals+='S-1-5-19'}
    foreach($sid in $principals|Select-Object -Unique){
        if($sid){$identity=New-Object Security.Principal.SecurityIdentifier($sid);$acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($identity,'FullControl','ContainerInherit,ObjectInherit','None','Allow')))}
    }
    Set-Acl -LiteralPath $path -AclObject $acl
}
function Protect-Binaries([string]$path) {
    $acl=New-Object Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true,$false)
    foreach($sid in @('S-1-5-18','S-1-5-32-544')){
        $identity=New-Object Security.Principal.SecurityIdentifier($sid)
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($identity,'FullControl','ContainerInherit,ObjectInherit','None','Allow')))
    }
    foreach($sid in @('S-1-5-19','S-1-5-32-545')){
        $identity=New-Object Security.Principal.SecurityIdentifier($sid)
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($identity,'ReadAndExecute','ContainerInherit,ObjectInherit','None','Allow')))
    }
    Set-Acl -LiteralPath $path -AclObject $acl
}
function Random-Secret {
    $bytes=New-Object byte[] 36
    $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
    try{$rng.GetBytes($bytes)}finally{$rng.Dispose()}
    [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
}
function Assert-Path([string]$path) {
    if($path.Contains('"') -or $path.Contains("`n") -or $path.Contains("`r") -or [IO.Path]::GetPathRoot($path).TrimEnd('\') -eq $path.TrimEnd('\')){throw 'Unsafe installation or state path.'}
}
function Quote([string]$value) { Assert-Path $value; '"'+$value.TrimEnd('\')+'"' }
function Native([string]$executable,[string[]]$arguments) {
    if(-not(Test-Path -LiteralPath $executable -PathType Leaf)){throw 'Required private executable is missing.'}
    $previousPreference=$ErrorActionPreference
    try{
        # Windows PowerShell 5.1 reports ordinary native stderr (Apache's
        # "Syntax OK", for example) as ErrorRecord. The exit code is decisive.
        $ErrorActionPreference='Continue'
        $output=& $executable @arguments 2>&1
        $code=$LASTEXITCODE
    }finally{$ErrorActionPreference=$previousPreference}
    if($code -ne 0){throw ('Native operation failed ('+[IO.Path]::GetFileName($executable)+', exit '+$code+').')}
    return $output
}
function Free-Port([int]$preferred,[int[]]$excluded) {
    for($port=$preferred;$port -lt $preferred+200;$port++){
        if($excluded -contains $port){continue}
        $listener=New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback,$port)
        try{$listener.Start();return $port}catch{}finally{$listener.Stop()}
    }
    throw 'No available product-owned loopback port in the configured range.'
}
function Assert-FreePort([int]$port) {
    $listener=New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback,$port)
    try{$listener.Start()}catch{throw "Configured port $port is occupied; no unrelated process was stopped."}finally{$listener.Stop()}
}
function Owned-Service {
    $existing=Get-CimInstance Win32_Service -Filter ("Name='"+$script:cfg.service_name+"'")
    if($existing){
        $binary=Join-Path $script:cfg.install_root 'workstation\DragonhydraService.exe'
        $expected=(Quote $binary)+' --state '+(Quote $script:cfg.state_root)+' --name '+$script:cfg.service_name
        if($existing.PathName -ne $expected){throw 'Service name belongs to a different installation; it was not changed.'}
    }
    return $existing
}
function Set-CoreNextOwnedServiceSid {
    param($Profile,[switch]$CreatedNow,[string]$Policy='',[switch]$SqlEnabled)
    $null=Assert-CoreNextProfile $Profile
    $name=[string]$Profile.service_name
    $service=Get-CimInstance Win32_Service -Filter ("Name='"+$name+"'")
    $expected=(Quote (Join-Path $Profile.install_root 'workstation\DragonhydraService.exe'))+' --state '+(Quote $Profile.state_root)+' --name '+$name
    if(-not $service -or $service.Name -cne $name -or $service.PathName -cne $expected -or $service.StartName -ine 'NT AUTHORITY\LocalService'){
        throw 'CORE_NEXT_SERVICE_SID_OWNERSHIP_MISMATCH'
    }
    if(-not $Policy -and -not $CreatedNow -and -not $SqlEnabled){
        return [pscustomobject]@{service_name=$name;installation_id=$Profile.installation_id;sid_type='LEGACY_NOT_REQUIRED';
            account='NT AUTHORITY\LocalService';changed=$false;observed_at=[DateTime]::UtcNow.ToString('o');
            verification_scope='Existing no-SQL profile unchanged; no service SID or SQL readiness inferred'}
    }
    if($Policy -cne 'unrestricted'){throw 'CORE_NEXT_SQL_SERVICE_SID_POLICY_REQUIRED'}
    if($CreatedNow -and $service.State -cne 'Stopped'){throw 'CORE_NEXT_NEW_SERVICE_MUST_BE_STOPPED'}
    $sc=Join-Path $env:WINDIR 'System32\sc.exe'
    function Read-ExactSidType {
        $raw=(@(Native $sc @('qsidtype',$name))|ForEach-Object{[string]$_}) -join "`n"
        $names=[regex]::Matches($raw,'(?m)^\s*SERVICE_NAME:\s*(\S+)\s*$')
        $types=[regex]::Matches($raw,'(?m)^\s*SERVICE_SID_TYPE:\s*(\S+)\s*$')
        if($names.Count -ne 1 -or $names[0].Groups[1].Value -cne $name -or $types.Count -ne 1){throw 'CORE_NEXT_SERVICE_SID_QUERY_UNVERIFIED'}
        $types[0].Groups[1].Value
    }
    $before=Read-ExactSidType
    if($before -cne 'UNRESTRICTED'){
        # Never retrofit another/older installation's service security settings.
        if(-not $CreatedNow -or $before -cne 'NONE'){throw 'CORE_NEXT_EXISTING_SERVICE_SID_UNVERIFIED'}
        $null=Native $sc @('sidtype',$name,'unrestricted')
    }
    if((Read-ExactSidType) -cne 'UNRESTRICTED'){throw 'CORE_NEXT_SERVICE_SID_CONFIGURATION_FAILED'}
    [pscustomobject]@{service_name=$name;installation_id=$Profile.installation_id;sid_type='UNRESTRICTED';
        account='NT AUTHORITY\LocalService';changed=($before -cne 'UNRESTRICTED');observed_at=[DateTime]::UtcNow.ToString('o');
        verification_scope='SCM configuration only; child token membership and SQL authentication require separate actual evidence'}
}
function Resolve-CoreNextServiceSid([string]$ServiceName) {
    if($ServiceName -cnotmatch '^DragonhydraCoreNext(?:candidate|baseline)[a-f0-9]{12}$'){throw 'CORE_NEXT_SERVICE_ACL_IDENTITY_MISMATCH'}
    $principal=New-Object Security.Principal.NTAccount('NT SERVICE',$ServiceName)
    $principal.Translate([Security.Principal.SecurityIdentifier])
}
function Set-CoreNextServiceProfileAccess {
    param($Profile,[string]$ProfilePath,$SidEvidence)
    $null=Assert-CoreNextProfile $Profile -CheckService
    $expectedProfile=Join-Path (Split-Path $Profile.install_root -Parent) 'installation-profile.json'
    if([IO.Path]::GetFullPath($ProfilePath) -ine $expectedProfile){throw 'CORE_NEXT_CANONICAL_PROFILE_PATH_REQUIRED'}
    $boundProfile=Read-CoreNextProfile $ProfilePath -CheckService
    # Normalize both through the same JSON parser: PowerShell 7 may parse ISO
    # timestamps as DateTime and serialize equivalent fractional seconds shorter.
    $expectedProfileObject=$Profile|ConvertTo-Json -Depth 12|ConvertFrom-Json
    if(($boundProfile|ConvertTo-Json -Depth 12 -Compress) -cne ($expectedProfileObject|ConvertTo-Json -Depth 12 -Compress)){throw 'CORE_NEXT_SERVICE_ACL_PROFILE_BINDING_MISMATCH'}
    if($SidEvidence.installation_id -cne $Profile.installation_id -or $SidEvidence.service_name -cne $Profile.service_name -or $SidEvidence.account -ine 'NT AUTHORITY\LocalService'){throw 'CORE_NEXT_SERVICE_ACL_IDENTITY_MISMATCH'}
    if($SidEvidence.sid_type -ceq 'LEGACY_NOT_REQUIRED'){
        return [pscustomobject]@{installation_id=$Profile.installation_id;service_name=$Profile.service_name;status='LEGACY_UNCHANGED';effective_access_verified=$false}
    }
    if($SidEvidence.sid_type -cne 'UNRESTRICTED'){throw 'CORE_NEXT_SERVICE_ACL_SID_REQUIRED'}
    $service=Get-CimInstance Win32_Service -Filter ("Name='"+$Profile.service_name+"'")
    $image=(Quote (Join-Path $Profile.install_root 'workstation\DragonhydraService.exe'))+' --state '+(Quote $Profile.state_root)+' --name '+$Profile.service_name
    if(-not $service -or $service.Name -cne $Profile.service_name -or $service.PathName -cne $image -or $service.StartName -ine 'NT AUTHORITY\LocalService'){throw 'CORE_NEXT_SERVICE_ACL_IDENTITY_MISMATCH'}
    $sid=Resolve-CoreNextServiceSid $Profile.service_name
    if($sid.Value -notmatch '^S-1-5-80-(?:\d+-){4}\d+$'){throw 'CORE_NEXT_SERVICE_ACL_SID_REQUIRED'}
    $beforeHash=(Get-FileHash -LiteralPath $ProfilePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $entries=@(
        @{path=(Split-Path $Profile.install_root -Parent);rights='ReadAndExecute';inherit='None'},
        @{path=$ProfilePath;rights='Read';inherit='None'},
        @{path=$Profile.install_root;rights='ReadAndExecute';inherit='ContainerInherit,ObjectInherit'},
        @{path=$Profile.state_root;rights='Modify';inherit='ContainerInherit,ObjectInherit'}
    )
    foreach($entry in $entries){
        $null=Assert-CoreNextOrdinaryPath $entry.path $Profile.lab_root
        $acl=Get-Acl -LiteralPath $entry.path
        # Add only this installation's ACE. Owner, protection and existing
        # SYSTEM/administrator/owner grants are not replaced by this repair.
        $rule=New-Object Security.AccessControl.FileSystemAccessRule($sid,$entry.rights,$entry.inherit,'None','Allow')
        $acl.AddAccessRule($rule)
        Set-Acl -LiteralPath $entry.path -AclObject $acl
        $actual=Get-Acl -LiteralPath $entry.path
        $required=[Security.AccessControl.FileSystemRights]$entry.rights
        $denies=@($actual.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])|Where-Object {$_.IdentityReference.Value -in @($sid.Value,'S-1-5-19','S-1-1-0','S-1-5-11') -and $_.AccessControlType -eq 'Deny' -and ($_.FileSystemRights -band $required)})
        if($denies.Count){throw 'CORE_NEXT_SERVICE_ACL_DENY_PRESENT'}
        $grants=@($actual.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])|Where-Object {$_.IdentityReference.Value -ceq $sid.Value -and $_.AccessControlType -eq 'Allow' -and ($_.FileSystemRights -band $required) -eq $required})
        if(-not $grants.Count){throw 'CORE_NEXT_SERVICE_ACL_READBACK_FAILED'}
    }
    $afterHash=(Get-FileHash -LiteralPath $ProfilePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if($beforeHash -cne $afterHash){throw 'CORE_NEXT_SERVICE_ACL_PROFILE_CHANGED'}
    [pscustomobject]@{schema_version=1;installation_id=$Profile.installation_id;service_name=$Profile.service_name;
        principal=('NT SERVICE\'+$Profile.service_name);service_sid=$sid.Value;profile_sha256=$afterHash;status='PROVISIONED';entries=$entries;
        effective_access_verified=$false;observed_at=[DateTime]::UtcNow.ToString('o');
        verification_scope='ACL provisioning/readback only; actual service token must pass startup preflight'}
}
function Assert-CoreNextImmutableFiles([string[]]$Paths) {
    # Opening for write without writing bytes verifies denial without changing
    # application/profile contents. A service must never repair its own ACLs.
    foreach($path in $Paths){
        $stream=$null;$denied=$false
        try{$stream=[IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::Write,[IO.FileShare]::ReadWrite)}
        catch [UnauthorizedAccessException]{$denied=$true}
        finally{if($stream){$stream.Dispose()}}
        if(-not $denied){throw 'CORE_NEXT_SERVICE_IMMUTABLE_PATH_WRITABLE'}
    }
}
function Test-CoreNextServiceProfileAccess {
    param($Profile,[string]$ProfilePath,$Provision)
    if($Provision.status -cne 'PROVISIONED' -or $Provision.installation_id -cne $Profile.installation_id -or $Provision.service_name -cne $Profile.service_name){throw 'CORE_NEXT_SERVICE_ACCESS_PROVISION_REQUIRED'}
    $sid=Resolve-CoreNextServiceSid $Profile.service_name
    $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
    if($identity.User.Value -cne 'S-1-5-19' -or $Provision.service_sid -cne $sid.Value -or -not ([Security.Principal.WindowsPrincipal]$identity).IsInRole($sid)){throw 'CORE_NEXT_SERVICE_TOKEN_IDENTITY_MISMATCH'}
    $null=Read-CoreNextProfile $ProfilePath
    $hash=(Get-FileHash -LiteralPath $ProfilePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if($hash -cne $Provision.profile_sha256){throw 'CORE_NEXT_SERVICE_ACCESS_PROFILE_CHANGED'}
    $immutablePaths=@($ProfilePath)
    foreach($relative in @('workstation\Workstation.ps1','workstation\CoreNextProfile.ps1','workstation\DragonhydraService.exe','server\DRAGONHYDRA-Server.exe')){
        $path=Assert-CoreNextOrdinaryPath (Join-Path $Profile.install_root $relative) $Profile.install_root
        $immutablePaths+=$path
        $stream=[IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
        try{$null=$stream.ReadByte()}finally{$stream.Dispose()}
    }
    Assert-CoreNextImmutableFiles $immutablePaths
    $probe=Join-Path $Profile.state_root ('service-access-'+[Guid]::NewGuid().ToString('N')+'.tmp')
    $stream=[IO.File]::Open($probe,[IO.FileMode]::CreateNew,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    try{$stream.WriteByte(1);$stream.Flush();$stream.Position=0;if($stream.ReadByte() -ne 1){throw 'CORE_NEXT_SERVICE_STATE_READBACK_FAILED'}}
    finally{$stream.Dispose();[IO.File]::Delete($probe)}
    [pscustomobject]@{schema_version=1;installation_id=$Profile.installation_id;service_name=$Profile.service_name;
        account=$identity.Name;account_sid=$identity.User.Value;service_sid=$sid.Value;service_sid_enabled=$true;
        profile_sha256=$hash;profile_read=$true;application_read=$true;immutable_write_denied=$true;state_write=$true;
        observed_at=[DateTime]::UtcNow.ToString('o');verification_scope='Actual supervisor token before backend launch; executable launch/readiness require later acceptance'}
}
function Close-OwnedClient {
    $clientPath=Join-Path $script:cfg.install_root 'client\DRAGONHYDRA-Client.exe'
    $statePath=Join-Path $script:cfg.state_root 'client'
    foreach($candidate in @(Get-CimInstance Win32_Process -Filter "Name='DRAGONHYDRA-Client.exe'"|Where-Object {$_.ExecutablePath -eq $clientPath -and $_.CommandLine -and $_.CommandLine.Contains($statePath)})){
        $client=Get-Process -Id $candidate.ProcessId -ErrorAction SilentlyContinue
        if($client -and -not $client.HasExited){
            $null=$client.CloseMainWindow()
            if(-not $client.WaitForExit(10000)){throw 'Close this workstation client before repairing or uninstalling its binaries.'}
        }
    }
}
function Status([string]$stage,[string]$errorCode='') {
    $script:phase=$stage
    Save-Json ([ordered]@{stage=$stage;updated_at=[DateTime]::UtcNow.ToString('o');service_name=$script:cfg.service_name;api_url=('http://127.0.0.1:'+$script:cfg.api_port);joomla_url=('http://127.0.0.1:'+$script:cfg.web_port);backend='sqlite';admin_database='MariaDB';optional_ai='not_configured';error=$errorCode;processes=@($script:children|ForEach-Object {@{role=$_.Role;pid=$_.Process.Id}})}) (Join-Path $StateRoot 'status.json')
}
function Initialize-CoreNextPassiveSockets {
    if('Dragonhydra.Workstation.CoreNextPassiveSockets' -as [type]){return}
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace Dragonhydra.Workstation {
  public static class CoreNextPassiveSockets {
    [DllImport("iphlpapi.dll",SetLastError=true)]
    static extern uint GetExtendedTcpTable(IntPtr table,ref int size,bool sorted,int family,int tableClass,uint reserved);
    public static bool OwnsLoopbackListener(int port,int processId) {
      if(port<18800 || port>65535 || processId<=0) return false;
      int size=0;
      uint code=GetExtendedTcpTable(IntPtr.Zero,ref size,false,2,3,0);
      if(code!=122 || size<4 || size>16*1024*1024) throw new InvalidOperationException("TCP_TABLE_UNVERIFIED");
      for(int attempt=0;attempt<2;attempt++) {
        if(size<4 || size>16*1024*1024) throw new InvalidOperationException("TCP_TABLE_UNVERIFIED");
        int allocated=size;IntPtr table=Marshal.AllocHGlobal(allocated);
        try {
          code=GetExtendedTcpTable(table,ref size,false,2,3,0);
          if(code==122) continue;
          if(code!=0 || size<4 || size>allocated) throw new InvalidOperationException("TCP_TABLE_UNVERIFIED");
          int count=Marshal.ReadInt32(table);
          if(count<0 || count>(size-4)/24) throw new InvalidOperationException("TCP_TABLE_UNVERIFIED");
          for(int i=0;i<count;i++) {
            int at=4+i*24;
            uint address=unchecked((uint)Marshal.ReadInt32(table,at+4));
            uint wirePort=unchecked((uint)Marshal.ReadInt32(table,at+8));
            int actualPort=(int)(((wirePort&255)<<8)|((wirePort>>8)&255));
            if(Marshal.ReadInt32(table,at)==2 && address==0x0100007f && actualPort==port && Marshal.ReadInt32(table,at+20)==processId) return true;
          }
          return false;
        } finally {Marshal.FreeHGlobal(table);}
      }
      throw new InvalidOperationException("TCP_TABLE_UNVERIFIED");
    }
  }
}
'@
}
function Get-CoreNextHeartbeatChild([string]$Role,[string]$Relative) {
    $entries=@($script:children|Where-Object {$_.Role -eq $Role})
    if($entries.Count -ne 1){return $null}
    $entry=$entries[0]
    try{
        if($entry.Executable -ine (Join-Path $script:cfg.install_root $Relative) -or $entry.Process.HasExited -or $entry.Process.Id -le 0){return $null}
        return $entry.Process
    }catch{return $null}
}
function Read-CoreNextHeartbeatJson([string]$Path) {
    $null=Assert-CoreNextOrdinaryPath $Path $StateRoot
    $stream=[IO.FileStream]::new($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
    try{
        $buffer=New-Object byte[] 16385;$length=0
        do{$count=$stream.Read($buffer,$length,$buffer.Length-$length);$length+=$count}while($count -gt 0 -and $length -lt $buffer.Length)
        if($length -gt 16384){throw 'HEARTBEAT_METADATA_UNVERIFIED'}
        return ([Text.UTF8Encoding]::new($false,$true).GetString($buffer,0,$length)|ConvertFrom-Json)
    }finally{$stream.Dispose()}
}
function Invoke-CoreNextHeartbeatHttp([int]$Port,[string]$Path,[string]$Token='') {
    if($Port -lt 18800 -or $Port -gt 65535 -or $Path -notin @('/','/administrator/','/dragon/api/v1/health/live','/dragon/api/v1/health/ready')){throw 'INVALID_HEARTBEAT_HTTP_TARGET'}
    $request=[Net.HttpWebRequest]::Create('http://127.0.0.1:'+$Port+$Path)
    $request.Method='GET';$request.AllowAutoRedirect=$false;$request.Proxy=$null;$request.Timeout=1000;$request.ReadWriteTimeout=1000
    if($Token){$request.Headers['Authorization']='Bearer '+$Token}
    $response=$null;$stream=$null;$status=0;$headersAt=$null;$clock=[Diagnostics.Stopwatch]::StartNew()
    try{
        $response=$request.GetResponse();$status=[int]$response.StatusCode
        if($status -eq 200){$headersAt=[DateTime]::UtcNow.ToString('o')}
        if($status -ne 200 -or $response.ContentLength -gt 16384){return @{ok=$false;status=$status;body='';observed_at=[DateTime]::UtcNow.ToString('o');http_200_at=$headersAt}}
        $stream=$response.GetResponseStream();$memory=[IO.MemoryStream]::new();$buffer=New-Object byte[] 1024
        try{
            while($true){
                $remaining=1000-[int]$clock.ElapsedMilliseconds
                if($remaining -le 0){throw 'HEARTBEAT_HTTP_DEADLINE'}
                $pending=$stream.ReadAsync($buffer,0,$buffer.Length)
                if(-not $pending.Wait($remaining)){throw 'HEARTBEAT_HTTP_DEADLINE'}
                $count=$pending.GetAwaiter().GetResult()
                if($count -eq 0){break}
                if($memory.Length+$count -gt 16384){throw 'HEARTBEAT_HTTP_SIZE_LIMIT'}
                $memory.Write($buffer,0,$count)
            }
            return @{ok=$true;status=$status;body=[Text.UTF8Encoding]::new($false,$true).GetString($memory.ToArray());observed_at=[DateTime]::UtcNow.ToString('o');http_200_at=$headersAt}
        }finally{$memory.Dispose()}
    }catch{
        $failure=$_.Exception.GetBaseException()
        if($failure -is [Net.WebException] -and $failure.Response -is [Net.HttpWebResponse]){$status=[int]$failure.Response.StatusCode}
        return @{ok=$false;status=$status;body='';observed_at=[DateTime]::UtcNow.ToString('o');http_200_at=$headersAt}
    }
    finally{if($stream){$stream.Dispose()};if($response){$response.Dispose()};$request.Abort();$clock.Stop()}
}
function Test-CoreNextHeartbeatTcp([int]$Port,[int]$ProcessId) {
    if($Port -lt 18800 -or $Port -gt 65535 -or $ProcessId -le 0){return 'UNVERIFIED'}
    $clock=[Diagnostics.Stopwatch]::StartNew();$client=$null;$pending=$null
    try{
        Initialize-CoreNextPassiveSockets
        if(-not [Dragonhydra.Workstation.CoreNextPassiveSockets]::OwnsLoopbackListener($Port,$ProcessId)){return 'UNVERIFIED'}
        $remaining=500-[int]$clock.ElapsedMilliseconds;if($remaining -le 0){return 'UNVERIFIED'}
        $client=[Net.Sockets.TcpClient]::new();$pending=$client.ConnectAsync('127.0.0.1',$Port)
        if(-not $pending.Wait($remaining)){return 'UNAVAILABLE'}
        $null=$pending.GetAwaiter().GetResult();if(-not $client.Connected){return 'UNAVAILABLE'}
        return 'READY'
    }catch{return 'UNVERIFIED'}finally{if($client){$client.Dispose()};$clock.Stop()}
}
function Save-CoreNextHeartbeatReceipt($Value) {
    $target=Join-Path $StateRoot 'runtime-observations.json';$temporary=$null
    $null=Assert-CoreNextOrdinaryPath $target $StateRoot
    try{
        $temporary=$target+'.'+[Guid]::NewGuid().ToString('N')+'.tmp'
        $null=Assert-CoreNextOrdinaryPath $temporary $StateRoot
        $stream=[IO.FileStream]::new($temporary,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try{$bytes=$utf8.GetBytes(($Value|ConvertTo-Json -Depth 8));$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
        $null=Assert-CoreNextOrdinaryPath $target $StateRoot
        $null=Assert-CoreNextOrdinaryPath $temporary $StateRoot
        [Dragonhydra.Workstation.AtomicFile]::Commit($temporary,$target)
    }finally{
        if($temporary -and (Test-Path -LiteralPath $temporary)){
            try{$null=Assert-CoreNextOrdinaryPath $temporary $StateRoot;[IO.File]::Delete($temporary)}catch{}
        }
    }
}
function Get-CoreNextHeartbeatStamp($Value,[DateTime]$Upper) {
    if($Value -is [DateTime]){
        if($Value.Kind -eq [DateTimeKind]::Unspecified -or $Value.ToUniversalTime() -gt $Upper.ToUniversalTime()){return $null}
        return $Value.ToUniversalTime().ToString('o')
    }
    if(-not ($Value -is [string]) -or $Value -notmatch '(?:Z|[+-][0-9]{2}:[0-9]{2})$'){return $null}
    $parsed=[DateTimeOffset]::MinValue
    if(-not [DateTimeOffset]::TryParse($Value,[ref]$parsed) -or $parsed.UtcDateTime -gt $Upper.ToUniversalTime()){return $null}
    return $parsed.UtcDateTime.ToString('o')
}
function Get-CoreNextHeartbeatPrevious([int]$ApiPid) {
    try{
        $value=Read-CoreNextHeartbeatJson (Join-Path $StateRoot 'runtime-observations.json')
        if($value.schema_version -ne 2 -or $value.observer -cne 'core-next.supervisor' -or $value.api_pid -ne $ApiPid -or $value.supervisor_pid -le 0 -or -not ($value.api_verified -is [bool])){return $null}
        foreach($key in @('installation_id','source_commit','build_id','service_name')){if($value.$key -cne $script:cfg.$key){return $null}}
        $now=[DateTime]::UtcNow;$observed=Get-CoreNextHeartbeatStamp $value.observed_at $now
        $expiry=Get-CoreNextHeartbeatStamp $value.expires_at $now.AddSeconds(90)
        if(-not $observed -or -not $expiry){return $null}
        $span=([DateTimeOffset]::Parse($expiry)-[DateTimeOffset]::Parse($observed)).TotalSeconds
        if($span -le 0 -or $span -gt 90){return $null}
        if($value.api_verified){
            $last=Get-CoreNextHeartbeatStamp $value.last_success_at ([DateTimeOffset]::Parse($observed).UtcDateTime)
            if(-not $last -or ([DateTimeOffset]::Parse($observed)-[DateTimeOffset]::Parse($last)).TotalSeconds -gt 90){return $null}
        }
        return $value
    }catch{return $null}
}
function Read-CoreNextHeartbeatServiceEvidence {
    param([string]$Name,[string]$ExpectedImage,[int]$SupervisorId)
    # Exact local SCM/CIM reads only. Configuration alone never attests a service.
    try{
        if($Name -cnotmatch '^Dragonhydra[A-Za-z0-9_-]{0,60}\z' -or $SupervisorId -le 0){return $null}
        $service=@(Get-CimInstance -ClassName Win32_Service -Filter ("Name='"+$Name+"'") -OperationTimeoutSec 1 -ErrorAction Stop)
        if($service.Count -ne 1 -or $service[0].Name -cne $Name -or $service[0].State -cne 'Running' -or
                $service[0].ProcessId -le 0 -or $service[0].PathName -cne $ExpectedImage){return $null}
        $process=@(Get-CimInstance -ClassName Win32_Process -Filter ('ProcessId='+$SupervisorId) -OperationTimeoutSec 1 -ErrorAction Stop)
        if($process.Count -ne 1 -or $process[0].ProcessId -ne $SupervisorId -or
                $process[0].ParentProcessId -ne $service[0].ProcessId){return $null}
        return [ordered]@{schema_version=1;service_name=$Name;service_process_id=[int]$service[0].ProcessId;
            supervisor_process_id=$SupervisorId;observed_at=[DateTime]::UtcNow.ToString('o');
            verification_scope='SCM_RUNNING_SERVICE_AND_SUPERVISOR_PARENT_ONLY'}
    }catch{return $null}
}
function Get-CoreNextHeartbeatServiceIdentity {
    # A single in-process runspace bounds the heartbeat wait even if CIM stalls.
    # Keep at most one request in flight; never accumulate retries or processes.
    if(-not (Get-Variable -Name coreNextServiceQuery -Scope Script -ErrorAction SilentlyContinue)){$script:coreNextServiceQuery=$null}
    $name=$script:cfg.service_name
    if($name -cnotmatch '^Dragonhydra[A-Za-z0-9_-]{0,60}\z'){return $null}
    $image='"'+(Join-Path $script:cfg.install_root 'workstation\DragonhydraService.exe')+'" --state "'+$script:cfg.state_root+'" --name '+$name
    if(-not $script:coreNextServiceQuery){
        $shell=[PowerShell]::Create()
        try{
            $null=$shell.AddScript(${function:Read-CoreNextHeartbeatServiceEvidence}.ToString()).AddArgument($name).AddArgument($image).AddArgument($PID)
            $script:coreNextServiceQuery=@{shell=$shell;handle=$shell.BeginInvoke();image=$image;name=$name}
        }catch{$shell.Dispose();return $null}
    }
    $pending=$script:coreNextServiceQuery
    if(-not $pending.handle.IsCompleted){$null=$pending.handle.AsyncWaitHandle.WaitOne(1200)}
    if(-not $pending.handle.IsCompleted){return $null}
    try{
        $result=@($pending.shell.EndInvoke($pending.handle))
        if($pending.image -cne $image -or $pending.name -cne $name -or $result.Count -ne 1){return $null}
        return $result[0]
    }catch{return $null}finally{$pending.shell.Dispose();$script:coreNextServiceQuery=$null}
}
function Save-CoreNextHeartbeatSnapshot([int]$ApiPid,[bool]$ApiVerified,$KernelSuccess,$Checks) {
    $serviceIdentity=$null;if($ApiVerified){$serviceIdentity=Get-CoreNextHeartbeatServiceIdentity}
    $at=[DateTime]::UtcNow;$stamp=$at.ToString('o');$previous=Get-CoreNextHeartbeatPrevious $ApiPid
    $success=Get-CoreNextHeartbeatStamp $KernelSuccess $at
    if(-not $success -or ($at-([DateTimeOffset]::Parse($success).UtcDateTime)).TotalSeconds -gt 90){$ApiVerified=$false;$success=$null}
    if(-not $ApiVerified -and $previous){try{$success=Get-CoreNextHeartbeatStamp $previous.last_success_at $at}catch{}}
    foreach($name in @('web_server','joomla_administration','joomla_website','mariadb_storage')){
        if(-not $Checks.Contains($name)){$Checks[$name]=@{state='UNVERIFIED';reason='KERNEL_IDENTITY_NOT_VERIFIED';metrics=@{};scope='No fresh component proof without authenticated same-build kernel verification'}}
        $check=$Checks[$name]
        $observed=$null;if($check.ContainsKey('observed_at')){$observed=Get-CoreNextHeartbeatStamp $check.observed_at $at}
        $check.observed_at=if($observed){$observed}else{$stamp}
        $last=$null;if($check.ContainsKey('last_success_at')){$last=Get-CoreNextHeartbeatStamp $check.last_success_at ([DateTimeOffset]::Parse($check.observed_at).UtcDateTime)}
        if(-not $ApiVerified){$check.state='UNVERIFIED';$check.reason='KERNEL_IDENTITY_NOT_VERIFIED';$last=$null}
        if($check.state -eq 'READY' -and (-not $last -or ($at-([DateTimeOffset]::Parse($last).UtcDateTime)).TotalSeconds -gt 90)){$check.state='UNVERIFIED';$check.reason='LOCAL_CHECK_SUCCESS_UNVERIFIED';$last=$null}
        if($check.state -ne 'READY'){
            $last=$null
            if($previous){try{$old=$previous.checks.$name;$oldObserved=Get-CoreNextHeartbeatStamp $old.observed_at ([DateTimeOffset]::Parse($check.observed_at).UtcDateTime);if($oldObserved){$last=Get-CoreNextHeartbeatStamp $old.last_success_at ([DateTimeOffset]::Parse($oldObserved).UtcDateTime)}}catch{}}
        }
        $check.last_success_at=$last
    }
    $receipt=[ordered]@{schema_version=2;observer='core-next.supervisor';installation_id=$script:cfg.installation_id;source_commit=$script:cfg.source_commit;build_id=$script:cfg.build_id;service_name=$script:cfg.service_name;api_pid=$ApiPid;supervisor_pid=$PID;api_verified=$ApiVerified;last_success_at=$success;observed_at=$stamp;expires_at=$at.AddSeconds(45).ToString('o');checks=$Checks}
    if($ApiVerified -and $serviceIdentity){$receipt.service_identity=$serviceIdentity}
    Save-CoreNextHeartbeatReceipt $receipt
}
function Write-CoreNextHeartbeat {
    # No status/configuration mutation, provider call, inference, job or service operation.
    # A receipt is renewed only after authenticating this exact live kernel/build.
    $knownKernelId=0
    try{
        $at=[DateTime]::UtcNow
        if($script:cfg.product -cne 'DRAGONHYDRA CORE NEXT' -or $script:cfg.edition -cne 'CORE NEXT' -or
            $script:cfg.installation_id -cnotmatch '^core-next-[a-f0-9]{32}$' -or
            $script:cfg.source_commit -cnotmatch '^[a-f0-9]{40}$' -or
            $script:cfg.service_name -cnotmatch '^Dragonhydra[A-Za-z0-9_-]{0,60}$' -or
            -not $script:cfg.build_id -or [IO.Path]::GetFullPath($script:cfg.state_root).TrimEnd('\') -ine $StateRoot){return $false}
        $kernel=Get-CoreNextHeartbeatChild 'kernel' 'server\DRAGONHYDRA-Server.exe'
        $apache=Get-CoreNextHeartbeatChild 'apache' 'web\apache\bin\httpd.exe'
        $database=Get-CoreNextHeartbeatChild 'database' 'web\mariadb\bin\mysqld.exe'
        if(-not $kernel){return $false}
        $knownKernelId=[int]$kernel.Id
        if(-not $apache -or -not $database){throw 'OWNED_CHILD_NOT_RUNNING'}
        $endpoint=Read-CoreNextHeartbeatJson (Join-Path $StateRoot 'kernel\endpoint.json')
        if($endpoint.pid -ne $kernel.Id -or $endpoint.url -cne ('http://127.0.0.1:'+$script:cfg.api_port)){throw 'KERNEL_ENDPOINT_UNVERIFIED'}
        if((Test-CoreNextHeartbeatTcp $script:cfg.api_port $kernel.Id) -ne 'READY'){throw 'KERNEL_LISTENER_UNVERIFIED'}
        $session=Read-CoreNextHeartbeatJson (Join-Path $StateRoot 'kernel\local-session.json')
        if(-not ($session.token -is [string]) -or $session.token.Length -lt 32 -or $session.token.Length -gt 512){throw 'KERNEL_AUTHENTICATION_UNVERIFIED'}
        $live=Invoke-CoreNextHeartbeatHttp $script:cfg.api_port '/dragon/api/v1/health/live' $session.token
        $ready=Invoke-CoreNextHeartbeatHttp $script:cfg.api_port '/dragon/api/v1/health/ready' $session.token
        if(-not $live.ok -or -not $ready.ok){throw 'KERNEL_HEALTH_UNVERIFIED'}
        $identity=($live.body|ConvertFrom-Json).installation;$health=$ready.body|ConvertFrom-Json
        if($identity.product -cne 'DRAGONHYDRA CORE NEXT' -or $identity.installation_id -cne $script:cfg.installation_id -or
            $identity.source_commit -cne $script:cfg.source_commit -or $identity.build_id -cne $script:cfg.build_id -or
            $identity.version -cne $script:cfg.version -or $health.version -cne $script:cfg.version -or
            $health.source_sha -cne $script:cfg.source_commit -or $health.status -cne 'ready'){throw 'KERNEL_BUILD_UNVERIFIED'}
        $kernelSuccess=[DateTime]::UtcNow.ToString('o')
        $homepageCheck=@{ok=$false;status=0;body=''};$admin=@{ok=$false;status=0;body=''}
        if($apache){$homepageCheck=Invoke-CoreNextHeartbeatHttp $script:cfg.web_port '/';$admin=Invoke-CoreNextHeartbeatHttp $script:cfg.web_port '/administrator/'}
        $checks=[ordered]@{}
        $checks.web_server=@{state='UNAVAILABLE';reason='OWNED_WEB_HTTP_UNAVAILABLE';metrics=@{http_status=[int]$homepageCheck.status;listener_present=$false};scope='OWNED_APACHE_PARENT_AND_LOOPBACK_HTTP_ONLY; no authenticated Joomla proof'}
        if($apache -and $homepageCheck.status -eq 200){$checks.web_server=@{state='READY';reason='OWNED_LOOPBACK_HTTP_RESPONDED';metrics=@{http_status=200;process_id=[int]$apache.Id;listener_present=$true};scope='OWNED_APACHE_PARENT_ALIVE_AND_LOOPBACK_HTTP_200_HEADERS; no child-listener PID or authenticated Joomla claim'}}
        $checks.joomla_administration=@{state='UNAVAILABLE';reason='JOOMLA_LOGIN_BOOTSTRAP_UNAVAILABLE';metrics=@{http_status=[int]$admin.status};scope='ANONYMOUS_JOOMLA_LOGIN_BOOTSTRAP_ONLY; administrator authentication not tested'}
        if($admin.ok -and $admin.body -match 'mod-login-username' -and $admin.body -match '<form'){$checks.joomla_administration.state='DEGRADED';$checks.joomla_administration.reason='LOCAL_LOGIN_BOOTSTRAP_ONLY'}
        elseif($admin.status -eq 200){$checks.joomla_administration.state='UNVERIFIED';$checks.joomla_administration.reason='LOGIN_BOOTSTRAP_NOT_VERIFIED_WITHIN_BOUNDED_RESPONSE'}
        $checks.joomla_website=@{state='UNAVAILABLE';reason='JOOMLA_PUBLIC_SHELL_UNVERIFIED';metrics=@{http_status=[int]$homepageCheck.status};scope='PUBLIC_BRANDED_COMPONENT_SHELL_ONLY; no private data or authenticated operation proof'}
        $websiteSuccess=$null
        if($homepageCheck.ok -and $homepageCheck.body -match 'DRAGONHYDRA' -and $homepageCheck.body -match 'data-dragonhydra-workspace'){$checks.joomla_website.state='READY';$checks.joomla_website.reason='BRANDED_PUBLIC_COMPONENT_SHELL_RESPONDED';$websiteSuccess=[DateTime]::UtcNow.ToString('o')}
        elseif($homepageCheck.status -eq 200){$checks.joomla_website.state='UNVERIFIED';$checks.joomla_website.reason='PUBLIC_COMPONENT_SHELL_NOT_VERIFIED_WITHIN_BOUNDED_RESPONSE'}
        $dbState='UNAVAILABLE';if($database){$dbState=Test-CoreNextHeartbeatTcp $script:cfg.database_port $database.Id}
        $checks.mariadb_storage=@{state='UNVERIFIED';reason='OWNED_DATABASE_LISTENER_UNVERIFIED';metrics=@{listener_present=$false};scope='OWNED_DATABASE_PROCESS_AND_TCP_LISTENER_PLUS_JOOMLA_BOOTSTRAP; no direct SQL permission/schema/integrity proof'}
        $databaseSuccess=$null
        if(-not $database){$checks.mariadb_storage.state='UNAVAILABLE';$checks.mariadb_storage.reason='OWNED_DATABASE_PROCESS_NOT_RUNNING'}
        elseif($dbState -eq 'READY' -and $admin.ok -and $admin.body -match 'mod-login-username'){$checks.mariadb_storage.state='READY';$checks.mariadb_storage.reason='OWNED_DATABASE_TCP_AND_JOOMLA_BOOTSTRAP';$checks.mariadb_storage.metrics=@{process_id=[int]$database.Id;listener_present=$true};$databaseSuccess=[DateTime]::UtcNow.ToString('o')}
        elseif($dbState -eq 'UNAVAILABLE'){$checks.mariadb_storage.state='UNAVAILABLE';$checks.mariadb_storage.reason='OWNED_DATABASE_TCP_UNAVAILABLE'}
        $checks.web_server.observed_at=$homepageCheck.observed_at
        if($checks.web_server.state -eq 'READY'){$checks.web_server.last_success_at=$homepageCheck.http_200_at}
        $checks.joomla_administration.observed_at=$admin.observed_at
        $checks.joomla_website.observed_at=[DateTime]::UtcNow.ToString('o')
        if($checks.joomla_website.state -eq 'READY'){$checks.joomla_website.last_success_at=$websiteSuccess}
        $checks.mariadb_storage.observed_at=[DateTime]::UtcNow.ToString('o')
        if($checks.mariadb_storage.state -eq 'READY'){$checks.mariadb_storage.last_success_at=$databaseSuccess}
        foreach($binding in @(@('kernel','server\DRAGONHYDRA-Server.exe'),@('apache','web\apache\bin\httpd.exe'),@('database','web\mariadb\bin\mysqld.exe'))){if(-not(Get-CoreNextHeartbeatChild $binding[0] $binding[1])){return $false}}
        Save-CoreNextHeartbeatSnapshot ([int]$kernel.Id) $true $kernelSuccess $checks
        return $true
    }catch{
        if($knownKernelId -gt 0){try{Save-CoreNextHeartbeatSnapshot $knownKernelId $false $null ([ordered]@{})}catch{}}
        return $false
    }
}
function Web([string]$operation) {
    $php=Join-Path $script:cfg.install_root 'web\php\php.exe'
    $hook=Join-Path $script:cfg.install_root 'web\manage.php'
    $ini=Join-Path $StateRoot 'web-config\php.ini'
    $arguments=if($operation -eq 'prepare'){@('-n',$hook,$configFile,$operation)}else{@('-c',$ini,$hook,$configFile,$operation)}
    $previousPreference=$ErrorActionPreference
    try{$ErrorActionPreference='Continue';$lines=& $php @arguments 2>&1;$code=$LASTEXITCODE}finally{$ErrorActionPreference=$previousPreference}
    $text=$lines -join "`r`n"
    foreach($key in @('root_password','db_password','core_db_password','admin_password')){
        $secret=$script:cfg.$key
        if($secret){$text=$text.Replace($secret,'[REDACTED]')}
    }
    [IO.File]::WriteAllText((Join-Path $StateRoot ('web-'+$operation+'.log')),$text,$utf8)
    if($code -ne 0){throw "Joomla operation $operation failed, exit $code. Inspect the private web-$operation.log."}
    return $text
}
function Start-Owned([string]$role,[string]$exe,[string[]]$arguments,[string]$directory) {
    $p=Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $directory -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $StateRoot ($role+'.stdout.log')) -RedirectStandardError (Join-Path $StateRoot ($role+'.stderr.log'))
    $script:children.Add(@{Role=$role;Process=$p;Executable=$exe})
    return $p
}
function Wait-Port([int]$port,$process) {
    for($i=0;$i -lt 120;$i++){
        if($process.HasExited){throw 'Managed component exited before binding its configured port.'}
        $client=New-Object Net.Sockets.TcpClient
        try{$client.Connect('127.0.0.1',$port);return}catch{Start-Sleep -Milliseconds 250}finally{$client.Dispose()}
    }
    throw "Managed component startup deadline expired for port $port."
}
function Api([string]$method,[string]$path,$body=$null,[string]$key='') {
    $token=(Read-Json (Join-Path $StateRoot 'kernel\local-session.json')).token
    $headers=@{Authorization=('Bearer '+$token)}
    if($key){$headers['Idempotency-Key']=$key}
    $params=@{Uri=('http://127.0.0.1:'+$script:cfg.api_port+'/dragon/api/v1'+$path);Method=$method;Headers=$headers;TimeoutSec=10;UseBasicParsing=$true}
    if($null -ne $body){$params.Body=($body|ConvertTo-Json -Compress);$params.ContentType='application/json'}
    Invoke-RestMethod @params
}
function Stop-OwnedChildren {
    if(@($script:children|Where-Object {$_.Role -eq 'kernel'}).Count){
        try{$null=Api 'POST' '/system/shutdown' @{} }catch{}
    }
    foreach($entry in @($script:children|Where-Object {$_.Role -eq 'kernel'})){
        if(-not $entry.Process.HasExited){$null=$entry.Process.WaitForExit(10000)}
    }
    foreach($entry in @($script:children|Where-Object {$_.Role -eq 'apache'})){
        if(-not $entry.Process.HasExited){
            $parent=$entry.Process.Id
            $descendants=@(Get-CimInstance Win32_Process -Filter ("ParentProcessId="+$parent)|Where-Object {$_.ExecutablePath -eq $entry.Executable})
            foreach($child in $descendants){Stop-Process -Id $child.ProcessId -ErrorAction SilentlyContinue}
            Stop-Process -Id $parent -ErrorAction SilentlyContinue
            $null=$entry.Process.WaitForExit(5000)
        }
    }
    if(@($script:children|Where-Object {$_.Role -eq 'database'}).Count){try{$null=Web 'shutdown'}catch{}}
    foreach($entry in $script:children){
        if(-not $entry.Process.HasExited){$null=$entry.Process.WaitForExit(10000)}
        if(-not $entry.Process.HasExited){Stop-Process -Id $entry.Process.Id -ErrorAction SilentlyContinue}
    }
}

Assert-Path $StateRoot
if($Action -eq 'Install'){
    if(-not([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Installation requires Windows administrator rights.'}
    if(-not $InstallRoot){throw 'InstallRoot is required.'}
    $InstallRoot=[IO.Path]::GetFullPath($InstallRoot).TrimEnd('\');Assert-Path $InstallRoot
    if($StateRoot.StartsWith($InstallRoot+'\',[StringComparison]::OrdinalIgnoreCase) -or $InstallRoot.StartsWith($StateRoot+'\',[StringComparison]::OrdinalIgnoreCase) -or $InstallRoot -eq $StateRoot){throw 'Binary and data directories must be separate.'}
    if(-not $OwnerSid){$OwnerSid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value}
    foreach($file in @('server\DRAGONHYDRA-Server.exe','client\DRAGONHYDRA-Client.exe','workstation\DragonhydraService.exe','web\manage.php','web\payload-manifest.json')){
        if(-not(Test-Path -LiteralPath (Join-Path $InstallRoot $file))){throw "Required packaged component is missing: $file"}
    }
    if(Test-Path -LiteralPath $configFile){
        $script:cfg=Read-Json $configFile
        Assert-CoreNextConfig $script:cfg $coreProfile
        if($script:cfg.install_root -ne $InstallRoot -or $script:cfg.service_name -ne $ServiceName){throw 'Retained state belongs to a different installation; no authority was changed.'}
        $OwnerSid=$script:cfg.owner_sid
    }else{
        if((Test-Path -LiteralPath $StateRoot) -and @(Get-ChildItem -LiteralPath $StateRoot -Force).Count){throw 'The selected data directory is nonempty and not owned by this workstation; it was not changed.'}
        if(Get-Service -Name $ServiceName -ErrorAction SilentlyContinue){throw 'Requested service name already exists; it was not changed.'}
        New-Item -ItemType Directory -Path $StateRoot -Force|Out-Null
        Protect-Directory $StateRoot $OwnerSid -ServiceSpecific
        $apiPort=[int]$coreProfile.ports.api;$webPort=[int]$coreProfile.ports.web;$dbPort=[int]$coreProfile.ports.database
        foreach($port in @($apiPort,$webPort,$dbPort)){Assert-FreePort $port}
        $script:cfg=[pscustomobject][ordered]@{schema_version=1;product_version=$coreProfile.version;install_root=$InstallRoot;state_root=$StateRoot;service_name=$ServiceName;owner_sid=$OwnerSid;api_port=$apiPort;web_port=$webPort;database_port=$dbPort;api_base=('http://127.0.0.1:'+$apiPort+'/dragon/api/v1');bridge_secret_path=(Join-Path $StateRoot 'kernel\joomla-bridge.json');root_password=(Random-Secret);db_name='dragonhydra_admin';db_user='dragonhydra_admin';db_password=(Random-Secret);core_db_name='dragonhydra_core';core_db_user='dragonhydra_core';core_db_password=(Random-Secret);admin_user='dragonadmin';admin_password=(Random-Secret);admin_email='administrator@dragonhydra.invalid';site_name='DRAGONHYDRA';kernel_backend='sqlite';optional_ai=@{enabled=$false;runtime='llama.cpp';endpoint=$null;model_directory=(Join-Path $StateRoot 'models');status='optional_not_installed'};analytics=@{authority='kernel';external_sql_server='optional_not_configured';external_postgresql='optional_not_configured';xlsx_export=$true}}
        foreach($key in @('product','edition','installation_id','environment_id','browser_user_data','cookie_name','joomla_session_suffix','build_id','source_commit','version')){$script:cfg|Add-Member -NotePropertyName $key -NotePropertyValue $coreProfile.$key -Force}
        $script:cfg|Add-Member -NotePropertyName profile_path -NotePropertyValue $ProfilePath -Force
        $script:cfg.db_name=$coreProfile.database.admin_schema;$script:cfg.db_user=$coreProfile.database.admin_user
        $script:cfg.core_db_name=$coreProfile.database.core_schema;$script:cfg.core_db_user=$coreProfile.database.core_user
        $script:cfg.site_name='DRAGONHYDRA CORE NEXT'
        $script:cfg.product_version=$coreProfile.version
        $script:cfg|Add-Member -NotePropertyName service_sid_policy -NotePropertyValue 'unrestricted'
        Assert-CoreNextConfig $script:cfg $coreProfile
        Save-Json $script:cfg $configFile
    }
    if($script:cfg.product_version -cne $coreProfile.version){$script:cfg.product_version=$coreProfile.version;Save-Json $script:cfg $configFile}
    Protect-Directory $StateRoot $OwnerSid -ServiceSpecific:($script:cfg.service_sid_policy -ceq 'unrestricted')
    Protect-Binaries $InstallRoot
    $null=Owned-Service
    foreach($folder in @('kernel','client','models')){New-Item -ItemType Directory -Force -Path (Join-Path $StateRoot $folder)|Out-Null}
    if($SeedSnapshot -or $SeedSnapshotSha256){
        if(-not $SeedSnapshot -or -not $SeedSnapshotSha256){throw 'CORE_NEXT_SEED_PATH_AND_HASH_REQUIRED'}
        $seed=Assert-CoreNextOrdinaryPath $SeedSnapshot (Join-Path $coreProfile.lab_root 'snapshots')
        if(-not(Test-Path -LiteralPath $seed -PathType Leaf) -or (Get-FileHash -LiteralPath $seed -Algorithm SHA256).Hash.ToLowerInvariant() -cne $SeedSnapshotSha256){throw 'CORE_NEXT_SEED_HASH_MISMATCH'}
        $target=Join-Path $StateRoot 'kernel\core.sqlite3'
        if(Test-Path -LiteralPath $target){throw 'CORE_NEXT_SEED_CANNOT_REPLACE_EXISTING_DATABASE'}
        Copy-Item -LiteralPath $seed -Destination $target
        if((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -cne $SeedSnapshotSha256){throw 'CORE_NEXT_SEED_COPY_HASH_MISMATCH'}
        Save-Json @{source=$seed;sha256=$SeedSnapshotSha256;installation_id=$coreProfile.installation_id;provider_schedules='disabled';credentials_copied=$false} (Join-Path $StateRoot 'kernel\seed-snapshot.json')
    }
    Save-Json @{administration_url=('http://127.0.0.1:'+$script:cfg.web_port+'/administrator/');product=$coreProfile.product;edition=$coreProfile.edition;installation_id=$coreProfile.installation_id;environment_id=$coreProfile.environment_id;build_id=$coreProfile.build_id;source_commit=$coreProfile.source_commit;version=$coreProfile.version;profile_path=$ProfilePath;state_root=$StateRoot;install_root=$InstallRoot} (Join-Path $StateRoot 'kernel\product.json')
    Save-Json @{username=$script:cfg.admin_user;password=$script:cfg.admin_password;url=('http://127.0.0.1:'+$script:cfg.web_port+'/administrator/')} (Join-Path $StateRoot 'first-run.json')
    Save-Json @{service_name=$ServiceName;installation_id=$coreProfile.installation_id;browser_user_data=$coreProfile.browser_user_data;profile_path=$ProfilePath} (Join-Path $StateRoot 'launcher.json')
    Save-Json @{install_root=$InstallRoot;state_root=$StateRoot;service_name=$ServiceName;product=$coreProfile.product;installation_id=$coreProfile.installation_id;profile_path=$ProfilePath} (Join-Path $InstallRoot 'workstation-installed.json')
    $service=Owned-Service
    $newServiceCreated=$false
    if(-not $service){
        $image=(Quote (Join-Path $InstallRoot 'workstation\DragonhydraService.exe'))+' --state '+(Quote $StateRoot)+' --name '+$ServiceName
        # Typed CIM avoids Windows PowerShell 5.1 stripping the nested quotes
        # required by a service ImagePath containing spaces and arguments.
        # Keep a reboot from starting a partially provisioned installation. The
        # delayed-auto policy is applied only after SID/profile ACL provisioning.
        $created=Invoke-CimMethod -ClassName Win32_Service -MethodName Create -Arguments @{Name=$ServiceName;DisplayName='DRAGONHYDRA Complete Workstation';PathName=$image;ServiceType=[byte]16;ErrorControl=[byte]1;StartMode='Manual';StartName='NT AUTHORITY\LocalService'}
        if($created.ReturnValue -ne 0){throw ('Owned service registration failed, code '+$created.ReturnValue)}
        $newServiceCreated=$true
        $null=Native (Join-Path $env:WINDIR 'System32\sc.exe') @('description',$ServiceName,'Private DRAGONHYDRA kernel, Joomla web stack and database; loopback only.')
        # A newly registered service has no automatic restart actions. Enable
        # recovery only after genuine first-run readiness below; a broken first
        # installation must retain one controlled failure for reconciliation.
        $null=Native (Join-Path $env:WINDIR 'System32\sc.exe') @('failureflag',$ServiceName,'1')
    }
    $researchSqlEnabled=$false
    $researchConfig=Join-Path $StateRoot 'kernel\research-storage.json'
    if(Test-Path -LiteralPath $researchConfig){$researchSqlEnabled=(Read-Json $researchConfig).provider -ceq 'sqlserver'}
    $sidEvidence=Set-CoreNextOwnedServiceSid -Profile $coreProfile -CreatedNow:$newServiceCreated -Policy $script:cfg.service_sid_policy -SqlEnabled:$researchSqlEnabled
    Save-Json $sidEvidence (Join-Path $StateRoot 'service-sid.json')
    $accessEvidence=Set-CoreNextServiceProfileAccess -Profile $coreProfile -ProfilePath $ProfilePath -SidEvidence $sidEvidence
    Save-Json $accessEvidence (Join-Path $StateRoot 'service-profile-access.json')
    $null=Native (Join-Path $env:WINDIR 'System32\sc.exe') @('config',$ServiceName,'start=','delayed-auto')
    if((Get-Service $ServiceName).Status -ne 'Running'){Status 'queued';Start-Service $ServiceName}
    $deadline=[DateTime]::UtcNow.AddSeconds($StartupTimeout)
    do{
        Start-Sleep -Milliseconds 500
        $statusPath=Join-Path $StateRoot 'status.json'
        if(Test-Path -LiteralPath $statusPath){
            $status=Read-Json $statusPath
            if($status.stage -eq 'ready'){
                if($newServiceCreated){$null=Native (Join-Path $env:WINDIR 'System32\sc.exe') @('failure',$ServiceName,'reset=','86400','actions=','restart/30000/restart/120000/restart/300000')}
                Write-Output ('DRAGONHYDRA ready: http://127.0.0.1:'+$script:cfg.api_port+'; Joomla http://127.0.0.1:'+$script:cfg.web_port+'; service '+$ServiceName);return
            }
            if($status.stage -eq 'failed'){throw ('First-run initialization failed: '+$status.error)}
        }
    }while([DateTime]::UtcNow -lt $deadline)
    throw 'Workstation startup timed out. State and private diagnostics were retained for repair.'
}

if(-not(Test-Path -LiteralPath $configFile)){throw 'This directory has no owned workstation configuration.'}
$script:cfg=Read-Json $configFile
Assert-CoreNextConfig $script:cfg $coreProfile
if($script:cfg.state_root -ne $StateRoot){throw 'State ownership mismatch.'}
if($InstallRoot -and [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\') -ne $script:cfg.install_root){throw 'Installation ownership mismatch.'}
$ServiceName=$script:cfg.service_name
if($Action -eq 'Status'){
    $null=Owned-Service
    if(Test-Path -LiteralPath (Join-Path $StateRoot 'status.json')){Get-Content -LiteralPath (Join-Path $StateRoot 'status.json') -Raw}
    return
}
if($Action -in @('Stop','Uninstall')){
    $service=Owned-Service
    Close-OwnedClient
    if($service -and $service.State -ne 'Stopped'){
        Stop-Service -Name $ServiceName
        (Get-Service $ServiceName).WaitForStatus('Stopped',[TimeSpan]::FromSeconds(70))
    }
    if($Action -eq 'Uninstall' -and $service){$null=Native (Join-Path $env:WINDIR 'System32\sc.exe') @('delete',$ServiceName)}
    Write-Output ('Owned service '+$ServiceName+' '+$Action+' completed. All user data retained at '+$StateRoot)
    return
}

$exitCode=0
try{
    if($script:cfg.service_sid_policy -ceq 'unrestricted'){
        $provision=Read-Json (Join-Path $StateRoot 'service-profile-access.json')
        $access=Test-CoreNextServiceProfileAccess -Profile $coreProfile -ProfilePath $ProfilePath -Provision $provision
        Save-Json $access (Join-Path $StateRoot 'service-profile-access-runtime.json')
    }
    $stopFile=Join-Path $StateRoot 'stop.request'
    if(Test-Path -LiteralPath $stopFile){Remove-Item -LiteralPath $stopFile}
    Status 'preparing'
    foreach($port in @($script:cfg.api_port,$script:cfg.web_port,$script:cfg.database_port)){Assert-FreePort $port}
    $null=Web 'prepare'
    $web=Join-Path $script:cfg.install_root 'web'
    $env:PATH=(Join-Path $web 'php')+';'+(Join-Path $web 'apache\bin')+';'+(Join-Path $web 'mariadb\bin')+';'+$env:WINDIR+'\System32;'+$env:WINDIR
    $mysqlData=Join-Path $StateRoot 'mysql-data'
    if(-not(Test-Path -LiteralPath (Join-Path $mysqlData 'mysql'))){
        Status 'initializing_database'
        $null=Native (Join-Path $web 'mariadb\bin\mysql_install_db.exe') @(('--datadir='+$mysqlData),('--port='+$script:cfg.database_port),'--silent')
    }
    Status 'starting_database'
    $database=Start-Owned 'database' (Join-Path $web 'mariadb\bin\mysqld.exe') @(('--defaults-file='+(Quote (Join-Path $StateRoot 'web-config\my.ini'))),'--console') (Join-Path $web 'mariadb')
    Wait-Port $script:cfg.database_port $database
    $null=Web 'provision'
    Status 'starting_kernel'
    $kernel=Start-Owned 'kernel' (Join-Path $script:cfg.install_root 'server\DRAGONHYDRA-Server.exe') @('--state',(Quote (Join-Path $StateRoot 'kernel')),'--port',[string]$script:cfg.api_port,'--init-bridge') (Join-Path $script:cfg.install_root 'server')
    Wait-Port $script:cfg.api_port $kernel
    for($i=0;$i -lt 60;$i++){
        try{if((Api 'GET' '/health/ready').status -eq 'ready'){break}}catch{Start-Sleep -Milliseconds 500}
        if($i -eq 59){throw 'Kernel readiness deadline expired.'}
    }
    foreach($file in @('endpoint.json','local-session.json')){Copy-Item -LiteralPath (Join-Path $StateRoot ('kernel\'+$file)) -Destination (Join-Path $StateRoot ('client\'+$file)) -Force}
    Status 'initializing_joomla'
    $null=Web 'install'
    $null=Web 'configure'
    Status 'starting_website'
    $apacheRoot=Join-Path $web 'apache'
    $httpConfig=Join-Path $StateRoot 'web-config\httpd.conf'
    $null=Native (Join-Path $apacheRoot 'bin\httpd.exe') @('-t','-d',$apacheRoot,'-f',$httpConfig)
    $apache=Start-Owned 'apache' (Join-Path $apacheRoot 'bin\httpd.exe') @('-d',(Quote $apacheRoot),'-f',(Quote $httpConfig)) $apacheRoot
    Wait-Port $script:cfg.web_port $apache
    $homepage=Invoke-WebRequest -UseBasicParsing -Uri ('http://127.0.0.1:'+$script:cfg.web_port+'/') -TimeoutSec 15
    if($homepage.StatusCode -ne 200){throw 'Joomla homepage is not ready.'}
    Status 'importing_public_sample'
    $job=Api 'POST' '/jobs' @{kind='import_public';mode='retained'} 'workstation-first-run-public-v1'
    for($i=0;$i -lt 240;$i++){
        $result=Api 'GET' ('/jobs/'+$job.id)
        if($result.status -eq 'succeeded'){break}
        if($result.status -in @('failed','cancelled','interrupted')){throw 'Initial retained-data import did not succeed.'}
        Start-Sleep -Milliseconds 500
        if($i -eq 239){throw 'Initial sample import timed out.'}
    }
    Status 'ready'
    $nextHeartbeat=[DateTime]::UtcNow
    while(-not(Test-Path -LiteralPath $stopFile)){
        foreach($entry in $script:children){if($entry.Process.HasExited){throw ('Managed component exited: '+$entry.Role)}}
        if([DateTime]::UtcNow -ge $nextHeartbeat){$null=Write-CoreNextHeartbeat;$nextHeartbeat=[DateTime]::UtcNow.AddSeconds(15)}
        Start-Sleep -Seconds 1
    }
    Status 'stopping'
}catch{
    $message=$_.Exception.Message
    foreach($key in @('root_password','db_password','core_db_password','admin_password')){if($script:cfg.$key){$message=$message.Replace($script:cfg.$key,'[REDACTED]')}}
    Status 'failed' ($script:phase+': '+$message)
    [IO.File]::AppendAllText((Join-Path $StateRoot 'supervisor-errors.log'),[DateTime]::UtcNow.ToString('o')+' '+$message+"`r`n",$utf8)
    $exitCode=1
}finally{
    Stop-OwnedChildren
    if($exitCode -eq 0){Status 'stopped'}
}
exit $exitCode
