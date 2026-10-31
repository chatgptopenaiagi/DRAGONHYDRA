# Resume checkpoint — 2026-10-31

Workspace: `C:\xampp\DRAGONHYDRA`. Work stopped for preservation at the user's weekly budget limit. No A6 installation, preflight, provider fetch, model start or new service action occurred at this stop. Existing handover notes and all historical artifacts remain authoritative for their own dates.

Read this file, `NEXT-OBJECTIVES.md`, `ENGINEERING-STATE.json`, `CONTINUOUS-PROGRESS.md`, and `NEXT-LINUX-A6.md` before acting. Root is separately preparing the preservation report, resume instructions and Git publication. Read-only Git observation at this checkpoint: branch `genesis3-android-alpha`, HEAD `7e04b4ca355cee0bc322b579146be348644c444c`; a later root publication may advance it. Do not reset, clean or discard the working tree.

## Exact next action

The **prepared but NOT EXECUTED** read-only preflight command is:

`build/workstation/evidence/provider-a6-helper-review/preflight-command.ps1`

After consulting the machine capability registry and reviewing the prepared command, verify the reviewed helper hash and run that command only:

```powershell
Set-Location -LiteralPath 'C:\xampp\DRAGONHYDRA'
$resumeHelperHash = (Get-FileHash -LiteralPath 'tests/installation/context_ai_workstation.py' -Algorithm SHA256).Hash.ToLowerInvariant()
if ($resumeHelperHash -ne 'ddede711aef497282610cc7109f6190c57569e47076a8471b773b4da4b17c9fa') { throw 'Reviewed A6 helper changed; review before proceeding.' }
& 'C:\Program Files\PowerShell\7\pwsh.exe' -NoProfile -File 'C:\xampp\DRAGONHYDRA\build\workstation\evidence\provider-a6-helper-review\preflight-command.ps1'
```

The helper creates private evidence and a consistent read-only SQLite backup. It does not install or create a provider/model job in preflight. If the selected output directory already exists, inspect it and choose a fresh reviewed output; never overwrite evidence or automatically repeat a partially completed phase.

**Repair is a separate later action.** Require the passed preflight `journey.json`, review it, compute its SHA-256, then prepare a fresh command with `--phase repair --apply --preflight-receipt <path> --preflight-receipt-sha256 <reviewed SHA>` and a fresh output directory. It permits one hidden pinned NSIS invocation against the existing A2 test service only. Readchecks is another separate `--apply` phase requiring the passed repair receipt and its SHA. Do not run either from this preservation checkpoint without completing the preceding review.

## Built versus installed

**A6 is built and archive-verified, NOT installed.**

| A6 input | Exact value |
|---|---|
| Installer | `dist/connections/workstation-a6/DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe` |
| Installer bytes | 64,359,085 |
| Installer SHA-256 | `2d87e2bfac18099d9921674a2975604999fc7a79cddf36f5404cd293ff20c2d1` |
| Frozen kernel SHA-256 | `6960835b332728672183b2953c4003119ed743a721793dd6e21a7b66181607fc` |
| Source content SHA-256 | `886161d0a8c4f0bf3364fd6d0a9966630398bba6bfe27b84de9c5999a307acd4` |
| Source manifest SHA-256 | `110699237a7135eade0906145d7a5e0110300e14165fd7f5de9c955f545df6de` |
| UI app.js SHA-256 | `02f41202e40b8ea85948e3a115e360b74d76ef7abad35b0ee5e1702a90bc9053` |
| Extraction receipt SHA-256 | `9f4570cfeab2d46a9d7ba38b18968995016c7185c0671a0011960a08203d9df1` |

Reports: `build/connections/payload-20261031-a6/{BUILD-REPORT,SOURCE-MANIFEST,PAYLOAD-MANIFEST,INTEGRITY-VERIFICATION}.json` and `dist/connections/workstation-a6/{EXTRACTION-VERIFICATION,TEST-REPORT}.json`. The kernel has 68 scoped inputs, 710 files and 28 passing frozen smoke groups. Installer extraction verified 10,662 payload files plus seven NSIS extras. It is unsigned; no A6 installed, clean-machine or reboot claim exists.

**Last verified installation is A5-r2**, service `DragonhydraProvidersA2Test`, LocalService SID `S-1-5-19`:

- Install: `build/workstation/test-install/provider-a2/application files`.
- State: `build/workstation/test-install/provider-a2/state data`; kernel authority is SQLite under `kernel/core.sqlite3`.
- API/Joomla/MariaDB ports: 18746 / 18747 / 18748. Expected retained baseline: 1,221 records and 461 connector observations.
- Existing installed StatsBomb context: `source_context:e0d23975cdb98ebbdbc1ec0c0882b4e58d981970805f6c2417c2c653c9eb918e` for native match 3869685. It contains 4,407 events, France 24 / Argentina 26 source squad entries, and original 3:3 score. Preserve this context; do not submit another acquisition.
- Model configuration is blank. Four later explanation/export jobs and 16 events were ordinary concurrent activity with origin unproven; preserve them. Do not restore an earlier DB over them.
- A5 installed receipts: `build/workstation/evidence/provider-a5-r2-{repair,context}/journey.json`. Original C7 and all A4/A5 artifacts remain immutable.

