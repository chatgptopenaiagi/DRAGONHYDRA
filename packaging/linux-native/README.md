# Native Linux API-server component

This packaging increment is owned separately from the active coordinator's
`packaging/linux` preparation bundle. It reads that frozen bundle without edits.
It builds a genuine Debian AMD64 package with the application and all pinned
Linux server libraries, including CPython3.14's native `pydantic_core` wheel.
The OS CPython3.14 runtime is an explicit dependency. No Python package download
occurs during installation or startup. Revision5 applies one exact-hash,
reviewed Linux listener patch to its isolated payload. The base wheel stays
unchanged. The effective source manifest, application build-info and Debian
identity record both the base and patched identities; wheel RECORD is updated.

This is **not the complete workstation**: no desktop application, Apache/PHP,
Joomla, MariaDB or model weights are included. SQLite is the selected sports
backend. Broader Linux workstation packaging remains unfinished.

Build from the project root in the installed Ubuntu26.04 WSL environment:

```sh
PIP_CACHE_DIR="$PWD/runtime/linux-native/cache" TMPDIR="$PWD/runtime/linux-native/scratch" \
  python3 -m pip download --index-url https://pypi.org/simple --only-binary=:all: \
  --dest runtime/linux-native/wheels fastapi==0.162.0 uvicorn==0.42.0 openpyxl==3.1.5 tzdata==2026.2
python3 -B packaging/linux-native/build_deb.py \
  --bundle build/linux/prep-20261031-r2/dragonhydra-linux-dev-9f3d6e5ab108 \
  --work build/linux/native-kernel-20261031/build-5 --revision 5 \
  --output dist/linux/native-kernel-20261031/r5
```

On an authorized Ubuntu26.04 x86_64 host with Python3.14, install the resulting
`.deb` through `sudo apt install ./dragonhydra-api_..._amd64.deb`. On a systemd
host its package script enables and starts `dragonhydra-api.service`. The API
binds loopback only and selects a free port on its first managed start, then
retains it in `/var/lib/dragonhydra-api/managed-port.json`. The actual address is in
`/var/lib/dragonhydra-api/endpoint.json`; the protected local-session file is for
the server administrator's explicit pairing flow. This component has no desktop
shortcut or automatic public/LAN exposure. No VPS address is implied.

Revision5 keeps that address through restart and bounded failure recovery.
Normal command-line `--port 0` retains its ephemeral behavior. An explicit
`DRAGONHYDRA_PORT` overrides the saved choice. A conflicting live listener is
reported with its errno; no listener is killed or silently displaced. Upgrading
an active revision4 captures its verified endpoint before stopping the exact
package-owned service. It waits up to75 seconds for the legacy TCP TIME_WAIT
state to retire before unpacking. This is a bounded upgrade delay. Subsequent
Linux listeners use SO_REUSEADDR; SO_REUSEPORT is never enabled.

Configuration is `/etc/dragonhydra/api.env` (root-readable), binaries are under
`/opt/dragonhydra/api`, state is `/var/lib/dragonhydra-api`. Use native `systemctl
status/restart dragonhydra-api` for service management. Uninstall scripts retain
the state directory; administrators must explicitly choose whether to retain
credentials before any manual data removal.

Revision6 also removes this unit's package-created enablement links and reloads
systemd after removal, so the removed executable cannot remain registered as a
loaded service. The helper's `purge` action here clears only service bookkeeping;
it does not purge the Debian package or delete configuration, database, evidence,
pairing or managed-port files. Reinstallation applies normal systemd enable
presets afresh. Upgrade and failed-upgrade actions do not run removal cleanup.

Verification records distinguish Debian-format inspection, isolated root/extract
installation, actual private HTTP launch and restart, systemd activation and a
clean-machine installation. WSL headless results do not establish Linux desktop
or clean-machine success. No production signature is provided.

The archive writer explicitly sets root ownership and0644/0755 modes, with0600
for the environment template. It never copies permissive DrvFS modes or uses
`dpkg --nocheck`. Each included wheel retains its upstream metadata and notices.
