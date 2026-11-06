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

The correction stays within the existing coordinator. `find_release()` queries
`gh api --paginate --slurp repos/{repo}/releases?per_page=100`, checks every page,
and selects the exact tag. Invalid response/record shapes, repeated release IDs,
multiple matching releases and transport/authentication failures are refusals.
Only a successful valid listing with no matching tag returns absence. Both the
required `release()` lookup and the initial `publish()` discovery use this helper.

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

Focused validation passed all 50 cases across the 19 new lookup/publication
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

This is a separate release-tooling correction. Application source remains
`2d603431aac0bd86f6ae07e07f124fdfdc0dccce`; its nine software packages and six
sealed metadata assets retain their existing bytes and hashes. A checked tooling
commit may execute the existing coordinator with that explicit application source
identity. It does not relabel or rebuild the application, rewrite its annotated
tag, replace sealed assets, or claim that publication/download verification has
already succeeded.
