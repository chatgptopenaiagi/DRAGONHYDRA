# Frozen A4 Linux refresh contract

2026-10-31. Packaging continuation only; the interactive CLI owns newer shared
application development. This contract does not authorize changes to that code.

The entire A4 input is `build/connections/payload-20261031-a4/{SOURCE-MANIFEST.json,source}`:
62 hash-verified files, content SHA256
`8b3e7e0e440b9f4d090517237724999bcd824d86f460663e65d940c9c1d20fd5`.
It contains all55 application/resource files. Existing Linux prep-r2 has53
application files and63 total manifest inputs, content SHA256
`9f3d6e5ab1082a81c19308cdce3bea2e1efd3d31729227a027248644d56a86c4`.
It is not an equally current application. Do not overlay live checkout files or
copy its older application files into the new source tree.

A4 adds `local_ai_settings.py` and `mariadb_migration.py`; seven other application
files differ: API/contracts, connector service/store, local-AI service, product,
and dashboard app.js. A4 is a point-in-time snapshot, excluding the newer CLI
StatsBomb event/lineup context design and subsequent implementation.

Smallest implementation: `packaging/linux-native/prepare_frozen_bundle.py` reads
both complete manifests, verifies every listed file before and after staging,
copies the full62-file A4 input, then adds exactly eight hash-verified build
support files from `build/linux/prep-20261031-r2/source`: pyproject.toml, README.md,
the server Python lock, and the five existing Linux prep templates. Its own
snapshotted packaging script is a separate input. Preserve the A4 origin and
Linux support origin manifests. Derive an honest new composite identity; do not
label combined build support as A4's original content hash or as a Git commit.

The existing `scripts/build_linux_bundle.py` main is unsuitable here: ROOT-bound
collection would select live or old source. Reuse its verified ROOT-independent
build-environment and wheel-inspection helpers from frozen prep-r2 only. Existing
Windows Python3.14.10 has build1.4.0 and uv_build0.12.7. Build with the same backend,
`--wheel --no-isolation`; no installs/downloads. The native uv-build executable
does not support the attempted `--version` CLI probe; package metadata and the
prior successful build establish its pinned version, not that unsupported flag.

The new wheel must contain every one of A4's55 package/resource files byte-for-
byte, plus generated build_info.json and legitimate dist-info metadata. Verify
RECORD, Requires-Python>=3.14,<3.15, entry points, private-payload exclusions and
the composite/origin identities. Preserve version0.4.0a1 and API/schema1. Native
Linux CLI/import proof must load the extracted new wheel without checkout or
global packages; it is separate from starting the API or installing a package.

Existing17 Linux dependency wheels are pinned and verified in the R6 input
manifest. Reuse them unchanged. Their native CPython314/x86_64 binding was tested
on Ubuntu26.04.1. A4's declared direct dependencies are unchanged; a fresh native
package build still must check dependency closure and actually import them.

Only owned `packaging/linux-native` requires packaging changes: accept the new
composite source manifest, retain both origins in build identity, and apply the
existing exact-hash Linux socket patch. A4's server.py is the same SHA256
`855c3e28d98d2aa7bad554aff2aff1683d0cb3a4e03565533b0a2fc0e869105b`,
so the reviewed R6 transform remains applicable. R6 managed-port/lifecycle work
must remain intact. Keep its running service/data/port55971 during preparation.

Debian version ordering needs a monotonic build sequence before the content hash.
Changing only the hash and trailing revision can sort below R6. Read-only native
dpkg comparison proved `0.4.0~alpha.1+dev20261031.r7.8b3e7e0e440b-1` greater than
`0.4.0~alpha.1+dev20261031.9f3d6e5ab108-6`; substitute the actual new composite
prefix and verify again. Product/Python versions remain unchanged. Existing
systemd acceptance needs an explicit expected-base identity, while the exact
R4-to-R5 upgrade harness must not be reused blindly for this different candidate.

After wheel preparation, root coordinates native package construction and the
isolated upgrade. Require current artifact extraction tests, existing760-match
team/standings/cited deterministic explanation/XLSX journey, same-port restart,
one bounded failure recovery, and retained pairing/evidence/counts. Add Linux
A4-specific public health/settings, structured-package and receipt-binding
checks. The Windows frozen connector harness uses CREATE_NO_WINDOW and DPAPI;
do not relabel those results as native Linux tests. Linux credentials use a
protected service environment; Windows-only key storage must fail specifically
with VAULT_PLATFORM and retain previous settings. Do not use a dummy key for
inference or claim model execution from passive configuration health.

Full Linux desktop/Joomla/PHP/MariaDB workstation installation, a real Linux
model run, fresh successful public HTTPS sync, and clean-machine tests are
separate unfinished proofs. R6 is an installed API component, not those products.
No VPS target, production Android signer, or provider key is invented here.
