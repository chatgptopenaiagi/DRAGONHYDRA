# XAMPP role

`C:\xampp` is DRAGONHYDRA's local infrastructure body. The project lives at `C:\xampp\DRAGONHYDRA`; its source, experiments, runtime evidence and secrets are not placed beneath Apache's document root. Existing applications retain their separate directories and database ownership.

The discovered baseline is Apache 2.4.58, PHP 8.2.12 and MariaDB 10.4.32, with HTTP 80, HTTPS 443 and database 3306. These are local observations, not a recommendation to replace the installation. The final inspection and service evidence are recorded in [PROGRESS.md](PROGRESS.md). Service versions and runtime configuration must be rechecked before future operational changes.

## Responsibility boundaries

| Component | Appropriate use | Boundary |
| --- | --- | --- |
| Apache | Local web delivery, future dashboards/admin surfaces and bounded HTTP routing | No neural-model execution inside an HTTP worker. Only explicitly selected public assets/adapters enter a web root. |
| PHP | XAMPP-native administration and thin web adapters | No duplicate domain temporal rules, long GPU training or heavy analytical pipeline. |
| MariaDB | Operational transactional state, source/jobs metadata and current projections | Historical analytics use their appropriate P2 engines; no universal database mandate. |
| Python 3.14 / Conda | Evidence validation, orchestration, math, AI, simulation and tests | Runs as an explicit process outside PHP; exact interpreter is selected by configuration/launcher. |
| PyTorch / CUDA / cuDNN | Bounded accelerator workloads when the operation supports them | A working Apache response does not establish GPU availability. |

The first implemented bridge is Python → MariaDB over loopback, with a [successful measured SELECT-only checkpoint — curated summary](evidence/foundation-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/genesis-20260924T155516Z-ddf9f093/bridge.json`). It does not establish a Python HTTP service, Apache reverse proxy, PHP-to-Python API or a job worker. Future web integration should submit a validated bounded request or job reference to a Python boundary and return a status/result reference; a PHP request should not own a long-running calculation.

## Joomla is a controlled source

The prior Joomla experiment at `C:\xampp\htdocs\joomla-codex-lab` supplies a known test database. [The MariaDB proof](../src/dragonhydra/integration/mariadb_probe.py) uses a separate SELECT-only account and fixed aggregate queries. It does not install a Joomla extension, change Joomla content or make its CMS schema part of DRAGONHYDRA's domain model. The earlier experiment records remain under `experiments/joomla-codex-lab` with their existing provenance.

No web directory, Apache/PHP configuration or Joomla file must change merely to perform this SQL proof. Account provisioning is scoped to the dedicated probe identity; no existing root password or unrelated grant is changed. Credentials stay in `runtime/secrets` outside web delivery, with paths rather than values in [genesis.toml](../config/genesis.toml).

## Local operation policy

Keep interfaces loopback-scoped for this laboratory. Do not install permanent Windows services, open firewall rules, expose remote phpMyAdmin or reinterpret localhost proof as Internet deployment. Inspect actual ports and process state before starting/restarting a component; use installed XAMPP-supported mechanisms only when needed. Avoid stopping an existing service used by another application.

Future service changes require a concrete reason, a targeted backup where applicable, exact change records and a verification/rollback plan. No change is justified solely by a newer software version number. XAMPP maintenance and security lifecycle evaluation are separate scoped work; this genesis neither upgrades the stack nor certifies it for public deployment.

Browser launch and browser GUI control remain distinct capabilities. They are not requirements for the current Python/MariaDB bridge and do not substitute for executable verification. The implemented source and executed outcomes are separated in [DRAGONHYDRA_GENESIS.md](DRAGONHYDRA_GENESIS.md) and [PROGRESS.md](PROGRESS.md).
