Published and independently verified: `genesis-linux-a7-20261101`, source commit `2ca96e9`, seven assets exact; all25 prior assets unchanged. The linked publication receipt records this later gate. Container now stopped with installed state retained; all acceptance servers exited0.

# Linux A6 runtime acceptance and GENESIS A7 — 2026-11-01

The existing Linux A6 distribution was installed and executed successfully in an
isolated Linux container. A reproduced installer defect then justified the A7
packaging increment. A6 archives, releases, Windows services, independent R8
files and existing databases were preserved. The starting repository checkpoint
was `060e1f549f66cd7239826c93695e01713e66ef18` on
`continuity/genesis-20261031-a6`; resolve the later checkpoint in
`ENGINEERING-STATE.json` and Git.

The engineering release identifier is `genesis-linux-a7-20261101`. The declared
product/Python versions remain `0.4.0-alpha.1` / `0.4.0a1`: A7 repairs installation
validation rather than changing the cross-platform application contract. All
application source inputs remain byte-identical to A6. Only Linux preflight and
its README differ among the scoped build inputs. The embedded build identity
therefore has a new source-content hash:
`8f170de1559b135cba73ecc5b12dda4d4cfdd94616136532e6e2a7649de15e3c`.

Publication is a separate gate. A6 publication was reverified with all three
assets matching GitHub sizes/digests and all 22 historical release assets
unchanged. Consult
[`LINUX-A7-PUBLICATION-VERIFICATION-20261101.json`](verified-reports/LINUX-A7-PUBLICATION-VERIFICATION-20261101.json)
for the A7 publication result; build and runtime receipts alone do not prove an
upload. The aggregate runtime evidence is
[`LINUX-A7-RUNTIME-VERIFICATION.json`](verified-reports/LINUX-A7-RUNTIME-VERIFICATION.json).

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| A6 `prep-20261031-a6/dragonhydra-linux-dev-3319aed91dd0.tar.gz` | 303125 | `2a1b74207661c191e48750e64d268b0f7727c5215a324091264c05c60acabee2` |
| A6 `prep-20261031-a6/wheel/dragonhydra-0.4.0a1-py3-none-any.whl` | 298310 | `021e07fd23deb43836171b44c95d25ec27b34a8db8209b667f2dd334d5f83d09` |
| A7 `prep-20261101-a7/dragonhydra-linux-dev-8f170de1559b.tar.gz` | 304065 | `a146186c9a1416059fbd6e9978a3da7a62ec8592b8ed9dae6989a04a934ca05a` |
| A7 `prep-20261101-a7/wheel/dragonhydra-0.4.0a1-py3-none-any.whl` | 298309 | `8b060a28de5eff5ab252d7c1586df36fd99ac626acd3df9e1d57c55b55138871` |

Paths in this table are beneath `build/linux/`. Same-named A6/A7 wheels have
different embedded build identities and must remain in separate directories and
releases. A7 was built once into a fresh output directory; A6 was not rebuilt.

The registered Ubuntu-26.04 distribution could not start because
`D:\WSL\Ubuntu-26.04\ext4.vhdx` was unavailable (`ERROR_PATH_NOT_FOUND`). The
observed D: contents were installation media. No storage remapping, OS reinstall
or R8 modification was attempted. Existing Docker Desktop/Engine 29.9.2 worked;
the cached alternative Python was 3.12 and incompatible. The acceptance container
uses the official Python 3.14.10 slim image pinned to
`python@sha256:cd89c30eda26ee911a4611b18680086e0ea42e6f5f8cbe653d07fa7958c9cec8`.
Execution reported Linux x86_64, the WSL2 kernel and glibc 2.41. The container is
`dragonhydra-a6-acceptance-20261101-r1`, with networking `none`, repository inputs
mounted read-only at `/inputs`, and selected host evidence at `/evidence`.
Application execution used UID 10001, native Linux state mode 0700 and session
token mode 0600. HTTP probes ran inside the container against allocated
127.0.0.1 ports; no host port was published.

The following dependency command actually completed inside that disposable
container. It installed 17 existing cached wheels, each matching the existing
hash lock; it made no dependency downloads or host package changes:

```sh
python -I -m pip install --no-index \
  --find-links=/inputs/runtime/linux-native/locked-wheels --require-hashes \
  -r /inputs/build/linux/native-kernel-20261031/public-r4/requirements.lock
```

The dependency lock SHA-256 is
`ae5a0c19ec94e188235728db94380dc5769c371faedad69f92fb70278b38a995`.
Direct server versions were FastAPI 0.162.0, Uvicorn 0.42.0, OpenPyXL 3.1.5 and
tzdata 2026.2. The cached native Pydantic core wheel targets CPython 3.14 x86_64
manylinux; this proof does not cover Alpine/musl or another Python minor version.

After extraction with the standard library's safe data filter, the documented
installer completed with exit 0 for each new prefix. The exact A7 invocation was:

```sh
/bin/bash /opt/dragonhydra-a7-acceptance/bundle/dragonhydra-linux-dev-8f170de1559b/install.sh \
  --prefix /opt/dragonhydra-a7-acceptance/installed \
  --state /opt/dragonhydra-a7-acceptance/state --port 18763 --apply
```

