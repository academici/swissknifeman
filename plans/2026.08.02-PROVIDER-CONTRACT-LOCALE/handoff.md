# HANDOFF — 2026-08-10 — after P0.2

**Next:** design-item: task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.2

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | repository-plan-read · plan-contract-design |
| Context | cold-start — plan-step |
| Суть | Replace the impossible manual-review input with a deterministic, privacy-minimized classification carrier and explicit review boundary. |
| Команда | `$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.2` |

```text
$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.2

РЕЖИМ: remediation
ВХОД: phases/P0/P0.2.md; bundles/P0.2.json; phases/P0/P0.2.state.md; artifacts/P0.1/evidence/provider-{fleet-inventory,source-snapshot}.json
СКОУП: 1) replace the 1.95M-token manual-read requirement with a deterministic, bounded evidence carrier; 2) preserve exact-one, no-write and fail-closed classification semantics; 3) make the validator and bundle executable under the declared read budget.
НЕ ТРОГАТЬ: P0.1 evidence, P0.3/P0.4 contracts, provider/fleet targets, or any classification outcome without reviewed evidence.
```

**Done:** P0.1 is closed with deviations in commits `0169e256` and `3989711b`. P0.2 route and Task Contract are valid, but the item is escalated before mutation because its required snapshots are mechanically 13,421 paths / approximately 1.95M estimated tokens while final heuristic classification is forbidden.

**Remaining:** Redesign P0.2's evidence boundary; P0.3 and P0.4 remain phase-first blocked behind a terminal P0.2.

**Sources of truth:** `phases/P0/P0.2.md` · `bundles/P0.2.json` · `phases/P0/P0.2.state.md` · `journal.jsonl`.

**Open risks:** `plans/verify-citations.py` is absent, so P0.1's citation gate could not run; this environment defect remains non-green.

**Workarounds/Deferred/Open questions:**

- workarounds: —
- deferred: P3.2 owns the Codex hook provenance repair.
- open_questions: —
