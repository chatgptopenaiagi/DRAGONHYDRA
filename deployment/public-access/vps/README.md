# Optional VPS gateway: prepared, not deployed

Phase A uses the existing Windows site and separate allowlist gateway. Phase B can put an authorized VPS in front of that same gateway. The Windows host makes one outbound SSH connection; neither the Joomla database nor its administration port is forwarded.

```text
Public HTTP by actual IP -> VPS nginx -> VPS127.0.0.1:18080
                               |
                    outbound SSH remote forward
                               |
                   Windows127.0.0.1:18734 gateway
```

Read-only discovery on this workstation found the existing Windows OpenSSH client at `C:\Windows\System32\OpenSSH\ssh.exe`, no user `.ssh/config`, no user `known_hosts`, and no configured VPS target in the project at the time of the check. No VPS was purchased, contacted or configured. No real public IP, SSH account, host-key verification, DNS name or TLS certificate has been invented.

Before deployment, supply an authorized existing VPS target in `target.json` using the accompanying schema example. Use a dedicated unprivileged account and an identity readable by the actual Windows task identity. Independently verify the VPS SSH host fingerprint through the provider's trusted console or an existing authenticated channel; then populate the explicit `known_hosts_file`. The scripts never convert `ssh-keyscan` output into trust.

The prepared VPS-side files are `../tunnel/sshd-dragonhydra.conf.example`, `../tunnel/authorized_keys.example`, and `../reverse-proxy/vps-nginx.conf.example`. The SSH daemon Match block restricts forwarding to remote TCP on one loopback listener. It denies sessions, TTYs, agent forwarding, X11, streamlocal and tunnel devices. The authorized key has a matching `permitlisten` restriction. An administrator must test the complete effective SSH configuration with `sshd -t` and `sshd -T -C user=dragonhydra-tunnel,host=ACTUAL_HOST,addr=ACTUAL_WINDOWS_SOURCE_IP` before a controlled reload, retaining an existing recovery session. These commands are instructions for the configured VPS, not local execution evidence.

`render_vps.py` supplies a complete offline render path using only Python's standard library. It validates the actual globally routable IPv4 and an existing public SSH key, keeps generated outputs within this deployment tree, substitutes the IP and produces per-file SHA-256 manifests. It never reads a private key, contacts a server or changes operating-system configuration. With no real target it returns `requires_configuration` and writes no rendered target files.

`install-gateway.sh` runs on the actual authorized Linux VPS. It defaults to render/dry-run, requires existing nginx/OpenSSH/systemd and opens no Windows inbound port. The explicit `--apply` path requires the VPS administrator. It refuses symlink targets, files without its own ownership marker and an unproven existing account with the reserved name. It backs up only its three scoped files, installs a dedicated account, tests full nginx/sshd configuration and effective forwarding restrictions, then reloads only the selected SSH unit and nginx. It does not replace global configuration or change firewall rules. A validation/reload failure restores its own prior files and removes only an account newly created by that apply. Existing SSH connections remain the recovery channel. Linux commands below are prepared instructions; none were executed on a VPS in this session:

```sh
# On the authorized VPS, from the copied deployment tree:
bash vps/install-gateway.sh --ip VPS_PUBLIC_IP --public-key-file /path/to/windows-tunnel.pub
# Review generated files and preserve the provider-console recovery path, then:
sudo bash vps/install-gateway.sh --ip VPS_PUBLIC_IP --public-key-file /path/to/windows-tunnel.pub --apply
```

Both templates clear any visitor-supplied `CF-Connecting-IP` and set `X-Real-IP` from the actual VPS TCP peer. They forward neither visitor cookies nor bearer/Joomla bridge credentials. The Windows gateway must trust this sanitized address only for its explicitly configured VPS public Host; it must not trust arbitrary inbound identity headers.

