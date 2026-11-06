# Development release draft discovery — November 6, 2026

The normal release coordinator created an empty development draft and then failed
to rediscover it through `GET /repos/{owner}/{repo}/releases/tags/{tag}`. GitHub's
[release API documentation](https://docs.github.com/en/rest/releases/releases)
defines that lookup for published releases. The authenticated release list also
includes drafts visible to users with push access. Treating a by-tag 404 as draft
absence therefore broke the existing publisher after creation.

The failed `stage-draft` operation remains preserved. Its stderr receipt has
SHA-256 `66399d4a3a774b682cf150a934632831333eff1a6b46f729c5291e2517052078`;
the independent authenticated release listing has SHA-256
`c727fbd3fcb3c4e07723cf0d1ed871a9ddba8ddfade9615edfb1b4e5cdce7746`.
Draft ID `436407881` was observed with the exact candidate tag, draft/prerelease
flags, expected author and notes, and zero assets. The preserved ledger still
had an empty publication object (SHA-256
`d2228b29c0decc87833274ffd61367002524fe4ce9cb7bad27858ef3fd31e6c6`).

The first correction stayed within the existing coordinator. `find_release()` queries
`gh api --paginate --slurp repos/{repo}/releases?per_page=100`, checks every page,
and selects the exact tag. Invalid response/record shapes, repeated release IDs,
multiple matching releases and transport/authentication failures are refusals.
Only a successful valid listing with no matching tag returns absence. Both the
required `release()` lookup and the initial `publish()` discovery used this helper
at that tooling checkpoint.

Existing ownership rules remain unchanged. An existing draft is resumable only
when its ID and owned-draft flag match this run's ledger. The correction neither
adopts the stranded draft nor edits its ledger ownership. Root separately
preserved and removed only that exact empty failed draft at 11:16:24 UTC after
checking its identity. The cleanup receipt has SHA-256
`d596248e74ac5a2171adb7f54b26a98f315844fc9d9aff165413a44258686732`
and records genuine subsequent HTTP404, zero deleted assets and no ledger edit.
This code adds no deletion or alternate publication route.

Exact source tag checks, primary installed acceptance, privacy, preservation,
asset allowlists/hashes, no-clobber uploads, prerelease/latest flags, draft note
verification and authenticated download verification are unchanged. Mocked tests
cover draft and published discovery, pagination, genuine absence, wrong tags,
duplicates, malformed/authentication/network failures, foreign-draft refusal,
new draft creation and owned-draft resume. Tests do not contact GitHub or create a
real release ledger.

Initial focused validation passed all 50 cases across the 19 new lookup/publication
fixtures and the existing release guard, resource, Joomla packaging, worktree and
runtime-input modules. There were zero failures, errors or skips. From the tooling
worktree, with `src`, `tests` and `scripts` on `PYTHONPATH`, the command is:

```text
python -B -m unittest test_release_draft_lookup test_core_next_release test_release_resources test_release_joomla_gateway test_release_worktree_binding test_runtime_release_inputs
```

The separate tooling-test receipt has SHA-256
`b5e2ad3abcadaf342dec0d08ee0c69d1763fa4c0f6e81468e3df1d9aa1fe696c`.
These tests are a tooling scope, not a replacement for or addition to the sealed
application's installed acceptance counts.

The next controlled stage created empty draft `436419791`, but the immediate
authenticated listing still returned no matching release. The failed receipt has
SHA-256 `a3910218c1582d32516e2d9cbd851e2dc9fdeeac238d3c0c0e7b5204133fc6f9`.
Root separately preserved and removed only that empty failed draft. Its subsequent
normal and no-cache listing probes both reported absence with identical response
hashes. The probe receipt has SHA-256
`180943a0541a3d3e70638662daa3830b0c153a4460b192710ffd4cb072607326`.
The listing visibility failure mechanism remains unproven; the response cache
headers and this comparison do not establish a cache-layer cause.

The follow-up removes the read-after-write listing dependency. The same publisher
uses the documented [create-release API](https://docs.github.com/en/rest/releases/releases#create-a-release)
through `gh api --method POST ... --input <private-request-file>`. Its UTF-8 JSON
contains the exact tag, full application source as `target_commitish`, title,
reviewed notes, JSON booleans `draft: true` and `prerelease: true`, and
`make_latest: "false"`. Both private request and raw response files are opened
exclusively before POST, and the returned response is persisted before parsing.
Unknown, partial, malformed or mismatched responses do not create ledger ownership
or upload anything. The retained exclusive files prevent an automatic second
creation attempt.

Ownership is recorded only from the successful create response after strict
positive ID, exact tag/name/notes, draft/prerelease and zero-assets checks. No
immediate re-list is needed. The response's `target_commitish` is informational:
GitHub ignores that input when the tag already exists, while the unchanged remote
annotated-tag peel gates remain the authoritative application source checks.
Owned operations refresh the exact numeric release ID using authenticated GET
with `Cache-Control: no-cache`; wrong IDs/tags, malformed replies and request
failures are refusals without list fallback or creation. Unknown pre-existing
releases still use the complete authenticated list and remain nonadoptable.

The same focused command then passed all 60 cases, including 29 lookup/create/
ownership cases, with zero failures, errors or skips. It checks exclusive private
evidence, exact create payload, raw-response preservation, uncertain attempts,
owned-ID refresh, source-tag checks and unchanged publication flags. Receipt
SHA-256: `661e92cccc29bb1e96fe7476677383547123bb6f8ea839f759449a7a225d4d9c`.
No real network, release ledger, service or SQL operation ran in these fixtures.

This is a separate release-tooling correction. Application source remains
`2d603431aac0bd86f6ae07e07f124fdfdc0dccce`; its nine software packages and six
sealed metadata assets retain their existing bytes and hashes. A checked tooling
commit may execute the existing coordinator with that explicit application source
identity. It does not relabel or rebuild the application, rewrite its annotated
tag, replace sealed assets, or claim that publication/download verification has
already succeeded.
