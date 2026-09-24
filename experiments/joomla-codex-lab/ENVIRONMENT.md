# Joomla laboratory environment

Observed on 2026-09-24. All experiment files and changes remain under `C:\xampp`; the existing Python installation was used in place and was not changed.

## Web and database stack

| Item | Observed value |
| --- | --- |
| XAMPP root | `C:\xampp` |
| Structure | Existing `apache`, `php`, `mysql`, `phpMyAdmin`, `htdocs`, XAMPP control programs and supplied startup scripts |
| Apache | 2.4.58 Win64, Apache Lounge VS17 |
| Apache executable | `C:\xampp\apache\bin\httpd.exe` |
| PHP | 8.2.12, x64 thread-safe; CLI and Apache module verified |
| PHP CLI | `C:\xampp\php\php.exe` |
| Loaded PHP configuration | `C:\xampp\php\php.ini` |
| Database | MariaDB 10.4.32 |
| Database executable | `C:\xampp\mysql\bin\mysqld.exe` |
| Database configuration | `C:\xampp\mysql\bin\my.ini` |
| Database data directory | `C:\xampp\mysql\data` |
| phpMyAdmin | 5.2.1, installed at `C:\xampp\phpMyAdmin`; localhost HTTP 200; existing `Require local` access restriction retained |
| Apache main DocumentRoot | `C:\xampp\htdocs` |
| Joomla directory | `C:\xampp\htdocs\joomla-codex-lab` |
| Experiment records | `C:\xampp\DRAGONHYDRA\experiments\joomla-codex-lab` |
| Ports | Apache HTTP 80, HTTPS 443; MariaDB TCP 3306 |
| Frontend | <http://localhost/joomla-codex-lab/> |
| Administrator | <http://localhost/joomla-codex-lab/administrator/> |

The existing `localhost` virtual host in `apache\conf\extra\httpd-vhosts.conf` uses `C:/xampp/htdocs` and has aliases `127.0.0.1`, `192.168.8.8`, and `DESKTOP-1TG2EVG`. The main configuration also names `localhost:80`. The existing HTTPS virtual host in `httpd-ssl.conf` uses the same DocumentRoot and server name `www.example.com:443`. Other existing virtual hosts were left unchanged, including the pre-existing reference to the missing `C:/CS16-LAB/web/public-deny` directory.

`Apache2.4` and `mysql` were already running as automatic Windows services. No service was installed, newly started, or reconfigured. Apache was gracefully restarted to load GD. Captured processes were Apache parent PID 5188 and child PID 22440, and MariaDB PID 5496; PIDs are observation-time values. See processes (LOCAL EVIDENCE PATH: `experiments/joomla-codex-lab/evidence/processes.json`), listeners (LOCAL EVIDENCE PATH: `experiments/joomla-codex-lab/evidence/listeners.json`), and virtual hosts (LOCAL EVIDENCE PATH: `experiments/joomla-codex-lab/evidence/apache-vhosts.txt`).

The existing listeners were on all interfaces: Apache `0.0.0.0` and `::` on ports 80/443, MariaDB `::` on port 3306. Their bindings were not changed. The new site's `.htaccess` allows only loopback client addresses (`127.0.0.1` and `::1`) and disables directory indexes. Frontend, administrator and static CSS access through the machine's LAN address returned 403 over HTTP and HTTPS; all three returned 200 through localhost HTTP. See local access verification (LOCAL EVIDENCE PATH: `experiments/joomla-codex-lab/evidence/local-access-verification.json`). No firewall rule or remote phpMyAdmin access was added.

## Joomla selection and PHP requirements

