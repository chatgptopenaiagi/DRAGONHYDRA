# CORE NEXT release adapter

`scripts/core_next/release.py` extends the existing `Coordinator` from
`scripts/release_coordinator.py`. It reuses the owned-draft ledger, no-clobber
uploads, exact annotated-tag check, remote asset checks and complete-download hash
verification. The shared coordinator gains an optional `draft_only` seam and
optional exact Git/GitHub CLI paths; its existing default behavior is unchanged.

The adapter requires explicit `--lab`, `--assets`, `--tag` and `--source-commit`.
There is no historical default tag. The tag must equal the CORE NEXT version
matrix, and the frozen Git commit must contain that exact matrix. State and
private receipts stay under the lab's `release/<tag>`; distributable files must
be under `lab/dist`. No original installation or source working tree is written.

## Reviewed asset specification

Supply `prepare --spec <lab/evidence/release-spec.json>`. The private specification
uses this shape; every filename is explicit, without globs:

```json
{
  "tag": "v0.5.0-dev.1-core-next",
  "source_commit": "<full frozen Git SHA>",
  "primary_acceptance": "<lab>/evidence/windows-acceptance.json",
  "privacy_receipt": "<lab>/evidence/release-privacy.json",
  "artifacts": [{
    "kind": "workstation",
    "filename": "<actual new Setup filename.exe>",
    "version": "0.5.0-dev.1",
    "target": "Windows 11 x64; current-host isolated installation",
    "build_configuration": {"mode": "fresh CORE NEXT product build"},
    "dependencies": [".NET Framework 4.8", "WebView2"],
    "build_receipt": {
      "path": "<lab>/build/workstation/build-report.json",
      "source_field": "source_sha",
      "version_field": "version",
      "artifact_sha256_field": "artifact.sha256"
    },
    "acceptance": [{
      "path": "<lab>/evidence/windows-acceptance.json",
      "source_field": "source_commit",
      "checks": ["passed", "fresh_install.passed"],
      "scope": "Fresh isolated current-host installation; no clean-machine or OS reboot claim"
    }],
    "acceptance_scope": "Actual recorded installation and behavior scope",
    "known_limitations": ["Unsigned development build", "No clean-machine/OS reboot acceptance"]
  }]
}
```

Seven distinct kinds are mandatory: `workstation`, `desktop`, `joomla`, `server`,
`wheel`, `sdist`, `source`. Android and Linux are optional independent kinds;
omission is recorded as NOT_RUN, never as a successful build/test. Each included
artifact requires actual version, target, build configuration and acceptance
scope. Build witnesses bind source, version and exact artifact SHA through the
specified dotted fields. Acceptance witnesses name actual true checks and scope.
Their file hashes are captured and checked again before publication. Only names,
hashes and scope enter the public manifest; private witness paths stay in the run
ledger. Hash strings are lowercase SHA-256.

For `source`, omit `build_receipt`: exact Git-blob inspection supplies intrinsic
source proof. If its named ZIP is absent, prepare creates it through `git archive`
with the fixed `DRAGONHYDRA-CORE-NEXT/` prefix. Its complete paths and Git blob
contents must match the frozen commit. Other archives are checked for integrity,
traversal/private-state/key paths and appropriate embedded source/version identity.
Windows EXE version metadata must identify 0.5.0. Wheel and sdist versions must be
0.5.0.dev1. Joomla package/component identity must be 0.5.0-dev.1 with embedded
current source. Reusing any exact A9 artifact bytes under a new name is refused.

The reviewed directory must already contain `RELEASE-NOTES.md`, `INSTALLATION.md`,
`BUILD-REPORT.json` and `TEST-REPORT.json`. Prepare adds `ARTIFACT-MANIFEST.json`
and `SHA256SUMS.txt`, refuses overwrite, and checks the exact file allowlist.
These are concrete review artifacts; prepare does not publish or install anything.

## Primary acceptance and final privacy

Publication validation requires the agreed `windows-acceptance.json` fields:
`passed:true`, exact `source_commit`, exact Setup `artifact_sha256`, and each of
`fresh_install`, `behavior`, `control_center`, `isolation`, `restart`, `repair`,
`uninstall` with `passed:true`. `fresh_install.installation_id` must identify an
owned `core-next-<32 hex>` profile. Every group supplies a nonempty `evidence`
array of `{path,sha256}` pointing to actual lab files. Their bytes are checked;
claims still retain their stated current-host scope and do not imply signing,
clean-machine or reboot acceptance.

After the final asset directory is assembled, supply a private privacy receipt:

```json
{
  "passed": true,
  "source_commit": "<same frozen SHA>",
  "artifact_sha256": {"<every final asset filename including manifest and sums>": "<actual SHA256>"}
}
```

The privacy receipt is outside the assets directory to avoid recursive checksums.
It must bind every final asset exactly. A scan over earlier staging files does
not pass this gate. Runtime configs, snapshots, private keys and raw secret
values never belong in public reports/assets.

## Explicit publication sequence

All commands use the same explicit common arguments. `status`, `prepare`,
`validate` are local; `history` performs remote reads. Parent-authorized
`stage-draft` invokes the existing publisher with `draft_only=True`, uploading
only the exact verified set to an owned draft. It does not make that draft public.
Parent-authorized `publish` verifies the same owned draft and publishes using
`--prerelease --latest=false`. Neither command uses `--clobber` or moves a tag.

`verify` downloads and rehashes every asset, checks the remote names/sizes/SHA-256
digests, and verifies all earlier releases/assets/tag and branch references from
`releases-before.json`, `tags-before.txt` and `branches-before.txt`. The existing
stable/latest release must remain unchanged. Only the completed verification
records `PUBLICATION_AND_DOWNLOADS_VERIFIED`. A failed/uncertain mutation is
reconciled through existing draft/release state, not automatically resent.

Seven focused offline guard tests cover private/traversal paths, original-path
rejection, version/source/hash witnesses, primary acceptance/evidence gates,
renamed-old wheel content, Joomla embedded source and draft-only publication
through a mocked existing coordinator. Tests contact no remote service. Actual
builds, installation, privacy scanning and publication remain separately evidenced.
