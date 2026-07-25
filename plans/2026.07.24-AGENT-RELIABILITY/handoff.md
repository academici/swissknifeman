# HANDOFF — 2026-07-25 — after P0.4

**Committed item tree: `9fdec6d3`** (item-commit: self-host Codex hook lifecycle restored
via the existing D104 bootstrap-transfer, plus three synced ТЗ/repo-drift fixes recorded
D61 — 7 files, 158 insertions). This file's own commit follows as bookkeeping; its hash is
not self-referenced.

**P0.4 closed `🟠 Done with deviations`.** `findings/04-runtime-preflight.md`'s two defects
(unmanaged `.codex/hooks.json`, missing `context.observer` handler) are repaired: the memory
hook is preserved byte-for-byte, the observer is registered second, `.codex/hooks/lifecycle.py`
and `.swissknifeman/provider-artifacts.lock.json` exist and are `noop`/`clean` under
`maind.provider_deploy.plan_provider_artifacts`. Full diagnosis —
`findings/P0.4-hook-integrity.md`. The 🟠 is **process, not product** (D61): the item-commit
carries a one-line stale-path fix to `packages/harness/lib/harness/instructions.py` (outside
this item's `Files` — a different plan's archival commit, `5b79f926`, had broken it and, with
it, `packages/harness/scripts/validate.sh` for the whole package, independent of this item's
own work).

**Phase P0 is NOT terminal.** All 4 items are now non-`⬜` (P0.1–P0.3 🟢, P0.4 🟠), but
`## 4. Phase Index & Status Board` stays `3/4` / `🟡 In progress` (the counter counts only
🟢; closing the phase is a separate `plan-close`/audit step this run did not perform). Phase
P1 is next; its first item, P1.1, does not require P0 to be formally closed — only terminal
(`plan.md` Phase-first rule: "все её items 🟢/🟠/⛔"), which P0 now is.

**Commit hygiene, live warning (unchanged from the previous handoff).** The shared working
tree still carries an unrelated foreign diff (staged and unstaged, mixed — `roadmap/*.md`
deletions, `packages/harness/lib/harness/agentpacks.py`, `test_agentpacks.py`,
`test_settings_audit_fieldcase.py`, `plans/README.md` and several archived `plans/*`
directories) from a concurrent process. This item was committed with an explicit pathspec
(`git commit … -- <the seven Files>`), so the foreign content stayed out and stayed exactly
as it was. Every close in this tree must use the pathspec form.

**Next:** P1.1 — freeze identity/ownership/capability inventory. Routing (`plan.md` §3):
`frontier/high` / `manual` / `review=full` — above the `plan-exec` pin (`sonnet/medium`), so
the routing gate blocks a `/task:plan-exec` launch. Form is **ЗАПУСК ВРУЧНУЮ**
(equivalently: `/model opus` + `/effort high` + `/task:plan-run`). `roadmap.md` lists P1.1 as
`solo`, so this is a single-item launch, not a group.

| Параметр | Значение |
|:--|:--|
| Model | Opus (`frontier` по §3 Routing; renderer-таблица roadmap, D33) |
| Thinking | high — freeze item, full review, no batching |
| Capabilities | `command.subagents` |
| Context | `continue (/clear) — ручной item` (`same-session — item`; P1.1 depends only on terminal P0, which now holds) |
| Суть | Freeze identity/ownership/capability inventory: repo-derived collision set, machine-readable observed before-state, owner-map of all 16+1 measured collisions, exact 13-identity/26-projection private bootstrap map + `workflow-craft` class-B record |

````
РЕЖИМ: task:plan-run 2026.07.24-AGENT-RELIABILITY P1.1 (Routing = manual, frontier/high; НЕ plan-exec — тот пинит sonnet/medium и по гейту протокола обязан отклонить этот item).
ВХОД: plans/2026.07.24-AGENT-RELIABILITY/plan.md → handoff.md → phases/P1.md Phase Context + P1.1 целиком → Required Reads P1.1 (26 файлов, порядок как в ТЗ).
ПРЕДУСЛОВИЕ: фаза P0 терминальна (все 4 items 🟢/🟠 — P0.1–P0.3 🟢, P0.4 🟠 с Known Deviations, D61); сверить это по `phases/P0.md` Phase Status ДО любой мутации.
СКОУП: строго Scope Included P1.1 — identity/ownership contract, repo-derived cold collision detection (D44), machine-readable observed before-state (один read-only capture), owner-map всех измеренных коллизий (16 root↔installed + 1 installed↔installed), exact 13-identity/26-projection класс-A bootstrap map + класс-B запись `workflow-craft`, `generated-artifact-version-v1.md` + version ledger по пяти owner-item'ам (P1.2/P1.3/P1.5/P2.2/P2.3), diff-scope guard с foreign-commit атрибуцией. Files — ровно 11 путей из ТЗ P1.1.
НЕ ТРОГАТЬ: source fixes (skiller/task/harness код) — этот item только замораживает контракт/карты, не правит носители; внешние плагины; fleet-установки; семантический редизайн; user-owned enabled-множество провайдера (D42 — только диагностика, не правка профиля).
ЗАКРЫТИЕ: полный цикл 1–8 plan-exec/plan-run протокола — все команды Validation P1.1 зелёные ДО item-коммита, item-коммит ПО PATHSPEC (`git commit … -- <Files>`), bookkeeping-коммит плановых путей, handoff.md с реальным хешем, plan-lint --baseline HEAD.
````

