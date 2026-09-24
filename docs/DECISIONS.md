# DRAGONHYDRA decisions

## Scientific D023: evaluation discipline, reconstruction and prospective clocks

**Date:** 2026-09-24. **Status:** ACCEPTED for experimental Phase A, owner-directed.

**Decision:** Add EVALUATION_DISCIPLINE, explicit STRICT_PIT/RECONSTRUCTED_PIT, minimal identities, simple chronological baselines and one-league prospective acquisition. Preserve actual capture clocks, baseline tag and original records. Use existing SQL read access and local derived artifacts; add no storage technology or dependency.

**Reason:** Retrospective imports cannot create historical observation proof. Evaluation must constrain future model complexity, and genuine timestamps need to start accumulating now.

**Alternatives:** silently backdate availability; defer evaluation until V9; add a feature store or advanced model; or use explicit low-confidence reconstruction and simple baselines. Chosen: the last option plus a genuine current snapshot from the already reviewed provider.

**Evidence:** [Scientific report](SCIENTIFIC_VALIDATION_SPINE.md), [curated measurements](evidence/scientific-spine-summary.json), [ADR-011](architecture/ADR-011-scientific-validation.md).

**Trade-offs:** One season/date proxies do not establish predictive superiority. Declared identities remain source-scoped. A first capture is not sustained collection, and the complete laboratory is not clean-machine reproducible. Scheduling, Poisson, market benchmarking and prospective predictions remain future bounded blocks. Browser repair is deferred; existing ACCEPT_WITH_WARNING is retained without migration.

## Repository D022: private baseline and explicit test tiers

**Date:** 2026-09-24. **Status:** ACCEPTED, owner-directed.

**Decision:** Use private `chatgptopenaiagi/DRAGONHYDRA`, local-authoritative `main`, Python 3.14 CI with portable contracts, separate live/machine/browser tiers, and no automatic sports acquisition or infrastructure provisioning in Actions. Retain copyright policy without inventing an open-source license. Pin Actions by full verified commit and keep token permissions read-only.

**Reason:** A durable engineering home needs reproducible checks without pretending that hosted runners contain the owner's databases, GPU or browser. Private visibility does not make secrets suitable for Git.

**Alternatives:** Upload the whole laboratory; silently downgrade Python; skip live failures as CI success; introduce GitFlow; or isolate reviewed source and tests. Chosen: the isolated, lightweight baseline with preserved live requirements.

**Evidence:** [Test tiers](TESTING.md), [current baseline validation](evidence/repository-baseline-summary.json), [repository report](reports/GITHUB_BASELINE.md). Final local 207 and portable 164 tests pass. Initial schema portability and stale synthetic-presentation test failures remain preserved and explained.

**Trade-offs:** A clone can run portable checks but cannot recreate the complete local lab from source alone. Current DTO tests must follow actual immutable receipt provenance rather than a historical fixture's last-state assumption. New source acquisition, models and V2 expansion remain out of scope.

## Repository D023: curated evidence and staged-file link validity

**Date:** 2026-09-24. **Status:** ACCEPTED, explicit owner guardrail.

**Decision:** LOCAL FORENSIC EVIDENCE stays under ignored `runtime/checkpoints`; REPOSITORY-SAFE EVIDENCE is whitelisted, small JSON summaries under `docs/evidence`. Preserve source hashes and time/claim limitations. Markdown links must resolve within the actual intended Git index, not merely the working directory. Ignored originals are represented as inline LOCAL EVIDENCE PATH coordinates.

**Reason:** Working-directory-only link checks falsely pass when an ignored local target is absent on GitHub. Uploading checkpoints would expose unnecessary data and expand the repository without architectural value.

**Alternatives:** Commit all checkpoints; leave broken links; remove provenance entirely; or curate minimal evidence with explicit local coordinates. Chosen: curated evidence and a failing staged-link check.

**Evidence:** [Evidence layer](evidence/README.md), [link audit](../scripts/check_repository_links.py), its regression tests, and 87 reconciled ignored-evidence links including all 74 checkpoint links found before the first commit.

