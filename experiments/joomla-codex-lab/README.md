# Codex XAMPP Joomla capability experiment

Run date: 2026-09-24. Working root: `C:\xampp`.

**Joomla 5.4.8 is installed and independently verified.** Frontend and administrator HTTP requests return 200, the dedicated database contains 76 tables, and Joomla's management CLI works. Windows browser launch was rejected by automatic approval review before execution. No browser GUI interaction or visual verification is claimed.

- [Open the frontend](http://localhost/joomla-codex-lab/)
- [Open the administrator login](http://localhost/joomla-codex-lab/administrator/)
- Local credentials: `credentials.local.txt` beside this report. This ACL-protected file is marked LOCAL TEST SECRET / DO NOT COMMIT / DO NOT COPY TO WEB ROOT. It contains the generated non-obvious Super User username and password. Passwords are deliberately absent from these reports.

## Completion report

| Requested result | Evidence-backed outcome |
| --- | --- |
| 1. XAMPP root | `C:\xampp`; site `C:\xampp\htdocs\joomla-codex-lab`. |
| 2. Apache | 2.4.58 Win64, Apache Lounge VS17. |
| 3. PHP | 8.2.12 ZTS; CLI `C:\xampp\php\php.exe`; web SAPI `apache2handler`. |
| 4. Database server | MariaDB 10.4.32, verified through both binary and live SQL. |
| 5. Actual ports | Apache HTTP 80 and HTTPS 443; MariaDB TCP 3306. This site's verified URL uses HTTP 80. |
| 6. Selected Joomla | 5.4.8. |
| 7. Selection reason | PHP 8.2 meets Joomla 5's PHP >=8.1 requirement, but not Joomla 6's PHP >=8.3 requirement. MariaDB 10.4.32 meets Joomla 5's >=10.4 requirement. Official latest page listed 5.4.8 and 6.1.3. |
| 8. Download | [Official full ZIP](https://downloads.joomla.org/cms/joomla5/5-4-8/Joomla_5-4-8-Stable-Full_Package.zip?format=zip), 34,308,912 bytes. Published SHA1 and MD5 both matched. See `evidence/download.json` for URLs, hashes, and UTC times. |
| 9. PHP requirements | All required and additionally requested modules pass after enabling bundled GD. Memory 512M; upload/post 40M each; execution time 120 seconds. Upload/post recommendations of 64M are not met but do not block this installation. |
| 10. Database created | `joomla_codex_lab`, utf8mb4 / utf8mb4_unicode_ci. |
| 11. Dedicated account | `joomla_codex@localhost`; privileges only on this database, no grant option or global operational privileges. Read of `mysql.user` denied. Root password unchanged. |
| 12. Official installer | `installation/joomla.php help install` inspected first. Supported options passed to the actual installer through an in-process PHP argv wrapper, keeping secrets out of shell arguments. Exit 0; Joomla reported installed. |
| 13. Frontend | HTTP 200, title `Home`, site name visible, Joomla/Cassiopeia marker found; PHP source not exposed. |
| 14. Administrator | HTTP 200, title `Codex XAMPP Laboratory - Administration`, login form present. No browser login performed. |
| 15. Management CLI | `php cli/joomla.php list` and `php cli/joomla.php config:get debug` exit 0; debug is false. |
| 16. Browser launch | **BLOCKED_BY_ENVIRONMENT**. `Start-Process` URL launch command rejected before execution: `blocked by policy`. **BROWSER_LAUNCHED=false**. |
| 17. Browser GUI control | Unavailable in this session. **BROWSER_GUI_CONTROLLED=false**; visual interaction requires the user. |
| 18. Files created | Joomla package files; site `.htaccess`, root/admin/API `defines.php`, secret-free root `configuration.php`; all six requested Markdown records; credential file; private runtime configuration; download archive; evidence files and three PHP provisioning/verification helpers. The temporary PHP HTTP probe was removed. |
| 19. Configuration changes | Existing `C:\xampp\php\php.ini`: only `;extension=gd` became `extension=gd`. New site access and configuration-path files are described below. Shared Apache and MariaDB configuration files were not modified. |
| 20. Backups | `backups/php.ini.before-gd`: original PHP configuration. No unrelated applications or databases were replaced. |
| 21. Services | Apache2.4 and mysql Windows services already existed and were running. No services installed or newly started. Existing Apache gracefully restarted to load GD. MariaDB left running. |
| 22. Failures | Browser launch policy rejection remains. Initial missing GD and login-shell Conda mismatch resolved. Existing unrelated missing DocumentRoot warnings remain. See [FAILURES.md](FAILURES.md). |
| 23. Manual actions | Open the two URLs above for browser inspection; use the local credential file to sign into Joomla if desired. No manual installation or database setup remains. |
| 24. CODEX_REACH_SCORE | Discovery, compatibility selection, verified download, extraction, database/account creation, CLI installation, private configuration, population, HTTP and CLI operation all completed. Existing service availability was verified; startup from a stopped state was not tested. Browser launch was policy-blocked and GUI interaction was unavailable. No invented percentage. |
| 25. NEXT_EXACT_ACTION | In a separate experiment, use `codex-pytorch` Python 3.14.7 to read published-content counts from Joomla through a new localhost SELECT-only database account and emit JSON. This integration has not been implemented. See [NEXT_EXPERIMENT.md](NEXT_EXPERIMENT.md). |

## Local access and secret storage

The pre-existing Apache listeners bind all interfaces and the localhost virtual host permits LAN clients. Only this new site was restricted: its `.htaccess` uses a rewrite rule rejecting source addresses other than `127.0.0.1` and `::1`. This avoids the parent `<Location>` authorization overriding a directory-only access rule. Frontend, administrator and static CSS return 200 through localhost and 403 from source `192.168.8.8` over both HTTP and HTTPS. No firewall, public host, remote phpMyAdmin access, or shared listener settings changed.

Joomla generated its normal configuration during installation. It was then relocated to `private-config/configuration.php` outside `htdocs`. Custom `defines.php` files use Joomla's existing `JPATH_CONFIGURATION` hook for frontend, administrator, API and CLI. The root `configuration.php` is a secret-free compatibility loader. Joomla's configuration writer uses this same private path (confirmed by source inspection; no unnecessary configuration save was performed).

The private runtime configuration necessarily contains Joomla's database password; the plaintext Super User password is stored only in `credentials.local.txt`. Credentials and the private directory have Windows ACLs restricted to the current operator, SYSTEM and Administrators. A scan found no generated plaintext database or Super User password in any site file. `.gitignore` excludes local secrets, private configuration, backups and downloads.

## Evidence and records

- [ENVIRONMENT.md](ENVIRONMENT.md): stack, Python, CUDA and configuration inventory.
- [INSTALL_LOG.md](INSTALL_LOG.md): ordered actions and validation.
- [CAPABILITY_MATRIX.md](CAPABILITY_MATRIX.md): all 18 requested stages and exact classifications.
- [FAILURES.md](FAILURES.md): encountered issues, remedies and remaining limitations.
- [NEXT_EXPERIMENT.md](NEXT_EXPERIMENT.md): proposed Joomla/Python integration only.
- `evidence/`: version/configuration metadata, published checksum verification, installer help/output, database privilege/population checks, HTTP/access checks, management CLI output, and rejected browser launch record.

Official references: [latest releases](https://downloads.joomla.org/latest), [Joomla 5.4 requirements](https://manual.joomla.org/docs/5.4/get-started/technical-requirements/), [5.4.8 release and checksums](https://downloads.joomla.org/cms/joomla5/5-4-8).