The numeric-IP HTTP baseline serves `http://VPS_PUBLIC_IP/` directly on port80 after replacing that placeholder with the real authorized VPS address and adding it to the Windows gateway Host allowlist. It requires no domain, certificate or HTTPS redirect. It proxies only anonymous read-only content, strips visitor identity/cookies, and rejects private paths and non-read methods. The existing Windows gateway remains the authority for public route eligibility and uses its own reader contract to call the kernel. It permits supported public Joomla content, read-only `/sports` pages, matching public assets and supported read-only sports API paths. It does not grant access to Joomla administration, sessions, jobs, exports, sources or mutations. Database3306/18733, inference and private Apache18732 ports remain unforwarded. Run `nginx -t` on the actual target before applying the completed configuration. No nginx or Linux distribution compatibility has been tested by preparing these files.

Optional IP HTTPS uses `../reverse-proxy/vps-nginx-https-ip.conf.example` in addition to that baseline. It requires a trusted certificate whose subjectAltName contains the actual IP, independently of any domain. The baseline serves `/.well-known/acme-challenge/` from `/var/lib/dragonhydra/acme` directly on the VPS, without proxying that path through Windows. Let's Encrypt supports IP certificates with 160-hour validity. Its current Certbot guidance requires version5.4 or newer for IP webroot validation; the nginx/apache Certbot installer plugins do not yet install IP certificates. On the actual VPS, first verify the installed Certbot version, create the ACME webroot with narrow web-server read permissions, confirm its public challenge reachability, and test issuance using:

```sh
sudo certbot certonly --staging --preferred-profile shortlived --webroot \
  --webroot-path /var/lib/dragonhydra/acme --ip-address VPS_PUBLIC_IP \
  --cert-name dragonhydra-ip
```

After staging validation succeeds, repeat without `--staging` for a publicly trusted certificate, inspect the actual IP SAN and enable the separate HTTPS configuration. Configure automatic renewal and a deployment hook that runs `nginx -t && systemctl reload nginx`; verify `certbot renew --dry-run` and the actual timer on the tested distribution. The short validity makes verified automated renewal essential. No certificate was requested, no ACME account was created, and no nginx reload or remote renewal test was run here. Official current instructions: [Let's Encrypt IP certificate availability](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability) and [Certbot IP webroot support](https://letsencrypt.org/2026/03/11/shorter-certs-certbot).

Local configuration checks do not open a VPS connection:

```powershell
pwsh -NoProfile -File deployment/public-access/scripts/Start-DragonVpsTunnel.ps1
pwsh -NoProfile -File deployment/public-access/scripts/Register-DragonVpsTunnelTask.ps1
```

With a real target, existing usable identity and verified known-host entry, the first script runs `ssh -G` offline to inspect the resulting configuration. `-Connect` is the explicit runtime switch. It checks the existing local gateway, then runs one SSH process with strict host-key verification, noninteractive authentication, forward failure detection, connection deadline and keepalives.

Current local evidence is limited to Windows OpenSSH9.5p2 execution, PowerShell syntax and no-target results, Python renderer syntax/no-target JSON, and `bash -n` through the existing Git Bash executable. Git Bash syntax validation is not a Linux deployment, a systemd/nginx test, or proof of an operational SSH tunnel.

The optional native task runs as `NT AUTHORITY\LOCAL SERVICE` at boot. It requires exact read permissions on the selected target/config/key files and a noninteractive usable SSH key. Prepare permissions for that service account separately; the script makes no broad ACL grants and copies no private key. The task has one supervisor with three bounded restarts and refuses overlapping instances. `Register-DragonVpsTunnelTask.ps1 -Install` registers the task but does not start it. Task registration and boot/reconnect behavior have not been tested here. Removing the named task and closing its SSH connection withdraws the remote listener; it does not remove Joomla data or change any unrelated service.

After an authorized deployment, verify externally from a network other than the Windows host: the actual public IP's HTTP content, selected canonical match and odds states, blocked private paths, read-only method rejection, process restart/reconnect, source freshness and closed database/inference ports. If optional IP HTTPS is configured, separately verify SAN/trust and certificate renewal. Record the actual IP, target OS/packages, commands and receipts then. Until those checks run, the state remains **configuration prepared; VPS deployment not run**.

Official references: [OpenSSH remote forwarding](https://man.openbsd.org/ssh_config#RemoteForward), [sshd PermitListen and forwarding restrictions](https://man.openbsd.org/sshd_config#PermitListen), [nginx proxy module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass), [Microsoft OpenSSH configuration](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh-server-configuration).
