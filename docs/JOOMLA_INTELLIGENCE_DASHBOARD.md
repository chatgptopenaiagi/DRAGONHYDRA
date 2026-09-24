# Local presentation

URL: http://localhost/joomla-codex-lab/dragonhydra/

JSON DTO: http://localhost/joomla-codex-lab/dragonhydra/?format=json

This is a custom PHP endpoint inside the Joomla site's directory, one of the requested supported integration choices. It does not edit Joomla core, register a native Joomla component or modify Joomla content tables. The page links back to Joomla. A native Joomla menu/module remains optional future work.

Tracked source is `web/dashboard`; deployed copies are `C:\xampp\htdocs\joomla-codex-lab\dragonhydra`. It displays source/fixture/quote/conflict counts, measured database status, dynamic bridge state, separate Desktop confirmation and capture origin, latest processing status, last fetch, real fixtures and synthetic odds.

Python reads SQL using `dragonhydra_read`, creates the DTO, and writes `dragonhydra_web.presentation_cache` using `dragonhydra_ops`. PHP uses `dragonhydra_web`, which can SELECT only that table. Credentials stay in protected project runtime storage; `config/dashboard.local.json` holds only the credential path. No SQL Server credentials reach Joomla or PHP.

Run `scripts/Run-WebPipeline.ps1 summary` to rebuild. Fetch/process commands also refresh the cache after completion. The page reads the cache afresh on each request and shows its build time and age; no background polling or remote collection happens in the browser. SQL health is explicitly a summary-time measurement; MariaDB is checked by each page read. Synthetic odds cannot be mistaken for historical bookmaker observations.

The deployment has a localhost Apache access rule, a PHP REMOTE_ADDR guard, local Host validation, GET-only behavior, HTML escaping and restrictive CSP. Live tests verified HTTP 200, JSON/HTML bridge agreement, POST rejection, forged-host rejection and absent secrets. Visual inspection through a Desktop browser is blocked by tool availability; HTTP and response-content verification is complete.
