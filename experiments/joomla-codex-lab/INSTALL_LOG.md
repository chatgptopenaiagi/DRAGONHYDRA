# Installation log

Experiment date: 2026-09-24 (Europe/Vienna, UTC+02:00). All experiment writes stayed under `C:\xampp`. This record contains no passwords.

## 1. Inspect before changing

Inspected XAMPP directory structure and applicable ancestor instruction files; no applicable AGENTS.md files were found. Neither requested site nor experiment directory existed. Existing htdocs applications were left alone.

Read XAMPP `properties.ini`, Apache's main/virtual-host/SSL/XAMPP includes, MySQL `bin/my.ini`, PHP settings and XAMPP startup batch scripts. Ran Apache version, runtime/vhost dumps and module listing; PHP version, ini and module commands; MariaDB binary version and live SQL server/port query. Verified localhost response (302 to dashboard) and phpMyAdmin HTTP 200.

Apache and MariaDB were already running as existing automatic Windows services. Initial Apache parent PID 5188, child 6976; MariaDB PID 5496. Final Apache child after graceful restart: 22440. HTTP/HTTPS ports 80/443, database port 3306. Main and localhost DocumentRoot: `C:/xampp/htdocs`.

Checked inherited `codex-pytorch`: Python 3.14.7, torch 2.14.0+cu132, CUDA available, NVIDIA RTX 3050. Default login shell activates base, where torch is absent; subsequent commands used `login:false` to retain the intended environment. No Python or Conda packages were changed.

## 2. Select and download official Joomla

Verified official latest downloads listed Joomla 6.1.3 and 5.4.8. PHP 8.2.12 selects Joomla 5.4.8. MariaDB 10.4.32 satisfies its minimum. Required GD was the only missing module in the requested module set.

Created experiment directories `downloads`, `backups`, `evidence`. Downloaded the official HTTPS full ZIP from the URL in `evidence/download.json`, with curl restricted to HTTPS for both initial and redirected URLs.

- Download started: 2026-09-24T15:25:23.1476169Z.
- Download finished: 2026-09-24T15:27:02.3366545Z.
- Filename: `Joomla_5-4-8-Stable-Full_Package.zip`.
- Size: 34,308,912 bytes.
- Published SHA1 verified: `e1f8a8c1c2cb78502f7b47093abfb728fb53a44e`.
- Published MD5 verified: `f0d22974bf47e8673b2f8f84a1c6ec66`.
- Additional locally calculated SHA256: `8d3585939bca8e6b1d5f3e97dda2cc557c61e610daf488c871e1f62a97be9bd0` (not claimed as publisher verification).

## 3. Minimal local PHP configuration

Copied original `C:\xampp\php\php.ini` to `backups/php.ini.before-gd` before editing. Changed only `;extension=gd` to `extension=gd`. PHP CLI confirmed GD loaded; Apache `-t` returned Syntax OK with pre-existing unrelated DocumentRoot warnings.

Gracefully restarted the existing Apache service with:

```powershell
& C:\xampp\apache\bin\httpd.exe -k restart -n Apache2.4
```

No service installation, firewall modification or database restart occurred. HTTP PHP probe proved web SAPI `apache2handler`, same php.ini, all requested extensions present, memory 512M, upload/post 40M and execution time 120. The 64M upload/post recommendations were left unmet because they are not installation blockers.

## 4. Create protected site and extract

Created the new site directory and a `.htaccess` rejecting non-loopback source addresses via mod_rewrite, with directory listing disabled. Shared Apache authorization includes a later LAN-permitting Location block; the independent rewrite guard is required for reliable site isolation.

Inspected each ZIP entry's resolved destination to ensure it remained inside the site and would not overwrite an existing file. Extracted 13,643 entries. Confirmed `index.php`, administrator entrypoint, `installation/joomla.php`, `cli/joomla.php`, and Joomla version source.

Ran `php installation/joomla.php help install` and retained output in `evidence/installer-help.txt` before constructing installer arguments.

