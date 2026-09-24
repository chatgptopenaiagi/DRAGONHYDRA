# Failures and capability limits

The Joomla deployment and independent HTTP/database/CLI checks succeeded. Browser launch remains incomplete because the execution environment rejected the launch command before it ran.

| Finding | Classification | Handling and final state |
| --- | --- | --- |
| GD was installed but disabled in PHP | `AUTONOMOUS_WITH_LOCAL_CONFIGURATION` | Backed up `php.ini`, enabled only `extension=gd`, gracefully restarted existing Apache, and verified GD in CLI and web PHP. Resolved. |
| Login shell changed Conda to base, where PyTorch was unavailable | `AUTONOMOUS_WITH_LOCAL_CONFIGURATION` | Used `login:false` to preserve `codex-pytorch` and confirmed Python 3.14.7, PyTorch 2.14.0+cu132 and CUDA availability. No environment or package changes. Resolved. |
| Requested Windows browser launch command was rejected | `BLOCKED_BY_ENVIRONMENT` | The command containing `Start-Process -FilePath` for the two verified localhost URLs was rejected before execution with `CreateProcess ... rejected: blocked by policy`. No more specific reason was supplied. No browser launch is claimed. |
| Browser visual inspection, clicking and administrator login | `REQUIRED_USER_GUI` | No browser-interaction tool was available. HTTP responses and CLI state were verified independently; no GUI control or visual validation is claimed. |

The browser launch rejection came from automatic approval/execution review, despite the user's explicit authorization. The rejected command did not execute. Completing the GUI portion requires opening [the frontend](http://localhost/joomla-codex-lab/) and [the administrator page](http://localhost/joomla-codex-lab/administrator/) in the user's browser. The plaintext Super User password is stored only in the designated local secret file; Joomla's runtime database password is also in its protected configuration outside htdocs. No password is included here.

## Nonblocking diagnostics and pre-existing conditions

- Apache reports `AH00112` for the existing missing DocumentRoot `C:/CS16-LAB/web/public-deny`. The unrelated virtual-host configuration was not changed. The laboratory's `localhost` virtual host resolves to `C:/xampp/htdocs` and serves Joomla successfully.
- A GD probe that redundantly specified `-d extension=gd` after GD was enabled emitted an "already loaded" diagnostic. Later ordinary PHP CLI and web checks were clean.
- `httpd -h` returned exit code 1 while displaying command help. This was not an Apache startup or runtime failure.
- An ACL-inspection invocation passed two paths to `icacls`, which rejected the second argument without changing any ACL. A subsequent `Get-Acl` inspection verified the protected credential/runtime configuration access rules.
- PHP upload and POST limits remain 40M. They are below the experiment's 64M recommendation but did not prevent the official Joomla installation; they were not changed without a demonstrated requirement.
- Existing Apache and database listeners bind beyond loopback. They were not broadened or reconfigured. The new site's loopback guard was verified with HTTP and HTTPS 403 responses through the LAN address, while localhost worked.

There was no remaining Joomla compatibility, database-credential, installation, configuration, database-population, frontend, administrator-endpoint or CLI blocker. Joomla 5.4.8 meets the observed stack's [official minimum requirements](https://manual.joomla.org/docs/5.4/get-started/technical-requirements/) and was downloaded from [Joomla's official release page](https://downloads.joomla.org/cms/joomla5/5-4-8). No integration with Python was attempted during this deployment experiment.
