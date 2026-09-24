# Proposed next experiment: Python 3.14 reads Joomla data

**NEXT_EXACT_ACTION:** In a separate experiment, use the existing `codex-pytorch` Python 3.14.7 interpreter to query published Joomla content counts through a new localhost SELECT-only database account and emit a JSON result.

This is a proposal only. No Python/Joomla integration, additional account, connector package, service or Joomla extension was implemented during deployment.

## Intended test

1. Inspect the existing `j5faba9_content` and `j5faba9_categories` table definitions in `joomla_codex_lab`; confirm the installed Python 3.14 environment and available compatible database connector.
2. Create a separate account restricted to SELECT on these two tables, reachable only from localhost. Store its generated secret outside htdocs. Do not reuse Joomla's application credentials for analytics.
3. Run Python from `C:\Users\Administrator\anaconda3\envs\codex-pytorch\python.exe`, working below this experiment's sibling integration directory under `C:\xampp\DRAGONHYDRA\experiments`.
4. Return JSON containing query time, published article count, and counts by category. The fresh Joomla installation may legitimately have zero articles; do not invent sample results.
5. Independently compare Python's result with an equivalent local SQL query and verify the new account cannot perform writes or read unrelated tables.

Success would prove the Python 3.14 laboratory can consume real Joomla/MariaDB data without manual GUI work or a new public service. CUDA/PyTorch is not required for this small query, and its environment should remain unchanged unless a required connector is explicitly included in the next experiment's scope.

## Current browser handoff

The Joomla deployment itself is functional. Browser launch was blocked by automatic approval review, so the user may open [the frontend](http://localhost/joomla-codex-lab/) and [administrator](http://localhost/joomla-codex-lab/administrator/) manually to inspect the interface. Administrator credentials are in the protected `credentials.local.txt` file; no login is necessary to validate the already-passed server-side deployment checks.