**Done:**
- `.codex/hooks.json` — composed `SessionStart`: the pre-existing memory command
  (byte-identical, first) + the new `context.observer` group (matcher
  `startup|resume|clear|compact`, second), validated by
  `harness.hooks.validate_d104_codex_lifecycle_composition` before the write.
- `.codex/hooks/lifecycle.py` — created (`render_codex_hook_handler()`): validates
  `--surface context.observer` and the required SessionStart payload keys, emits a
  read-only `systemMessage`, exits `2` on malformed input.
- `.swissknifeman/provider-artifacts.lock.json` — created; owns both artifacts under
  adapter `maind.d104.bootstrap-transfer`. `maind.provider_deploy.plan_provider_artifacts`
  reports both `noop`/`clean` on the live tree.
- `~/.claude/hooks/run-report/_lib.py` staleness (`harness doctor`) fixed by
  `harness hooks --global` (global, non-git action).
- `packages/harness/lib/harness/instructions.py:241` (`contract_path()`) and one hardcoded
  path in `test_provider_conformance.py:170` re-pointed from the pre-archival
  `plans/2026.07.19-DUAL-PROVIDER/...` to `plans/archive/2026.07.19-DUAL-PROVIDER/...` —
  fixes `test_provider_instructions.py` (28/28), `test_instruction_compatibility.py` (6/6)
  and `packages/harness/scripts/validate.sh` (`validate: OK`), independent of this item's
  hook work.
- `plan.md` D61 (three ТЗ/repo-drift syncs, recorded as process deviations) and Update Log.

**Remaining:** 18/22 items still `⬜` (or, for P0.4, `🟠`). Phase order unchanged: P0 → P1
(P1.1→P1.2→P1.3→**P1.5**→P1.4, D41) → P2 → P3 → P4. P1.1 is next.

**Sources of truth:** `plan.md` v1.12.5 (§5 D61, §4 Phase Index P0 3/4) · `phases/P0.md`
(P0.4 Completion Notes/Known Deviations, Phase Handoff) · `phases/P1.md` (P1.1 full spec) ·
`findings/P0.4-hook-integrity.md` · `.swissknifeman/provider-artifacts.lock.json` ·
`journal.jsonl`.

**Open risks:**
- **`harness hooks --provider codex --observer --dry-run` reports `warning: stale-source`
  (exit 0), not clean.** Named, understood (`findings/P0.4-hook-integrity.md` §5): the
  plain harness CLI computes its own `ArtifactSource` provenance, distinct by design from
  the `maind.d104.bootstrap-transfer` adapter that actually owns the composed artifact. The
  authoritative check is `maind.provider_deploy.plan_provider_artifacts` (green). Not
  remediated — reconciling the two adapter identities would be a harness/maind
  cross-package refactor outside P0.4's Scope; named as Pending Work.
- **Codex process restart not verified from inside this session** (this session is Claude,
  not Codex). If a live Codex process has this repo open, its cached hook registry predates
  the observer addition — AGENTS.md's live-path verification step applies at the next Codex
  cold-start/restart on this repo.
- Same standing debt as the previous handoff, untouched by this item: three A2 findings
  (base-sha capture order; missing workflow-carrier for a claimed autonomous multi-session
  chain; `research/01–03` missing RAG markers); A1 F11; Claude `workflow-craft` projection;
  read-only Claude enabled-set measurement.
- `plans/README.md` § «Очередь планов» still shows this plan's stale item counter — outside
  this item's Files/carve-out, not touched.

**Workarounds/Deferred/Open questions:**
- workarounds: —;
- deferred: the harness-CLI/maind-adapter provenance mismatch (§ Open risks above) —
  candidate follow-up, no owner item yet;
- open_questions: —.
