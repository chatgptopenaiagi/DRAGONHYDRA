#requires -Version 7.0
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$projectRoot=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$state=Join-Path $projectRoot ('runtime\scratch\lifecycle-'+[Guid]::NewGuid().ToString('N'))
$evidence=Join-Path $projectRoot 'runtime\evidence\installation'
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
$checks=[Collections.Generic.List[object]]::new()
$listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,0)
$listener.Start()
$occupiedPort=$listener.LocalEndpoint.Port
try {
    # An existing listener stays alive while the product allocates a separate port.
    $first=& (Join-Path $projectRoot 'scripts\Start-Dragonhydra.ps1') -NoOpen -State $state | ConvertFrom-Json
    if ([Uri]::new($first.url).Port -eq $occupiedPort) { throw 'Product collided with another listener.' }
    $second=& (Join-Path $projectRoot 'scripts\Start-Dragonhydra.ps1') -NoOpen -State $state | ConvertFrom-Json
    if ($first.pid -ne $second.pid -or -not $second.reused) { throw 'Relaunch spawned a duplicate server.' }
    $checks.Add(@{name='start-and-reuse';passed=$true;pid=$first.pid;endpoint=$first.url})
    $checks.Add(@{name='coexists-with-unrelated-listener';passed=$listener.Server.IsBound;occupied_port=$occupiedPort})
    $token=(Get-Content -LiteralPath (Join-Path $state 'local-session.json') -Raw | ConvertFrom-Json).token
    $headers=@{Authorization=('Bearer '+$token)}
    $health=Invoke-RestMethod -Uri ($first.url+'/dragon/api/v1/health/ready') -Headers $headers -TimeoutSec 5
    $checks.Add(@{name='authenticated-readiness';passed=($health.status -in @('ready','ok'))})
    & (Join-Path $projectRoot 'scripts\Stop-Dragonhydra.ps1') -State $state | Out-Null
    $third=& (Join-Path $projectRoot 'scripts\Start-Dragonhydra.ps1') -NoOpen -State $state | ConvertFrom-Json
    $retained=(Get-Content -LiteralPath (Join-Path $state 'local-session.json') -Raw | ConvertFrom-Json).token
    if($token -ne $retained){throw 'Restart lost local pairing.'}
    $checks.Add(@{name='graceful-restart-retains-pairing';passed=$true;pid=$third.pid})
    & (Join-Path $projectRoot 'scripts\Stop-Dragonhydra.ps1') -State $state | Out-Null
    $result=@{created_at=[DateTime]::UtcNow.ToString('o');state=$state;checks=$checks;passed=$true;scope='Development server lifecycle; not a clean product installation test'}
    $result | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $evidence 'development-lifecycle.json') -Encoding utf8
    $result | ConvertTo-Json -Depth 7
} catch {
    @{created_at=[DateTime]::UtcNow.ToString('o');state=$state;checks=$checks;passed=$false;error=$_.Exception.Message} | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $evidence 'development-lifecycle.json') -Encoding utf8
    throw
} finally {
    $listener.Stop()
    if (Test-Path -LiteralPath (Join-Path $state 'endpoint.json')) {
        try { & (Join-Path $projectRoot 'scripts\Stop-Dragonhydra.ps1') -State $state | Out-Null } catch { Write-Warning $_.Exception.Message }
    }
}
