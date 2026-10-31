# DRAGONHYDRA public access

Phase A is running at **https://metallica-kevin-dangerous-limits.trycloudflare.com/**.
Open the home page, choose **Browse DRAGONHYDRA matches**, select a match, open a
team, use browser Back, and open standings. The same retained canonical records
serve the local product and this public view. The public gateway contains no
separate sports store or calculations.

The [Cloudflare report](cloudflare/REPORT.md) and [permanent IP report](vps/REPORT.md)
record independent results. Phase B is prepared and has not been deployed: no
actual VPS or trusted SSH target was configured. `188.74.136.7` remains the
observed NordVPN outbound IP; it is not a new inbound web gateway.

All new deployment code lives here. Existing application sources, Joomla core,
database ownership, provider credentials, NordVPN settings and Codex configuration
are not modified by the gateway. The origin was discovered running before tunnel
setup. The Apache recovery test used only that exact product-owned origin.

| Component | Current local endpoint | Public exposure |
| --- | --- | --- |
| Existing Joomla frontend | `http://127.0.0.1:18732/` | Approved frontend and assets through gateway |
| Existing Joomla administration | `http://127.0.0.1:18732/administrator/` | Denied |
| Existing kernel API | Endpoint read from `runtime/product/endpoint.json` | Allowlisted GET resources through reader HMAC |
| Public boundary | `http://127.0.0.1:18734/` | Cloudflare tunnel target; loopback bind |
| MariaDB | Loopback port 18733 | Not forwarded |
| Cloudflare metrics | Loopback endpoint in `cloudflare/quick-tunnel.json` | Not forwarded |

The API boundary permits matches, teams, competitions, supported context and
statistical forecasts. It denies sessions, jobs, exports, connections, updates,
debugging, vaults and all state-changing methods. Visitor cookies and identity
headers are never forwarded to Joomla or used as kernel identity. Joomla forms
are suppressed in the public response because this deployment is read only.
Private local administration continues to work independently.

The thin `/sports` viewer reads the existing API; unavailable lineups, odds and
injuries stay explicit. Reconstructed standings are labelled unofficial. It
does not create live fixtures or claim local LLM output. Responses have bounded
size, timeout, concurrency, per-address request budgets and short API caching.
Only fixed local origins are configured. Joomla asset cache-busters, incoming
scheme/host, spaced team searches and overlapping browser navigation are tested.

Run from PowerShell 7 in `C:\xampp\DRAGONHYDRA`:

```powershell
& .\deployment\public-access\scripts\Start-PublicGateway.ps1
& .\deployment\public-access\scripts\Start-QuickTunnel.ps1
```

These commands reuse verified existing deployment processes. The local Joomla
and kernel must already be ready; the gateway does not supervise or duplicate
the application. The existing product kernel launcher remains
`scripts/Start-Dragonhydra.ps1`. The gateway automatically reads a changed kernel
endpoint after a normal product restart. Cloudflare's current hostname and PID
are in `cloudflare/quick-tunnel.json`. A newly created Quick Tunnel gets a new
hostname. The tunnel has no uptime promise and does not support SSE.

To withdraw only public access:

```powershell
& .\deployment\public-access\scripts\Stop-QuickTunnel.ps1
& .\deployment\public-access\scripts\Stop-PublicGateway.ps1
```

This leaves Joomla, the kernel, database and VPN running.

Verification commands:

```powershell
& .\runtime\server-env\Scripts\python.exe -B -m unittest discover -s deployment/public-access/tests -p test_gateway.py -q
& .\runtime\server-env\Scripts\python.exe -B deployment/public-access/tests/browser_public.py --url https://metallica-kevin-dangerous-limits.trycloudflare.com --output deployment/public-access/evidence/browser-public
& .\deployment\public-access\scripts\Start-DragonVpsTunnel.ps1
& .\deployment\public-access\scripts\Register-DragonVpsTunnelTask.ps1
```

The first two exercise the public boundary and actual controls. The latter two
perform local validation and report `requires_configuration` while no real VPS
target is present. See [VPS setup](vps/README.md) for the IP HTTP baseline,
optional trusted IP HTTPS, SSH identity constraints and deployment steps.

`evidence/browser-public/journey.json` records browser responses and screenshots;
`evidence/remote-*-observer.json` records independent remote fetches, including a
rendered match list and actual API result. These are distinct from requests sent
by the Windows host through the public URL. No phone/carrier test is claimed.
`evidence/apache-recovery.json` proves the actual origin outage/recovery without
stopping the database or kernel. One Joomla cross-document transition warning is
recorded separately; the navigation assertions and application error checks pass.

No VPS SSH connection, Linux installation, task registration, reboot test or
certificate issuance was performed. Existing installed applications remain the
application-development session's responsibility; this directory deploys access
to those applications.
