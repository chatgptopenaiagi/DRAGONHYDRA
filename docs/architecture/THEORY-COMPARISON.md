# Architectural alternatives and evidence

| Approach | Actual implementation | Strengths | Limits | Decision |
|---|---|---|---|---|
| Original A9-derived System Control Center | `a63068de...`: `module_registry.py`, `system_workflow.py`, Joomla `SystemModules` | Broad role inventory, status filter, validated service-name presentation and read navigation; 54 reference tests rerun successfully | Different unpublished schema/identity and passive probe model; metadata does not prove model execution | Preserve history; integrate compatible UI and stronger typed service evidence through the existing CORE NEXT contract |
| Composed CORE NEXT | F `ede5bf...`: `kernel/composition.py`, ports, registry, observer, workflow | One logical core, injected responsibilities, worker-owned observation, cached reads, profile/build binding, immutable research | Mixed installed component identities and pending new Windows lifecycle; optional capabilities remain unverified without evidence | Selected integration foundation; retain one authoritative implementation |
| Independent DRAGON foundation | `1d044992...`: `dragon.data_engine`, `dragon.models`, DuckDB, Polars, Qt shell | Typed probability validation and strictly-before-kickoff `result_available_at` feature joins; 42 tests passed in isolated snapshot | Abstract model interface, no proven trained forecast/evaluation workflow; caller-supplied availability does not establish historical acquisition; different storage/client contracts | Retain for future research; no replacement of SQLite, Tauri, provider identity or point-in-time provenance |

The current four base forecast outputs plus ensemble are five outputs, not five
independent trained models. Existing deterministic mathematics is shared across
the A9-derived histories. No measured predictive accuracy or performance advantage
is inferred from code presence, test count, model listing or abstract interfaces.

The isolated foundation test used its existing 3.12 interpreter with its existing
dependency directory. It installed nothing and did not repair the original venv.
The first harness run hit a shared temporary-directory ACL; the second used an
explicit disposable test directory and passed all 42 unchanged assertions. This
was a harness/environment problem, not a proven application defect.
