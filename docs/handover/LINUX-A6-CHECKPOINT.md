# Linux A6 preparation checkpoint

2026-10-31, C:\xampp\DRAGONHYDRA. Source/build docs frozen at installed-A6
commit138cf476de31692687239e356c2391b01dfe13cf. No product-source change.
The original builder ran ONCE, exit0:

```powershell
.\runtime\server-env\Scripts\python.exe -B scripts\build_linux_bundle.py --work build\linux\prep-20261031-a6 --verify-wsl
```

Do not rerun into this work directory. Build status was
`linux_core_verified_server_requires_dependencies`. Existing Python/build/uv
tools were reused without downloads or installs. Builder SHA256
`1eb97a451d42feccddc709042b7b86e325d2cad83d28c26f3396c8ac36ddfd9e`.

| Retained artifact under build/linux/prep-20261031-a6 | Bytes | SHA256 |
|---|---:|---|
| dragonhydra-linux-dev-3319aed91dd0.tar.gz |303125|`2a1b74207661c191e48750e64d268b0f7727c5215a324091264c05c60acabee2`|
| wheel/dragonhydra-0.4.0a1-py3-none-any.whl |298310|`021e07fd23deb43836171b44c95d25ec27b34a8db8209b667f2dd334d5f83d09`|

Actual71inputs/61product files/62common Windows-A6 manifest inputs/75wheel
members/9archive entries were verified. All common/product bytes match Windows
A6 source886161d0a8c4f0bf3364fd6d0a9966630398bba6bfe27b84de9c5999a307acd4.
Linux complete source hash is
`3319aed91dd0bb8d74062ed2335f5817422615e30e51d11c3fc970f477de5804`;
packaging inputs differ by design. All prior Linux archives remain intact.

Actual Ubuntu-26.04 `/usr/bin/python3`3.14.4 passed four wheel CLI cases.
Stock interpreter preflight honestly returned2: fastapi0.162.0, uvicorn0.42.0,
openpyxl3.1.5 and tzdata2026.2 unavailable. This does not describe the independent
R8 owner's vendored runtime. No dependency install or service activation occurred.

Both supplemental helpers ran with the exact prefix below, first with
`retained-parser-smoke.py`, then `retained-package-contract-smoke.py`, exit0:

```powershell
& 'C:\Windows\System32\wsl.exe' --distribution Ubuntu-26.04 --cd /mnt/c/xampp/DRAGONHYDRA --exec /usr/bin/python3 -I -B /mnt/c/xampp/DRAGONHYDRA/build/linux/prep-20261031-a6/retained-parser-smoke.py
```

The parser consumed existing copied event/lineup bytes, without provider fetch,
database read or backup. It reproduced4407events, France24/Argentina26 squad
entries,29types/181groups, page offsets0/2200/4400 with200/200/7rows and projection
SHA256`6a36c2bdb29ab890fae4e0e3b13764bdef9e60d36c8682029e72740f1ab59603`.

Package/3 pure contract parity used the retained3167-byte package, hash60802e45...
aa6. Genuine A6 wheel validation/request/output functions matched Windows hashes:

| Value | Bytes | SHA256 |
|---|---:|---|
| Canonical request |1162|`014602fe24118d588f5826607977e29110e493f713ef6d08e401a23de30510e5`|
| Prompt UTF8 |806|`7e83bfec751b59ab0a133fffcf154fe135d034016e7c624ec84ca114b882fb8a`|
| SYNTHETIC F3 selected output |3079|`04d514665b6312ec94d478aafaeda05f5643d77eb8a6b4099b09311a7425f065`|

Three trusted citations/four input IDs matched. SQLite definitions were imported
genuinely; DB connections/file reads, grounding, network, settings/vault access,
subprocesses, API/worker startup and inference attempts were0. No live R8 profile,
model, systemd or Windows service/configuration action was performed. This is
parser/contract parity, not Linux A6 API/backend/model/VPS acceptance.

Reports are committed under verified-reports/LINUX-A6-*. Final integrity SHA256
`dcf44686da1288f663b48d83c2710f59a4c4f03e1d011926f1cb027e00086c6b`.
Final guard SHA256`56f9a4b087d3a218d982d0f0c100612a8ec5465982fa96ea4d98981db92c2aec`.
Both supplemental reports bind that guard. Earlier guard/proofs are preserved
locally under supplemental-history/pre-sql-sidecar-guard-r1; both checks actually
reran after sidecar-read denial was tightened. No full builder repeat occurred.

Exact helpers are archived under commands/linux-a6/ with restoration notes.
Raw sports documents, database/state/configuration/keys and model weights are
excluded. Publish this wheel under a NEW development release: its valid filename
overlaps the old A5 wheel but its bytes differ. Read the publication receipt for
the final URL, Git commit, server digest and asset verification.
