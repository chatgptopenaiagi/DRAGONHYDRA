#requires -Version 7.0
[CmdletBinding()]
param([switch]$NoOpen, [switch]$Browser, [string]$State, [int]$Port=0)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
if (-not $State) { $State=Join-Path $projectRoot 'runtime\product' }
$statePath=[IO.Path]::GetFullPath($State)
$expectedRoot=[IO.Path]::GetFullPath($projectRoot)+[IO.Path]::DirectorySeparatorChar
if (-not $statePath.StartsWith($expectedRoot,[StringComparison]::OrdinalIgnoreCase)) { throw 'Development state must stay inside the project.' }
New-Item -ItemType Directory -Path $statePath -Force | Out-Null
$endpointFile=Join-Path $statePath 'endpoint.json'
$sessionFile=Join-Path $statePath 'local-session.json'
$python=Join-Path $projectRoot 'runtime\server-env\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Project server environment is missing. See the verified build/status record for setup.' }
$basePython=(& $python -I -B -c 'import sys; print(sys._base_executable)').Trim()
function Get-OwnedEndpoint {
    if (-not (Test-Path -LiteralPath $endpointFile)) { return $null }
    try {
        $endpoint=Get-Content -LiteralPath $endpointFile -Raw | ConvertFrom-Json
        $uri=[Uri]$endpoint.url
        if ($uri.Scheme -ne 'http' -or $uri.Host -ne '127.0.0.1') { return $null }
        $proc=Get-CimInstance Win32_Process -Filter "ProcessId=$([int]$endpoint.pid)"
        if (-not $proc -or $proc.ExecutablePath -notin @($python,$basePython) -or -not $proc.CommandLine.Contains($python) -or $proc.CommandLine -notmatch 'dragonhydra\.server' -or -not $proc.CommandLine.Contains($statePath)) { return $null }
        $probeToken=(Get-Content -LiteralPath $sessionFile -Raw | ConvertFrom-Json).token
        $health=Invoke-RestMethod -Uri ($endpoint.url.TrimEnd('/')+'/dragon/api/v1/health/ready') -Headers @{Authorization=('Bearer '+$probeToken)} -TimeoutSec 3
        if ($health.status -ne 'ready' -and $health.status -ne 'ok') { return $null }
        return $endpoint
    } catch { return $null }
}
$endpoint=Get-OwnedEndpoint
$reused=[bool]$endpoint
if (-not $endpoint) {
    $oldPythonPath=$env:PYTHONPATH
    try {
        $env:PYTHONPATH=Join-Path $projectRoot 'src'
        $arguments=@('-B','-m','dragonhydra.server','--host','127.0.0.1','--port',[string]$Port,'--state',('"'+$statePath+'"'))
        $server=Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $statePath 'server.stdout.log') -RedirectStandardError (Join-Path $statePath 'server.stderr.log')
    } finally { $env:PYTHONPATH=$oldPythonPath }
    $deadline=[DateTime]::UtcNow.AddSeconds(35)
    do {
        Start-Sleep -Milliseconds 250
        $server.Refresh()
        if ($server.HasExited) { throw "Server startup failed (exit $($server.ExitCode)). See $statePath\server.stderr.log" }
        $endpoint=Get-OwnedEndpoint
    } while (-not $endpoint -and [DateTime]::UtcNow -lt $deadline)
    if (-not $endpoint) { throw "Server readiness timed out. See $statePath\server.stderr.log" }
}
$token=(Get-Content -LiteralPath $sessionFile -Raw | ConvertFrom-Json).token
if (-not $token) { throw 'Local pairing file is missing a token.' }
$launchUrl=$endpoint.url.TrimEnd('/')+'/#token='+[Uri]::EscapeDataString($token)
$client=Join-Path $projectRoot 'dist\DRAGONHYDRA-Client-x64.exe'
if (-not $NoOpen) {
    if (-not $Browser -and (Test-Path -LiteralPath $client)) {
        Start-Process -FilePath $client -ArgumentList @('--state',('"'+$statePath+'"')) -WorkingDirectory $projectRoot | Out-Null
    } else { Start-Process $launchUrl | Out-Null }
}
[pscustomobject]@{url=$endpoint.url;pid=$endpoint.pid;state=$statePath;reused=$reused;opened=(-not $NoOpen);client=if(Test-Path -LiteralPath $client){'tauri'}else{'system-browser'}} | ConvertTo-Json -Compress
