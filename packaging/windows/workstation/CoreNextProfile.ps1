#requires -Version 5.1
# Pure profile validation; dot-sourcing does not install, bind ports or write state.
function Assert-CoreNextOrdinaryPath([string]$Path,[string]$Root) {
    if(-not [IO.Path]::IsPathRooted($Path) -or $Path.IndexOfAny([char[]]"`"`r`n") -ge 0 -or $Path -match '(?:^|[\\/])\.\.(?:[\\/]|$)'){throw 'CORE_NEXT_ABSOLUTE_ORDINARY_PATH_REQUIRED'}
    $full=[IO.Path]::GetFullPath($Path).TrimEnd('\');$boundary=[IO.Path]::GetFullPath($Root).TrimEnd('\')
    if(-not $full.StartsWith($boundary+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'CORE_NEXT_PATH_OUTSIDE_LAB'}
    $walk=$full
    while($walk){
        # A missing future leaf is permitted, but an unreadable existing path is
        # not evidence that it is ordinary. Force terminating provider errors so
        # validation stays fail-closed even when the caller uses Continue.
        $item=$null
        try{$item=Get-Item -LiteralPath $walk -Force -ErrorAction Stop}
        catch{
            $denied=$_.CategoryInfo.Category -in @('PermissionDenied','SecurityError')
            $cause=$_.Exception
            while($cause){if($cause -is [UnauthorizedAccessException]){$denied=$true};$cause=$cause.InnerException}
            if($denied){throw [UnauthorizedAccessException]::new(('CORE_NEXT_PATH_ACCESS_DENIED: '+$walk),$_.Exception)}
            if($_.Exception -isnot [Management.Automation.ItemNotFoundException] -or $_.CategoryInfo.Category -ne 'ObjectNotFound'){throw}
        }
        if($item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'CORE_NEXT_REPARSE_PATH_REJECTED'}
        $next=Split-Path -Path $walk -Parent;if($next -eq $walk){break};$walk=$next
    }
    $full
}
function Assert-CoreNextProfile($Profile,[string]$LabRoot='C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB',[switch]$CheckService) {
    if($Profile.schema_version -ne 1 -or $Profile.product -cne 'DRAGONHYDRA CORE NEXT' -or $Profile.edition -cne 'CORE NEXT' -or $Profile.installation_id -cnotmatch '^core-next-[a-f0-9]{32}$' -or $Profile.environment_id -cnotin @('baseline','candidate')){throw 'CORE_NEXT_PROFILE_IDENTITY_REQUIRED'}
    $lab=[IO.Path]::GetFullPath($LabRoot).TrimEnd('\')
    if($Profile.lab_root -ine $lab){throw 'CORE_NEXT_LAB_IDENTITY_MISMATCH'}
    $root=Join-Path $lab ('profiles\'+$Profile.installation_id)
    $suffix=$Profile.installation_id.Substring($Profile.installation_id.Length-12)
    foreach($pair in @(@('install_root','application'),@('state_root','state'),@('browser_user_data','browser'))){
        $actual=Assert-CoreNextOrdinaryPath $Profile.($pair[0]) $lab
        if($actual -ine (Join-Path $root $pair[1])){throw 'CORE_NEXT_PROFILE_PATH_IDENTITY_MISMATCH'}
    }
    $service='DragonhydraCoreNext'+$Profile.environment_id+$suffix
    if($Profile.service_name -cne $service -or $service -notmatch '^Dragonhydra[A-Za-z0-9_-]{0,60}$' -or $Profile.uninstall_id -cne ('DRAGONHYDRA-CORE-NEXT-'+$Profile.installation_id) -or $Profile.shortcut_name -cne ('DRAGONHYDRA CORE NEXT '+$Profile.environment_id+' '+$suffix)){throw 'CORE_NEXT_SERVICE_OR_SHELL_IDENTITY_MISMATCH'}
    $ports=@([int]$Profile.ports.api,[int]$Profile.ports.web,[int]$Profile.ports.database)
    if(@($ports|Sort-Object -Unique).Count -ne 3 -or @($ports|Where-Object {$_ -lt 18800 -or $_ -gt 65535}).Count){throw 'CORE_NEXT_DISTINCT_ISOLATED_PORTS_REQUIRED'}
    foreach($pair in @(@('admin_schema','dhcn_admin_'),@('admin_user','dhcn_admin_'),@('core_schema','dhcn_core_'),@('core_user','dhcn_core_'))){if($Profile.database.($pair[0]) -cne ($pair[1]+$suffix)){throw 'CORE_NEXT_DATABASE_IDENTITY_MISMATCH'}}
    if($Profile.cookie_name -cne ('dhcn_'+$suffix) -or $Profile.joomla_session_suffix -cne $Profile.installation_id){throw 'CORE_NEXT_SESSION_IDENTITY_MISMATCH'}
    if($Profile.provider_schedules -cne 'disabled' -or $Profile.copy_credentials -ne $false){throw 'CORE_NEXT_FRESH_PRIVATE_STATE_REQUIRED'}
    if($Profile.api_namespace -cne '/dragon/api/v1' -or $Profile.kernel_schema_version -ne 1 -or $Profile.source_commit -cnotmatch '^[a-f0-9]{40}$' -or -not $Profile.build_id -or $Profile.version -cnotmatch '^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?$'){throw 'CORE_NEXT_BUILD_CONTRACT_REQUIRED'}
    if($CheckService){
        $existing=Get-CimInstance Win32_Service -Filter ("Name='"+$service+"'")
        $expected='"'+(Join-Path $Profile.install_root 'workstation\DragonhydraService.exe')+'" --state "'+$Profile.state_root+'" --name '+$service
        if($existing -and ($existing.PathName -cne $expected -or $existing.StartName -ine 'NT AUTHORITY\LocalService')){throw 'CORE_NEXT_EXISTING_SERVICE_NOT_OWNED'}
    }
    $Profile
}
function Read-CoreNextProfile([string]$Path,[switch]$CheckService) {
    $null=Assert-CoreNextOrdinaryPath $Path 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB'
    if(-not(Test-Path -LiteralPath $Path -PathType Leaf -ErrorAction Stop)){throw 'CORE_NEXT_PROFILE_MISSING'}
    try{$profile=Get-Content -LiteralPath $Path -Raw -ErrorAction Stop|ConvertFrom-Json -ErrorAction Stop}
    catch [UnauthorizedAccessException]{throw [UnauthorizedAccessException]::new(('CORE_NEXT_PROFILE_READ_ACCESS_DENIED: '+$Path),$_.Exception)}
    $profile=Assert-CoreNextProfile $profile -CheckService:$CheckService
    if([IO.Path]::GetFullPath($Path) -ine (Join-Path (Split-Path $profile.install_root -Parent) 'installation-profile.json')){throw 'CORE_NEXT_CANONICAL_PROFILE_PATH_REQUIRED'}
    $profile
}
function Assert-CoreNextConfig($Config,$Profile) {
    foreach($key in @('installation_id','product','edition','environment_id','install_root','state_root','service_name','browser_user_data','cookie_name','joomla_session_suffix')){if($Config.$key -cne $Profile.$key){throw 'CORE_NEXT_PERSISTED_BINDING_MISMATCH'}}
    if($Config.api_port -ne $Profile.ports.api -or $Config.web_port -ne $Profile.ports.web -or $Config.database_port -ne $Profile.ports.database){throw 'CORE_NEXT_PERSISTED_PORT_MISMATCH'}
    if($Config.db_name -cne $Profile.database.admin_schema -or $Config.db_user -cne $Profile.database.admin_user -or $Config.core_db_name -cne $Profile.database.core_schema -or $Config.core_db_user -cne $Profile.database.core_user){throw 'CORE_NEXT_PERSISTED_DATABASE_MISMATCH'}
}
function New-CoreNextProfileObject([string]$Environment='candidate',[string]$SourceCommit,[string]$Version,[string]$BuildId,[string]$LabRoot='C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB',[int[]]$ReservedPorts=@()) {
    if($SourceCommit -cnotmatch '^[a-f0-9]{40}$' -or $Version -cnotmatch '^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?$'){throw 'CORE_NEXT_RELEASE_IDENTITY_REQUIRED'}
    $lab=[IO.Path]::GetFullPath($LabRoot).TrimEnd('\');$id='core-next-'+[Guid]::NewGuid().ToString('N');$suffix=$id.Substring($id.Length-12)
    $profileRoot=Join-Path $lab ('profiles\'+$id);$ports=@()
    for($port=18800;$port -le 65535;$port++){if($port -notin $ReservedPorts){$ports+=$port;if($ports.Count -eq 3){break}}}
    if($ports.Count -ne 3){throw 'CORE_NEXT_NO_AVAILABLE_PORT_TRIPLE'}
    if(-not $BuildId){$BuildId='setup-'+$SourceCommit.Substring(0,12)}
    $profile=[pscustomobject][ordered]@{schema_version=1;product='DRAGONHYDRA CORE NEXT';edition='CORE NEXT';installation_id=$id;environment_id=$Environment;lab_root=$lab;
        install_root=(Join-Path $profileRoot 'application');state_root=(Join-Path $profileRoot 'state');browser_user_data=(Join-Path $profileRoot 'browser');
        service_name=('DragonhydraCoreNext'+$Environment+$suffix);shortcut_name=('DRAGONHYDRA CORE NEXT '+$Environment+' '+$suffix);uninstall_id=('DRAGONHYDRA-CORE-NEXT-'+$id);
        ports=@{api=$ports[0];web=$ports[1];database=$ports[2]};database=@{admin_schema=('dhcn_admin_'+$suffix);admin_user=('dhcn_admin_'+$suffix);core_schema=('dhcn_core_'+$suffix);core_user=('dhcn_core_'+$suffix)};
        cookie_name=('dhcn_'+$suffix);joomla_session_suffix=$id;provider_schedules='disabled';copy_credentials=$false;
        api_namespace='/dragon/api/v1';kernel_schema_version=1;source_commit=$SourceCommit;build_id=$BuildId;version=$Version;created_utc=[DateTime]::UtcNow.ToString('o')}
    Assert-CoreNextProfile $profile -LabRoot $lab
}
function New-CoreNextPrivateProfileDirectory([string]$Path,[string]$LabRoot='C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB') {
    $directory=Assert-CoreNextOrdinaryPath $Path $LabRoot
    if((Split-Path -Path $directory -Parent) -ine (Join-Path $LabRoot 'profiles') -or (Split-Path -Path $directory -Leaf) -cnotmatch '^core-next-[a-f0-9]{32}$'){throw 'CORE_NEXT_NEW_PROFILE_PATH_REQUIRED'}
    # Never re-ACL an existing installation. No profile contents are written until
    # the newly created directory has stopped inheriting broad laboratory access.
    if(Test-Path -LiteralPath $directory -ErrorAction Stop){throw 'CORE_NEXT_NEW_PROFILE_PATH_REQUIRED'}
    $null=New-Item -ItemType Directory -Path $directory -ErrorAction Stop
    $acl=Get-Acl -LiteralPath $directory -ErrorAction Stop
    $acl.SetAccessRuleProtection($true,$false)
    $owner=[Security.Principal.WindowsIdentity]::GetCurrent().User
    foreach($sid in @([Security.Principal.SecurityIdentifier]::new('S-1-5-18'),[Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'),$owner)){
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow'))
    }
    # Set-Acl preserves the directory's existing owner; service-specific access
    # is added only after the installer registers and verifies its own service.
    Set-Acl -LiteralPath $directory -AclObject $acl -ErrorAction Stop
    $directory
}
function New-CoreNextInstallationProfile([string]$Environment='candidate',[string]$SourceCommit,[string]$Version,[string]$BuildId) {
    $lab='C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB';$profiles=Join-Path $lab 'profiles'
    $used=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue|Select-Object -ExpandProperty LocalPort)
    if(Test-Path -LiteralPath $profiles){
        $null=Assert-CoreNextOrdinaryPath (Join-Path $profiles 'reserved-profile-check') $lab
        foreach($directory in Get-ChildItem -LiteralPath $profiles -Directory){
            if($directory.Name -notmatch '^core-next-[a-f0-9]{32}$' -or $directory.Attributes -band [IO.FileAttributes]::ReparsePoint){continue}
            $file=Join-Path $directory.FullName 'installation-profile.json'
            if(Test-Path -LiteralPath $file){try{$reserved=Read-CoreNextProfile $file;$used+=@([int]$reserved.ports.api,[int]$reserved.ports.web,[int]$reserved.ports.database)}catch{throw 'CORE_NEXT_EXISTING_PROFILE_RESERVATION_INVALID'}}
        }
    }
    $profile=New-CoreNextProfileObject -Environment $Environment -SourceCommit $SourceCommit -Version $Version -BuildId $BuildId -ReservedPorts $used
    $directory=Split-Path $profile.install_root -Parent
    $null=Assert-CoreNextOrdinaryPath $directory $lab
    if(Test-Path -LiteralPath $directory){throw 'CORE_NEXT_NEW_PROFILE_PATH_REQUIRED'}
    $null=New-CoreNextPrivateProfileDirectory $directory -LabRoot $lab
    $file=Join-Path $directory 'installation-profile.json'
    [IO.File]::WriteAllText($file,($profile|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
    [pscustomobject]@{profile_path=$file;profile=$profile}
}
function Assert-CoreNextReleaseBinding($Profile,[string]$Version,[string]$SourceCommit) {
    if($Version -and $Version -cne $Profile.version){throw 'CORE_NEXT_RELEASE_VERSION_MISMATCH'}
    if($SourceCommit -and $SourceCommit -cne $Profile.source_commit){throw 'CORE_NEXT_RELEASE_SOURCE_MISMATCH'}
}
function Assert-CoreNextInstallerMarker($Ini,$Profile,[string]$ProfilePath) {
    if($Ini.Identity -cne 'DRAGONHYDRA CORE NEXT v1' -or $Ini.InstallRoot -ine $Profile.install_root -or $Ini.StateRoot -ine $Profile.state_root -or $Ini.ServiceName -cne $Profile.service_name -or $Ini.InstallationId -cne $Profile.installation_id -or $Ini.ProfilePath -ine $ProfilePath -or $Ini.ShortcutName -cne $Profile.shortcut_name -or $Ini.UninstallId -cne $Profile.uninstall_id){throw 'CORE_NEXT_INSTALLER_MARKER_NOT_OWNED'}
}
