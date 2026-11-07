# GENESIS-6.2 virtual experimental development distribution

Component `0.3.0-virtual-experimental` is Python/web research software. It is not
an inventory product, EXE, production installer or real ERP/WMS/POS/TMS connector.
All experimental inventory, demand, shipments, providers and credentials are
fictional. Existing GENESIS-6/6.1 mathematics and sealed archives remain intact.

The curated distribution contains the tracked code, ten mirrored web assets,
PowerShell scripts, virtual tests and documentation needed by this increment.
It excludes inherited real-data fixtures, credentials, runtime databases and
dependency binaries. GENESIS62-BUILD.json and GENESIS62-PAYLOAD.json bind one
clean committed source tree to file sizes, SHA256 and Git blob hashes. Startup
rejects missing, modified, extra and reparse payload entries. This is integrity
verification, not a signature; verify the archive's external SHA256 as well.

Extract to a new path retaining `GENESIS-6.2-COGNITIVE-LOGISTICS/source`. With the
existing verified environment:

```powershell
pwsh -NoProfile -File .\scripts\Start-Genesis62.ps1 `
  -Python 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\tools-env\Scripts\python.exe'
```

Open `http://127.0.0.1:19400/#logistics`. The inert virtual pairing marker is
`virtual-genesis62-session-not-a-real-account-1234`. No dependencies are installed
automatically. The runtime lives outside sealed source in the new lane. The
foreground process creates no Windows service, installer, firewall or registry
configuration. Stop through authenticated application shutdown or Ctrl+C.

Create an episode, inspect the inventory/forecast/network, execute a replenishment
decision, then explicitly advance time. Subsequent days use the retained plan;
new episodes start with order-up-to/acquire-none. A learned plan keeps its original
frozen model until an explicit new decision replaces it. Training and analysis
are explicit actions, never dashboard-refresh side effects. Training previews
are small, labelled research diagnostics; use the predeclared offline study for
scientific conclusions.

```powershell
.\scripts\Verify-Genesis62.ps1 -OutputDirectory '..\evidence\new-verification'
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
$python = 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\tools-env\Scripts\python.exe'
& $python -B -m unittest discover -s tests -p 'test_realtime_*.py' -v
& $python -B -m unittest discover -s tests -p 'test_future_*.py' -v
& $python -B scripts\accept_genesis62.py --output '..\evidence\new-acceptance' --seed 8821 --cases 40 --days 20
& $python -B scripts\browser_genesis62.py --output '..\evidence\new-browser'
```

Evidence destinations must be new. Browser acceptance needs the owned running
server and the already-installed Playwright/Edge tools. Mathematical experiments
need no internet or external API key. The source builder only reads clean Git
blobs and creates a new archive; it does not publish. Publication is a separate
owner-authorized prerelease step after mandatory acceptance, with downloaded
asset hashes verified. Software acceptance and better operational decisions are
separate claims. Read [the architecture](logistics/ARCHITECTURE.md) and
[predeclared experiment](logistics/EXPERIMENT-PROTOCOL.md).
