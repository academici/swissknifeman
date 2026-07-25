# HANDOFF — 2026-07-25 — after P0.3

**Committed item tree: `f405017a`** (item-commit: Acceptance v1 + the frozen bank,
7 files, 4375 insertions). This file's own commit follows as bookkeeping; its hash is
not self-referenced.

**G0 is recorded.** The freeze exists as `plan.md` D59 (the agent records it, D50), so
**P0.4 is unblocked** — it is the plan's first behaviour mutation and the only open item
of P0. There is no separate owner stop before it; the only live owner gate remains G1 at
P4.3.

**Commit hygiene, live warning (unchanged).** The shared working tree's index still carries
an unrelated staged deletion of `roadmap/*.md` files from a concurrent process. This item
was committed with an explicit pathspec (`git commit … -- <the seven Files>`), so the
foreign content stayed out and stayed staged, untouched. Every close in this tree must use
the pathspec form; a bare `git commit -m` after a scoped `git add` still sweeps the whole
index.

**Next:** P0.4 — restore the effective hook lifecycle. Routing (`plan.md` §3):
`implementation/high` / `manual` / `review=full` — above the `plan-exec` pin
(`sonnet/medium`), so the routing gate blocks a `/task:plan-exec` launch. Form is
**ЗАПУСК ВРУЧНУЮ** (equivalently: `/model sonnet` + `/effort high` + `/task:plan-run`).
`roadmap.md` lists P0.4 as `solo`, so this is a single-item launch, not a group.

| Параметр | Значение |
|:--|:--|
| Model | Sonnet (`implementation` по §3 Routing; renderer-таблица roadmap, D33) |
| Thinking | high — first live behaviour mutation, hook rollback |
| Capabilities | `command.subagents` |
| Context | `continue (/clear) — ручной item` (`same-session — item`; P0.4 depends on the recorded G0) |
| Суть | Repair self-host hook ownership/handler drift against the frozen P0 contracts and prove cold/live executable integrity with a rollback path |

