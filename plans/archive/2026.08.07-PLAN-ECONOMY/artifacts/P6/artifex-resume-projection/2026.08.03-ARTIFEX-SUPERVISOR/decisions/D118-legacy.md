---
id: D118
date: 2026-08-06
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

[OWNER-DELEGATION:P5.2-BRIDGE-ARCHITECTURE] `brief/32-p5.2-bridge-architecture-owner-delegation-2026-08-06.md` records the owner's literal reply delegating the OQ-P5.2-BRIDGE architecture pick to this session: «на твое усмотрение как правильнее, это пакет ии для ии». Under that delegation, the engineering decision is package-owned: extend `packages/artifex/lib/artifex/cli.py`'s existing `dispatch-business` seam (currently validate-only per D108/P5.5 — `_dispatch_business` returns `intent_written: False` by design) with a sibling execution path that composes the already-existing `providers/{codex,claude_code}.build_business_argv`, `providers/claude_code.fold_business_records`, `activity.ProviderActivityPort` and `worker.run`, mirroring the exact admission→argv→activity→schedule pattern the smoke `_dispatch` command already uses. A plan-local-only bridge inside `run-pilot.py` (D116's rejected-by-void approach) would reimplement that execution pattern outside the package, which is the "second/plan-local successor" P5.2's own Scope Excluded already forbids. `run-pilot.py` stays a thin stateless caller of the package's new business-execution entry point, not a parallel implementation. **Consequences:** P5.2 Files/Implementation Rules gain the package paths below; the package gains one additive execution seam, not a new CLI surface beyond `dispatch-business`'s existing contract; D108/P5.5's validate-only guarantee for `dispatch-business` without `--execute`-equivalent intent must remain provable, since P5.5's own acceptance depended on zero business intent. RAG:— (repo-grounded: `packages/artifex/lib/artifex/cli.py:_dispatch_business`, `providers/codex.py:build_business_argv`, `providers/claude_code.py:build_business_argv,fold_business_records`, `activity.py`, existing smoke `_dispatch` pattern).

## Почему

Reusing the package's own already-built provider/activity/worker primitives is smaller and more consistent with P5.5's design than duplicating dispatch logic in a one-off plan script, and keeps a single executable boundary for P5.3/P5.4/P6 to consume later — matching P5.2's explicit prohibition on a second successor implementation.
