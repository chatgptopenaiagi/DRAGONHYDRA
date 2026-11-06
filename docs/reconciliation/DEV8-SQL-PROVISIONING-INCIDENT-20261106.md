# dev.8 native SQL owner maintenance defects — November 6, 2026

The sealed0e5df367 candidate genuinely passed fresh Windows installation without
manual ACL repair. Its nativePS5.1 SQL owner Apply then failed before opening SQL.
The original validated receipt, failed temporary receipt and started lock remain
preserved under LAB/release-evolution-20261106/dev8-acceptance-r1/genesis84.
No retry or modification of the installed helper/sealed software occurred.

Two independent reproductions established the causes. PowerShell's IDictionary
adapter maps SqlConnectionStringBuilder.DataSource (and four other CLR spellings)
to unsupported connection-string keywords, raising ArgumentException. The existing
receipt writer then called File.Replace with a PowerShell null backup argument;
PS5.1 coerces it into an empty filename, masking the provisioning exception.

The correction uses canonical dictionary keywords with identical integrated auth,
encryption, certificate choice, timeout, pooling and application-name values.
Receipt commits reuse the existing packaged DragonhydraAtomicFile.dll typed Commit
method. Ordinary-path and leftover-temp guards remain. A failure keeps its primary
exception even when recording the failure itself cannot succeed. No database role,
object grant, authentication policy, forecasting formula or storage ownership changed.

Eight regression methods passed across15 actual PowerShell7/native5.1 host runs,
including historical failure reproduction, repeated UTF8 replacement, shared readers,
locked/stale/unsafe/missing-helper negatives and original-exception preservation.
The new tests use only the explicitly owner-authorized Process RemoteSigned context;
no machine/user policy is changed and no SQL/service operation occurs in those tests.

The distinct development-maintenance Apply `sql-reconciliation-r2` executed helper
correction source `4a8177691bc272acb9258e256c7e9155baba76d3` against the installed
`0e5df36704eeeaadbbf2380cc5352473fc2ebf0b` ff4 candidate. It failed with
`new_database_created=true` at helper line105, `ExecuteNonQuery`, before owned-schema
verification. Its failed receipt was saved successfully with
`MethodInvocationException` and inner `ArgumentException`; the corrected receipt
writer did not mask this new primary failure.

Actual managed-provider probes under both PowerShell hosts established the next
cause: `Convert-CoreNextSqlHash` constructed `byte[]`, but function output enumeration
made the caller receive `System.Object[]`. `AddWithValue` retained that type, and the
actual `get_SqlDbType()` getter raised "No mapping exists from object type
System.Object[] to a known managed provider native type." The smallest source
correction returns the byte array as one pipeline object with unary comma. The
new real-host regression verifies `System.Byte[]`, `VarBinary`, size32 and identical
checksum bytes for the canonical schema hash, all-zero, all-FF and mixed-case
vectors. It also reproduces the exact frozen4a Object[] provider failure. These are
in-memory parameter checks: no connection is opened and no SQL command executes.

The separate read-only rollback inspection found
`DRAGONHYDRA_CORE_NEXT_SQL_86AAD1DB720F` ONLINE with zero user tables and zero
triggers. It has no ownership/migration marker, service login, database user or
research-storage configuration. The schema transaction rolled back; database
creation itself remains visible. The empty, unowned database, failed R2 receipt,
started lock and executed4a helper are retained. No retry, database adoption or
drop occurred, and those are not implied by this source repair. The seven prior
database metadata records and95 server settings matched their preserved hashes.

Evidence is under
`LAB/release-evolution-20261106/dev8-acceptance-r1/genesis84/sql-reconciliation-r2/diagnostic-r1`:
`DIAGNOSTIC-SUMMARY.json`, `EXACT-ROLLED-BACK-SQL-STATE.json` and the two
`*-HASH-PARAMETER-R2.json` host receipts. The original4a commit and its executed
bundle remain unchanged. Later qualification requires a distinct clean candidate,
new committed source and a separate operation; the failed ff4 operation must never
be replayed. SQL owner Apply and actual service SQL authentication remain unpassed.

A separately hash-bound development-maintenance bundle may qualify this correction
against the still-isolated installed0e5 server, with ExpectedSourceCommit truthfully
remaining0e5 and correction_source_commit separately recorded. This does not patch
that installed application, alter the sealed packages or constitute acceptance of
newly rebuilt release software. The original failed operation remains failed.

Any corrected distribution must be built into fresh paths from one final committed
source; version remains the unpublished0.5.0-dev.8. Preserve frozen0e5, all nine sealed
packages and the original ff4 service/profile/evidence. Final installed SQL/lifecycle/
GUI/privacy/coordinator and publication results remain separate actual gates.

The existing coordinator has already bound the held
`v0.5.0-dev.8-core-next` run to source0e5. Its identity remains immutable. The
supported corrected run uses the separately verified unused matrix tag
`v0.5.0-dev.8-core-next-r2`, retaining every software version at0.5.0-dev.8.
The coordinator and all acceptance gates remain unchanged. Selecting the new
run does not authorize publication before genuine corrected-source acceptance.
