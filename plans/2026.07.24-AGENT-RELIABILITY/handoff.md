# HANDOFF — 2026-07-25 — after P0.2

**Committed item tree: `fab8620b`** (item-commit: Task Contract v1 spec + schema +
examples + validator, 4 files, 3069 insertions). This file's own commit follows as
bookkeeping; its hash is not self-referenced.

**Commit hygiene, live warning.** The shared working tree's index STILL carries an
unrelated staged deletion of 12 `roadmap/*.md` files from a concurrent process (the same
class of foreign staged content that swept into `55e8477b` during P0.1). This item was
committed with an explicit pathspec (`git commit … -- <the four Files>`), so the foreign
content stayed out and stayed staged, untouched. Every close in this tree must use the
pathspec form; a bare `git commit -m` after a scoped `git add` still sweeps the whole
index.

**Next:** P0.3 — Acceptance v1 and the fixed bank. Routing (`plan.md` §3):
`frontier/high` / `manual` / `review=full` — above the `plan-exec` pin (`sonnet/medium`),
so the routing gate blocks a `/task:plan-exec` launch. Form is **ЗАПУСК ВРУЧНУЮ**
(equivalently: set the session to Opus/high and run `task:plan-run`).

| Параметр | Значение |
|:--|:--|
| Model | Opus (`frontier` по §3 Routing) |
| Thinking | high — freeze thresholds/graders before any behavior mutation |
| Capabilities | `command.subagents` |
| Context | `same-session — item` (AR Такт 1 / Track 1A order: P0.3 depends on terminal P0.2) |
| Суть | Freeze Acceptance v1: 20–50 bank cases, deterministic graders, baseline results, bank manifest, exact floors, and the G0 D-entry the agent records itself (D50) |

````
РЕЖИМ: task:plan-run 2026.07.24-AGENT-RELIABILITY P0.3 (Routing = manual, frontier/high; НЕ plan-exec — тот пинит sonnet/medium и по гейту протокола обязан отклонить этот item).
ВХОД: plans/2026.07.24-AGENT-RELIABILITY/plan.md → handoff.md → phases/P0.md Phase Context + P0.3 целиком → Required Reads P0.3 (12 файлов, порядок как в ТЗ; п.5–7 — только что запечатанный Task Contract v1: root/contracts/task-contract-v1.md, task-contract-v1.schema.json, artifacts/P0.2/task-contract-examples.json).
СКОУП: строго Scope Included P0.3 (phases/P0.md) — 20–50 failure/control cases, детерминированные assertions, transcript/outcome graders, bank manifest, baseline results, floors §8 (с квалификатором D53), G0 как D-запись агента (D50). Files — ровно семь путей из ТЗ P0.3.
НЕ ТРОГАТЬ: P1/P2/P3 fixes; hook mutation (P0.4 остаётся заблокирован до зафиксированного freeze'а); fleet trials; post-candidate tuning порогов; artifacts/source-evidence/** (immutable, D30); чужой staged дифф roadmap/*.md в индексе.
ЗАКРЫТИЕ: полный цикл 1–8 plan-exec/plan-run протокола — item-коммит ПО PATHSPEC (`git commit … -- <Files>`), bookkeeping-коммит плановых путей, handoff.md с реальным хешем, plan-lint --baseline HEAD.
````

**Done:**
- `root/contracts/task-contract-v1.md` — the sealed spec: closed field set (11 required
  D5 fields + `slice` + `cold_start` + identity), the 6-rank carrier precedence ladder,
  "a lower carrier narrows safety but never widens authority", the D30 proof-class rule,
  both predicates with ordered typed codes, the root/subagent slice partition, the
  cold-start payload, and the `Context`-enum projection table.
- `root/contracts/task-contract-v1.schema.json` — `additionalProperties: false` at every
  level; no field exists outside the sealed set.
- `artifacts/P0.2/task-contract-examples.json` — 11 full scenario contracts + 12
  single-field negative mutations (RFC-7386 merge patch over a named base) + 16 declared
  reason codes + 5 corpus-coverage rows.
- `artifacts/P0.2/validate_task_contract.py` — stdlib-only sole executable owner: JSON
  Schema subset interpreter, both predicates, `--rehash` hash generation, corpus-coverage
  proof. Run: `23 cases checked, 16 reason codes exercised, 4/4 critical corpus cases
  mapped to a field and a check` (exit 0, on `fab8620b`).
- Non-vacuity probed on temporary copies (not committed): a flipped expectation, a removed
  coverage row and a tampered contract byte each produce exit 1 with the exact reason.

**Remaining:** 20/22 items still `⬜`. Phase order unchanged: P0 → P1
(P1.1→P1.2→P1.3→**P1.5**→P1.4, D41) → P2 → P3 → P4. P0.4 stays blocked until the P0.3
freeze is recorded as a D-entry (G0 — the agent records it, D50).

**Sources of truth:** `plan.md` v1.12.3 (§2, §5 D30/D45/D50, §7 Exported — the
task-contract row is now `committed P0.2`) · `phases/P0.md` (P0.2 Completion Notes, P0.3
next) · `root/contracts/task-contract-v1.md` + its schema · `artifacts/P0.2/task-contract-examples.json` ·
`root/contracts/source-evidence-verification-v1.md` · `artifacts/P0.1/verification-report.json` ·
`plans/README.md` § «Кросс-плановая последовательность» · `journal.jsonl`.

**Open risks:**
- Residual plan-lint diagnostics outside this item's Scope are named in the report's Lint
  line; none of them originate from this item's diff.
- The `Context`-enum literals diverge between `plan-protocol` SKILL §8 (neutral) and
  `packages/task/commands/*` (Russian projections). Task Contract v1 canonizes the neutral
  values and records the projection; converging the literals is P2.2 enforcement work, not
  this item's.
- Same three A2 findings remain outside scope (base-sha capture order vs the canonical
  `plan-exec`/`plan-run` order; missing workflow-carrier for a claimed autonomous
  multi-session chain; `research/01–03` missing direct RAG markers) — named debt.
- `classified_lifecycle_events`(550) and `dedup_correction` totals stay permanently
  `pinned-not-recomputable`; Task Contract v1 now makes this machine-enforced — such a
  quantity can never satisfy a public acceptance predicate (`EVIDENCE_PROOF_CLASS_INSUFFICIENT`).
- `plans/README.md` § «Очередь планов» still shows AGENT-RELIABILITY as `🟡 0/22` — that
  file is outside this item's Files/carve-out and was intentionally not touched; the next
  session that edits it for another reason should refresh the counter to `2/22`.

**Workarounds/Deferred/Open questions:**
- workarounds: —;
- deferred: same as the previous handoff (three A2 findings; A1 F11; Claude
  `workflow-craft` projection; read-only Claude enabled-set measurement;
  `findings/P1.5-collision-closure.md` outside Required Reads of P2.1/P2.5/P3.4), plus the
  `Context`-enum literal convergence routed to P2.2;
- open_questions: —.
