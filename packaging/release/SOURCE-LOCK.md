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
