# Software inventory

This is a project-local inventory, observed 2026-10-28; it is not a machine-wide scan. Machine-readable details and source receipts are in [software-inventory.json](software-inventory.json).

| Component | Current evidence and role |
| --- | --- |
| PowerShell | 7.6.9 executed in this workspace. |
| Python | `py -3.14` executes Python 3.14.10; `python` on PATH was 3.10, so use the explicit launcher. |
| SQLite | Python's sqlite3 runtime reports 3.50.4; local DBs are under `runtime/`. |
| Git | 2.56.0.windows.3; before checkpointing the workspace root was unborn `master` with no commits. |
| Project | `dragon.py` dispatches `src/dragonhydra`; the exercised CLI and tests use the Python standard library. |
| Codex CLI | `codex --version` ran and reported 0.164.0; it was not modified. |
| GitHub CLI | `gh --version` reported 2.103.2; authenticated repository access and privacy were checked. |
| pip | `py -3.14 -m pip --version` reported 26.2.2; no system-wide installation was performed. |

The observed host was Windows 11 Pro Insider Preview build 29695, 64-bit,
with an AMD Ryzen 5 5600G (12 logical processors), 64 GiB installed memory,
AMD Radeon integrated graphics and an NVIDIA GeForce RTX 3050. The exercised
statistical models use CPU and Python's standard library; neither a GPU backend
nor GPU model execution was verified. Packaging uses separately documented
project-local tools; GPU and third-party ML libraries are not project runtime
dependencies.

Packaging uses the project-local `uv` build backend and PyInstaller; the exact
build commands and smoke results are retained with the release metadata. An
attempt with locally available Nuitka 2.8.10 failed while compiling Python
3.14.10 internals (`_gc_runtime_state` has no `young` member); do not assume
that historical Nuitka installation supports this interpreter.

The directory contains other pre-existing untracked evidence and project trees. They are not dependencies of the new root-level package. `runtime/` and `data/raw/` are ignored by the root `.gitignore`. Do not assume ignored artifacts are present on another machine.

The initial frozen verification recorded 161 tests, exit code 0, at 2026-10-28T14:38:20Z. The post-packaging verification recorded 163 passing tests at 14:43:46Z; see [TEST-RESULTS.md](TEST-RESULTS.md) and the recovery archive metadata.
