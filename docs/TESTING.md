# Test tiers and CI boundary

Python **3.14** is required in every tier. The portable suite validates contracts without claiming that SQL Server, MariaDB, XAMPP, CUDA or a Desktop browser exists on GitHub. The full local suite remains [scripts/run_tests.py](../scripts/run_tests.py), unchanged by CI separation.

| Tier | Scope | Requirements | GitHub Actions |
| --- | --- | --- | --- |
| 1 | Unit, temporal/provenance contracts, configuration validation, parser/odds primitives, mocked ingestion and handoff recovery, repository audit/link tests | Python 3.14 standard library and authored checkout | Ubuntu and Windows |
| 2 | Database least privilege, append/replay/as-of behavior, configured Joomla endpoint, generated credential containment | Provisioned local SQL Server/MariaDB/XAMPP, bounded credentials and existing synthetic fixture state | No |
| 3 | Canonical Conda interpreter, NumPy/PyTorch/CUDA/cuDNN, Windows services/listeners, pinned local PDF parser | Owner's configured Windows laboratory and project-local vendor libraries | No |
| 4 | Genuine Desktop browser capture through filesystem handoff, CLI, SQL Server, MariaDB and Joomla | Available Desktop browser, reviewed public source, actual capture and receipts | No; manual evidence gate |

## Tier 1: portable checks

From a fresh checkout, with Python 3.14 on PATH:

```powershell
python scripts/run_ci.py
python scripts/run_ci.py --list
python scripts/run_ci.py --syntax-only
```

No package installation, editable install, local credentials, database driver or GPU library is needed. `run_ci.py` adds the checkout's `src` and `tests` paths, creates only the ignored `runtime/tmp` parent, compiles authored Python in memory, validates package metadata, then runs the explicit portable manifest. Synthetic temporary artifacts are cleaned by their tests. Tests may mock network and database operations, but real socket access, canonical `runtime/secrets`/`runtime/vendor` reads and optional live-library imports fail the tier. This guard catches accidental dependencies; it is not a sandbox for hostile code.

Test classes must be classified in `PORTABLE_CLASSES` or `LOCAL_CLASSES` in [run_ci.py](../scripts/run_ci.py). Five mixed-class tests have explicit `LOCAL_METHODS` entries: two generated probe-credential checks, the dual-database secret/checkpoint comparison, the pinned project-local PDF parser check, and exact published-schema equality at the canonical laboratory root. New/unclassified classes and stale manifest entries fail CI. Local tests are reported as outside the selected tier, never counted as passed or skipped. Any skipped portable test fails the tier.

The original published handoff schema embeds `C:\xampp\DRAGONHYDRA`; the runtime schema binds to the actual checkout. The original equality test remains unchanged in tier 3. A [portable comparison](../tests/test_ci_contracts.py) verifies both root bindings and exact equality of every other schema field, so a checkout can run outside the laboratory path without weakening envelope validation.

The repository baseline selects **164 portable tests** and leaves **43 existing tests** in local tiers (207 total). Use current runner output for subsequent counts. Passing tier 1 is not equivalent to passing the complete suite or demonstrating a genuine Desktop capture.

Scientific Phase A adds portable temporal properties/canaries, revision replay, entity ambiguity/rescheduling, metric known answers, deterministic chronological replay and mocked prospective acquisition. These use Python's standard library only; generated temporal cases avoid a new property-testing dependency. Historical demonstration and genuine source capture are separate local experiments, never CI network tasks. Current results are in the [scientific summary](evidence/scientific-spine-summary.json).

Optional immutable local evidence (the directory must already exist):

```powershell
python scripts/run_ci.py --output runtime/checkpoints/<new-checkpoint>/portable-tests.json
```

The JSON file must be new; it records passed/failed/error/skipped counts, test IDs, outside-tier reasons and blocked dependency attempts. Do not upload runtime evidence through Actions.

## Local laboratory setup

These commands describe the existing owner machine, not an automatically reproducible server installation. Configuration paths, driver directories, services, credentials and synthetic checkpoint fixtures must already exist. Provisioning is a separate reviewed operation; tests do not create accounts or alter unrelated applications.

```powershell
conda activate codex-pytorch
Set-Location C:\xampp\DRAGONHYDRA
$env:PYTHONPATH = "$PWD\src;$PWD\tests"
$env:PYTHONDONTWRITEBYTECODE = '1'
```

## Tier 2: local integration

Run the existing service tests and the three generated-credential checks explicitly:

