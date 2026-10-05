# Research synthesis — PLAN1 (2026-10-05)

Captures: `artifacts/design-rag/pplx-01.md` … `pplx-05.md` (perplexity-web). Search output is provenance;
each row states what it changes in the design.

| # | Finding | Marker | Design consequence |
|:--|:--|:--|:--|
| R1 | No existing tool offers JSON-Schema-validated task plans plus generated Markdown views. Task Master is closest (`tasks.json`: status, dependencies, subtasks, `testStrategy`) but has no published schema; beads moved its source of truth from JSONL to Dolt and treats JSONL as export; Spec Kit/OpenSpec/Kiro keep specs in Markdown. | RAG:✅ pplx-01 | Build our own small engine; adopt Task Master's explicit `testStrategy` idea as typed `validation[]`, beads' lesson "one declared source of truth, views are exports". Nothing to vendor. |
| R2 | Backlog.md and beads restrict mutations to CLI/MCP so dependencies, statuses and links are checked; free file editing requires schema validation and reference/cycle checks. | RAG:✅ pplx-01 | All mutations through `plan.py`; `plan.py check` validates schema, refs and cycles; views carry a "generated" banner. |
| R3 | Dependencies need semantics: distinguish "blocks", "parent/child" and "can run in parallel" instead of row order. | RAG:✅ pplx-01 | Item `depends_on` (blocking) separate from `related[]` (non-blocking, typed relation); batches are explicit groups in phase JSON. |
| R4 | A cheap scout helps as an index/router ("where to look and why"), not as author of the final design; ContextBench (2026): heavy agentic scaffolding gives small retrieval gains, agents fetch context they never use and favour recall over precision. No public measurement proves "cheap briefing first" raises pass rate. | RAG:✅ pplx-02 (truncated) | Deterministic context pack is the default; the weak-model scout is opt-in, produces only a map of paths/symbols with reasons, and is measured through the log before it becomes a default (D3). |
| R5 | OpenAI Codex guidance: keep AGENTS.md short and accurate; give task-specific context in the prompt as Goal / Context / Constraints / Done-when; 32 KiB is a loading cap, not a target; conflicting rules across levels confuse the model. | RAG:✅ pplx-03 | Commands shrink to a few verbs; the context pack is rendered in exactly the Goal/Context/Constraints/Done-when order; protocol detail moves into code and schemas. |
| R6 | Logging: harness writes the automatic trace; the agent writes only a sparse friction log at natural boundaries. Minimal event: `v, ts, task_id, type, summary` + optional `impact, next, ref`; type enum `deviation, blocker, difficulty, decision, assumption`. | RAG:✅ pplx-04 | `log.jsonl` with lifecycle events written by the API and the five friction types written by the agent through one command; the context pack replays relevant friction to the next item. |
| R7 | No tiny maintained stdlib-only Draft 2020-12 validator could be verified; recommended: own validator for a closed keyword profile, failing closed on unsupported keywords. Chevron (MIT) offers Mustache with partials; `string.Template` has no sections/partials. | RAG:✅ pplx-05 | Own closed-profile validator (P1.1) and own ~150-line Mustache subset with partials (P1.3); `lib/task` stays stdlib-only, nothing vendored. |
| R8 | Owner's YouTube short on context-gathering orchestration could not be read. | [UNVERIFIED] | D3 is based on R4 and the owner's own description. |

## Repository facts used by the design (RAG:—)

- `packages/task/lib/task/` has ~25.4K lines across 55 modules plus `plan_lint_checks/`; tests ~19.7K lines in 70 files.
  The v2 executor path, digest bundles, route evidence and terminal admission are the main sources of
  rigidity recorded in `roadmap/2026-10-02-task-plan-run-rigidity.md` (ROUTE_LAUNCH_MISMATCH, BATCH_STALE,
  no close command, no owner-amendment operation).
- `plan-run.md` is 131 lines of protocol prose over 15 internal modules — the instruction overload of B10.
- Item fields used across 350 items in 4 repositories: Intent, Why, Scope Included/Excluded, Inputs, Files,
  Required Reads, Implementation Rules, Code Guidance, Validation, Deliverables (+ state: Status, Completion
  Notes, Pending Work, Known Deviations, Escalation Needed); `Authority` in 36 items.
- External consumers of the Task runtime: `packages/harness` (Stop hook `plan-terminal-admission.py`,
  review-gate `plan-lint.sh`/`plan-citations.sh`), `packages/artifex/lib/artifex/compiler.py`
  (`plan-lint.py --json`, `task.task_contract build`), `packages/skiller/lib/skiller/publication.py`
  (PYTHONPATH only), `core/provider/runtime.py` (package path only).
- Model pool: `packages/task/configs/command-routing.json` → `mappings.<provider>.model_inventory.entries[]`
  (`id`, `roles`, `patterns`, `status`), class pins in `class_selectors`.
