#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('Install','Run','Stop','Uninstall','Status')][string]$Action,
    [string]$InstallRoot,
    [string]$StateRoot=(Join-Path $env:ProgramData 'DRAGONHYDRA'),
    [ValidatePattern('^Dragonhydra[A-Za-z0-9_-]{0,60}$')][string]$ServiceName='DragonhydraWorkstation',
    [string]$OwnerSid,
    [int]$StartupTimeout=300
)
$ErrorActionPreference='Stop'
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
function Protect-Directory([string]$path,[string]$owner) {
    $acl=New-Object Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true,$false)
    foreach($sid in @('S-1-5-18','S-1-5-32-544','S-1-5-19',$owner)|Select-Object -Unique){
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
        if($script:cfg.install_root -ne $InstallRoot -or $script:cfg.service_name -ne $ServiceName){throw 'Retained state belongs to a different installation; no authority was changed.'}
        $OwnerSid=$script:cfg.owner_sid
    }else{
        if((Test-Path -LiteralPath $StateRoot) -and @(Get-ChildItem -LiteralPath $StateRoot -Force).Count){throw 'The selected data directory is nonempty and not owned by this workstation; it was not changed.'}
        if(Get-Service -Name $ServiceName -ErrorAction SilentlyContinue){throw 'Requested service name already exists; it was not changed.'}
        New-Item -ItemType Directory -Path $StateRoot -Force|Out-Null
        Protect-Directory $StateRoot $OwnerSid
        $apiPort=Free-Port 18743 @();$webPort=Free-Port 18740 @($apiPort);$dbPort=Free-Port 18741 @($apiPort,$webPort)
        $script:cfg=[pscustomobject][ordered]@{schema_version=1;product_version='0.4.1-dev.1';install_root=$InstallRoot;state_root=$StateRoot;service_name=$ServiceName;owner_sid=$OwnerSid;api_port=$apiPort;web_port=$webPort;database_port=$dbPort;api_base=('http://127.0.0.1:'+$apiPort+'/dragon/api/v1');bridge_secret_path=(Join-Path $StateRoot 'kernel\joomla-bridge.json');root_password=(Random-Secret);db_name='dragonhydra_admin';db_user='dragonhydra_admin';db_password=(Random-Secret);core_db_name='dragonhydra_core';core_db_user='dragonhydra_core';core_db_password=(Random-Secret);admin_user='dragonadmin';admin_password=(Random-Secret);admin_email='administrator@dragonhydra.invalid';site_name='DRAGONHYDRA';kernel_backend='sqlite';optional_ai=@{enabled=$false;runtime='llama.cpp';endpoint='http://127.0.0.1:18746';model_directory=(Join-Path $StateRoot 'models');status='optional_not_installed'};analytics=@{authority='kernel';external_sql_server='optional_not_configured';external_postgresql='optional_not_configured';xlsx_export=$true}}
        Save-Json $script:cfg $configFile
    }
    Protect-Directory $StateRoot $OwnerSid
    Protect-Binaries $InstallRoot
    $null=Owned-Service
    foreach($folder in @('kernel','client','models')){New-Item -ItemType Directory -Force -Path (Join-Path $StateRoot $folder)|Out-Null}
    Save-Json @{administration_url=('http://127.0.0.1:'+$script:cfg.web_port+'/administrator/')} (Join-Path $StateRoot 'kernel\product.json')
    Save-Json @{username=$script:cfg.admin_user;password=$script:cfg.admin_password;url=('http://127.0.0.1:'+$script:cfg.web_port+'/administrator/')} (Join-Path $StateRoot 'first-run.json')
    Save-Json @{service_name=$ServiceName} (Join-Path $StateRoot 'launcher.json')
    Save-Json @{install_root=$InstallRoot;state_root=$StateRoot;service_name=$ServiceName;product='DRAGONHYDRA Workstation'} (Join-Path $InstallRoot 'workstation-installed.json')
    $service=Owned-Service
    if(-not $service){
        $image=(Quote (Join-Path $InstallRoot 'workstation\DragonhydraService.exe'))+' --state '+(Quote $StateRoot)+' --name '+$ServiceName
        # Typed CIM avoids Windows PowerShell 5.1 stripping the nested quotes
        # required by a service ImagePath containing spaces and arguments.
        $created=Invoke-CimMethod -ClassName Win32_Service -MethodName Create -Arguments @{Name=$ServiceName;DisplayName='DRAGONHYDRA Complete Workstation';PathName=$image;ServiceType=[byte]16;ErrorControl=[byte]1;StartMode='Automatic';StartName='NT AUTHORITY\LocalService'}
        if($created.ReturnValue -ne 0){throw ('Owned service registration failed, code '+$created.ReturnValue)}
        $null=Native (Join-Path $env:WINDIR 'System32\sc.exe') @('description',$ServiceName,'Private DRAGONHYDRA kernel, Joomla web stack and database; loopback only.')
        $null=Native (Join-Path $env:WINDIR 'System32\sc.exe') @('failure',$ServiceName,'reset=','86400','actions=','restart/30000/restart/120000/restart/300000')
        $null=Native (Join-Path $env:WINDIR 'System32\sc.exe') @('failureflag',$ServiceName,'1')
    }
    $null=Native (Join-Path $env:WINDIR 'System32\sc.exe') @('config',$ServiceName,'start=','delayed-auto')
    if((Get-Service $ServiceName).Status -ne 'Running'){Status 'queued';Start-Service $ServiceName}
    $deadline=[DateTime]::UtcNow.AddSeconds($StartupTimeout)
    do{
        Start-Sleep -Milliseconds 500
        $statusPath=Join-Path $StateRoot 'status.json'
        if(Test-Path -LiteralPath $statusPath){
            $status=Read-Json $statusPath
            if($status.stage -eq 'ready'){Write-Output ('DRAGONHYDRA ready: http://127.0.0.1:'+$script:cfg.api_port+'; Joomla http://127.0.0.1:'+$script:cfg.web_port+'; service '+$ServiceName);return}
            if($status.stage -eq 'failed'){throw ('First-run initialization failed: '+$status.error)}
        }
    }while([DateTime]::UtcNow -lt $deadline)
    throw 'Workstation startup timed out. State and private diagnostics were retained for repair.'
}

if(-not(Test-Path -LiteralPath $configFile)){throw 'This directory has no owned workstation configuration.'}
$script:cfg=Read-Json $configFile
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
    while(-not(Test-Path -LiteralPath $stopFile)){
        foreach($entry in $script:children){if($entry.Process.HasExited){throw ('Managed component exited: '+$entry.Role)}}
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
