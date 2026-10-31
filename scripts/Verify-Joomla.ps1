#requires -Version 7.0
[CmdletBinding()]
param(
    [ValidateSet('Prepare','Start','Install','Configure','Status','Stop')][string]$Action='Status',
    [string]$ApiBase='http://127.0.0.1:50299/dragon/api/v1',
    [string]$BridgeSecretPath='C:\xampp\DRAGONHYDRA\runtime\product\joomla-bridge.json',
    [int]$WebPort=18732,
    [int]$DatabasePort=18733
)
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$state=Join-Path $project 'runtime\scratch\joomla-integration'
$evidence=Join-Path $project 'runtime\product-evidence\joomla'
$php=Join-Path $state 'php84\php.exe'
$site=Join-Path $state 'site'
$config=Join-Path $state 'private.json'
$processFile=Join-Path $state 'processes.json'
$harness=Join-Path $project 'server\joomla\integration\manage.php'
$apache='C:\xampp\apache\bin\httpd.exe'
$mysql='C:\xampp\mysql\bin\mysqld.exe'
$apacheConfig=Join-Path $state 'httpd.conf'
$mysqlConfig=Join-Path $state 'my.ini'
if (-not $state.StartsWith($project+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid integration workspace' }
New-Item -ItemType Directory -Force -Path $state,$evidence | Out-Null

function Protect-OwnedDirectory([string]$directory) {
    $identity=[Security.Principal.WindowsIdentity]::GetCurrent().Name
    $acl=Get-Acl -LiteralPath $directory
    $acl.SetAccessRuleProtection($true,$false)
    foreach($principal in @($identity,'NT AUTHORITY\SYSTEM')) {
        $rule=[Security.AccessControl.FileSystemAccessRule]::new($principal,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $directory -AclObject $acl
}
function Invoke-Checked([string]$executable,[string[]]$arguments,[string]$log) {
    $output=& $executable @arguments 2>&1
    $exit=$LASTEXITCODE
    if($log){$output | Set-Content -LiteralPath (Join-Path $evidence $log) -Encoding utf8NoBOM}
    $output | Write-Output
    if($exit -ne 0){throw "Owned integration command failed with exit $exit; see $log"}
}
function Assert-FreePort([int]$port) {
    $listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,$port)
    try{$listener.Start()}catch{throw "Product integration port $port is occupied; no existing listener was stopped."}finally{$listener.Stop()}
}
function Wait-OwnedPort([int]$port,[int]$pidValue) {
    for($attempt=0;$attempt -lt 40;$attempt++) {
        if(-not(Get-Process -Id $pidValue -ErrorAction SilentlyContinue)){throw "Owned process $pidValue exited before readiness; inspect integration logs."}
        $client=[Net.Sockets.TcpClient]::new()
        try{$client.Connect('127.0.0.1',$port); return} catch {Start-Sleep -Milliseconds 250} finally {$client.Dispose()}
    }
    throw "Owned process did not bind port $port before its startup deadline."
}
function Load-Config {
    if(-not(Test-Path -LiteralPath $config)){throw 'Run -Action Prepare first.'}
    return Get-Content -LiteralPath $config -Raw | ConvertFrom-Json
}

if($Action -eq 'Prepare') {
    Protect-OwnedDirectory $state
    $downloads=Join-Path $state 'downloads'; New-Item -ItemType Directory -Force -Path $downloads | Out-Null
    $artifacts=@(
        @{name='Joomla_6-2-0-Stable-Full_Package.zip';url='https://downloads.joomla.org/cms/joomla6/6-2-0/Joomla_6-2-0-Stable-Full_Package.zip?format=zip';algorithm='SHA1';hash='67a107c83b3084701a1a4acb151cd0452e5deaaf';destination=$site},
        @{name='php-8.4.27-1-Win32-vs17-x64.zip';url='https://downloads.php.net/~windows/releases/php-8.4.27-1-Win32-vs17-x64.zip';algorithm='SHA256';hash='53db2047139bdfb8e6c7c7d5860a0a6a2a4f1dcac49fcf18ae610a14d8ccdf5b';destination=(Join-Path $state 'php84')}
    )
    $receipts=@()
    foreach($artifact in $artifacts) {
        $file=Join-Path $downloads $artifact.name
        if(-not(Test-Path -LiteralPath $file)){Invoke-WebRequest -Uri $artifact.url -OutFile $file -TimeoutSec 120}
        $hash=(Get-FileHash -LiteralPath $file -Algorithm $artifact.algorithm).Hash.ToLowerInvariant()
        if($hash -ne $artifact.hash){throw "Checksum mismatch: $($artifact.name)"}
        if(-not(Test-Path -LiteralPath $artifact.destination)){Expand-Archive -LiteralPath $file -DestinationPath $artifact.destination}
        $receipts+=@{name=$artifact.name;url=$artifact.url;verification_algorithm=$artifact.algorithm;expected=$artifact.hash;actual=$hash;sha256=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant();bytes=(Get-Item -LiteralPath $file).Length}
    }
    $receipts | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $evidence 'downloads.json') -Encoding utf8NoBOM
    if(-not(Test-Path -LiteralPath $config)) {
        $cfg=@{site=$site.Replace('\','/');database_port=$DatabasePort;web_port=$WebPort;api_base=$ApiBase;bridge_secret_path=$BridgeSecretPath;admin_username='dragon-integration';reader_username='dragon-reader'}
        foreach($key in 'root_password','database_password','admin_password','reader_password'){$cfg[$key]=[Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(24))+'aA!9'}
        $cfg | ConvertTo-Json | Set-Content -LiteralPath $config -Encoding utf8NoBOM
    }
    $p=(Join-Path $state 'php84').Replace('\','/')
    $temp=(Join-Path $state 'temp').Replace('\','/')
    New-Item -ItemType Directory -Force -Path $temp,(Join-Path $state 'sessions') | Out-Null
    @(( 'extension_dir="'+$p+'/ext"'),'extension=curl','extension=fileinfo','extension=gd','extension=intl','extension=mbstring','extension=mysqli','extension=openssl','extension=pdo_mysql','extension=sodium','extension=zip','date.timezone=UTC','memory_limit=256M','max_execution_time=60','upload_max_filesize=64M','post_max_size=64M','display_errors=Off','log_errors=On',('error_log="'+$state.Replace('\','/')+'/php-error.log"'),'error_reporting=E_ALL','session.use_strict_mode=1',('session.save_path="'+$state.Replace('\','/')+'/sessions"'),('sys_temp_dir="'+$temp+'"'),('upload_tmp_dir="'+$temp+'"')) | Set-Content -LiteralPath (Join-Path $p 'php.ini') -Encoding utf8NoBOM
    Invoke-Checked $php @('-v') 'php-version.txt'
    Invoke-Checked $php @('-m') 'php-modules.txt'
    'Pinned Joomla/PHP artifacts verified. Test credentials are protected in private.json and were not printed.'
    exit
}

$cfg=Load-Config
if($Action -eq 'Start') {
    if(Test-Path -LiteralPath $processFile){
        $existing=Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
        if(Get-Process -Id $existing.mysql -ErrorAction SilentlyContinue){throw 'Owned database is already running; use Status or Stop.'}
    }
    Assert-FreePort $cfg.database_port; Assert-FreePort $cfg.web_port
    $dbData=Join-Path $state 'mysql-data'
    if(-not(Test-Path -LiteralPath (Join-Path $dbData 'mysql'))) {
        Invoke-Checked 'C:\xampp\mysql\bin\mysql_install_db.exe' @(('--datadir='+$dbData),('--password='+$cfg.root_password),('--port='+$cfg.database_port),'--silent') 'database-initialize.txt'
    }
    $s=$state.Replace('\','/')
    @('[mysqld]','basedir=C:/xampp/mysql',('datadir="'+$dbData.Replace('\','/')+'"'),('port='+$cfg.database_port),'bind-address=127.0.0.1','skip-name-resolve','max_connections=20','innodb_buffer_pool_size=64M','performance_schema=OFF',('pid-file="'+$s+'/mysql.pid"'),('log-error="'+$s+'/mysql-error.log"')) | Set-Content -LiteralPath $mysqlConfig -Encoding utf8NoBOM
    $mysqlProcess=Start-Process -FilePath $mysql -ArgumentList @(('--defaults-file="'+$mysqlConfig+'"'),'--console') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $state 'mysql.stdout.log') -RedirectStandardError (Join-Path $state 'mysql.stderr.log')
    @{mysql=$mysqlProcess.Id;apache=0;mysql_config=$mysqlConfig;apache_config=$apacheConfig} | ConvertTo-Json | Set-Content -LiteralPath $processFile -Encoding utf8NoBOM
    Wait-OwnedPort $cfg.database_port $mysqlProcess.Id
    Invoke-Checked $php @($harness,$config,'provision') 'database-provision.txt'
    $p=(Join-Path $state 'php84').Replace('\','/')
    $web=$site.Replace('\','/')
    @('ServerRoot "C:/xampp/apache"',('Listen 127.0.0.1:'+$cfg.web_port),('ServerName 127.0.0.1:'+$cfg.web_port),('PidFile "'+$s+'/apache.pid"'),('ErrorLog "'+$s+'/apache-error.log"'),'LogLevel warn','LoadModule authz_core_module modules/mod_authz_core.so','LoadModule authz_host_module modules/mod_authz_host.so','LoadModule dir_module modules/mod_dir.so','LoadModule mime_module modules/mod_mime.so','LoadModule log_config_module modules/mod_log_config.so','LoadModule headers_module modules/mod_headers.so',('LoadFile "'+$p+'/php8ts.dll"'),('LoadModule php_module "'+$p+'/php8apache2_4.dll"'),('PHPIniDir "'+$p+'"'),'AddHandler application/x-httpd-php .php','DirectoryIndex index.php',('DocumentRoot "'+$web+'"'),('<Directory "'+$web+'">'),'AllowOverride None','Options -Indexes','Require all granted','</Directory>','<Files "configuration.php">','Require all denied','</Files>','ServerTokens Prod','ServerSignature Off','Header always set X-Content-Type-Options nosniff') | Set-Content -LiteralPath $apacheConfig -Encoding utf8NoBOM
    Invoke-Checked $apache @('-t','-f',$apacheConfig) 'apache-config-test.txt'
    $apacheProcess=Start-Process -FilePath $apache -ArgumentList @('-f',$apacheConfig) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $state 'apache.stdout.log') -RedirectStandardError (Join-Path $state 'apache.stderr.log')
    @{mysql=$mysqlProcess.Id;apache=$apacheProcess.Id;mysql_config=$mysqlConfig;apache_config=$apacheConfig} | ConvertTo-Json | Set-Content -LiteralPath $processFile -Encoding utf8NoBOM
    Wait-OwnedPort $cfg.web_port $apacheProcess.Id
    Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in $cfg.database_port,$cfg.web_port } | Select-Object LocalAddress,LocalPort,OwningProcess | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'listeners.json') -Encoding utf8NoBOM
    "Owned integration stack bound http://127.0.0.1:$($cfg.web_port); database loopback:$($cfg.database_port)."
} elseif($Action -eq 'Install') {
    if(-not(Test-Path -LiteralPath (Join-Path $site 'configuration.php'))){Invoke-Checked $php @($harness,$config,'install') 'joomla-install.txt'}
    $package=Join-Path $project 'dist\pkg_dragonhydra-0.3.0.zip'
    Invoke-Checked $php @((Join-Path $site 'cli\joomla.php'),'extension:install',('--path='+$package),'--no-interaction') 'extension-install.txt'
    Invoke-Checked $php @($harness,$config,'configure') 'extension-configure.txt'
    Invoke-Checked $php @($harness,$config,'status') 'database-status.json'
} elseif($Action -eq 'Configure') {
    $cfg.api_base=$ApiBase; $cfg.bridge_secret_path=$BridgeSecretPath
    $cfg | ConvertTo-Json | Set-Content -LiteralPath $config -Encoding utf8NoBOM
    Invoke-Checked $php @($harness,$config,'configure') 'extension-configure.txt'
} elseif($Action -eq 'Status') {
    Invoke-Checked $php @($harness,$config,'status') 'database-status.json'
} elseif($Action -eq 'Stop') {
    if(-not(Test-Path -LiteralPath $processFile)){return}
    $owned=Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
    if(Get-Process -Id $owned.mysql -ErrorAction SilentlyContinue){
        Invoke-Checked $php @($harness,$config,'shutdown') 'database-shutdown.txt'
        for($attempt=0;$attempt -lt 40 -and (Get-Process -Id $owned.mysql -ErrorAction SilentlyContinue);$attempt++){Start-Sleep -Milliseconds 250}
    }
    $ownedWeb=Get-CimInstance Win32_Process -Filter "Name='httpd.exe'" | Where-Object {$_.CommandLine -and $_.CommandLine.Contains($apacheConfig)}
    foreach($process in $ownedWeb){Stop-Process -Id $process.ProcessId -ErrorAction SilentlyContinue}
    'Stopped only the private database via authenticated shutdown and Apache processes carrying the exact owned configuration path.'
}
