# HANDOFF — 2026-07-25 — after P0.1

**Committed item tree: `a81effd1`** (item-commit: contract + verifier + tests +
report + `pre-plan-sha.txt` + incident corpus). This file's own commit follows
as bookkeeping; its hash is not self-referenced.

**Programmatic gate D56 is satisfied.** Stages A, A0, B, C of
`plans/README.md` § «Программа: этапы A–D» are ✅ as of 2026-07-25 (321 paths,
19 live intersections all owned, 0 blind spots, cross-plan audit verdict
ATTENTION with 9 findings already routed to Такт 0 payloads). P0.1 is exactly
step 01 of Такт 1 / Track 1A in that README's «Кросс-плановая
последовательность» — it is now closed.

**Next:** P0.2 — Task Contract v1. Routing (`plan.md` §3): `frontier/high` /
`manual` / `review=full` — this exceeds the `plan-exec` pin (`sonnet/medium`),
so the routing gate (protocol step 2) blocks a `/task:plan-exec` launch. Form
is **ЗАПУСК ВРУЧНУЮ**.

| Параметр | Значение |
|:--|:--|
| Model | Opus (`frontier` по §3 Routing) |
| Thinking | high — frozen contract с open design decisions, full-класс не батчится |
| Capabilities | `command.subagents` |
| Context | `NEW SESSION` — following AR Такт 1 / Track 1A order (P0.2 depends on terminal P0.1) |
| Суть | Freeze Task Contract v1 schema/spec/examples: Goal/Must/Never/Done/Authority/Next/Route/Evidence/Portability/Conflicts/Version, consuming P0.1's proof-class report |

````
РЕЖИМ: task:plan-run 2026.07.24-AGENT-RELIABILITY P0.2 (Routing = manual, frontier/high; НЕ plan-exec — тот пинит sonnet/medium и по гейту протокола обязан отклонить этот item).
ВХОД: plans/2026.07.24-AGENT-RELIABILITY/plan.md → handoff.md → phases/P0.md Phase Context + P0.2 целиком → Required Reads P0.2 (16 файлов, порядок как в ТЗ).
СКОУП: строго Scope Included P0.2 (phases/P0.md) — schema, precedence/conflict result, content hash/supersedes, authority classes, public acceptance, pre-mutation/pre-final predicates, root/subagent slice, cold-start payload. Files — ровно четыре пути из ТЗ P0.2.
НЕ ТРОГАТЬ: task package implementation; owner-intent inference; new orchestrator; any behavior mutation (P0.4 остаётся заблокирован до P0.3 G0).
ЗАКРЫТИЕ: полный цикл 1–8 plan-exec/plan-run протокола — item-коммит по Files, bookkeeping-коммит плановых путей, handoff.md с реальным хешем, plan-lint --baseline HEAD.
````

**Done:**
- `pre-plan-sha.txt` = `7479972f2a582ab8583270c30fad8da1ff56659e` (D45, sole
  `PRE_PLAN_SHA` producer for the whole plan; read-only for every later item).
- `root/contracts/source-evidence-verification-v1.md` — machine contract:
  four closed proof classes, names the exact F1 gap (per-record key closure,
  fresh histogram recompute, cross-manifest linkage, corpus/session field
  shape) that the immutable `verify_source_bundle.py` does not cover, and
  names `classified_lifecycle_events`(550)/`outcomes`/`dedup_correction` as
  explicitly `pinned-not-recomputable`.
- `artifacts/P0.1/semantic-verification-contract.json` — 16 declared
  assertions (7 `recomputed`, 7 `cross-checked`, 2 `pinned-not-recomputable`,
  0 `unknown`).
- `artifacts/P0.1/semantic_bundle_verifier.py` + `verification-report.json` —
  `semantic verification passed: 16/16 assertions` against the committed
  bundle; delegates the four immutable commands (`verify`/`map-state`/
  `verify-results`/`verify-claim-inventory`) as subprocess cross-checks and
  never re-implements them.
- `artifacts/P0.1/test_semantic_bundle_verifier.py` — 15/15 tests pass:
  valid-base full pass, 8 mutated-temp-copy failure modes (rehashed manifest
  field change, missing `source_committed_paths`, duplicate `case_id`,
  forbidden payload key in a session record, malformed confidence/timestamp/
  selector, journal `result` drift correctly recomputed not silently matched,
  journal forbidden-key drift), a structural guard that the two pinned facts
  are never declared `recomputed`, and a guard that running the verifier
  never writes below `artifacts/source-evidence/`.
- `findings/P0.1-incident-corpus.md` — per-hypothesis table linking D1's
  falsifiable hypothesis to the five committed corpus cases with confidence
  and proof class, plus the recomputed 591-record journal histograms.
- `git diff --exit-code -- artifacts/source-evidence` clean — immutable
  bundle unchanged.

**Remaining:** 21/22 items still `⬜`. Phase order unchanged: P0 → P1
(P1.1→P1.2→P1.3→**P1.5**→P1.4, D41) → P2 → P3 → P4.

**Sources of truth:** `plan.md` v1.12.2 (§2, §5 D45/D50, §7 Exported) ·
`phases/P0.md` (P0.1 Completion Notes, P0.2 next) · `root/contracts/source-evidence-verification-v1.md` ·
`artifacts/P0.1/verification-report.json` · `findings/P0.1-incident-corpus.md` ·
`plans/README.md` § «Программа: этапы A–D» и § «Кросс-плановая
последовательность» (item-level exec order across the three live plans) ·
`journal.jsonl`.

**Open risks:**
- Same three A2 findings named in the previous handoff remain outside this
  item's scope (base-sha capture order vs canonical `plan-exec`/`plan-run`
  order; missing workflow-carrier for a claimed autonomous multi-session
  chain; `research/01–03` missing direct RAG markers) — named debt, not
  blocking.
- `classified_lifecycle_events`(550) and `dedup_correction` totals in the
  committed bundle remain permanently `pinned-not-recomputable`: no
  classifier or raw-rollout access is committed to the plan directory. Any
  future item that needs those exact derivations must either accept the
  bundle's stored value as labelled context (never as a deterministic
  acceptance predicate, D30) or produce its own committed classifier as new
  Scope.
- `plans/README.md` § «Очередь планов» still shows AGENT-RELIABILITY as
  `🟡 0/22` — that file is outside this item's Files/carve-out
  (`plans/<PLAN-ID>/**` + `plans/ACTIVE.md`) and was intentionally not
  touched; the next session that edits `plans/README.md` for another reason
  should refresh the counter to `1/22`.

**Workarounds/Deferred/Open questions:**
- workarounds: —;
- deferred: same as previous handoff (three A2 findings; A1 F11; mirrored
  `Consumed` line in `2026.07.25-ECO-OPT`; Claude `workflow-craft` projection;
  read-only Claude enabled-set measurement; `findings/P1.5-collision-closure.md`
  outside Required Reads of P2.1/P2.5/P3.4);
- open_questions: —.
