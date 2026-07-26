# HANDOFF — 2026-07-26 — after P2.5

**Next:** phase P2 item-terminal (5/5) — close/reconcile it before P3 starts (Phase-first rule).

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `low` |
| Capabilities | — |
| Context | `NEW SESSION — шаг-не-item` |
| Суть | Реконсилировать и закрыть фазу P2 по git-фактам (все 5 items терминальны: P2.1🟢/P2.2🟢/P2.3🟢/P2.4🟢/P2.5🟠), обновить Phase Handoff/Status Board, затем открыть P3.1 |

```
/task:plan-close 2026.07.24-AGENT-RELIABILITY P2
```

**Done:**

- **P2.1–P2.4 закрыты 🟢** — детали `phases/P2.md` соответствующих Completion Notes.
- **P2.5 закрыт 🟠 Done with deviations** (2026-07-26, `task:plan-run` под **implementation/medium**
  = предписанный §3 Routing `implementation/medium`, точное совпадение). Произведено:
  - `plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/candidate-results.json`,
    `.../result-manifest.json`, `.../verify_result_manifest.py` (P2.5-owned verifier/manifest
    writer, не переизобретает грейдинг — вызывает замороженный `run_bank.py candidate`, D30) и
    `findings/P2.5-scenario-results.md`.
  - Все 31 замороженных кейса `reliability-bank-v1` (`bank_version 1.0.0`) прогнаны через
    реальные вызовы `task.task_contract.pre_mutation`/`pre_final` (15 кейсов),
    `task.review_policy` (`reopens_product`/`LoopBudget`/`review_transition`, 2), `task.route_evidence`
    (`capture_actual`/`classify`/`dispatch_guard`/`canonical_actor`, 3),
    `task.command_catalog`/`command_render` (реальный provider-рендеринг, 3) и прямое чтение
    закоммиченной evidence (`artifacts/P1.4/effective-carrier-set.json`, `.codex/hooks.json` +
    `.swissknifeman/provider-artifacts.lock.json`, `artifacts/source-evidence/sessions/**`,
    `skiller registry --check` — 5). Результат: **30/31 зелёных**
    (`first_pass_success 0.9677`). Floors: met F2/F3/F7/F11/F12/F13/F14; **not-met F1**
    (`critical_requirement_retention 0.96`); deferred F4 (уже терминален, P1.4)/F5 (уже
    терминален, P0.4)/F6/F8/F9/F10 (требуют P3.3 live layer-2 paired run).
  - **Единственный residual:** `trace-record-missing` — P3.1/P3.2 (unified trace) ещё не
    существует, честно репортится `declared_status: failed`, не подделан.
  - Validation: `py_compile` OK · оба `json.tool` OK · полный прогон `verify_result_manifest.py`
    → `30/31 кейсов green, floors not-met: F1, residual: trace-record-missing` ·
    `packages/task/scripts/validate.sh` / `packages/skiller/scripts/validate.sh` (444 тестов) /
    `packages/harness/scripts/validate.sh` → все `validate: OK`.
  - Diff-scope guard: item-коммит `14b3e6ce` несёт ровно `Files` — посторонний дифф нет.
  - **Known Deviations (material, не только process — см. `phases/P2.md` P2.5 Known
    Deviations):** (1) "fresh item dispatch"/"cold recovery" (root-supervisor → fresh
    subagent → cold recovery) не были буквально воспроизведены — гарнесс работал прямым
    вызовом внутри текущей сессии, не симулированным multi-subagent диспатчем; сами
    проверяемые швы (`task_contract`/`review_policy`/`route_evidence`) от этого не зависят,
    но механика диспатча этим item'ом не доказана. (2) task-specific temp roots per provider
    (D48) материализованы только для 3 кейсов, реально нуждающихся в двух провайдерах
    (`wrong-provider-invocation`, `claude-only-carrier`, `control-provider-neutral-rendering`)
    — остальные 28 читали живой каталог репо напрямую; запрет на `HOME`/`CODEX_HOME`/
    global state (собственно D48) не нарушен ни разу.

**Remaining:**

17/22 items. Фаза P2 item-terminal (5/5), не закрыта формально (нет reconciliation-прохода
`plan-close`) → P3 (5 items) → P4 (3 items).

**Sources of truth:**

`plan.md` v1.14.4 (§3 Routing, §4 Status Board, §6 Update Log) ·
`phases/P2.md` § P2.5 Completion Notes/Known Deviations (факты закрытия) ·
`plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.5/result-manifest.json` ·
`findings/P2.5-scenario-results.md` · `roadmap.md` § P3 · `journal.jsonl`.

**Open risks:**

- **Строка фазы P0 в `plan.md` §4 всё ещё протухла** (унаследовано, не этим item'ом; владелец
  правки — `task:plan-close 2026.07.24-AGENT-RELIABILITY P0`).
- **`packages/task/docs/reference/provider-commands.md` не входит в
  `artifacts/P1.1/remediation-map.json::owners.P2.2.paths`** (унаследовано от P2.2). Владелец
  правки карты — P1.1 (D#).
- **P2.5's dispatch/cold-recovery/per-provider temp-root narrowing (Known Deviations выше)** —
  не пере-открыт как отдельный item; если владелец хочет буквальную механику — новый P2.5-scoped
  follow-up или переиспользовать P3.4 (disposable-worktree canary несёт смежную machinery).
- **`trace-record-missing` — единственный provable residual, владелец P3.1/P3.2.** F1 not-met
  до тех пор.
- **F4/F5 репортятся `deferred` в `result-manifest.json` только по метаданным floor-строки**
  (`evaluate_floors` классифицирует по `baseline_source`, не по факту измерения) — оба уже
  реально закрыты зелёными (P1.4/P0.4); это артефакт `run_bank.py`'s общей логики, не пробел
  этого item'а.
- **`plan-lint`: см. свежий прогон при следующем шаге** (`--baseline HEAD` на item-коммите
  `14b3e6ce`, не пересчитывалось этим handoff — плановый шаг `plan-close` сделает это заново).
- Прежний долг (без изменений этим item'ом): две находки A2 (закрыто по факту исполнения
  P2.2/P2.3); `research/01–03` без ссылок на слой 1; A1 F11; `command.interactive-user-input`
  вне каталога capability; Claude enabled-set `unknown`; Claude-проекция `workflow-craft`;
  расхождение провенанса harness-CLI ↔ maind-адаптера (P0.4).

**Workarounds/Deferred/Open questions:**

- **workarounds:** нет новых этим item'ом.
- **deferred:** протухшая строка фазы P0 в §4; `trace-record-missing` → P3.1/P3.2; F6/F8/F9/F10 →
  P3.3 live layer-2 paired run; буквальная dispatch/cold-recovery/per-provider-root механика
  P2.5 (см. Open risks); исторический A2-долг.
- **open_questions:** нет открытых для владельца — по D50 развилки закрываются записью.