**Trade-offs:** Repository readers can inspect selected historical metrics and source hashes but need authorized local artifacts to independently recompute those hashes. Raw diagnostics remain local. Curated summaries never turn synthetic or blocked browser evidence into successful Desktop proof.

## Roadmap D021: restore and preserve numeric ranges

**Date:** 2026-09-24. **Status:** ACCEPTED, explicit owner correction.

**Decision:** Initial scope is **2–3 high-quality sources (two to three)**. A normal session implements approximately **3–5 closely related roadmap items (three to five)** in one coherent block. Preserve owner-authored dash/en-dash separators exactly. Correct D019 and all copied interpretations; retain the original checkpoint as historical evidence and create a new correction checkpoint.

**Reason:** The owner identified collapsed numeric ranges as transcription/formatting errors, not intent. Small source counts prove one complete auditable intelligence loop; bounded sessions remain testable and reviewable.

**Alternatives:** Keep the corrupted integers, leave the interpretation pending, or restore the explicitly clarified ranges. Chosen: restore the ranges; no further scope clarification is needed.

**Evidence:** Owner's roadmap-integrity correction; [all corrected occurrences and audit scope](ROADMAP_RANGE_CORRECTION.md); [new correction checkpoint — curated summary](evidence/roadmap-integrity-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/roadmap-range-correction-20260924T185126Z-9eb65c7a`).

**Trade-offs:** Earlier evidence retains incorrect wording for historical traceability, so current records explicitly supersede it. Legitimate section numbers, versions, identifiers, timestamps and hashes are not rewritten. No functionality or runtime behavior changes.

## Roadmap D019: incremental stages and evidence-based status

**Date:** 2026-09-24. **Status:** ACCEPTED, owner-directed.

**Decision:** Adopt [the master roadmap](DRAGONHYDRA_MASTER_ROADMAP.md) as long-term direction, keep V1 active, and maintain a separate [status file](ROADMAP_STATUS.md). Preserve provenance, temporal discipline and feedback-driven research. Execute one coherent authorized block at a time; the plan does not authorize all future work. Per the owner's correction recorded in D021, begin with **2–3 sources (two to three)** and approximately **3–5 closely related items (three to five)** per normal session. The earlier literal-integer interpretation is superseded; preserve range separators exactly.

**Reason:** The owner explicitly requires gradual evolution and measurable value before complexity. Existing CLI ingestion and synthetic bridge evidence cannot establish a genuine Desktop capture.

**Alternatives:** Implement all versions immediately; infer completion from file counts or contracts; use arbitrary completion percentages; or separate plans from demonstrated capabilities. Chosen: the last option, with UNMEASURED percentages until an acceptance denominator is defined.

