#requires -Version 7.0
[CmdletBinding()]
param([string]$State, [string]$ServerBinary)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
. (Join-Path $PSScriptRoot 'Dragonhydra-ServerOwnership.ps1')
$selection=Resolve-DragonhydraServer $projectRoot $State $ServerBinary
$statePath=$selection.state
$endpointFile=Join-Path $statePath 'endpoint.json'
if (-not (Test-Path -LiteralPath $endpointFile)) { return }
$endpoint=Get-DragonhydraOwnedEndpoint $selection -Probe
if(-not $endpoint){return}
$ownedProcessId=[int]$endpoint.pid
$token=(Get-Content -LiteralPath (Join-Path $statePath 'local-session.json') -Raw | ConvertFrom-Json).token
$uri=[Uri]$endpoint.url
if ($uri.Scheme -ne 'http' -or $uri.Host -ne '127.0.0.1') { throw 'Refusing shutdown outside the product loopback endpoint.' }
$response=Invoke-RestMethod -Method Post -Uri ($endpoint.url.TrimEnd('/')+'/dragon/api/v1/system/shutdown') -Headers @{Authorization=('Bearer '+$token)} -ContentType 'application/json' -Body '{}' -TimeoutSec 5
$deadline=[DateTime]::UtcNow.AddSeconds(15)
do {
    Start-Sleep -Milliseconds 150
    $running=Get-Process -Id $ownedProcessId -ErrorAction SilentlyContinue
} while ($running -and [DateTime]::UtcNow -lt $deadline)
if ($running) { throw 'Verified product process did not stop gracefully before its deadline. No unrelated process was stopped.' }
[pscustomobject]@{stopped=$ownedProcessId;state=$statePath;data_retained=$true;graceful=$true;server_mode=$selection.mode} | ConvertTo-Json -Compress