````
РЕЖИМ: task:plan-run 2026.07.24-AGENT-RELIABILITY P0.4 (Routing = manual, implementation/high; НЕ plan-exec — тот пинит sonnet/medium и по гейту протокола обязан отклонить этот item).
ВХОД: plans/2026.07.24-AGENT-RELIABILITY/plan.md → handoff.md → phases/P0.md Phase Context + P0.4 целиком → Required Reads P0.4 (19 файлов, порядок как в ТЗ; п.2–4 — только что замороженные Acceptance v1 / bank-manifest / findings P0.3).
ПРЕДУСЛОВИЕ: G0 зафиксирован записью D59 в plan.md §5 (агент, D50) — сверить наличие записи и хеши bank-manifest.json ДО любой мутации; записи нет → писать нельзя.
СКОУП: строго Scope Included P0.4 — точные harness provider/hook seams, шаблон общего обработчика maind, self-host .codex/hooks.json, focused-тесты, синтетические cold/live зонды, compatibility shim только если кэшированный live-путь этого требует. Files — ровно 14 путей из ТЗ P0.4.
НЕ ТРОГАТЬ: новые фичи хуков; эмуляция auto-approve; записи в consumer/fleet; удаление кэшированного пути до доказательства рестартом; artifacts/source-evidence/** (immutable, D30); замороженный банк artifacts/reliability-bank-v1/** (правка версионирует банк и требует переигровки обеих сторон, D15); чужой staged дифф roadmap/*.md в индексе.
ЗАКРЫТИЕ: полный цикл 1–8 plan-exec/plan-run протокола — packages/harness/scripts/validate.sh зелёный ДО item-коммита, item-коммит ПО PATHSPEC (`git commit … -- <Files>`), bookkeeping-коммит плановых путей, handoff.md с реальным хешем, plan-lint --baseline HEAD.
````

**Done:**
- `root/contracts/reliability-acceptance-v1.md` — the frozen acceptance: the bank, the
  deterministic-grader policy, the **two baseline layers**, 14 floors with a measurement
  owner and a baseline source each, the machine-enforced proof-class rule, and the
  correction procedure.
- `artifacts/reliability-bank-v1/` — 31 cases (25 critical / 6 control), 88 assertions,
  48 executable provenance probes, 26 families, seed `reliability-bank-v1/2026-07-25`;
  `graders.json` (8 deterministic operators, `llm_judge_allowed: false`); `run_bank.py`
  (stdlib-only sole owner: validation, probes, grading, metrics, floors, manifest,
  `baseline|verify|candidate|sample`); `baseline-results.json`; `bank-manifest.json`
  (`content_hash=82d1e6a9997dc8de…`).
- Layer-1 run: `31 cases, 88 assertions, 48 probes green`, first-pass `0.1935`
  (critical `0.0`, retention `0.0`), floors `not-met: F1,F2,F3,F7,F11,F12,F13`, `met: F14`,
  `deferred: F4,F5,F6,F8,F9,F10`. Red on layer-1 is the point: layer-1 is the behaviour
  **before** the repair.
- Non-vacuity probed on temporary copies (not committed): a mechanically-built passing
  candidate reaches `first-pass 1.0` with no bank-owned floor unmet (the bank is winnable);
  a flipped expectation changes the grade; a floor with a pinned input and a floor citing a
  `pinned-not-recomputable` evidence id are both refused; a tampered `baseline-results.json`
  fails `verify`. Re-running `baseline` is byte-identical.
- `plan.md` D59 (G0 freeze + the four decisions taken by record) and D60 (the P0.3
  Validation command was unrunnable; ТЗ synchronised, `test_eval.py` → `Ran 32 tests OK`).

**Remaining:** 19/22 items still `⬜`. Phase order unchanged: P0 → P1
(P1.1→P1.2→P1.3→**P1.5**→P1.4, D41) → P2 → P3 → P4. P0.4 is next and is the first item
allowed to change behaviour.

**Sources of truth:** `plan.md` v1.12.4 (§5 D59/D60, §7 Exported — the acceptance row is now
`committed P0.3`, §8 marked frozen, §10 G0 recorded) · `phases/P0.md` (P0.3 Completion Notes,
P0.4 next) · `root/contracts/reliability-acceptance-v1.md` ·
`artifacts/reliability-bank-v1/bank-manifest.json` · `findings/P0.3-acceptance-freeze.md` ·
`root/contracts/task-contract-v1.md` · `artifacts/P0.1/verification-report.json` ·
`plans/README.md` § «Кросс-плановая последовательность» · `journal.jsonl`.

**Open risks:**
- **Layer-2 does not exist yet.** Four floors (F6 trace completeness, F8 Δpass@1, F9 context
  input, F10 owner intervention) stay `deferred` until the live paired run on
  `artifacts/P0.1/pre-plan-sha.txt` at P3.3. A green plan verdict without layer-2 is
  impossible by manifest construction — that is intended, not an oversight.
- **Layer-1 controls pass cheaply.** With no blocking layer in existence, the six controls
  cannot be blocked today; their discriminating power is candidate-side, which is exactly
  what F14 (`false_block_rate == 0`, added beyond §8) exists to catch. Named in the contract
  and in `findings/P0.3-acceptance-freeze.md` §3.
- **The bank's probes will start drifting on purpose.** Once P2 lands the compiler seam, the
  `absent-control-derived` probes stop holding and `run_bank.py baseline` refuses to
  regenerate; layer-1 becomes historical by construction. `verify` still works on any tree
  and reports the drift explicitly. Do not "fix" it by loosening a probe — that versions the
  bank (D15).
- Residual `plan-lint` diagnostics outside this item's Scope are named in the report's Lint
  line; none of them originate from this item's diff.
- Same three A2 findings remain outside scope (base-sha capture order vs the canonical
  `plan-exec`/`plan-run` order; missing workflow-carrier for a claimed autonomous
  multi-session chain; `research/01–03` missing direct RAG markers) — named debt.
- `plans/README.md` § «Очередь планов» still shows AGENT-RELIABILITY as `🟡 0/22` — that file
  is outside this item's Files/carve-out and was intentionally not touched; the next session
  that edits it for another reason should refresh the counter to `3/22`.

**Workarounds/Deferred/Open questions:**
- workarounds: —;
- deferred: layer-2 paired baseline (P3.3) with floors F6/F8/F9/F10; F4 → P1.4, F5 → P0.4;
  the D42 live-host diagnostic → P1.5; plus the standing debt (three A2 findings; A1 F11;
  Claude `workflow-craft` projection; read-only Claude enabled-set measurement;
  `findings/P1.5-collision-closure.md` outside Required Reads of P2.1/P2.5/P3.4; the
  `Context`-enum literal convergence routed to P2.2);
- open_questions: —.
