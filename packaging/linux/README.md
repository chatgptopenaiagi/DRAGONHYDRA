# Linux preparation bundle

This development bundle contains a platform-independent application wheel, its
exact source manifest, a read-only target preflight, an explicit local installer,
and a user-service template. It does not include a Linux Python interpreter,
server dependencies, Joomla/MariaDB, local model weights or a desktop application.
The current source is identified by its content hash; it is not a frozen release.

The current source includes the installed Windows A6 context/package/3 contract
and dashboard. The preceding A5 r2 preparation wheel reproduced all4,407 retained
event rows, both source squads and native pages under Ubuntu Python3.14.4 without
provider HTTP or database writes, supplementing four core CLI cases. Those are
historical parser/core proofs; inspect this bundle's actual report before claiming
new validation. A separate owner has installed A5-derived R8 API/model components;
their environment and scope are recorded in the concurrent handoff. Recheck and
reuse compatible existing dependencies rather than assuming the earlier stock
interpreter's missing-package result describes every environment. Task receipts,
archive hashes and exact source comparisons are retained under `build/linux`.

The supported application runtime is Python 3.14. Reuse an existing compatible
environment containing the exact FastAPI, Uvicorn, OpenPyXL and tzdata versions
listed by the preflight. Missing dependencies produce `requires_configuration`.
No package, model or operating-system component is downloaded by these scripts.

Inspect without installing:

```sh
python3 preflight.py --bundle .
```

On an authorized Linux host with a passing preflight, choose a **new** private
prefix and state path, then explicitly install the included wheel:

```sh
bash install.sh --prefix /absolute/private/dragonhydra --state /absolute/private/dragonhydra-state --apply
```

The installer creates a venv that reuses the inspected interpreter's installed
packages and installs only this wheel with `--no-index --no-deps`. It refuses an
existing prefix, retains partial-install diagnostics, and changes no service.
It writes a reviewed user-systemd unit into the selected prefix; it neither
registers nor activates it. To run manually after installation:

```sh
DRAGONHYDRA_STATE=/absolute/private/dragonhydra-state /absolute/private/dragonhydra/run-server.sh
```

The API always binds `127.0.0.1`. Protect its generated pairing token. Public
access requires separately authorized HTTPS and the existing read-only gateway;
this package exposes no VPS endpoint or database port. A real VPS address, SSH
host trust and deployment access have not been supplied. The existing gateway
preparation is under `deployment/public-access/vps` in the source project.

The Windows build report distinguishes wheel construction, actual Linux core
smoke checks and missing Linux server dependencies. A passing CLI smoke is not
an installed HTTP service or a reboot test. Inspect `build-report.json` outside
the bundle for the exact current verification scope.

Android production signing also remains external: the existing Android build
uses the established development certificate. No authorized production publisher
keystore is configured; this bundle does not create a signing identity.
