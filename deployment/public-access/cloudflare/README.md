# DRAGONHYDRA temporary public tunnel

The project-local Cloudflare executable is pinned in `install-receipt.json`.
Release 2026.10.6 was downloaded from the official Cloudflare GitHub release,
verified against both the release checksum and GitHub asset SHA-256, and passed
Cloudflare Authenticode signature verification. It is not installed globally or
registered as a Windows service.

Run from PowerShell 7 in `C:\xampp\DRAGONHYDRA`:

```powershell
& .\deployment\public-access\scripts\Install-Cloudflared.ps1
& .\deployment\public-access\scripts\Start-QuickTunnel.ps1
```

`Start-QuickTunnel.ps1` requires the restricted public gateway's health endpoint
at `http://127.0.0.1:18734/public-health` to be ready. It exposes that gateway
only, uses HTTP/2, disables automatic updates and binds metrics to loopback.
An existing verified project process is reused. The actual temporary HTTPS
address and PID are stored in `quick-tunnel.json`; logs stay in `logs`.

The initial live URL is
<https://metallica-kevin-dangerous-limits.trycloudflare.com>.
HTTP checks from the same Windows host through the public Cloudflare HTTPS route
are recorded in `external-http-checks.json`. They do not establish access from an
unrelated external network. Public health,
homepage and read-only matches returned 200; Joomla administration, phpMyAdmin,
configuration.php and jobs returned 403 through Cloudflare.

Stop only this project tunnel:

```powershell
& .\deployment\public-access\scripts\Stop-QuickTunnel.ps1
```

Quick Tunnels are temporary development endpoints: the address changes after a
new tunnel is created, availability is not guaranteed, and SSE is unsupported.
Cloudflare documents a 200 concurrent-request limit. This tunnel leaves existing
VPN, Apache, database, firewall and Codex configuration unchanged.

Official documentation:
<https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/>.
