# Database port policy

DRAGONHYDRA uses MariaDB at `127.0.0.1:3306` and SQL Server at `127.0.0.1:1433`. Both ports were already in use by their intended engines simultaneously. Port 14330 remains a fallback only if a later inspection proves that another required service owns 1433.

## Observed listeners before integration

| Port | Protocol | Process / service | PID | Listen address | Interpretation |
| --- | --- | --- | --- | --- | --- |
| 3306 | TCP | `mysqld` / `mysql` | 5496 | `::` | Existing MariaDB listener; IPv4 loopback connection tested separately |
| 1433 | TCP | `sqlservr` / `MSSQLSERVER` | 13136 | `0.0.0.0`, `::` | Existing SQL Server application listener |
| 1434 | TCP | `sqlservr` / `MSSQLSERVER` | 13136 | `127.0.0.1`, `::1` | Local dedicated administrator connection, identified in ERRORLOG |
| 1434 | UDP | None | None | None | SQL Browser is Stopped and Disabled |
| 14330 | TCP | None | None | None | Unused fallback |

PIDs are checkpoint observations, not configuration constants. See initial listener evidence (LOCAL EVIDENCE PATH: `runtime/checkpoints/sql-diagnosis-20260924T162551Z/simultaneous-listeners.json`) and network settings (LOCAL EVIDENCE PATH: `runtime/checkpoints/sql-diagnosis-20260924T162551Z/network-auth.json`). The [final capability checkpoint — curated summary](evidence/dual-database-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/dual-database-20260924T163749Z-e9b792e6/capabilities.json`) independently records both listeners at once, both database services Running, Apache on 80/443, and Joomla HTTP 200. Database PIDs remained 5496 and 13136; no service restart occurred.

## Existing and retained configuration

| Setting | Before | Selected after |
| --- | --- | --- |
| MariaDB port | 3306 | 3306, unchanged |
| SQL TCP enabled | 1 | 1, unchanged |
| SQL ListenOnAllIPs | 1 | 1, unchanged |
| SQL IPAll TcpDynamicPorts | Blank | Blank, unchanged |
| SQL IPAll TcpPort | 1433 | 1433, unchanged |
| SQL Browser | Stopped / Disabled | Unchanged |
| Firewall configuration | Existing machine policy | Unchanged |

With SQL Server Listen All enabled, IPAll controls the port and individual IP Enabled fields are ignored. The blank dynamic field and explicit 1433 value already meet the static-port objective. [Microsoft TCP/IP properties](https://learn.microsoft.com/en-us/sql/tools/configuration-manager/tcp-ip-properties-ip-addresses-tab?view=sql-server-ver16) documents these settings.

No registry/network change or service restart is justified merely to reproduce the existing state. Read-only configuration snapshots are evidence, not backups of a modification that never occurred.

## Local-use compromise

OWNER_INTENT: Local development without opening database services to the Internet.

OBSERVED_CONSTRAINT: The machine already has broad listeners and active SQL connections whose local and client address is `10.5.0.2`. Restricting the instance to loopback could break those existing applications.

OPTIONS: Preserve the shared instance and use explicit loopback clients; or audit all consumers and later schedule a binding change with rollback.

CHOSEN_SOLUTION: Preserve existing bindings and firewall rules. New DRAGONHYDRA adapters accept local loopback endpoints and different ports. Do not claim the database servers themselves are now loopback-only, or that a listener snapshot proves Internet reachability.

REASON: No port conflict exists, and preserving unrelated workloads is part of the task. A future network-hardening change requires an inventory of dependent clients and an agreed endpoint transition.
