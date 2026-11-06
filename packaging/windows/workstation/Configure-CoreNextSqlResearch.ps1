#requires -Version 5.1
<# Explicit OWNER maintenance, never a service-start hook or an application store.
   Preview performs no SQL connection. Apply must run in a matching-owner
   Windows PowerShell 5.1 child after the exact candidate is installed. #>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ProfilePath,
    [Parameter(Mandatory)][string]$ExpectedInstallationId,
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{40}$')][string]$ExpectedSourceCommit,
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{64}$')][string]$ExpectedServerSha256,
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{64}$')][string]$ExpectedSchemaSha256,
    [Parameter(Mandatory)][string]$SqlServer,
    [string]$Database,
    [switch]$TrustServerCertificate,
    [string]$ReceiptPath,
    [switch]$Apply
)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -eq 5){$env:PSModulePath=Join-Path $PSHOME 'Modules'}
. (Join-Path $PSScriptRoot 'CoreNextProfile.ps1')

function Get-CoreNextSqlHash([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Get-CoreNextSqlHex([byte[]]$Bytes){([BitConverter]::ToString($Bytes)).Replace('-','').ToLowerInvariant()}
# Return one typed binary value; pipeline enumeration otherwise collects Object[].
function Convert-CoreNextSqlHash([string]$Value){,([byte[]]@(for($i=0;$i -lt 64;$i+=2){[Convert]::ToByte($Value.Substring($i,2),16)}))}
function Get-CoreNextSqlNames($Profile){
    $null=Assert-CoreNextProfile $Profile
    if($Profile.environment_id -cne 'candidate'){throw 'CORE_NEXT_SQL_CANDIDATE_REQUIRED'}
    $suffix=$Profile.installation_id.Substring($Profile.installation_id.Length-12)
    [pscustomobject]@{database=('DRAGONHYDRA_CORE_NEXT_SQL_'+$suffix.ToUpperInvariant());principal=('NT SERVICE\'+$Profile.service_name)}
}
function Get-CoreNextSqlSchemaPlan([string]$Path,[string]$ExpectedHash){
    if((Get-CoreNextSqlHash $Path) -cne $ExpectedHash){throw 'CORE_NEXT_SQL_SCHEMA_HASH_MISMATCH'}
    $text=[IO.File]::ReadAllText($Path)
    $tables=@([regex]::Matches($text,'(?im)^CREATE TABLE dbo\.(dh_research_[a-z_]+)\s*\(')|ForEach-Object{$_.Groups[1].Value})
    $triggers=@([regex]::Matches($text,'(?im)^CREATE TRIGGER dbo\.(dh_research_[a-z_]+)\s')|ForEach-Object{$_.Groups[1].Value})
    if($tables.Count -ne 8 -or $triggers.Count -ne 9 -or @($tables|Sort-Object -Unique).Count -ne 8 -or @($triggers|Sort-Object -Unique).Count -ne 9){throw 'CORE_NEXT_SQL_CANONICAL_SCHEMA_REQUIRED'}
    [pscustomobject]@{tables=$tables;triggers=$triggers;batches=@([regex]::Split($text,'(?im)^\s*GO\s*$')|Where-Object{$_.Trim()});sha256=$ExpectedHash}
}
function New-CoreNextSqlGrantPlan([string]$Principal,[string[]]$Tables){
    if($Principal -cnotmatch '^NT SERVICE\\DragonhydraCoreNextcandidate[a-f0-9]{12}$'){throw 'CORE_NEXT_SQL_EXACT_SERVICE_PRINCIPAL_REQUIRED'}
    $expected=@('dh_research_owner','dh_research_migrations','dh_research_archives','dh_research_models','dh_research_predictions','dh_research_inputs','dh_research_notes','dh_research_note_audit')
    if(@(Compare-Object ($Tables|Sort-Object) ($expected|Sort-Object)).Count){throw 'CORE_NEXT_SQL_TABLE_ALLOWLIST_REQUIRED'}
    $grants=@([pscustomobject]@{permission='CONNECT';object=$null;sql=('GRANT CONNECT TO ['+$Principal+']')})
    foreach($table in $expected){$grants+=[pscustomobject]@{permission='SELECT';object=$table;sql=('GRANT SELECT ON OBJECT::dbo.['+$table+'] TO ['+$Principal+']')}}
    foreach($table in @('dh_research_archives','dh_research_models','dh_research_predictions','dh_research_inputs','dh_research_notes')){
        $grants+=[pscustomobject]@{permission='INSERT';object=$table;sql=('GRANT INSERT ON OBJECT::dbo.['+$table+'] TO ['+$Principal+']')}
    }
    $grants+=[pscustomobject]@{permission='UPDATE';object='dh_research_notes';sql=('GRANT UPDATE ON OBJECT::dbo.[dh_research_notes] TO ['+$Principal+']')}
    $grants
}
function Assert-CoreNextSqlSettings($Current,$Expected){
    $integerVersion=($Current.schema_version -is [int] -or $Current.schema_version -is [long])
    if(@(Compare-Object @($Current.PSObject.Properties.Name|Sort-Object) @('provider','schema_version','sqlserver')).Count -or -not $integerVersion -or $Current.schema_version -ne 1 -or $Current.provider -cne 'sqlserver'){throw 'CORE_NEXT_SQL_EXISTING_CONFIGURATION_CONFLICT'}
    $keys=@($Expected.sqlserver.Keys|Sort-Object)
    if(@(Compare-Object @($Current.sqlserver.PSObject.Properties.Name|Sort-Object) $keys).Count){throw 'CORE_NEXT_SQL_EXISTING_CONFIGURATION_CONFLICT'}
    foreach($key in $keys){
        $value=$Current.sqlserver.$key;$wanted=$Expected.sqlserver[$key]
        if($wanted -is [bool]){if($value -isnot [bool] -or $value -ne $wanted){throw 'CORE_NEXT_SQL_EXISTING_CONFIGURATION_CONFLICT'}}
        elseif($wanted -is [int]){if(($value -isnot [int] -and $value -isnot [long]) -or $value -ne $wanted){throw 'CORE_NEXT_SQL_EXISTING_CONFIGURATION_CONFLICT'}}
        elseif($value -isnot [string] -or $value -cne $wanted){throw 'CORE_NEXT_SQL_EXISTING_CONFIGURATION_CONFLICT'}
    }
}
function Get-CoreNextSqlValidatedSettingsHash([string]$Path,[string]$StateRoot,$Expected){
    $Path=Assert-CoreNextOrdinaryPath $Path $StateRoot
    # Validate and hash the same bytes while excluding concurrent file writers.
    $stream=[IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    $reader=$null;$sha=$null
    try{
        if($stream.Length -gt 65536){throw 'CORE_NEXT_SQL_EXISTING_CONFIGURATION_CONFLICT'}
        $reader=[IO.StreamReader]::new($stream,[Text.Encoding]::UTF8,$true,1024,$true)
        $current=$reader.ReadToEnd()|ConvertFrom-Json
        Assert-CoreNextSqlSettings $current $Expected
        $reader.Dispose();$reader=$null;$stream.Position=0
        $sha=[Security.Cryptography.SHA256]::Create()
        Get-CoreNextSqlHex ($sha.ComputeHash($stream))
    }finally{if($reader){$reader.Dispose()};if($sha){$sha.Dispose()};$stream.Dispose()}
}
function New-CoreNextSqlConnectionString([string]$Server,[string]$Target,[bool]$TrustCertificate){
    $builder=New-Object System.Data.SqlClient.SqlConnectionStringBuilder
    # PowerShell adapts this IDictionary through its keys; CLR property spellings
    # such as DataSource are not canonical connection-string keywords.
    $builder['Data Source']=$Server;$builder['Initial Catalog']=$Target;$builder['Integrated Security']=$true
    $builder['Encrypt']=$true;$builder['TrustServerCertificate']=$TrustCertificate
    $builder['Connect Timeout']=5;$builder['Pooling']=$false;$builder['Application Name']='DRAGONHYDRA owned SQL provisioning'
    $builder.ConnectionString
}
function Open-CoreNextSqlOwnerConnection([string]$Target){
    $connectionString=New-CoreNextSqlConnectionString $SqlServer $Target ([bool]$TrustServerCertificate)
    $connection=New-Object System.Data.SqlClient.SqlConnection($connectionString)
    $connection.Open()
    $command=$connection.CreateCommand();$command.CommandTimeout=10;$command.CommandText='SET XACT_ABORT ON; SET LOCK_TIMEOUT 3000;'
    try{$null=$command.ExecuteNonQuery()}finally{$command.Dispose()}
    $connection
}
function Invoke-CoreNextSql($Connection,[string]$Sql,[hashtable]$Parameters=@{},$Transaction=$null,[switch]$Read){
    $command=$Connection.CreateCommand();$command.CommandTimeout=10;$command.CommandText=$Sql
    if($Transaction){$command.Transaction=$Transaction}
    foreach($key in $Parameters.Keys){
        $value=$Parameters[$key]
        if($value -is [datetime]){$parameter=$command.Parameters.Add($key,[Data.SqlDbType]::DateTime2);$parameter.Scale=7;$parameter.Value=$value}
        else{$null=$command.Parameters.AddWithValue($key,$value)}
    }
    try{
        if($Read){$table=New-Object Data.DataTable;$reader=$command.ExecuteReader();try{$table.Load($reader)}finally{$reader.Dispose()};return ,$table}
        $null=$command.ExecuteNonQuery()
    }finally{$command.Dispose()}
}
function Assert-CoreNextOwnedSqlDatabase($Connection,$Schema){
    $exists=Invoke-CoreNextSql $Connection "SELECT OBJECT_ID(N'dbo.dh_research_owner',N'U') AS object_id" -Read
    if($exists.Rows.Count -ne 1 -or $exists.Rows[0].object_id -is [DBNull]){throw 'CORE_NEXT_SQL_DATABASE_NOT_OWNED'}
    $owner=Invoke-CoreNextSql $Connection 'SELECT product_id,schema_version,migration_sha256 FROM dbo.dh_research_owner WHERE owner_key=1' -Read
    if($owner.Rows.Count -ne 1 -or $owner.Rows[0].product_id -cne 'dragonhydra.research-archive' -or $owner.Rows[0].schema_version -ne 1 -or (Get-CoreNextSqlHex $owner.Rows[0].migration_sha256) -cne $Schema.sha256){throw 'CORE_NEXT_SQL_DATABASE_NOT_OWNED'}
    $migration=Invoke-CoreNextSql $Connection 'SELECT checksum FROM dbo.dh_research_migrations WHERE migration_name=@name' @{'@name'='research-archive/1'} -Read
    if($migration.Rows.Count -ne 1 -or (Get-CoreNextSqlHex $migration.Rows[0].checksum) -cne $Schema.sha256){throw 'CORE_NEXT_SQL_MIGRATION_MISMATCH'}
    $objects=Invoke-CoreNextSql $Connection "SELECT name,type FROM sys.objects WHERE schema_id=SCHEMA_ID(N'dbo') AND type IN ('U','TR') AND name LIKE N'dh[_]research[_]%' AND (type='U' OR object_id IN (SELECT object_id FROM sys.triggers WHERE is_disabled=0))" -Read
    $actual=@($objects.Rows|ForEach-Object{([string]$_.name)+'|'+([string]$_.type).Trim()})
    $expected=@($Schema.tables|ForEach-Object{$_+'|U'})+@($Schema.triggers|ForEach-Object{$_+'|TR'})
    if(@(Compare-Object ($actual|Sort-Object) ($expected|Sort-Object)).Count){throw 'CORE_NEXT_SQL_SCHEMA_INCOMPLETE'}
}
function Assert-CoreNextSqlNarrowPrincipal($Master,$Connection,[string]$Principal,[byte[]]$Sid,$Grants){
    $login=Invoke-CoreNextSql $Master 'SELECT sid,type_desc FROM sys.server_principals WHERE name=@name' @{'@name'=$Principal} -Read
    if($login.Rows.Count -ne 1 -or (Get-CoreNextSqlHex $login.Rows[0].sid) -cne (Get-CoreNextSqlHex $Sid) -or $login.Rows[0].type_desc -notin @('WINDOWS_LOGIN','WINDOWS_GROUP')){throw 'CORE_NEXT_SQL_LOGIN_IDENTITY_MISMATCH'}
    $roles=Invoke-CoreNextSql $Master 'SELECT role.name FROM sys.server_role_members m JOIN sys.server_principals member ON member.principal_id=m.member_principal_id JOIN sys.server_principals role ON role.principal_id=m.role_principal_id WHERE member.name=@name' @{'@name'=$Principal} -Read
    if($roles.Rows.Count){throw 'CORE_NEXT_SQL_SERVICE_SERVER_ROLE_FORBIDDEN'}
    $serverPermissions=Invoke-CoreNextSql $Master 'SELECT permission_name,state_desc FROM sys.server_permissions WHERE grantee_principal_id=SUSER_ID(@name)' @{'@name'=$Principal} -Read
    foreach($permission in $serverPermissions.Rows){if($permission.permission_name -cne 'CONNECT SQL' -or $permission.state_desc -cne 'GRANT'){throw 'CORE_NEXT_SQL_SERVICE_SERVER_PERMISSION_FORBIDDEN'}}
    $user=Invoke-CoreNextSql $Connection 'SELECT sid,type_desc FROM sys.database_principals WHERE name=@name' @{'@name'=$Principal} -Read
    if($user.Rows.Count -ne 1 -or (Get-CoreNextSqlHex $user.Rows[0].sid) -cne (Get-CoreNextSqlHex $Sid)){throw 'CORE_NEXT_SQL_USER_IDENTITY_MISMATCH'}
    $roles=Invoke-CoreNextSql $Connection 'SELECT role.name FROM sys.database_role_members m JOIN sys.database_principals member ON member.principal_id=m.member_principal_id JOIN sys.database_principals role ON role.principal_id=m.role_principal_id WHERE member.name=@name' @{'@name'=$Principal} -Read
    if($roles.Rows.Count){throw 'CORE_NEXT_SQL_SERVICE_DATABASE_ROLE_FORBIDDEN'}
    $permissions=Invoke-CoreNextSql $Connection 'SELECT permission_name,state_desc,class_desc,minor_id,OBJECT_NAME(major_id) AS object_name,OBJECT_SCHEMA_NAME(major_id) AS object_schema FROM sys.database_permissions WHERE grantee_principal_id=USER_ID(@name)' @{'@name'=$Principal} -Read
    foreach($permission in $permissions.Rows){
        $object=if($permission.object_name -is [DBNull]){$null}else{[string]$permission.object_name}
        $classOkay=($null -eq $object -and $permission.class_desc -ceq 'DATABASE' -and $permission.permission_name -ceq 'CONNECT') -or ($null -ne $object -and $permission.class_desc -ceq 'OBJECT_OR_COLUMN' -and $permission.object_schema -ceq 'dbo' -and $permission.minor_id -eq 0)
        if(-not $classOkay -or $permission.state_desc -cne 'GRANT' -or -not @($Grants|Where-Object{$_.permission -ceq $permission.permission_name -and $_.object -ceq $object})){throw 'CORE_NEXT_SQL_SERVICE_DATABASE_PERMISSION_FORBIDDEN'}
    }
}
function Save-CoreNextSqlReceipt($Record,[string]$Path,[string]$LabRoot){
    $Path=Assert-CoreNextOrdinaryPath $Path $LabRoot
    $temporary=Assert-CoreNextOrdinaryPath ($Path+'.tmp') $LabRoot
    if(Test-Path -LiteralPath $temporary){throw 'CORE_NEXT_SQL_UNRECONCILED_RECEIPT_TEMP'}
    if(-not ('Dragonhydra.Workstation.AtomicFile' -as [type])){
        $library=Assert-CoreNextOrdinaryPath (Join-Path $PSScriptRoot 'DragonhydraAtomicFile.dll') $LabRoot
        if(-not(Test-Path -LiteralPath $library -PathType Leaf)){throw 'CORE_NEXT_SQL_ATOMIC_HELPER_REQUIRED'}
        Add-Type -Path $library -ErrorAction Stop
    }
    [IO.File]::WriteAllText($temporary,($Record|ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
    # Keep File.Replace's nullable backup inside the existing typed helper:
    # Windows PowerShell 5.1 converts a direct $null backup to an illegal path.
    [Dragonhydra.Workstation.AtomicFile]::Commit($temporary,$Path)
}

$profile=Read-CoreNextProfile $ProfilePath -CheckService
$names=Get-CoreNextSqlNames $profile
if($profile.installation_id -cne $ExpectedInstallationId -or $profile.source_commit -cne $ExpectedSourceCommit){throw 'CORE_NEXT_SQL_EXPECTED_PROFILE_REQUIRED'}
if(-not $Database){$Database=$names.database}
if($Database -cne $names.database){throw 'CORE_NEXT_SQL_PROFILE_DATABASE_REQUIRED'}
if($SqlServer -cnotmatch '^lpc:' -or ($SqlServer -ine ('lpc:'+$env:COMPUTERNAME) -and $SqlServer -ine 'lpc:localhost' -and $SqlServer -cne 'lpc:.')){throw 'CORE_NEXT_SQL_EXPLICIT_LOCAL_LPC_REQUIRED'}
$configPath=Join-Path $profile.state_root 'workstation.json'
$null=Assert-CoreNextOrdinaryPath $configPath $profile.state_root
$config=Get-Content -LiteralPath $configPath -Raw|ConvertFrom-Json
Assert-CoreNextConfig $config $profile
if($config.service_sid_policy -cne 'unrestricted'){throw 'CORE_NEXT_SQL_SERVICE_SID_POLICY_REQUIRED'}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
if($identity.User.Value -cne $config.owner_sid){throw 'CORE_NEXT_SQL_MATCHING_OWNER_REQUIRED'}
$serverExe=Join-Path $profile.install_root 'server\DRAGONHYDRA-Server.exe'
$serverInfoPath=Join-Path $profile.install_root 'server\BUILD-INFO.json'
$null=Assert-CoreNextOrdinaryPath $serverExe $profile.install_root
$null=Assert-CoreNextOrdinaryPath $serverInfoPath $profile.install_root
$serverInfo=Get-Content -LiteralPath $serverInfoPath -Raw|ConvertFrom-Json
if((Get-CoreNextSqlHash $serverExe) -cne $ExpectedServerSha256 -or $serverInfo.source_sha -cne $ExpectedSourceCommit -or $serverInfo.version -cne $profile.version){throw 'CORE_NEXT_SQL_INSTALLED_SERVER_BINDING_MISMATCH'}
$schemaPath=Join-Path $profile.install_root 'server\_internal\dragonhydra\research_storage\schema_sqlserver.sql'
$null=Assert-CoreNextOrdinaryPath $schemaPath $profile.install_root
$schema=Get-CoreNextSqlSchemaPlan $schemaPath $ExpectedSchemaSha256
$grants=@(New-CoreNextSqlGrantPlan $names.principal $schema.tables)
$service=Get-CimInstance Win32_Service -Filter ("Name='"+$profile.service_name+"'")
$expected='"'+$profile.install_root+'\workstation\DragonhydraService.exe" --state "'+$profile.state_root+'" --name '+$profile.service_name
if(-not $service -or $service.PathName -cne $expected -or $service.StartName -ine 'NT AUTHORITY\LocalService'){throw 'CORE_NEXT_SQL_INSTALLED_SERVICE_NOT_OWNED'}
$sidQuery=& (Join-Path $env:WINDIR 'System32\sc.exe') qsidtype $profile.service_name
if($LASTEXITCODE -ne 0 -or ($sidQuery -join "`n") -notmatch 'SERVICE_SID_TYPE:\s*UNRESTRICTED'){throw 'CORE_NEXT_SQL_SERVICE_SID_UNVERIFIED'}
$settings=[ordered]@{schema_version=1;provider='sqlserver';sqlserver=[ordered]@{server=$SqlServer;database=$Database;driver='ODBC Driver 18 for SQL Server';
    authentication='windows_integrated';encrypt=$true;trust_server_certificate=[bool]$TrustServerCertificate;connection_timeout_seconds=5;query_timeout_seconds=10}}
$settingsPath=Join-Path $profile.state_root 'kernel\research-storage.json'
$null=Assert-CoreNextOrdinaryPath $settingsPath $profile.state_root
if(Test-Path -LiteralPath $settingsPath){
    $null=Get-CoreNextSqlValidatedSettingsHash $settingsPath $profile.state_root $settings
}
$plan=[ordered]@{schema_version='dragonhydra.core-next.sql-provisioning/1';mode=$(if($Apply){'apply'}else{'preview'});installation_id=$profile.installation_id;
    source_commit=$ExpectedSourceCommit;service_name=$profile.service_name;database=$Database;server=$SqlServer;principal=$names.principal;server_sha256=$ExpectedServerSha256;
    schema_sha256=$ExpectedSchemaSha256;selected_object_grants=@($grants|ForEach-Object{@{permission=$_.permission;object=$_.object}});
    owner_provision_only=$true;service_restart_performed=$false;no_service_database_creation_permission=$true;no_global_roles=$true}
$plan.service_account='NT AUTHORITY\LocalService';$plan.service_sid_type='UNRESTRICTED'
$plan.verification_scope='Owner provisioning/configuration only; actual installed-service ODBC identity and permissions remain unverified'
if(-not $Apply){$plan|ConvertTo-Json -Depth 6;return}
if($PSVersionTable.PSVersion.Major -ne 5 -or -not [Environment]::Is64BitProcess){throw 'CORE_NEXT_SQL_NATIVE_WINDOWS_POWERSHELL_51_REQUIRED'}
$ReceiptPath=Assert-CoreNextOrdinaryPath $ReceiptPath $profile.lab_root
if(Test-Path -LiteralPath $ReceiptPath){throw 'CORE_NEXT_SQL_FRESH_RECEIPT_REQUIRED'}
if(-not(Test-Path -LiteralPath (Split-Path $ReceiptPath -Parent) -PathType Container)){throw 'CORE_NEXT_SQL_PRIVATE_RECEIPT_PARENT_REQUIRED'}
$lockPath=Assert-CoreNextOrdinaryPath ($ReceiptPath+'.started.lock') $profile.lab_root
$lock=[IO.File]::Open($lockPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
$record=[ordered]@{};foreach($key in $plan.Keys){$record[$key]=$plan[$key]}
$record.passed=$false;$record.stage='validated';$record.started_at=[DateTime]::UtcNow.ToString('o');$record.automatic_retry=$false
$master=$null;$target=$null;$transaction=$null
try{
    Save-CoreNextSqlReceipt $record $ReceiptPath $profile.lab_root
    Add-Type -AssemblyName System.Data
    $sid=Get-CoreNextServiceSid -Profile $profile
    $sidBytes=New-Object byte[] $sid.BinaryLength;$sid.GetBinaryForm($sidBytes,0);$record.service_sid=$sid.Value
    $master=Open-CoreNextSqlOwnerConnection 'master'
    $exists=Invoke-CoreNextSql $master 'SELECT DB_ID(@name) AS database_id' @{'@name'=$Database} -Read
    if($exists.Rows[0].database_id -is [DBNull]){
        Invoke-CoreNextSql $master ('CREATE DATABASE ['+$Database+']')
        $record.new_database_created=$true
        $target=Open-CoreNextSqlOwnerConnection $Database
        $count=Invoke-CoreNextSql $target 'SELECT COUNT(*) AS count FROM sys.tables WHERE is_ms_shipped=0' -Read
        if($count.Rows[0].count -ne 0){throw 'CORE_NEXT_SQL_NEW_DATABASE_NOT_EMPTY'}
        $transaction=$target.BeginTransaction()
        foreach($batch in $schema.batches){Invoke-CoreNextSql $target $batch @{} $transaction}
        $at=[DateTime]::UtcNow;$checksum=Convert-CoreNextSqlHash $schema.sha256
        Invoke-CoreNextSql $target 'INSERT INTO dbo.dh_research_owner VALUES(1,@product,1,@checksum,@at)' @{'@product'='dragonhydra.research-archive';'@checksum'=$checksum;'@at'=$at} $transaction
        Invoke-CoreNextSql $target 'INSERT INTO dbo.dh_research_migrations VALUES(@name,@checksum,@at)' @{'@name'='research-archive/1';'@checksum'=$checksum;'@at'=$at} $transaction
        $transaction.Commit();$transaction.Dispose();$transaction=$null
    }else{$record.new_database_created=$false;$target=Open-CoreNextSqlOwnerConnection $Database}
    Assert-CoreNextOwnedSqlDatabase $target $schema
    $record.owned_database_verified=$true;$record.stage='owned_schema_verified';Save-CoreNextSqlReceipt $record $ReceiptPath $profile.lab_root
    $login=Invoke-CoreNextSql $master 'SELECT sid FROM sys.server_principals WHERE name=@name' @{'@name'=$names.principal} -Read
    if(-not $login.Rows.Count){Invoke-CoreNextSql $master ('CREATE LOGIN ['+$names.principal+'] FROM WINDOWS')}
    $user=Invoke-CoreNextSql $target 'SELECT sid FROM sys.database_principals WHERE name=@name' @{'@name'=$names.principal} -Read
    if(-not $user.Rows.Count){Invoke-CoreNextSql $target ('CREATE USER ['+$names.principal+'] FOR LOGIN ['+$names.principal+']')}
    Assert-CoreNextSqlNarrowPrincipal $master $target $names.principal $sidBytes $grants
    foreach($grant in $grants){Invoke-CoreNextSql $target $grant.sql}
    Assert-CoreNextSqlNarrowPrincipal $master $target $names.principal $sidBytes $grants
    $record.stage='object_grants_verified';Save-CoreNextSqlReceipt $record $ReceiptPath $profile.lab_root
    $null=Assert-CoreNextOrdinaryPath $settingsPath $profile.state_root
    if(-not(Test-Path -LiteralPath $settingsPath)){
        $temporary=$settingsPath+'.'+[Guid]::NewGuid().ToString('N')+'.tmp'
        $null=Assert-CoreNextOrdinaryPath $temporary $profile.state_root
        [IO.File]::WriteAllText($temporary,($settings|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
        $acl=New-Object Security.AccessControl.FileSecurity;$acl.SetAccessRuleProtection($true,$false)
        foreach($owner in @('S-1-5-18','S-1-5-32-544',$config.owner_sid)){
            $account=New-Object Security.Principal.SecurityIdentifier($owner)
            $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($account,'FullControl','Allow')))
        }
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($sid,'Read','Allow')))
        Set-Acl -LiteralPath $temporary -AclObject $acl
        $null=Assert-CoreNextOrdinaryPath $settingsPath $profile.state_root
        [IO.File]::Move($temporary,$settingsPath)
    }
    $record.configuration_sha256=Get-CoreNextSqlValidatedSettingsHash $settingsPath $profile.state_root $settings
    $record.configuration_reload_required=$true
    $record.authentication_verification='NOT_RUN: actual ODBC connection from the installed service remains mandatory'
    $record.passed=$true;$record.stage='configured_restart_required';$record.finished_at=[DateTime]::UtcNow.ToString('o')
    Save-CoreNextSqlReceipt $record $ReceiptPath $profile.lab_root
    @{passed=$true;receipt=$ReceiptPath;receipt_sha256=(Get-CoreNextSqlHash $ReceiptPath);service_restart_performed=$false}|ConvertTo-Json
}catch{
    $primaryFailure=$_
    if($transaction){try{$transaction.Rollback()}catch{};try{$transaction.Dispose()}catch{}}
    $record.passed=$false;$record.stage='failed_reconciliation_required';$record.failure_code='CORE_NEXT_SQL_OWNER_PROVISIONING_FAILED'
    $record.failure_class=$primaryFailure.Exception.GetType().Name
    $record.failure_line=$primaryFailure.InvocationInfo.ScriptLineNumber
    if($primaryFailure.Exception.InnerException){$record.failure_inner_class=$primaryFailure.Exception.InnerException.GetType().Name}
    if($primaryFailure.Exception -is [Data.SqlClient.SqlException]){$record.sql_error_number=$primaryFailure.Exception.Number;$record.sql_server_state=$primaryFailure.Exception.State}
    $record.finished_at=[DateTime]::UtcNow.ToString('o')
    $failure=[InvalidOperationException]::new('CORE_NEXT_SQL_OWNER_PROVISIONING_FAILED',$primaryFailure.Exception)
    try{Save-CoreNextSqlReceipt $record $ReceiptPath $profile.lab_root}
    catch{$failure.Data['receipt_failure_class']=$_.Exception.GetType().Name}
    # Preserve the original provisioning exception even if the failure receipt
    # cannot be committed; never let that secondary error hide the first one.
    throw $failure
}finally{
    if($target){$target.Dispose()};if($master){$master.Dispose()};$lock.Dispose()
}
