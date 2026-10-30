#requires -Version 7.0
[CmdletBinding()]
param([string]$State)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
if (-not $State) { $State=Join-Path $projectRoot 'runtime\product' }
$statePath=[IO.Path]::GetFullPath($State)
if (-not $statePath.StartsWith([IO.Path]::GetFullPath($projectRoot)+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Development state must stay inside the project.' }
$endpointFile=Join-Path $statePath 'endpoint.json'
if (-not (Test-Path -LiteralPath $endpointFile)) { return }
$endpoint=Get-Content -LiteralPath $endpointFile -Raw | ConvertFrom-Json
$python=Join-Path $projectRoot 'runtime\server-env\Scripts\python.exe'
$basePython=(& $python -I -B -c 'import sys; print(sys._base_executable)').Trim()
$proc=Get-CimInstance Win32_Process -Filter "ProcessId=$([int]$endpoint.pid)"
if (-not $proc) { return }
if ($proc.ExecutablePath -notin @($python,$basePython) -or -not $proc.CommandLine.Contains($python) -or $proc.CommandLine -notmatch 'dragonhydra\.server' -or -not $proc.CommandLine.Contains($statePath)) { throw 'Endpoint PID does not belong to this product server; no process was stopped.' }
$token=(Get-Content -LiteralPath (Join-Path $statePath 'local-session.json') -Raw | ConvertFrom-Json).token
$uri=[Uri]$endpoint.url
if ($uri.Scheme -ne 'http' -or $uri.Host -ne '127.0.0.1') { throw 'Refusing shutdown outside the product loopback endpoint.' }
$response=Invoke-RestMethod -Method Post -Uri ($endpoint.url.TrimEnd('/')+'/dragon/api/v1/system/shutdown') -Headers @{Authorization=('Bearer '+$token)} -ContentType 'application/json' -Body '{}' -TimeoutSec 5
$deadline=[DateTime]::UtcNow.AddSeconds(15)
do {
    Start-Sleep -Milliseconds 150
    $running=Get-Process -Id $proc.ProcessId -ErrorAction SilentlyContinue
} while ($running -and [DateTime]::UtcNow -lt $deadline)
if ($running) { throw 'Verified product process did not stop gracefully before its deadline. No unrelated process was stopped.' }
[pscustomobject]@{stopped=$proc.ProcessId;state=$statePath;data_retained=$true;graceful=$true} | ConvertTo-Json -Compress