## Accepted source behavior

`local_ai.py` keeps package/2 as default. Optional package/3 requires an explicit immutable C1 ID, reconstructs its exact retained parent and two role documents, adds only event-row/squad-entry counts, and permits model output containing a supplied fact ID only. Citations are resolved by application code. `source_context.by_id` verifies the selected record's structural predecessor prefix and reconstructs only the selected snapshot; a corrupt later tail does not rebind an old request. Default `latest()` remains conservative.

The API is under `/dragon/api/v1`: authenticated `GET /matches/{id}/analysis-package?context_record_id=<C1>` and explicit `POST /matches/{id}/local-explanations` body `{"context_record_id":"<C1>"}`. Omitted selectors retain /2 behavior. Queued requests freeze exact evidence; idempotent replay returns the same job. UI provides separate source-count package/export actions.

Source gate: 557 tests passed; eight Edge package/3 groups passed. The new installed helper has 11 offline guard tests passing in 0.474 s and independent static acceptance. Its historical helper inputs remain `statsbomb_context_workstation.py` SHA `d9991f2e3092b1cc96c45829f91e42942c985633f31ada2dcc0d58c02d1ab999` and `local_ai_workstation.py` SHA `44691a2ce7a46fd40839c6ab86722e715927eae56a94af927edfb37a29da2578`. Do not edit those historical helpers.

One actual SOURCE Qwen/API package/3 probe passed at `build/connections/sports-package-3-20261031/qwen-api-r1/report.json`. It selected **F1, E1-only finished-status**, retaining the full four-ID manifest. It did **not** select a C1 count fact. Do not repeat to force that result. Both owned processes exited, ports/keys/tokens were cleaned and retained source bytes stayed unchanged. Frozen F3/count-selection proof uses a labelled SYNTHETIC HTTP responder, not Qwen or provider downloads. Failed smoke setup receipts r1–r3 are preserved; clearing all Windows environment variables caused the synthetic HTTP failure, but the specific variable cause was not isolated.

## Tools, state and boundaries

Reuse `runtime/server-env/Scripts/python.exe` (Python 3.14.10), `PYTHONPATH=src` for tests, project-local `runtime/genesis2-pyinstaller-builder` (PyInstaller 6.22.3), PowerShell 7 at `C:\Program Files\PowerShell\7\pwsh.exe`, NSIS at `C:\Users\LOVE\AppData\Local\tauri\NSIS\makensis.exe`, and `C:\Program Files\7-Zip\7z.exe`. Existing Qwen runner/model paths are recorded in `scripts/probe_local_ai.py`; do not start them for the next installed check.

Before engineering, consult `C:\Users\LOVE\.codex\machine-capabilities\SOFTWARE-CAPABILITIES.md`, graph/routing/history/causal-memory JSON, and `C:\xampp\TRADING\scripts\Capability-Intelligence.ps1 ... -Json`. GENESIS-10 discovery starts at `E:\GENESIS-10\AGENTS.md` and `SESSION-HANDOFF.md`. Registry presence does not prove current functionality.

Previously observed endpoints were source `http://127.0.0.1:56864`, frozen-A2 `http://127.0.0.1:58141`, C7 `http://127.0.0.1:18744`, and A2 installed `http://127.0.0.1:18746`. These are historical bindings, not fresh health checks. Re-read public endpoint metadata and verify PID, executable, creation time and ownership before any authorized action. Never kill by port or assume an old PID is current.

Never print full `workstation.json`, pairing tokens, vault bodies or passwords. Use only the owner-readable **client** pairing metadata; kernel token/vault ACLs belong to LocalService/SYSTEM. No ownership/ACL takeover, credential rotation, model settings edit, ordinary provider resync, new context acquisition or additional restart belongs to the next readchecks phase.

## Publication checkpoint

Source9d6a9ef82f6f646ab020da5fb25969584e617299 is pushed on
`continuity/genesis-20261031-a6`. Final metadata follows on that branch.
Read PRESERVATION-REPORT.md and PUBLICATION-VERIFICATION.json. All11 release
payloads were verified by GitHub server digests. A6 is still NOT installed.
The committed safe preflight command copy is `docs/handover/commands/preflight-a6.ps1`
and matches the originally prepared build/evidence script; it has NOT run.
Do not execute it until the resume/environment/artifact/ownership checks pass.
