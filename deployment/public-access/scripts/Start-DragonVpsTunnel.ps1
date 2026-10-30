#requires -Version 7.0
[CmdletBinding()]
param(
    [string]$ConfigFile=(Join-Path $PSScriptRoot '..\vps\target.json'),
    [switch]$Connect
)
$ErrorActionPreference='Stop'
$publicRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$ssh=Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'
$keygen=Join-Path $env:WINDIR 'System32\OpenSSH\ssh-keygen.exe'
$result=[ordered]@{status='requires_configuration';deployed=$false;connection_started=$false;checks=@();missing=@();target=$null}
if(-not(Test-Path -LiteralPath $ConfigFile)) {
    $result.missing+=@('An actual authorized VPS target.json is not configured. Copy target.example.json and supply the target and independently verified key material.')
    $result | ConvertTo-Json -Depth 5
    if($Connect){exit 2}else{exit 0}
}
$cfg=Get-Content -LiteralPath $ConfigFile -Raw | ConvertFrom-Json
if($cfg.schema_version -ne 1){throw 'Unsupported VPS target schema'}
if($cfg.gateway_host -ne '127.0.0.1' -or $cfg.gateway_port -ne 18734 -or $cfg.remote_listen_host -ne '127.0.0.1' -or $cfg.remote_listen_port -ne 18080){throw 'Only the approved loopback gateway18734 to VPS-loopback18080 forwarding is supported.'}
$target=[string]$cfg.host
$user=[string]$cfg.user
if(-not $target -or $target -eq 'VPS_PUBLIC_IP'){$result.missing+='Actual VPS hostname or IP'}
elseif($target -notmatch '^[a-zA-Z0-9][a-zA-Z0-9.:-]{0,252}$' -or $target -match '(?i)placeholder|example|replace|\.invalid$'){throw 'Supply an actual authorized VPS hostname or IP, not a placeholder.'}
if($user -notmatch '^[a-z_][a-z0-9_-]{0,31}$'){throw 'Invalid dedicated unprivileged SSH username'}
if($user -eq 'root'){throw 'Use a dedicated unprivileged VPS forwarding account.'}
if([int]$cfg.port -lt 1 -or [int]$cfg.port -gt 65535){throw 'Invalid SSH port'}
foreach($name in 'identity_file','known_hosts_file') {
    $value=[string]$cfg.$name
    if(-not $value -or -not(Test-Path -LiteralPath $value -PathType Leaf)){$result.missing+=$name}
    elseif($value -match '[\r\n"]'){throw 'Invalid SSH file path'}
}
if(-not(Test-Path -LiteralPath $ssh)){$result.missing+='Installed Windows OpenSSH client'}
if($result.missing.Count) {
    $result | ConvertTo-Json -Depth 5
    if($Connect){exit 2}else{exit 0}
}
$hostLookup=if([int]$cfg.port -eq 22){$target}else{'['+$target+']:'+$cfg.port}
# Search an existing independently populated file; never ssh-keyscan-and-trust.
$known=& $keygen -F $hostLookup -f ([string]$cfg.known_hosts_file) 2>$null
if($LASTEXITCODE -ne 0 -or -not $known){throw 'The actual endpoint has no independently verified entry in the selected known_hosts file.'}
$result.checks+=@('Target and endpoint-specific known_hosts entry exist','Dedicated SSH user; local and remote listeners restricted to loopback','No keys, credentials or known_hosts entries were generated or overwritten')
$runtime=Join-Path $publicRoot 'tunnel\runtime'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$sshConfig=Join-Path $runtime 'vps-ssh.conf'
$identity=([IO.Path]::GetFullPath([string]$cfg.identity_file)).Replace('\','/')
$knownHosts=([IO.Path]::GetFullPath([string]$cfg.known_hosts_file)).Replace('\','/')
@('Host dragonhydra-vps',('    HostName '+$target),('    Port '+[int]$cfg.port),('    User '+$user),('    IdentityFile "'+$identity+'"'),('    UserKnownHostsFile "'+$knownHosts+'"'),'    GlobalKnownHostsFile none','    IdentitiesOnly yes','    BatchMode yes','    StrictHostKeyChecking yes','    ExitOnForwardFailure yes','    ConnectTimeout 8','    ServerAliveInterval 15','    ServerAliveCountMax 3','    TCPKeepAlive yes','    RequestTTY no','    ForwardAgent no','    ClearAllForwardings no','    RemoteForward 127.0.0.1:18080 127.0.0.1:18734') | Set-Content -LiteralPath $sshConfig -Encoding utf8NoBOM
$resolved=& $ssh -G -F $sshConfig dragonhydra-vps 2>$null
if($LASTEXITCODE -ne 0){throw 'OpenSSH rejected the generated configuration.'}
if(-not($resolved -match '^stricthostkeychecking true$|^stricthostkeychecking yes$')){throw 'Strict host key checking was not retained.'}
$result.checks+='Installed OpenSSH parsed generated settings offline with ssh -G; no VPS connection made by this check'
$result.status='prepared';$result.target=@{host=$target;port=[int]$cfg.port;user=$user;public_hostname=$cfg.public_hostname}
if(-not $Connect){$result | ConvertTo-Json -Depth 5;exit 0}
$client=[Net.Sockets.TcpClient]::new()
try{$client.Connect('127.0.0.1',18734)}catch{throw 'Existing Windows public allowlist gateway is not listening on127.0.0.1:18734.'}finally{$client.Dispose()}
# Run a single foreground SSH process. A native scheduled task may apply bounded
# restarts; this script does not add a second competing supervisor.
$result.connection_started=$true
$result.status='connecting';$result | ConvertTo-Json -Depth 5
& $ssh -N -T -F $sshConfig dragonhydra-vps
exit $LASTEXITCODE

