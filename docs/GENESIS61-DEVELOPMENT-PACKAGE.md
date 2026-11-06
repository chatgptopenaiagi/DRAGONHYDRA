# GENESIS-6.1 virtual experimental development package

This is source-based Python research software, component
`0.2.0-virtual-experimental`, not an EXE, Windows installer or production release.
Every sporting input, credential, provider, world and outcome is fictional.
There are no network provider calls or external OpenAI requests. The mock bridge
and original nine mathematical tools remain available in the replay workspace.

The curated package includes tracked Python modules, mirrored web assets,
PowerShell launch/verification scripts, acceptance and benchmark tools, automated
virtual tests and research documentation from one clean committed Git tree.
Inherited real-data fixtures, databases, configuration secrets, bytecode, runtime
files and dependency binaries are excluded before reading their Git blobs.
GENESIS61-BUILD.json binds the source SHA and manifest SHA; GENESIS61-PAYLOAD.json
records each file's SHA256, size and Git blob identity. Startup checks all files
and rejects extra, missing or changed payload bytes. This is integrity evidence,
not a digital signature; verify the ZIP against its separately supplied checksum.

## Launch with existing software

Extract to a new directory, retaining `GENESIS-6.1-FUTURE-RELEVANCE/source`.
Use the already working Python environment with FastAPI and Uvicorn; no dependency
installation is performed automatically. The engineering machine uses:

```powershell
pwsh -NoProfile -File .\scripts\Start-Genesis61.ps1 `
  -Python 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\tools-env\Scripts\python.exe'
```

Open `http://127.0.0.1:19390/#future`. The documented inert local pairing token is
`virtual-genesis61-session-not-a-real-account-1234`; it is not an external account
key. The process stays in the foreground. Its state belongs only in this new
lane's runtime directory. Protected GENESIS-6 port 19380 and legacy reserved ports
are rejected. No service, shortcut, registry entry or existing installation is
changed. Stop through the authenticated application shutdown operation or Ctrl+C.

Train an explicitly selected small fictional experiment, create a Jan-5 virtual
episode (default seed 400042), select a policy and execute a decision. A learned
model fitted on Jan 3 cannot be used at an earlier Jan-1 historical cutoff.
Advance virtual time explicitly to reveal deferred eligible observations and
later measure usefulness. `#research` retains the previous virtual replay tools.

## Reproduce checks

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
$python = 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\tools-env\Scripts\python.exe'
& $python -B -m unittest discover -s tests -p 'test_realtime_*.py' -v
& $python -B -m unittest discover -s tests -p 'test_future_*.py' -v
& $python -B -m unittest discover -s tests -p 'test_genesis*package.py' -v
& $python -B scripts\accept_genesis61.py --output '..\evidence\new-offline' --study-seed 7331 --study-cases 200
& $python -B scripts\browser_genesis61.py --output '..\evidence\new-browser'
```

Evidence destinations must be new. Browser verification requires the existing
Playwright environment and installed Edge plus the running owned server. Optional
benchmarks execute 100/1,000/10,000 actual direct-kernel decisions per policy;
their scope excludes journal/API throughput. Repeating numerical replay produces
equivalent probabilities; measured wall times are naturally variable.

The source builder is `scripts/build_genesis61.py`; it refuses dirty or mismatched
HEAD, creates only new output files outside source, and never publishes. The
previous sealed GENESIS-6 ZIP remains immutable. GitHub publication is not part of
this development acceptance.
