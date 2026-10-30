# DRAGONHYDRA public gateway deployment support

This package contains the read-only gateway, its public match viewer, Windows
helpers, nginx/SSH templates and validation tools. It contains no Joomla site,
database, server credentials, provider keys, Cloudflare executable or live tunnel
configuration. It must run on the server machine beside an existing configured
DRAGONHYDRA kernel and Joomla origin. `127.0.0.1` here refers to that server.

The packaged `build-info.json` identifies the release source. The historical
development Quick Tunnel is not an installation endpoint. New Quick Tunnels
receive their own temporary hostname and provide no uptime guarantee or SSE.
Permanent VPS configuration is supplied as deployment support and was not tested
against a real VPS for this release.

Tested requirements: Windows x64, PowerShell 7 and CPython 3.14 for the gateway;
an existing Joomla 6 / PHP 8.4 origin; DRAGONHYDRA `/dragon/api/v1` with schema 1.
Other Python or OS combinations are not claimed. The optional VPS side requires
an actual authorized Linux server, installed nginx/OpenSSH/systemd, a public IPv4,
an SSH forwarding identity and independently trusted host key.

From PowerShell 7 in the extracted gateway folder:

```powershell
py -3.14 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item -LiteralPath gateway.example.json -Destination gateway.json
```

Edit `gateway.json`: select the actual local Joomla listener and reference the
kernel state's `endpoint.json` and protected `joomla-bridge.json`. Relative file
references resolve beside the config file, regardless of the current directory.
Keep the gateway on the server; do not point a phone's localhost at Windows.
The server's explicit `--init-bridge` option provisions a new bridge secret before
startup without replacing an existing secret. Protect the selected state and
allow only the service identity that actually runs Joomla/gateway to read it.
Never place either state file inside a web document root.

```powershell
& .\scripts\Start-PublicGateway.ps1 -ConfigFile .\gateway.json -Python .\.venv\Scripts\python.exe -StateDirectory .\state -Port 18734
Invoke-RestMethod http://127.0.0.1:18734/public-health
& .\scripts\Install-Cloudflared.ps1
& .\scripts\Start-QuickTunnel.ps1 -GatewayUrl http://127.0.0.1:18734
```

Start only after local Joomla and kernel checks succeed. The Cloudflare helper
downloads the pinned official Windows x64 build, verifies its upstream checksum
and records its signature status. A network connection is required for that
download and the temporary tunnel. It exposes only the restricted gateway;
never tunnel Apache directly. The generated URL and process information remain
in your local `cloudflare/quick-tunnel.json`, not in this distribution.

Open the printed HTTPS URL, choose **Browse DRAGONHYDRA matches**, select a match,
open a team, return and open standings. Available source data is displayed through
the existing kernel. Missing odds, injuries and lineups remain explicit; computed
standings are labelled unofficial. No separate store or sports engine is created.

Allowed public requests are selected Joomla frontend/assets, `/sports` views and
approved match/team/competition GET operations. All mutations and privileged
administration, credentials, sessions, jobs, exports, debug and model-management
routes are rejected. Visitor cookies and authorization are not forwarded. Useful
503 pages appear during unavailable-origin failures.

Stop only your deployment processes:

```powershell
& .\scripts\Stop-QuickTunnel.ps1
& .\scripts\Stop-PublicGateway.ps1 -StateDirectory .\state
```

These helpers do not stop Joomla, the kernel, databases or VPN. They verify process
ownership before stopping a recorded process. A busy port produces a specific
failure; it never authorizes killing its listener. Startup can use `-Port 0` to
allocate an isolated test port; the actual endpoint is returned.

Optional verification (installed Edge is required for browser checks):

```powershell
& .\.venv\Scripts\python.exe -m pip install -r requirements-verification.txt
& .\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_gateway.py -q
& .\.venv\Scripts\python.exe -B tests/browser_public.py --url http://127.0.0.1:18734 --output state/evidence/browser
```

Tests use isolated mock upstreams and package-local scratch state. Do not execute
outage/recovery tests against a working public application. Such development
helpers are deliberately excluded from this archive.

For a permanent numeric-IP gateway, read `vps/README.md`. Supply a real VPS target
and verified identity; the dry-run defaults do not contact a server. HTTP can serve
the actual VPS IP without a domain. Optional IP HTTPS requires a certificate valid
for that exact IP and tested short-lived renewal. Templates alone establish no
VPS connectivity, reboot recovery or certificate issuance.

Before upgrading, stop only the gateway/tunnel processes and preserve your
configuration, state and independently managed backend. Extract the new package
alongside the old one, validate it on an isolated port, then select the preserved
configuration. Do not overwrite a live state directory with archive contents.
