# Source locking for GENESIS A9

The current integration milestone uses docs/releases/GENESIS-A9-VERSION-MAP.json;
component versions remain independent. The release manifest records exact per-asset
source commits and unchanged-input evidence for reused binaries. A clean detached
Git worktree or git archive prevents independent untracked development state from
entering packages. The final source ZIP is created from the exact annotated tag.

Build the Joomla package, standalone server/client, Android and Python packages only
through their explicit source-locked pipelines. Keep all mutable build/runtime state
outside the snapshot. Source code, constraints, tests and documentation are tracked;
private databases, passwords, pairings, browser profiles, signing keys and caches are
not. The public Python lock is narrowly tracked under config/runtime.

The repository is currently public (verified through GitHub metadata for this
release); no repository-visibility change is part of publication. Release creation
uses a new owned draft/prerelease and preserves existing tags/assets. Remote IDs,
sizes, digests and independent downloads must match before success is recorded.

The notes below describe the earlier integrated-release process and remain
historical where they mention a generated version.json or private repository.

# Integrated release source

The next prerelease uses the version mapping in `version.json`. A release source
commit contains only selected application, packaging, test, and documentation
files. Live product state, credentials, gateway/tunnel records, evidence and old
build outputs are excluded. A temporary Git index preserves the live checkout
and its staging area. The release branch/tag are new; existing refs are not moved.

`git archive` exports that exact commit to `build/release/<tag>/src`. Build
identity is generated outside the snapshot in `work/build_info.json`: product
version, Python version, full source commit, API namespace and schema version.
That file is a declared input to wheel, frozen server, client, APK and extension
packaging. Generated wheel staging adds this one controlled metadata resource.

Only retained documented public fixtures and synthetic examples are selected as
package inputs. The same dashboard bytes are included for the wheel/server;
the resource-mirror regression prevents divergence from the desktop source.
Private databases and source account credentials are never build inputs.

Build commands, exit codes, durations and input/output hashes are recorded in
`release-state.json` outside immutable assets. A stage can resume only when its
source and declared inputs/outputs match. Final software payload hashes precede
public reports, manifests and the checksum file. Signing changes require new
hashes. No byte-for-byte reproducibility claim is made without repeated builds.

The publisher uses only explicit manifest filenames and the named repository.
It creates one owned draft, checks remote upload states/digests and the peeled
annotated tag, then publishes without replacing old releases or marking the
prerelease Latest. Authenticated downloads are checked against final local bytes.
The repository remains private; public anonymous download availability is not
claimed. PyPI publication and repository settings are outside this workflow.
