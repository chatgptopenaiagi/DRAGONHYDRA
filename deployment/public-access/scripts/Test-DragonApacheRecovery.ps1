#requires -Version 7.0
[CmdletBinding()]
param([string]$PublicUrl='')
$ErrorActionPreference='Stop'
$publicRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$project=[IO.Path]::GetFullPath((Join-Path $publicRoot '..\..'))
$originConfig=Join-Path $project 'runtime\scratch\joomla-integration\httpd.conf'
$apache='C:\xampp\apache\bin\httpd.exe'
$output=Join-Path $publicRoot 'evidence\apache-recovery.json'
$logRoot=Join-Path $publicRoot 'logs'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $output),$logRoot | Out-Null
if(-not $PublicUrl){$PublicUrl=(Get-Content -LiteralPath (Join-Path $publicRoot 'cloudflare\quick-tunnel.json') -Raw | ConvertFrom-Json).public_url}
$uri=[Uri]$PublicUrl
if($uri.Scheme -ne 'https' -or -not $uri.Host.EndsWith('.trycloudflare.com') -or $uri.UserInfo -or $uri.Query){throw 'Use the recorded active public HTTPS tunnel URL.'}
$public=$PublicUrl.TrimEnd('/')
function Http-Probe([string]$address) {
    $stamp=[DateTime]::UtcNow.ToString('o')
    try {
        $r=Invoke-WebRequest -Uri $address -TimeoutSec 20 -SkipHttpErrorCheck
        return @{url=$address;at=$stamp;status=[int]$r.StatusCode;body=$r.Content}
    }catch{return @{url=$address;at=$stamp;status=$null;error=$_.Exception.GetType().Name}}
}
function Owned-Apache {
    $pattern='(?:^|\s)-f\s+"?'+[Regex]::Escape($originConfig)+'"?(?:\s|$)'
    @(Get-CimInstance Win32_Process -Filter "Name='httpd.exe'" | Where-Object {
        $_.ExecutablePath -eq $apache -and $_.CommandLine -match $pattern
    })
}
function Safe-Probe($probe) {
    $copy=@{}; foreach($key in $probe.Keys){if($key -ne 'body'){$copy[$key]=$probe[$key]}}
    if($probe.body){$copy.bytes=[Text.Encoding]::UTF8.GetByteCount([string]$probe.body)}
    return $copy
}
$receipt=[ordered]@{started_at=[DateTime]::UtcNow.ToString('o');status='running';scope='Only product-owned Apache processes using the exact existing integration httpd.conf';database_stopped=$false;kernel_stopped=$false;config_changed=$false;public_url=$public;assertions=@()}
$before=Owned-Apache
if($before.Count -lt 1){throw 'No running Apache process was proven to use the exact product-owned configuration; nothing stopped.'}
$unrelated=@(Get-CimInstance Win32_Process -Filter "Name='httpd.exe'" | Where-Object {$_.ProcessId -notin $before.ProcessId} | Select-Object ProcessId,CreationDate)
$receipt.before_pids=@($before.ProcessId)
$receipt.unrelated_before=$unrelated
$receipt.config_path=$originConfig
$receipt.executable=$apache
$localBefore=Http-Probe 'http://127.0.0.1:18734/'
$publicBefore=Http-Probe ($public+'/')
$apiBefore=Http-Probe 'http://127.0.0.1:18734/dragon/api/v1/matches?limit=1'
$receipt.before=@{local=(Safe-Probe $localBefore);public=(Safe-Probe $publicBefore);api=(Safe-Probe $apiBefore)}
if($localBefore.status -ne 200 -or $publicBefore.status -ne 200 -or $apiBefore.status -ne 200){throw 'Pre-outage baseline did not pass; no Apache process was stopped.'}
$totalBefore=($apiBefore.body | ConvertFrom-Json).total
$receipt.before.match_count=$totalBefore
$wasStopped=$false
try {
    # Every PID is checked again immediately before stopping. No service command,
    # port-based process search, unrelated PID or database stop is performed.
    foreach($item in ($before | Sort-Object ParentProcessId)) {
        $current=Get-CimInstance Win32_Process -Filter ('ProcessId='+$item.ProcessId) -ErrorAction SilentlyContinue
        if($current) {
            if($current.ExecutablePath -ne $apache -or $current.CommandLine -notmatch ('(?:^|\s)-f\s+"?'+[Regex]::Escape($originConfig)+'"?(?:\s|$)')){throw 'Apache PID ownership changed; refusing to stop it.'}
            Stop-Process -Id $item.ProcessId -ErrorAction Stop
            $wasStopped=$true
        }
    }
    for($i=0;$i -lt 40 -and (Owned-Apache).Count;$i++){Start-Sleep -Milliseconds 100}
    if((Owned-Apache).Count){throw 'Owned Apache processes did not exit before deadline.'}
    $down=Http-Probe 'http://127.0.0.1:18734/'
    $publicDown=Http-Probe ($public+'/')
    $apiDown=Http-Probe 'http://127.0.0.1:18734/dragon/api/v1/matches?limit=1'
    $receipt.outage=@{local=(Safe-Probe $down);public=(Safe-Probe $publicDown);api=(Safe-Probe $apiDown);friendly_message=($down.body -match 'DRAGONHYDRA is reconnecting' -and $down.body -match 'Please reload shortly');public_friendly_message=($publicDown.body -match 'DRAGONHYDRA is reconnecting')}
    if($apiDown.status -eq 200){$receipt.outage.match_count=($apiDown.body | ConvertFrom-Json).total}
}catch{$receipt.failure=$_.Exception.Message}
finally {
    if($wasStopped -and -not(Owned-Apache).Count) {
        $syntax=& $apache -t -f $originConfig 2>&1
        $syntax | Set-Content -LiteralPath (Join-Path $logRoot 'apache-recovery-syntax.log') -Encoding utf8NoBOM
        if($LASTEXITCODE -eq 0) {
            $started=Start-Process -FilePath $apache -ArgumentList @('-f',$originConfig) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot 'apache-recovery.stdout.log') -RedirectStandardError (Join-Path $logRoot 'apache-recovery.stderr.log')
            $receipt.restart_parent_pid=$started.Id
            for($i=0;$i -lt 40;$i++) {
                $client=[Net.Sockets.TcpClient]::new()
                try{$client.Connect('127.0.0.1',18732);break}catch{Start-Sleep -Milliseconds 250}finally{$client.Dispose()}
            }
        }else{$receipt.failure='Existing Apache configuration failed syntax verification during restore.'}
    }
}
$localAfter=Http-Probe 'http://127.0.0.1:18734/'
$publicAfter=Http-Probe ($public+'/')
$apiAfter=Http-Probe 'http://127.0.0.1:18734/dragon/api/v1/matches?limit=1'
$receipt.after=@{local=(Safe-Probe $localAfter);public=(Safe-Probe $publicAfter);api=(Safe-Probe $apiAfter);pids=@((Owned-Apache).ProcessId)}
if($apiAfter.status -eq 200){$receipt.after.match_count=($apiAfter.body | ConvertFrom-Json).total}
$unrelatedAfter=@(Get-CimInstance Win32_Process -Filter "Name='httpd.exe'" | Where-Object {$_.ProcessId -in $unrelated.ProcessId} | Select-Object ProcessId,CreationDate)
$receipt.unrelated_after=$unrelatedAfter
$receipt.unrelated_preserved=(@($unrelated.ProcessId | Sort-Object) -join ',') -eq (@($unrelatedAfter.ProcessId | Sort-Object) -join ',')
if($receipt.outage.local.status -eq 503 -and $receipt.outage.friendly_message){$receipt.assertions+='Actual origin outage produced a friendly HTTP503 through the still-running gateway'}
if($receipt.outage.public.status -eq 503 -and $receipt.outage.public_friendly_message){$receipt.assertions+='The active public HTTPS tunnel returned the same friendly HTTP503 during origin outage'}
if($receipt.outage.match_count -eq $totalBefore){$receipt.assertions+='Kernel read API retained the same match count while Apache was down'}
if($localAfter.status -eq 200 -and $publicAfter.status -eq 200){$receipt.assertions+='The exact same Apache executable/configuration restored local and public homepages to HTTP200'}
if($receipt.after.match_count -eq $totalBefore){$receipt.assertions+='Match count retained after recovery'}
if($receipt.unrelated_preserved){$receipt.assertions+='Every unrelated Apache process observed before the test was preserved'}
$receipt.status=if($receipt.assertions.Count -eq 6 -and -not $receipt.failure){'passed'}else{'failed'}
$receipt.finished_at=[DateTime]::UtcNow.ToString('o')
$receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $output -Encoding utf8NoBOM
$receipt | ConvertTo-Json -Depth 10
if($receipt.status -ne 'passed'){exit 1}