Joomla 5.4.8 was selected from the [official release download page](https://downloads.joomla.org/cms/joomla5/5-4-8). Installed PHP 8.2.12 fits the experiment's Joomla 5 branch rule and is below its PHP 8.3 threshold for Joomla 6. Apache 2.4.58, PHP 8.2.12 and MariaDB 10.4.32 meet the [Joomla 5 minimum requirements](https://manual.joomla.org/docs/5.4/get-started/technical-requirements/): Apache 2.4, PHP 8.1 and MariaDB 10.4.0.

The only missing required PHP extension was GD. The installed GD extension was enabled by changing `;extension=gd` to `extension=gd` in `php.ini`, after backing up the original to backups/php.ini.before-gd (LOCAL EVIDENCE PATH: `experiments/joomla-codex-lab/backups/php.ini.before-gd`). No other PHP setting was changed.

| PHP checks after restart | Result |
| --- | --- |
| `json`, `simplexml`, `dom`, `zlib`, `gd` | All loaded |
| `mysqli`, `pdo_mysql`, `mysqlnd` | All loaded |
| `mbstring`, `openssl`, `curl`, `fileinfo` | All loaded |
| `memory_limit` | 512M; above the 256M recommendation |
| `upload_max_filesize` | 40M; below the experiment's 64M recommendation, but did not block installation |
| `post_max_size` | 40M; below the experiment's 64M recommendation, but did not block installation |
| `max_execution_time` | 120 seconds in Apache PHP; above the 30-second recommendation |

The extension checks passed in both CLI PHP and Apache PHP. Values above are the web runtime values from php-web.json (LOCAL EVIDENCE PATH: `experiments/joomla-codex-lab/evidence/php-web.json`); php-modules.txt (LOCAL EVIDENCE PATH: `experiments/joomla-codex-lab/evidence/php-modules.txt`) records the CLI module list. The official installer accepted the actual requirements and completed successfully.

## Python and GPU laboratory

| Item | Observed value |
| --- | --- |
| Conda environment | `codex-pytorch` |
| Conda prefix | `C:\Users\Administrator\anaconda3\envs\codex-pytorch` |
| Canonical Python | 3.14.7 |
| Python executable | `C:\Users\Administrator\anaconda3\envs\codex-pytorch\python.exe` |
| PyTorch | `2.14.0+cu132` |
| PyTorch CUDA build | 13.2 |
| `torch.cuda.is_available()` | `True` |
| GPU | NVIDIA GeForce RTX 3050 |
| GPU memory | 6144 MiB |
| NVIDIA driver | 616.92 |

PowerShell commands with `login:false` preserve `codex-pytorch`. The login-shell startup changed the active environment to base, using `C:\Users\Administrator\anaconda3\python.exe`; that interpreter was also Python 3.14.7 but lacked PyTorch. Subsequent checks used the canonical environment. See Python and GPU evidence (LOCAL EVIDENCE PATH: `experiments/joomla-codex-lab/evidence/python-environment.json`). No Python downgrade, package installation, Conda modification, or Joomla/Python integration was performed.

## Deployment verification

The official full ZIP was downloaded over HTTPS, and both publisher-provided SHA-1 and MD5 matched. The recorded SHA-256 is a local additional fingerprint; it is not represented as a publisher-provided checksum. download.json (LOCAL EVIDENCE PATH: `experiments/joomla-codex-lab/evidence/download.json`) contains the exact source, times, size and hashes.

Joomla's official installer returned exit code 0, generated configuration, populated 76 tables in `joomla_codex_lab`, and removed the installation directory. The runtime account is `joomla_codex@localhost`; a read attempt against the unrelated `mysql` database was denied. Secret values are excluded from this document. Runtime configuration containing secrets resides outside `htdocs`, with a loader in the site's `configuration.php`.

Both frontend and administrator URLs returned HTTP 200 with Joomla content. Joomla CLI `list` reported version 5.4.8; `config:get debug` returned `false`. See installation verification (LOCAL EVIDENCE PATH: `experiments/joomla-codex-lab/evidence/installation-verification.json`), HTTP verification (LOCAL EVIDENCE PATH: `experiments/joomla-codex-lab/evidence/http-verification.json`), CLI commands (LOCAL EVIDENCE PATH: `experiments/joomla-codex-lab/evidence/joomla-cli-list.txt`), and debug value (LOCAL EVIDENCE PATH: `experiments/joomla-codex-lab/evidence/joomla-cli-debug.txt`).

Browser launch was blocked by execution policy before the launch command ran. No browser GUI interaction capability was available, and no visual inspection, browser login or clicking is claimed. See [FAILURES.md](FAILURES.md).
