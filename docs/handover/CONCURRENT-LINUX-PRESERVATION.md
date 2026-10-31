# Concurrent Linux artifact preservation

Observed existing metadata only. No new Linux runtime, installation, API, model or service verification was performed. The original working `PACKAGING-COORDINATION.md`, current pointers, artifacts and reports were left untouched. [Public-safe inventory](CONCURRENT-LINUX-PRESERVATION.json) binds every observed metadata file by size, SHA256 and time.

| Existing artifact | Bytes | SHA256 |
| --- | ---: | --- |
| [linux-api-r8](../../dist/linux/native-kernel-20261031/r8/dragonhydra-api_0.4.0~alpha.1+dev20261031.r8.ac7e694e9e38-1_amd64.deb) | 2,939,100 | `d8b741ee36921a536a4624e4c351f8f790c89b75e9bd2bea6127a72b865dd675` |
| [linux-optional-runtime](../../dist/linux/local-ai-20261031/dragonhydra-local-ai-runtime_0.7.0~dev+git2280f0f.cpu1-1_amd64.deb) | 5,956,236 | `a2f5e3a1e2e52f180479c572c3c27e5efd5934488062e754edc1535e5f33fe5a` |
| [linux-optional-setup](../../dist/linux/local-ai-setup-20261031/DRAGONHYDRA-0.4.1-dev.1-Linux-LocalAI-Setup.zip) | 14,484 | `7552d02c1c12993ad315ad333b7dfae5d50939845251644eee5656c7784049f7` |

The three files total 8,909,820 bytes, all below 2 GB. Their actual file hashes match the existing metadata. This inventory does not turn inherited test results into new test runs.

- **API R8:** installed/promoted native API component according to the existing owner receipts. Frozen A5 application origin `7251f7…566a`, base `ac7e694e…f8f8`, effective native source `1116ee30…1158`, with one disclosed Linux listener transform. It includes 17 dependency wheels; it is distinct from the earlier dependency-free Linux preparation archive. It is not A6 package/3 or a complete Linux desktop/Joomla/PHP/MariaDB workstation. Existing proofs retain 760 operational records; isolated five-provider replay is 2,140 observations without fresh HTTP. Context-reader evidence covers 64 parents and `not_requested`, not a 4,407-event ingestion.
- **Optional CPU runtime:** installed/version/help evidence and reference inference are recorded. Its historical public manifest still marks installed-prefix inference false; newer R8 application-level receipts report that later proof. Both scopes are preserved. Model weights, API and desktop are not included; CPU/OS constraints apply.
- **Optional setup ZIP:** standalone administrator source/support, not an installer or model runtime. Existing archive/controller/service proofs are referenced without rerun. Separate model/runtime/API are required. Protected root0600 plaintext credentials are created only by later administration; none are in this archive.

The setup ZIP contains exactly four regular files: `INSTALLATION.md`, `MODEL-PROFILE.json`, `SOURCE-IDENTITY.json` and `configure_local_ai.py`. CRC, names and bounded text checks found no active environment/credential files, private-key material or literal token/key patterns. No secret values were printed, and no live protected configuration was read.

Public provenance/report locations remain available beside the three packages: API `SOURCE-MANIFEST.json`, `EFFECTIVE-SOURCE-MANIFEST.json`, `INPUT-MANIFEST.json`, `WINDOWS-APPLICATION-ORIGIN-SOURCE-MANIFEST.json`, and each component’s existing artifact/test/installation reports. The earlier frozen base source archive remains referenced in JSON; no source snapshot was rebuilt.

Overall full-Linux-workstation, fresh provider HTTP, host-browser, reboot and clean-machine checks remain incomplete. Unsigned development components only. Root owns any commit/release/upload; none was performed here.