**Evidence:** Owner roadmap; [Web-to-SQL report](WEB_SQL_FINAL_REPORT.md); [bridge report](DESKTOP_CLI_BRIDGE_FINAL_REPORT.md); [final 190-test record — curated summary](evidence/desktop-cli-bridge-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/desktop-cli-bridge-20260924T183316Z/tests.json`). These are inspected historical results, not new live claims.

**Trade-offs:** Conservative status leaves future stages without numeric progress and requires acceptance criteria before percentages. Existing math contracts and synthetic odds helpers remain useful prototypes but do not mark later versions complete. The genuine Desktop handoff remains the next V1 proof block.

## Roadmap D020: durable ownership and architectural laws

**Date:** 2026-09-24. **Status:** ACCEPTED, owner-directed; implementation remains stage-gated.

**Decision:** SQL Server is primary structured intelligence memory; MariaDB owns operational/presentation state; DuckDB is the future analytical laboratory; Parquet holds large analytical history/archive. Python 3.14 remains invariant. Availability-aware replay and complete provenance remain mandatory. Desktop/CLI use explicit handoff artifacts. GPU and new components require measured value.

**Reason:** One primary owner per dataset and explicit interfaces preserve auditability and prevent uncontrolled replication or hidden dependencies.

**Alternatives:** Duplicate intelligence in MariaDB, blur collection/validation/prediction roles, choose runtimes opportunistically, or connect Desktop/CLI through private IPC. Rejected in favor of the owner's permanent boundaries.

**Evidence:** Roadmap sections 2–4, 6, 8 and 13; existing D001/D004/D005/D006/D014/D016–D018 and their milestone reports. The SQL/MariaDB split and artifact bridge already have bounded demonstrations; DuckDB/Parquet production workloads and predictive research feedback remain future work.

**Trade-offs:** Separate authoritative storage and derived caches require explicit recovery; temporal/provenance completeness requires more metadata; measurement may defer attractive technologies. This supersedes only outdated future-role statements in historical D005 (SQL Server deferred and Joomla outside presentation architecture), preserving the original entry as history. No implementation, account, permission or service change follows from adoption alone.

## Bridge D016: strict envelope and explicit origin

Introduce BrowserHandoffEnvelope v1 without changing the legacy manifest contract. Closed nested schemas and bounded scalar observations reduce the untrusted surface. Extend producer values with the explicitly requested test-fixture and preserve SYNTHETIC/MANUAL/CLI_FETCHED/DESKTOP_CONFIRMED separately. Successful Desktop capture requires a listed hashed browser evidence artifact; a blocked Desktop envelope is DESKTOP_BLOCKED. Local producer claims are trusted-file provenance, not browser-signed attestation.

## Bridge D017: additive identities and tables

Create dragonhydra_ingest_sqlserver and dragonhydra_bridge_read_sqlserver with only object-level SELECT/INSERT and SELECT respectively on five new bridge tables. Do not change dragonhydra_probe_sqlserver, dragonhydra_ingest, dragonhydra_read or any MariaDB identity. Reuse the existing narrowly scoped presentation cache for two bounded DTO rows. SQL remains authoritative; no bidirectional synchronization.

## Bridge D018: commit, receipt and recoverable publication

Claim via atomic rename under an exclusive one-shot lock. Preserve accepted bytes/hashes before append. SQL ID/hash uniqueness makes replay idempotent; changed content under an old ID fails. MariaDB publication is a separate commit, so failure after SQL explicitly records SQL_COMMITTED and permits safe replay. Receipts/checkpoints never overwrite earlier attempts. Detected sensitive input is retained only in the existing protected secret quarantine, with sanitized failed-area stubs; web content is never executed.

## Web D012: source evidence must survive extraction uncertainty

The user's correction requires corrupted license text never to become legal approval. Installed project-local pypdf 6.19.0 after verifying its official Python 3.14 classifier. Its extraction still contains invalid glyphs, so StatsBomb remains TERMS_STATUS=UNVERIFIED and LICENSE_STATUS=UNVERIFIED. Preserve original PDF hash, retrieval checkpoint, method, raw output and extraction status. Use OpenFootball's independently readable official CC0 text and documented raw JSON access for the actual fixture demo. The fourth research candidate is a replacement, not an expanded collector fleet.

## Web D013: capture origin and bridge processing state are independent

Browser availability is an observed event, not a permanent runtime constant. Append bridge events and derive the latest status when building the DTO. PROCESSED + CLI_FETCH does not establish Desktop research. A Desktop note must identify rendered capture evidence, source and byte hash. Local notes are trusted operator records, not attested browser signatures. Keep the actual Desktop stage blocked until observed.

## Web D014: versioned intelligence and operational presentation have different owners

The dedicated dragonhydra SQL schema retains append-only versions, hashes and predecessor links using SELECT/INSERT-only ingestion rights. A separate reader builds a small DTO; MariaDB owns cache/job state/integration metadata. PHP gets one-table SELECT only, never SQL Server credentials. The initial hybrid relational/JSON schema preserves provenance and typed Python contracts while deferring a fully flattened warehouse. No automatic dataset replication.

## Web D015: local presentation through a custom endpoint

Use a PHP endpoint under Joomla's existing directory, with Require local plus PHP network/method/Host guards. Do not modify core or Joomla content tables. Preserve existing service bindings and explicitly report their wildcard state; the new endpoint is local-only. No daemon, firewall widening, port forwarding or private IPC. UI verification uses HTTP/content tests because Desktop browser automation is unavailable.

## Dual database D008: measure before repairing

**OWNER_INTENT:** Run MariaDB and SQL Server 2022 simultaneously, with different stable ports.

**OBSERVED_CONSTRAINT:** Both were already running at inspection. MariaDB owned 3306; default SQL Server instance MSSQLSERVER owned 1433; TCP 1434 was its local dedicated-administrator endpoint. SQL Browser UDP 1434 was absent/disabled. Seven SQL startup logs showed successful readiness; no engine startup or port conflict was reproduced. Active SQL connections use this machine's VPN address 10.5.0.2.

**OPTIONS:** Move ports/restart services on the unverified premise; rebind the shared server to loopback and break existing clients; or retain working static settings and scope new adapters locally.

**CHOSEN_SOLUTION:** Preserve static ports and service/network configuration, keep MariaDB 3306 and SQL Server 1433, and use explicit 127.0.0.1 client endpoints. Export SQL network registry configuration as baseline evidence. No start/restart, firewall opening, root/app password change, system database repair or file replacement.

**REASON:** The intended coexistence already exists. Unnecessary engine changes would create risk without fixing the observed problem. Existing auxiliary SSIS missing-login errors and historical PolyBase/Launchpad warnings are separate from engine availability and remain outside this bounded repair.

## Dual database D009: modern driver and loopback TLS exception

**OWNER_INTENT:** Canonical Python 3.14 access without disturbing the GPU environment.

**OBSERVED_CONSTRAINT:** pyodbc was initially absent; Microsoft ODBC Driver 18 product 18.6.2.1 was already installed. An actual strict-certificate Python connection failed with SQLSTATE 08001 because the chain was not trusted. Encryption with a loopback-only TrustServerCertificate exception succeeded.

**OPTIONS:** Disable encryption; alter server/global certificate configuration; downgrade Python/use obsolete Native Client; or add a native cp314 driver and an explicit constrained local trust policy.

**CHOSEN_SOLUTION:** Official PyPI pyodbc 5.3.0 cp314-win_amd64 wheel, SHA256 verified and installed project-local with no dependencies. Retain existing PyMySQL 1.2.3 and ODBC Driver 18. SQL config enforces loopback, Encrypt=yes and an explicit TrustServerCertificate=yes exception. Certificate validation is reported false, not claimed successful. A properly trusted certificate remains the future solution if this boundary expands.

**REASON:** The actual client incompatibility is addressed without changing Python, NumPy, PyTorch, CUDA, cuDNN, ODBC installation or server bindings. Drivers run through codex-pytorch but are deliberately not installed into its site-packages.

## Dual database D010: bounded synthetic SQL Server workload

**OWNER_INTENT:** Test both engines through explicit adapters without database chaos.

**OBSERVED_CONSTRAINT:** Existing databases must be preserved and Joomla must remain read-only. No DRAGONHYDRA_LAB database or proposed SQL login existed at inspection.

**OPTIONS:** Reuse administrative or Joomla credentials; duplicate Joomla data; or create an isolated synthetic lab with its own reader.

**CHOSEN_SOLUTION:** Create DRAGONHYDRA_LAB with two synthetic rows and files in project runtime/sqlserver-lab. Grant its service account Modify only on that new directory. Create dragonhydra_probe_sqlserver with database CONNECT and object SELECT only; no fixed roles or grant option. Retain MariaDB's existing SELECT-only identity unchanged. Both write-denial probes use guaranteed zero-row UPDATE and rollback, never system/production writes.

**REASON:** Each store has its own controlled source. Typed capability reports expose engine identity, latency, read/write/transaction behavior and diagnostics. No general SQL API or automatic data copying was introduced. Dataset owners and OPERATIONAL_OWNER/ANALYTICAL_OWNER/CACHE/DERIVED_COPY/ARCHIVE meanings are explicit in the architecture docs.

## Dual database D011: permission evidence must reflect actual semantics

**OWNER_INTENT:** Prove least privilege and preserve failed approaches for review.

**OBSERVED_CONSTRAINT:** The first SQL runtime connection/read/UPDATE-denial succeeded, but the validator returned unhealthy. SQL Server reports SELECT once for the table and again for columns, and public grants include read-only encryption-key metadata visibility. The original validator incorrectly treated those as excess permissions. Review also found a potential blind spot for grants on other lab objects/schemas.

**OPTIONS:** Grant higher roles to make checks pass; ignore the failure; or correct the validator without broadening permissions.

**CHOSEN_SOLUTION:** Preserve the first failed report. Compare the effective permission set, explicitly allow the measured harmless public metadata permissions, require the exact direct CONNECT/SELECT grants, reject grant-option/schema/other-object scope, require only the sample object visible and zero writable schemas, and test the extra-grant rejection logic. No login permission escalation.

**REASON:** The final dual checkpoint passes 92 tests and both account proofs. The scope is the current server privileges and controlled database, not a guarantee about future mappings in every database.

## Historical genesis decisions

Date: 2026-09-24. These decisions reconcile owner intent with measured constraints. See the [technology matrix](TECHNOLOGY_COMPATIBILITY_MATRIX.md) for versions, source links and untested candidates.

## D001: canonical Python and environment

**OWNER_INTENT:** Python 3.14 is the primary computational language, inside Anaconda's codex-pytorch environment.

**TECHNICAL_CONSTRAINT:** Old DRAGON declares Python >=3.12,<3.13, while the working lab already has Python 3.14.7, NumPy 2.5.3 and PyTorch 2.14.0+cu132. PowerShell login startup can switch the active environment to base.

**OPTIONS:** Downgrade the lab; import the old environment; or create a new 3.14 project while inspecting donor concepts.

**CHOSEN_COMPROMISE:** A new Python >=3.14,<3.15 project, explicit canonical executable in configuration and launch script, login:false during agent commands. No Python or Conda package downgrade. Machine-specific paths remain in configuration/launcher defaults, not domain code.

**REASON:** The existing compute stack executes successfully, and old packaging metadata is not evidence that its underlying concepts cannot be ported. No donor implementation was copied.

## D002: preserve GPU baseline, prove execution

**OWNER_INTENT:** CUDA/cuDNN/PyTorch GPU acceleration, with room for future AI models.

**TECHNICAL_CONSTRAINT:** Driver discovery alone does not establish a usable tensor runtime; upgrading one component can break a verified wheel combination.

**OPTIONS:** Upgrade opportunistically; accept GPU identity as proof; or keep the stack and execute a reference-checked operation.

**CHOSEN_COMPROMISE:** Retain PyTorch 2.14.0+cu132 / CUDA runtime 13.2 / cuDNN 9.24. Verify a CUDA matrix multiplication against NumPy float64, report device and tolerance, and expose CPU fallback distinctly.

**REASON:** Measured correctness on the RTX 3050 matters more than newer version numbers. One timed smoke operation is not a benchmark or proof of all GPU workloads. No Qwen or large model installed.

## D003: smallest live Python/XAMPP bridge

**OWNER_INTENT:** Prove Python 3.14 can safely consume MariaDB data through XAMPP.

**TECHNICAL_CONSTRAINT:** No Python MariaDB driver was installed in the canonical environment. Joomla's runtime account can write, and its data must remain unchanged.

**OPTIONS:** Native MariaDB connector build; new environment; writable account reuse; or a project-local pure-Python driver and dedicated account.

**CHOSEN_COMPROMISE:** Official PyMySQL 1.2.3 wheel, SHA256 verified, installed only under runtime/vendor with no dependency resolution. Create dragonhydra_probe@localhost with SELECT on exactly joomla_codex_lab. Credentials are outside htdocs in ACL-protected runtime/secrets.

**REASON:** The live Python 3.14 connection and aggregate reads passed. Grant scope underscores are escaped, no role/table/column grants exist, and a zero-row UPDATE is rejected with error 1142. No root password, Joomla application account, Joomla rows, database schema, or service configuration changed. Root was used only for authorized one-time account provisioning.

## D004: six timestamps and immutable corrections

**OWNER_INTENT:** No future information in historical predictions, training, evaluation or replay.

**TECHNICAL_CONSTRAINT:** Old DRAGON's useful result-availability safeguard coexists with mutable fixture upserts and a kickoff-only target. Corrected data can otherwise rewrite historical knowledge.

**OPTIONS:** Retain overwrite semantics; use event time alone; or separate immutable evidence versions and evaluation context.

**CHOSEN_COMPROMISE:** Five intrinsic timestamps plus target_as_of_at on a typed request. Availability needs a proof reference and cannot precede observation or revision update. Generic availability is <= target; optional STRICTLY_BEFORE preserves score-derived kickoff feature policy. Corrections supersede only from their own availability onward. Future scheduled event_at is allowed for explicit expected claims.

**REASON:** Historical knowledge and real-world event time are different dimensions. The prototype tests delayed final results, corrected events and expected-to-confirmed goalkeeper changes. It is an in-memory contract proof, not yet a durable Medusa service or proof-authentication system.

## D005: distinct stores and compute engines

**OWNER_INTENT:** Multiple databases, mathematical engines, languages, and GPU computation.

**TECHNICAL_CONSTRAINT:** Installing every engine or replicating every table adds complexity without proving a boundary. Polars GPU support targets Linux/WSL2, not the current native Windows runtime.

**OPTIONS:** Force everything through PHP/MariaDB; install all engines now; or assign explicit workloads and defer unneeded integrations.

**CHOSEN_COMPROMISE:** MariaDB is operational state; DuckDB/Parquet are analytical memory; Polars CPU is the planned dataframe path. SQLite is optional utility state. SQL Server, Julia, MATLAB, Wolfram, Node/Go/Java services and local AI remain deferred adapters. None were integrated or newly installed.

**REASON:** Native Windows Python/GPU correctness is preserved. Apache/PHP remain infrastructure and presentation boundaries; heavy analytics and AI remain Python workloads. Joomla is outside the DRAGONHYDRA product architecture.

## D006: distinct tribunals and explicit limits

**OWNER_INTENT:** Multiple calculations, disagreement analysis and uncertainty-driven investigation.

**TECHNICAL_CONSTRAINT:** Comparable numbers need matching targets, units, as-of horizons, assumptions and numerical tolerances. A single universal confidence score would conceal incompatible meanings.

**OPTIONS:** Treat one engine as authoritative; average every output; or preserve typed results and distinct comparison responsibilities.

**CHOSEN_COMPROMISE:** MathEngine/MathEngineResult contracts expose engine/version, inputs, results/distributions, confidence or unknown, precision, warnings, assumptions, runtime, hardware and reason codes. Math Tribunal design compares numerical engines; Prediction Tribunal design compares predictive/model/evidence behavior. Neither tribunal is implemented in genesis.

**REASON:** The feedback loop must be able to refuse a comparison, identify missing/stale/conflicting evidence and ask Hydra a targeted question rather than manufacture certainty.

## D007: observation and bounded validation

**OWNER_INTENT:** Observable checkpoints for future CGCCHILD inspection; no hidden failures or invented success.

**TECHNICAL_CONSTRAINT:** Environment/package metadata, runtime smoke tests and full product integration establish different levels of evidence.

**OPTIONS:** One overwritten status file; huge diagnostic dump; or timestamped stage results with source/assumption records.

**CHOSEN_COMPROMISE:** Unique checkpoint directories store diagnostics, bridge, inventory, full test output and structured results. Documentation links exact runs. Configuration and code reviews uncovered invariant/grant/math-mutability issues before final validation; fixes and their tests are recorded in PROGRESS.

**REASON:** The observer can distinguish measured results from design, candidate packaging support and deferred work. Genesis is complete only within its explicit boundary.
