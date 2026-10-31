#requires -Version 7.0
[CmdletBinding()]
param([switch]$NoOpen, [switch]$Browser, [string]$State, [int]$Port=0, [string]$ServerBinary)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
. (Join-Path $PSScriptRoot 'Dragonhydra-ServerOwnership.ps1')
$selection=Resolve-DragonhydraServer $projectRoot $State $ServerBinary
$statePath=$selection.state
New-Item -ItemType Directory -Path $statePath -Force | Out-Null
$endpointFile=Join-Path $statePath 'endpoint.json'
$sessionFile=Join-Path $statePath 'local-session.json'
$endpoint=Get-DragonhydraOwnedEndpoint $selection -Probe
$reused=[bool]$endpoint
if (-not $endpoint) {
    $saved=@{}
    $environmentNames=if($selection.mode -eq 'frozen'){@('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','CONDA_PREFIX','PATH')}else{@('PYTHONPATH')}
    foreach($name in $environmentNames){$saved[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
    try {
        $arguments=@('--host','127.0.0.1','--port',[string]$Port,'--state',('"'+$statePath+'"'))
        if($selection.mode -eq 'source') {
            $env:PYTHONPATH=Join-Path $projectRoot 'src'
            $arguments=@('-B','-m','dragonhydra.server')+$arguments
        } else {
            foreach($name in $environmentNames){[Environment]::SetEnvironmentVariable($name,$null,'Process')}
            $env:PATH=$env:SystemRoot+'\System32;'+$env:SystemRoot
        }
        $server=Start-Process -FilePath $selection.executable -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $statePath 'server.stdout.log') -RedirectStandardError (Join-Path $statePath 'server.stderr.log')
    } finally {foreach($name in $environmentNames){[Environment]::SetEnvironmentVariable($name,$saved[$name],'Process')}}
    $deadline=[DateTime]::UtcNow.AddSeconds(35)
    do {
        Start-Sleep -Milliseconds 250
        $server.Refresh()
        if ($server.HasExited) { throw "Server startup failed (exit $($server.ExitCode)). See $statePath\server.stderr.log" }
        # A new coordinator writes its endpoint before it begins accepting HTTP.
        # Ownership failures propagate; only the initial readiness probe retries.
        $endpoint=Get-DragonhydraOwnedEndpoint $selection
        if($endpoint){try{$endpoint=Get-DragonhydraOwnedEndpoint $selection -Probe}catch [System.Net.Http.HttpRequestException]{$endpoint=$null}}
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
[pscustomobject]@{url=$endpoint.url;pid=$endpoint.pid;state=$statePath;reused=$reused;opened=(-not $NoOpen);client=if(Test-Path -LiteralPath $client){'tauri'}else{'system-browser'};server_mode=$selection.mode;server_binary=if($selection.mode -eq 'frozen'){$selection.executable}else{$null};source_content_sha256=$selection.source_content_sha256} | ConvertTo-Json -Compress
