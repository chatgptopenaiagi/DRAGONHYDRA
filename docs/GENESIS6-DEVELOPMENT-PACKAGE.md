# GENESIS-6 virtual development package

Component version: `0.1.0-virtual-experimental`. This is a web-first, synthetic
research development ZIP. Every match, event, market input, outcome and reasoner
response belongs to the virtual environment. No live provider or external OpenAI
request is configured. The virtual pairing token is a public simulation value,
not a credential for an existing installation.

## Build from a frozen source

Root freezes the complete source first. The existing Python 3.14 environment and
exact Git executable are reused. The builder reads a clean, matching Git HEAD;
it rejects dirty, mismatched or linked sources. It neither installs dependencies
nor runs the application. For example, from this source directory:

```powershell
& 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\tools-env\Scripts\python.exe' -B scripts/build_genesis6.py `
    --source-commit '<full frozen 40-character commit>' `
    --output '<existing output directory>\GENESIS-6-REALTIME-INTELLIGENCE-development.zip'
```

Both the ZIP and its `.zip.sha256` sidecar must be new paths outside the source.
The builder selects committed Git blobs before reading their contents. It includes
Python application code, six local web assets and their desktop source mirrors,
the virtual launcher, builder, offline acceptance and browser acceptance scripts,
realtime/package tests, realtime documentation,
this document, the public Python dependency lock and a license when present.
It excludes inherited sporting data, all `resources/data`, examples, fixtures,
unrelated tests, `.git`, bytecode caches, runtime state, databases and credential
files. Dependencies and installers are not bundled or downloaded.

Every member has a fixed ZIP timestamp and file mode, and members and JSON keys
are ordered. Identical committed bytes and commit metadata produce identical ZIP
bytes with the same Python/zlib toolchain. The package contains:

```text
GENESIS-6-REALTIME-INTELLIGENCE/
  source/
    GENESIS6-BUILD.json
    GENESIS6-PAYLOAD.json
    scripts/Start-Genesis6.ps1
    src/dragonhydra/...
```

`GENESIS6-BUILD.json` binds the full commit, component version, commit timestamp,
synthetic-only scope and payload-manifest SHA256. `GENESIS6-PAYLOAD.json` lists
each selected file's path, byte length, SHA256 and Git blob SHA1. Git SHA1 is
recorded as Git object identity; payload integrity uses SHA256.

## Extract and run

Compare the ZIP SHA256 with the separately trusted build receipt or distributed
digest before extraction. Keep the directory prefix above intact; the launcher
requires the `GENESIS-6-REALTIME-INTELLIGENCE/source` layout. Use the previously
verified Python 3.14 environment with the existing FastAPI, uvicorn, Pydantic and
application dependencies. The public lock describes that environment; this
package does not provision it. No installer or download is part of this workflow.

From the extracted `source` directory, a read-only identity check is:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
& '<existing Python executable>' -B -m dragonhydra.realtime.server --build-info
```

Then launch with PowerShell 7 and an available loopback port:

```powershell
& .\scripts\Start-Genesis6.ps1 -Python '<existing Python executable>' -Port 19380
```

The foreground server uses only `127.0.0.1`. Pair through the existing application
session screen using the simulation token printed by the launcher. Open the
Research tab and explicitly create a synthetic scenario. Navigation and status
reads do not create scenarios. Stop the owned foreground process normally when
finished. There are no service controls, SQL Server operations or original
installation adoption in this launcher.

A new marked runtime is created beneath the package's sibling `runtime/web`
directory, outside the sealed `source` tree. Existing unmarked nonempty state is
refused. An OS lock prevents concurrent use of the same marked runtime. Ports
18740 through 18751 are refused; an occupied selected port fails without stopping
its listener. The launcher uses Python `-B` so imports do not create bytecode files
inside the sealed source inventory.

`scripts/accept_genesis6.py` supplies the explicit offline synthetic acceptance
workflow. `scripts/browser_genesis6.py` supplies browser acceptance against the
owned loopback virtual server and requires the existing Playwright/Edge capability.
Run their documented `--help` contracts with the same Python and `-B`; keep their
new output paths outside sealed source. They do not provision dependencies. The
Git-dependent benchmark and `Verify-Genesis6.ps1` wrapper remain checkout-only and
are not bundled. These tools' presence does not establish executed acceptance.

## Truthful identity after extraction

When Git metadata exists in the source or an ancestor, identity comes from that
exact Git worktree. Git failure or a different Git root is an error; the package
seal cannot hide it. The Git route reports whether the checkout is dirty.

Only when Git metadata is absent does startup verify the curated package seal.
It requires the expected layout, schema, source/version agreement, manifest hash,
finite file policy, complete exact inventory and every file's length and hashes.
Missing, changed, extra, forbidden or reparse-linked files fail before runtime
creation or a listening socket. `--build-info` performs the same verification and
does not create state. Run with `-B`; an unexpected `__pycache__` is rejected.

Successful extracted identity reports `payload_verified: true` and
`verification_scope: LOCAL_PAYLOAD_SHA256_MANIFEST_AT_STARTUP`. This proves local
bytes match the included seal at that check. It is not a digital signature or
independent proof that a Git commit exists: trust in origin comes from the external
ZIP digest and build receipt. Rewriting code and both metadata files is outside
that local integrity claim. Verification occurs at startup, not continuously.

The package tests use fictional temporary fixtures. Passing those tests is not a
claim of installed Windows, native client, Android device, live-provider or
external-OpenAI acceptance. The final archive build, extracted launch and genuine
browser acceptance require separate recorded execution after source freeze.