A6 used the corresponding `/opt/dragonhydra-a6-acceptance` prefix and
`dragonhydra-linux-dev-3319aed91dd0` bundle. Pip dependency checks and installed
entry points passed. The installer wrote a local systemd template without
registering or activating it. The retained-state A6 HTTP run used the installed
venv interpreter; A7 exercised its installed `dragonhydra-server` entry point.
Both versions also executed their installed `run-server.sh` against separate
fresh states, passing `DRAGONHYDRA_STATE` and `DRAGONHYDRA_PORT=0` only in the child
environment. The wrapper always binds loopback; its port environment setting is
separate from the installer's systemd `--port` substitution.

| Executed gate | Result and scope |
|---|---|
| A6 retained-state runtime | 12 groups passed; existing wheel installed, imported and served actual HTTP |
| A7 retained-state runtime | 12 groups passed; repaired bundle installed and served through installed CLI |
| Health and errors | Readiness/liveness HTTP 200; anonymous matches 401, missing match 404, invalid limit 422 with expected structured codes |
| Retained sports | 1204 matches from the older isolated source snapshot; Argentina–France retained score 3:3, 4407 events, France 24 / Argentina 26 squad entries |
| Package contracts | Default `sports-evidence-package/2`; explicit context selects `/3`; package hash `60802e4502eac8a38e638d6711a302ac716d2711131c101ff221de87444a0aa6` equals the preserved Windows/source baseline |
| Analysis | Real 20-team standings with 760 played-team entries; durable deterministic explanation cites the retained source evidence |
| Exports | JSON, CSV and XLSX jobs wrote real files; HTTP downloads matched file SHA-256; OpenPyXL opened the workbook and checked the match ID and metadata sheets |
| Retained-state restart | Both versions restarted, retained the selected match/package and all three completed export jobs/files; all normal server exits were 0 |
| Fresh A6 / A7 | Each passed 7 groups: empty DB initialized, bundled retained import inserted 760 real records, all records remained identical after restart, repeated import inserted 0, SQLite integrity and foreign keys passed |

The 1204-match snapshot is deliberately separate from the preserved Windows
workstation's reported 1221 matches. It contains 760 public fixtures and 444
distinct current connector football records; 2140 stored connector observation
rows include historical captures. Counts are not interchangeable. Snapshot DB
and four context payload hashes matched before/after preparation; only the
isolated copies had pending jobs cancelled and schedules disabled. Live runtime
configuration, local-AI settings, `local-session.json` and credential-vault files
were not copied.

Cross-platform calculation comparison was separately executed using the exact
installed A6 wheel on Windows and Linux, separate copied state and fixed cutoff
`2026-10-31T23:59:59.000000Z`. Canonical comparison payloads matched byte-for-byte:
`3bbb93ad7afbe1c4c4a2f952ddc351885ae111e43ab56ae942112e40279300ed`.
The payload covers match IDs/presentations/shapes, selected match, reconstructed
standings, an available statistical forecast, deterministic explanation and
Package/3. The recorded numerical comparison found no differences at relative
and absolute tolerance `1e-12`. This is evidence for this wheel, snapshot and
cutoff, not all future data or every client. See the paired
`A6-WINDOWS-CALCULATIONS-20261101.json` and
`A6-LINUX-CALCULATIONS-20261101.json` under `verified-reports/`.

The installer repair closes an actual false-success case. With server packages
installed only in a parent venv, A6 preflight passed and installation returned
0, but the installed child failed with `ModuleNotFoundError: fastapi`.
`--system-site-packages` inherits the base interpreter's packages rather than
the parent venv's local packages, and `pip check` cannot discover absent optional
server extras. A7 inspects the new child's actual versions/imports before
application installation or state/launcher creation, returning exit 2 with
`INSTALLED_RUNTIME_DEPENDENCIES_UNAVAILABLE` when reuse is impossible. It also
checks the server import before reporting installation success. Actual negative
and positive Linux reproductions and focused regression tests passed; consult
`LINUX-A7-PARENT-VENV-REGRESSION-20261101.json` and
`LINUX-A7-POSITIVE-INSTALL-20261101.json` under `verified-reports/`.

Private raw data, DBs, tokens and generated exports remain local. Historical
failed helper receipts are retained: an initial diagnostic queried a nonexistent
table, an initial runtime assertion incorrectly assumed 1221 rows, and an
initial fresh-resource assertion included receipt filenames. These were helper
assumptions corrected without repeating the completed A6 installation or changing
application data. Their passing successors are separately identified.

This increment is **BUILT, INSTALLED, EXECUTED, TESTED and runtime VERIFIED** on
the named Linux container. Publication requires its independent server-digest
receipt. It does not establish Ubuntu/R8 recovery, systemd activation, reboot or
clean-machine operation, host-browser access, Linux desktop, Joomla/MariaDB
workstation integration, VPS deployment, model inference, new provider HTTP or
production signing. SQLite remains the application backend. The highest-value
remaining Linux objective is a new owned deployment/reboot acceptance target
with its environment and ownership established first; preserve this container
and its exact restart commands in the current handoff.
