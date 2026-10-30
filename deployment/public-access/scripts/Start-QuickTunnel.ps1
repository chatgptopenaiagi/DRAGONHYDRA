#requires -Version 7.0
[CmdletBinding()]
param([string]$GatewayUrl='http://127.0.0.1:18734')
$ErrorActionPreference='Stop'
$deploymentRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$toolRoot=Join-Path $deploymentRoot 'cloudflare'
$stateFile=Join-Path $toolRoot 'quick-tunnel.json'
$binary=Join-Path $toolRoot 'bin\cloudflared.exe'
$config=Join-Path $toolRoot 'quick-tunnel.yml'
$target=$GatewayUrl.TrimEnd('/')
$targetUri=[Uri]$target
if($targetUri.Scheme -ne 'http' -or $targetUri.Host -ne '127.0.0.1' -or $targetUri.AbsolutePath -ne '/' -or $targetUri.UserInfo -or $targetUri.Query -or $targetUri.Fragment){throw 'The tunnel target must be the local restricted gateway origin.'}
if(-not(Test-Path -LiteralPath $binary)){throw 'Run Install-Cloudflared.ps1 before starting the public demo.'}
$receipt=Get-Content -LiteralPath (Join-Path $toolRoot 'install-receipt.json') -Raw|ConvertFrom-Json
if((Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash -ne $receipt.sha256){throw 'Project cloudflared hash changed.'}
$health=Invoke-RestMethod -Uri ($target+'/public-health') -TimeoutSec 5
if($health.status -ne 'ready' -or $health.mode -ne 'read-only-public-gateway'){throw 'The restricted public gateway is not ready.'}
if(Test-Path -LiteralPath $stateFile){
    $existing=Get-Content -LiteralPath $stateFile -Raw|ConvertFrom-Json
    $proc=Get-CimInstance Win32_Process -Filter "ProcessId=$([int]$existing.pid)"
    if($proc -and $proc.ExecutablePath -eq $binary -and $proc.CommandLine.Contains($config) -and $proc.CommandLine.Contains($target)){
        $existing|ConvertTo-Json -Depth 6
        return
    }
    if($proc){throw 'Previous tunnel PID belongs to another process. No process was changed.'}
}
# Explicit project-only configuration prevents accidental use of a user's named-tunnel settings.
'{}'|Set-Content -LiteralPath $config -Encoding utf8
$logs=Join-Path $toolRoot 'logs'
New-Item -ItemType Directory -Path $logs -Force|Out-Null
$stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$stdout=Join-Path $logs ($stamp+'.stdout.log')
$stderr=Join-Path $logs ($stamp+'.stderr.log')
$arguments=@('--no-autoupdate','--config',('"'+$config+'"'),'tunnel','--url',$target,'--protocol','http2','--metrics','127.0.0.1:0','--loglevel','info')
$process=Start-Process -FilePath $binary -ArgumentList $arguments -WorkingDirectory $toolRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
$state=@{schema_version=1;pid=$process.Id;executable=$binary;target=$target;config=$config;protocol='http2';stdout=$stdout;stderr=$stderr;started_at=[DateTime]::UtcNow.ToString('o');public_url=$null;metrics_url=$null;status='starting';temporary=$true;server_sent_events_supported=$false}
$state|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $stateFile -Encoding utf8
$deadline=[DateTime]::UtcNow.AddSeconds(50)
do{
    Start-Sleep -Milliseconds 250
    $process.Refresh()
    $logText=@(Get-Content -LiteralPath $stdout,$stderr -Raw -ErrorAction SilentlyContinue)-join "`n"
    $urls=[regex]::Matches($logText,'https://[a-z0-9-]+\.trycloudflare\.com')
    if($urls.Count){$state.public_url=$urls[$urls.Count-1].Value}
    if($logText -match 'Starting metrics server on (127\.0\.0\.1:\d+)/metrics'){$state.metrics_url='http://'+$Matches[1]}
    if($process.HasExited){$state.status='failed';$state.exit_code=$process.ExitCode;break}
    if($state.public_url -and $logText -match 'Registered tunnel connection'){$state.status='connected';break}
}while([DateTime]::UtcNow -lt $deadline)
if($state.status -eq 'starting'){$state.status=if($state.public_url){'url-issued-connection-pending'}else{'startup-timeout'}}
$state|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $stateFile -Encoding utf8
$state|ConvertTo-Json -Depth 6
if($state.status -ne 'connected'){throw "Quick Tunnel is $($state.status). Inspect project-local tunnel logs."}

