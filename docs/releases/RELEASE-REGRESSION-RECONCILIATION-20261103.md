# Release regression reconciliation — 3 November 2026

The first dev.6 source, `40523425be06a7afe2f6223cb395f5e23b62300b`, and all its
packages and receipts are retained. All nine packages were built. Its Windows
standalone runtime passed17 checks, Android host tests15, Docker Linux runtime11
groups, and Python wheel/sdist installation checks passed. Those scopes do not
establish Windows service installation, native UI or device acceptance.

The subsequent unmodified source run found92 passing cases and one error in93.
The Joomla suite found69 passes, two failures and one skipped test in72.
These are preserved private receipts, not retroactively changed successes.

## Demonstrated fixture defects

1. `test_forecast_continuation.Guards.test_25` used the real historical
   reconciliation output path. That path now correctly exists after the successful
   one-shot reconciliation. The production reader refused it with
   `EXACT_FRESH_ACCEPTANCE_OUTPUT_REQUIRED`. The fixture now creates a temporary,
   nonexistent operation path and patches only its reader's operation constant.
   The production guard, historical receipt, controller and proof identities stay
   unchanged. Writes, snapshots and non-GET requests remain forbidden by the test.
   A separate negative case proves that existing output still refuses before
   imports or requests. No path-existence checks are mocked away.
2. The Joomla ACL assertion expected three guard sites. The actual component,
   unchanged since dev.5, has five: sync, probe, cancel, observe and shared
   workflow. Forecast and evaluation delegate to the guarded shared workflow.
   The assertion now checks the exact method set and both delegations, retaining
   POST CSRF, both permissions, profile binding and shell-execution exclusions.
3. The release-package test expected only two ZIP constituents. The supported
   sports homepage already ships a Cassiopeia child template as the third member.
   Exact membership remains mandatory; the test additionally inspects the child
   template files, parent and version. Source identity, private-file exclusions
   and metadata installation checks remain mandatory.

These are acceptance-test corrections, not product or mathematical repairs.
No installed profile, database, provider, service or historical artifact is changed.
New source identities must be built into fresh outputs; preliminary binaries must
not be renamed or relabelled as if compiled from this checkpoint.

## Verification and publication boundary

Corrected tests are rerun before freezing and again against the final commit.
Working-tree test results are distinguished from final committed-source results.
Before this freeze,94 distinct focused cases passed; the separate72-case Joomla
suite passed71 with one explicit private-snapshot integration NOT_RUN. All loaded
Joomla test-file hashes were stable. These do not supersede final-source reruns.
The prior93-case receipt and the prior72-case failure receipt remain unchanged.
The separate current-controller negative fixtures have already tested all six
public actions for invalid CSRF, missing permissions and foreign installation;
they do not establish an authenticated installed Joomla session.

The release remains held. Mandatory Windows installation/service/repair/retained
lifecycle and final installed privacy requirements are not weakened by fixing
test fixtures. No dev.6 public release, draft, tag or download is claimed here.

Evidence is under `LAB/release-evolution-20261103`: `source-checks-r2`,
`source-checks-r3`, `joomla-package-verification` and
`joomla-test-corrections-r2`. Raw snapshots, credentials and private profiles
remain outside Git and the distribution inputs. The historical original Forecast
receipt remains FAIL; the later reconciliation remains a distinct PASS.
