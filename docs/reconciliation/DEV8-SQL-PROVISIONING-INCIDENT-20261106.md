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

A separately hash-bound development-maintenance bundle may qualify this correction
against the still-isolated installed0e5 server, with ExpectedSourceCommit truthfully
remaining0e5 and correction_source_commit separately recorded. This does not patch
that installed application, alter the sealed packages or constitute acceptance of
newly rebuilt release software. The original failed operation remains failed.

Any corrected distribution must be built into fresh paths from one final committed
source; version remains the unpublished0.5.0-dev.8. Preserve frozen0e5, all nine sealed
packages and the original ff4 service/profile/evidence. Final installed SQL/lifecycle/
GUI/privacy/coordinator and publication results remain separate actual gates.