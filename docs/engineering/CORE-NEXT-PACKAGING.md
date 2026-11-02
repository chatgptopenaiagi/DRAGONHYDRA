# CORE NEXT isolated packaging

Source is `C:\xampp\DRAGONHYDRA-CORE-NEXT`. Private profiles, state, caches,
snapshots, binaries and acceptance evidence are under
`C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB`. The original DRAGONHYDRA checkout and its
four installed services are read-only references.

`scripts/New-CoreNextProfile.ps1` creates a fresh explicit profile. Profiles bind
product/edition, a GUID installation ID, environment, exact application/state/
browser directories, service, shortcuts, uninstaller, database identities, three
distinct ports starting at18800, cookie/session suffix, source commit and version.
They contain no passwords. Mutable state is created separately with new secrets.
The unified Setup EXE embeds the same PS5-compatible factory: double-clicking it
with no arguments creates a fresh side-by-side profile automatically. A source
checkout, private lab profile or developer command is not required by the user.
Ports already listening or reserved by another profile are excluded. An explicit
`/PROFILE=` selects an existing instance for repair/reinstallation and must match
the release product, edition, version and source commit. The selected GUID is a
runtime identity rather than an identity compiled into the release.
No original credentials, scheduler state or browser storage are imported.

The original A9 Setup has no port override and must not be executed with defaults.
For the comparison baseline, extract its locked archive, verify every member in
PAYLOAD-MANIFEST.json, then use `scripts/Prepare-CoreNextPayload.ps1` with the
baseline profile. Server/client bytes remain identical to A9. Only the deployment
supervisor, profile guards, launcher and private Joomla provisioning hook change.
`CORE-NEXT-PAYLOAD.json` records this boundary; it does not claim byte-identical
installer behavior. Source receipts and mathematical acceptance remain separate.

Preparation never creates/starts/stops a service. First installation is an
explicit parent/operator action through native64 Windows PowerShell5.1:

```powershell
$summary = Get-Content C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\evidence\baseline-profile.json -Raw | ConvertFrom-Json
& C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File ($summary.install_root + '\workstation\Workstation.ps1') `
  -Action Install -ProfilePath $summary.profile_path `
  -SeedSnapshot C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\snapshots\characterization-core.sqlite3 `
  -SeedSnapshotSha256 '<expected closed snapshot SHA256 from acceptance evidence>'
```

The seed must be a normal file under the lab snapshots directory and match its
expected hash. It is copied only to an absent, owned kernel/core.sqlite3 before
service creation. A previous database is never replaced by a retry. Snapshot
provenance and removal of session/job state require their own acceptance receipt.

After a clean source commit, build candidate components using existing tools:

```powershell
.\scripts\Build-Desktop.ps1 -SourceSha <commit> `
  -WorkRoot C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\build\desktop-<unique> `
  -OutputRoot C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\payloads\client-<unique>

.\scripts\release_android.ps1 -SourceRoot C:\xampp\DRAGONHYDRA-CORE-NEXT `
  -WorkRoot C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\build\android-<unique> `
  -ArtifactPath C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\releases\CORE-NEXT-0.5.0-dev.3-arm64.apk `
  -Version 0.5.0-dev.3 -VersionCode 6 -SourceSha <commit>

.\scripts\Build-Workstation.ps1 -ProfilePath <candidate-profile.json> `
  -BaselinePayloadRoot C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\baseline-payload `
  -BuildRoot C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\build\workstation-<unique> `
  -OutputRoot C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\releases\workstation-<unique> `
  -ServerPayloadRoot <new-frozen-server-root-with-PAYLOAD-MANIFEST.json> `
  -ClientBuildRoot <new-native-client-root-with-PAYLOAD-MANIFEST.json> `
  -JoomlaPackagePath <lab-zip-with-matching.manifest.json>
```

Desktop builds configure the isolated CLI cache through process-only NODE_PATH.
The GUI-subsystem EXE metadata probe uses redirected ProcessStartInfo streams and
a bounded wait. Optional `-CargoCacheRoot <previous-lab-cargo-target>` with its
sealed `cargo-dependency-cache.json` sidecar copies only per-file-hash-validated
dependencies into a fresh target. Rust version and Cargo.lock must match; own app
binaries, fingerprints and build outputs are excluded. The resulting EXE must
report the newly selected source commit and current source-content hash.

The candidate builder requires new server/client payloads whose version, source
commit, namespace, schema and file hashes match the explicit profile. Existing
Apache/PHP/MariaDB/Joomla runtime files come from the verified A9 payload. Source
and third-party runtime provenance remain distinct. NSIS compiles the selected
profile factory and derives shell identities from the selected instance. Normal
installation needs no arguments. An explicit `/PROFILE=` may be accompanied by
`/STATE=`, `/SERVICE=` and final `/D=` arguments, which must match that profile.
Optional `/SEED=` and
`/SEEDHASH=` pass the same guarded first-install snapshot contract. Reparse paths,
foreign services, database identities, nonempty unowned state, conflicting shell
links and incompatible release/profile identities are rejected before mutation.
Live deployment profiles, installer ownership markers and machine-specific
preparation receipts are excluded from the release payload; Setup creates each
instance's markers locally.

Native identity is `ai.dragonhydra.corenext.desktop`. Its launcher always supplies
the exact state and browser profile; a bare portable client has no original
backend fallback. Native connection checks /system product, edition and exact
installation ID before opening WebView. The shared frontend checks public health
identity before sending pairing credentials. Android identity is
`ai.dragonhydra.corenext.mobile`; the existing development signer is retained
without replacing the original application. It validates CORE NEXT identity,
supports exact instance pairing, and displays the connected ID.

Unit/guard checks, metadata probes, compilation, actual installation, native UI,
Android pairing, reboot and clean-machine acceptance are separate states. The
syntax-only NSIS fixtures under lab/tests are never release assets or installation
inputs. Installer and guest/service mutations remain explicit acceptance actions.

## Existing lab reservation limitation

The historical sdists test profile98f231... lacks Windows shell identity fields.
The normal factory correctly refuses that malformed reservation on this developer
host. It was preserved unchanged. Acceptance uses the existing pure profile-object
factory with explicit reservations from all profile port metadata and live listeners,
then full Windows-profile validation. This does not establish default-factory or
clean-machine acceptance; it does establish the tested explicit-profile Setup path.
Never delete an existing profile or disregard occupied ports to clear the guard.