```powershell
python -m unittest -v test_mariadb_probe.LiveMariaDBTests test_web_pipeline.LiveWebSQLTests test_handoff_bridge.LiveBridgeTests test_configuration.ConfigurationTests.test_plaintext_probe_secret_absent_from_source_config_docs test_configuration.ConfigurationTests.test_credential_repr_does_not_reveal_password test_dual_database.DualDatabaseConfigurationTests.test_secrets_absent_from_source_config_and_checkpoints
```

The database tests use dedicated bounded identities, rollback temporary insertion probes and test replay against the existing labelled synthetic envelope. They rely on initialized state; an empty database is not interchangeable with this laboratory. Joomla checks use `http://localhost/joomla-codex-lab/dragonhydra/`.

## Tier 3: machine regression

```powershell
python -m unittest -v test_compute.ComputeBaselineTests test_dual_database.LiveDualDatabaseTests test_web_pipeline.LicenseBridgeTests.test_unreadable_pdf_stays_unverified test_handoff_bridge.EnvelopeTests.test_schema_matches_published
python -m dragonhydra diagnostics
```

The PDF check verifies the pinned `runtime/vendor/pypdf-6.19.0` installation. CI intentionally does not substitute a globally installed parser or weaken its origin check. Compute checks retain the canonical interpreter path and actual GPU result requirements. CPU fallback remains a separately labelled diagnostic outcome.

For the complete existing local suite, including all tiers 1–3, use a new evidence destination:

```powershell
$checkpointName = 'local-tests-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$testCheckpoint = New-Item -ItemType Directory -Path (Join-Path 'runtime/checkpoints' $checkpointName)
python scripts/run_tests.py --output (Join-Path $testCheckpoint.FullName 'tests.json')
```

[Run-Genesis.ps1](../scripts/Run-Genesis.ps1) and [Run-DualDatabase.ps1](../scripts/Run-DualDatabase.ps1) also create unique local checkpoints and run diagnostics plus the full suite. They are intentionally not CI entry points. Preserve failed checkpoints as well as successful ones.

## Tier 4: genuine Desktop browser handoff

Follow [Desktop handoff instructions](CODEX_DESKTOP_HANDOFF_INSTRUCTIONS.md) and the [bridge contract](CODEX_DESKTOP_CLI_BRIDGE.md). Capture an allowed public source in the Desktop browser, preserve hashed artifacts and observation/availability times, publish the validated envelope, then run the existing one-shot consumer:

```powershell
python -m dragonhydra.handoff.publish --draft 'runtime/handoff/browser_notes/<UUID>.draft.json'
python -m dragonhydra handoff consume --once
```

Inspect the receipt, SQL provenance, MariaDB summary and Joomla output. A synthetic envelope, mocked browser path, CLI fetch or blocked-browser report cannot satisfy this gate. If the browser is unavailable, record that actual failure without forcing a success claim. `LiveBridgeTests` preserve strict assertions about the historical synthetic fixture and compare current presentation with the latest SQL envelope, validated archive and immutable final receipt. Blocked attempts must contribute zero observations and cannot become the confirmed Desktop handoff. Those consistency checks do not themselves certify a genuine capture.

## Workflow security and interpreter availability

[CI](../.github/workflows/ci.yml) runs on `push` to `main`, ordinary `pull_request` and manual dispatch. [Repository safety](../.github/workflows/security.yml) checks tracked content with `repository_audit.py --tracked --check`, Markdown links with `check_repository_links.py`, then Python syntax and metadata. The link check reads exact Git index blobs and requires targets to belong to that index; a file existing only on the local machine does not satisfy it. In a fresh Actions checkout, the index contains the checked-out commit. Both workflows use `contents: read`, full action commit pins, no persisted checkout credential, no repository secrets, no artifact uploads, and bounded job timeouts. Neither uses `pull_request_target`, live sources, bookmaker requests, infrastructure mutation or wagering. The safety scan is a bounded pattern/policy check, not a dependency vulnerability database audit or a proof that every possible secret has been detected.

Python 3.14 is explicitly selected with prereleases disabled. The [official Python build manifest](https://github.com/actions/python-versions/blob/main/versions-manifest.json) contained stable 3.14.7 Linux and Windows builds when verified on 2026-09-24. [setup-python's version selection](https://github.com/actions/setup-python/blob/v6.1.0/README.md) can obtain matching builds if absent from the hosted tool cache. A setup failure fails CI; there is no older-Python fallback.

Actions are pinned to `actions/checkout` v6.0.2 (`de0fac2e4500dabe0009e67214ff5f5447ce83dd`) and `actions/setup-python` v6.1.0 (`83679a892e2d95755f2dac6acb0bfd1e9ac5d548`), verified against their official repository tags. Review updates deliberately. Least-privilege tokens, ordinary PR events and full SHA pins follow [GitHub's secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use).