## 5. Provision database and credentials

Live local administrative connection succeeded without altering root credentials. Confirmed no existing database named `joomla_codex_lab` and no user named `joomla_codex`. Server general, slow-query and binary logging were all off at inspection.

Created an ACL-protected credentials file and private configuration directory. Generated independent cryptographically random database and Super User passwords, a random non-admin username, and safe table prefix `j5faba9_`. Passwords were never printed into ordinary logs or shell arguments.

`provision-database.php` created utf8mb4 database `joomla_codex_lab` and user `joomla_codex@localhost`. Database grant underscores were escaped so the grant matches exactly this database, not wildcard names. The account has no GRANT OPTION and only global USAGE. A dedicated-account TCP connection to `127.0.0.1:3306` succeeded. See `evidence/database-provision.json`.

## 6. Official CLI installation

The helper `run-official-installer.php` reads local credentials, constructs supported argv in memory, and requires the unchanged official `installation/joomla.php`. Console output is defensively redacted. No undocumented installer flags were used.

Values: site `Codex XAMPP Laboratory`; Super User real name `Codex Laboratory Operator`; generated username/password; email `operator@joomla-codex.test`; database type mysqli; host `127.0.0.1:3306`; dedicated account and database; generated prefix; `--no-interaction`, `--no-ansi`.

Installer exit code 0. It reported requirements, database connection, population and configuration creation OK, then removed its installation directory. Evidence: `evidence/cli-install.txt`.

## 7. Keep runtime secrets outside htdocs

Moved generated `configuration.php` to the ACL-protected `private-config` directory after verifying exact source/destination paths. Added root, administrator and API `defines.php` hooks to set `JPATH_CONFIGURATION`; root hook also covers CLI. Created a secret-free root configuration loader. No shipped Joomla entrypoint was edited.

The normal Joomla configuration writer saves to `JPATH_CONFIGURATION`, confirmed in package source; this supports future settings saves without returning secrets to htdocs. Management writes were not exercised. No plaintext Super User password is in runtime configuration; Joomla stores its password hash in the database.

## 8. Independent validation

`verify-installation.php` independently checked the dedicated database connection, 76 prefixed tables, 248 extension records, enabled Super User, matching password hash, root/private configuration existence and installer directory absence. Reading `mysql.user` using the dedicated account was denied. A scan found zero generated plaintext password matches anywhere in the site. All checks passed.

HTTP checks at 15:31:49 UTC returned frontend 200/title Home and administrator 200/title Codex XAMPP Laboratory - Administration. Both contain Joomla markers and the site name; administrator login form is present. No raw PHP source was detected. Final static CSS also returns 200.

Final loopback restrictions were checked against frontend, administrator and static CSS: localhost 200, own LAN source 192.168.8.8 HTTP and HTTPS 403. The HTTPS LAN denial check accepted the existing local certificate only to test access behavior; no certificate configuration changed. See `evidence/local-access-verification.json`.

Ran `php cli/joomla.php list --no-ansi` and `php cli/joomla.php config:get debug --no-ansi`: both exit 0, Joomla reports 5.4.8, debug false. See CLI evidence files for all available administrative commands. Did not invoke configuration changes, core updates, extension installs, user changes, or scheduled tasks merely because commands are available.

Removed the temporary PHP HTTP probe after capturing evidence.

## 9. Browser handoff and policy boundary

After successful independent HTTP/database checks, attempted a Windows command containing `Start-Process -FilePath` for both site URLs. Automatic approval review rejected the command before execution with `blocked by policy`; no more detailed reason was supplied. No launch occurred and no bypass was attempted. Recorded **BLOCKED_BY_ENVIRONMENT**, **BROWSER_LAUNCHED=false**, and **BROWSER_GUI_CONTROLLED=false** in `evidence/browser-launch.json`.

The user can open the two URLs in README for visual inspection and sign in with the protected local credentials. Installation and server-side operation require no further manual work. The proposed Python integration is documented only, not implemented.
