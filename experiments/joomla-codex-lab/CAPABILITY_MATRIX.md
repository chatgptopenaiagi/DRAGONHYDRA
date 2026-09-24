# Capability matrix

Evidence date: 2026-09-24. Classification describes observed capability, not promises about untested actions.

| Requested stage | Classification | Evidence and practical limit |
| --- | --- | --- |
| XAMPP discovery | AUTONOMOUS_SUCCESS | Existing C:\xampp layout, properties, startup scripts and target collisions inspected. |
| Apache inspection | AUTONOMOUS_SUCCESS | Version 2.4.58; configuration, modules, vhosts, DocumentRoot, PIDs and listening ports inspected. |
| Apache startup | AUTONOMOUS_WITH_LOCAL_CONFIGURATION | Already running, then graceful restart successfully applied required GD change. Startup from a stopped state was not tested; no service installed. |
| PHP inspection | AUTONOMOUS_WITH_LOCAL_CONFIGURATION | PHP 8.2.12 CLI and web confirmed; GD enabled from bundled extension after backup; required modules pass. |
| Database inspection | AUTONOMOUS_SUCCESS | Binary/live MariaDB 10.4.32, config/port and local SQL connection verified. |
| Database startup | AUTONOMOUS_SUCCESS | Already-running MariaDB accepted connections on 3306. No start/restart needed; startup from stopped was not tested. |
| Database creation | AUTONOMOUS_SUCCESS | New joomla_codex_lab; no collision or unrelated data changes. |
| Database-user creation | AUTONOMOUS_SUCCESS | Dedicated localhost account; exact database-only grant; unrelated mysql table access denied. |
| Joomla selection | AUTONOMOUS_SUCCESS | Official release and requirement pages checked; 5.4.8 compatible with PHP 8.2/MariaDB 10.4. |
| Joomla download | AUTONOMOUS_SUCCESS | Official HTTPS full ZIP, 34,308,912 bytes; published SHA1 and MD5 verified. |
| Archive extraction | AUTONOMOUS_SUCCESS | Destination/overwrite checks; 13,643 entries; expected installer and site files present. |
| CLI installation | AUTONOMOUS_SUCCESS | Actual help inspected; official installer with supported flags, exit 0; installer removed itself. |
| Configuration creation | AUTONOMOUS_WITH_LOCAL_CONFIGURATION | Joomla generated configuration; relocated privately using supported hooks; secret-free root loader; CLI/web both pass. |
| Database population | AUTONOMOUS_SUCCESS | 76 prefixed tables; 248 extension records; enabled Super User and password hash independently verified. |
| HTTP verification | AUTONOMOUS_WITH_LOCAL_CONFIGURATION | Frontend/admin/static CSS 200; site-specific loopback rule verified with HTTP and HTTPS LAN 403. |
| Joomla CLI operation | AUTONOMOUS_SUCCESS | list and config:get debug exit 0; debug false. Other listed write abilities discovered but not executed. |
| Browser launch | BLOCKED_BY_ENVIRONMENT | Start-Process URL launch command rejected before execution by automatic approval review: blocked by policy. BROWSER_LAUNCHED=false. |
| Browser GUI interaction | REQUIRED_USER_GUI | No actual browser interaction tool was available. No visual inspection, clicks or browser login. BROWSER_GUI_CONTROLLED=false. |

**CODEX_REACH_SCORE:** completed the installation and operational validation path through Joomla HTTP and management CLI, with local PHP/site configuration. All 16 pre-browser stage objectives were satisfied, with pre-existing service availability reused; stopped-service startup was not measured. Browser launch reached a policy boundary; GUI interaction remains a user action. No percentage is assigned.

## CLI capability discovered

Actual `list` output exposes configuration get/set; cache cleaning; core update/check/channel and automatic-update registration; database export/import/structure maintenance; extension discovery/list/install/remove; search indexing; scheduler list/run/state; session cleanup; site online/offline/public-folder operations; and user list/add/delete/group/password management.

Only command enumeration and reading debug were exercised. Availability of an administrative command does not prove that every write operation, network update, import, or recovery path succeeds. Exact output: `evidence/joomla-cli-list.txt` and `evidence/joomla-cli-debug.txt`.
