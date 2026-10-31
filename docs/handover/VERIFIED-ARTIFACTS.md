# Verified artifacts for preservation

This inventory selects eight existing release-asset candidates, each below the requested 2 GB ceiling. Only these deliverable files were hashed. No build, installation, WSL launch, service action, Git operation or upload was performed. [Public-safe JSON manifest](VERIFIED-ARTIFACTS.json) contains exact paths, sizes, hashes and per-artifact proof scopes.

The candidates intentionally span different verified revisions. **A6 is built and archive-tested, unsigned and not installed.** A5 r2 has earlier installed/LocalService evidence. The current Linux preparation is A5 r2, while the standalone desktop/server, Joomla, Android and gateway assets remain frozen at `v0.4.0-alpha.1`.

| Candidate | Version/snapshot | Bytes | SHA256 |
| --- | --- | ---: | --- |
| [Windows A6 complete workstation](../../dist/connections/workstation-a6/DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe) | 0.4.1-dev.1 / A6 | 64,359,085 | `2d87e2bfac18099d9921674a2975604999fc7a79cddf36f5404cd293ff20c2d1` |
| [Linux A5 r2 preparation archive](../../build/linux/prep-20261031-a5-r2/dragonhydra-linux-dev-09822a188bd1.tar.gz) | 0.4.0-alpha.1 / A5 r2 preparation | 294,855 | `dcf3c31f7fcfb11fc3170ddbdb3566eaf917e586a437de3dc93ec9d441de2562` |
| [Python A5 r2 wheel](../../build/linux/prep-20261031-a5-r2/wheel/dragonhydra-0.4.0a1-py3-none-any.whl) | 0.4.0a1 / A5 r2 preparation | 290,646 | `c46f4d3903d965765b193cad215062ce0b72174863a833d3b57f54aba01c353e` |
| [Joomla extension](../../dist/releases/v0.4.0-alpha.1/assets/pkg_dragonhydra-0.4.0-alpha.1.zip) | 0.4.0-alpha.1 | 13,526 | `66529fd54fd913b3fc90ef5b21e5b8c972956379c16a48b8d9a94419e60ed585` |
| [Android development APK](../../dist/releases/v0.4.0-alpha.1/assets/DRAGONHYDRA-0.4.0-alpha.1-Android-arm64-development.apk) | 0.4.0-alpha.1 | 17,345,938 | `8c139ad6a4f75a0518299431dcb64703910aa6b68f220272fcfabef5d17e6e0c` |
| [Standalone application server](../../dist/releases/v0.4.0-alpha.1/assets/DRAGONHYDRA-0.4.0-alpha.1-Server-win-x64.zip) | 0.4.0-alpha.1 | 19,295,262 | `ea9457f3662189172b4385d05eea884e67a655fbfdbc4c11e4994e44b3416467` |
| [Standalone desktop application](../../dist/releases/v0.4.0-alpha.1/assets/DRAGONHYDRA-0.4.0-alpha.1-Desktop-win-x64-Setup.exe) | 0.4.0-alpha.1 | 1,886,742 | `282b4175e269d82f525e2e67ab2ceb07d7cbd130e6f6735600f4c79c780a5384` |
| [Public gateway support](../../dist/releases/v0.4.0-alpha.1/assets/DRAGONHYDRA-0.4.0-alpha.1-PublicGateway.zip) | 0.4.0-alpha.1 | 41,356 | `373890613dfb71f668c52a04a1afcfa2aeebc78c72d582be145bfc49f78dfe55` |

The eight binary/archive candidates total 103,527,410 bytes. The Android APK is explicitly development signed. No production-signed APK, model weights or model runner is included.

Proof scopes:

- **Windows A6:** 557 source tests, 28 frozen groups, 710 kernel files, 68 source inputs and all 10,662 installer payload files verified. Frozen contextual selection is synthetic. Real Qwen proof was source API/worker only and selected F1/E1, not a contextual count. A6 has no installation, LocalService, reboot or clean-machine claim.
- **Linux A5 r2 archive/wheel:** four actual Ubuntu Python 3.14.4 CLI cases and retained parser proof for 4,407 events, squads 24/26 and native pages. Four server dependencies were missing; no Linux API/server, database grounding, model or VPS deployment was verified. This preparation predates A6 package/3.
- **Frozen application server/desktop:** historical packaged/native application tests; standalone server ZIP includes its entire private Python runtime. These are older application distributions, not the A6 kernel. Desktop needs WebView2 and a configured server.
- **Joomla:** historical fresh/upgrade installation and eight browser groups on the recorded Joomla/PHP/MariaDB stack. The extension ZIP contains no web/database runtime.
- **Android:** historical emulator install/update, 14 Flutter tests and nine native groups, using the existing Android Debug development signer. Physical-device and production-signing claims are absent.
- **Gateway:** historical contract and lifecycle tests. No permanent VPS deployment or configured public identity is included.

Keep these historical references unchanged:

- [A5 r2 installed scope](../../dist/connections/workstation-a5-r2/INSTALLATION.md), installer SHA256 `b8bcc4d7ee26ea7db2f163fd20fecdbd95349ef5ac085d40375f43e5918d7544`.
- [Original C7 manifest](../../dist/workstation/0.4.1-dev.1/ARTIFACT-MANIFEST.json), installer SHA256 `a2a1cde06f7a9fbc86e1e564dc5aabb8984368bcf2c2d919f2f492568bd67d97`.
- [Frozen v0.4.0-alpha.1 manifest](../../dist/releases/v0.4.0-alpha.1/assets/ARTIFACT-MANIFEST.json) and [earlier engineering handover manifest](RELEASE-MANIFEST.json).

The A5 r2 wheel has the same valid wheel filename as the older frozen-release wheel but a different hash. Preserve the existing tag/asset; use a separately chosen release rather than replacing its historical file. Only upload explicitly selected artifacts. Live state, private databases, configuration/vault files, tokens, keys, unreviewed logs and model weights are outside this inventory. No publication is claimed here.
