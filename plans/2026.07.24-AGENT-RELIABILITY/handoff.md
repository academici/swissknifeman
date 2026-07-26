# HANDOFF — 2026-07-26 — after P3.10

**Next:** ЗАПУСК ВРУЧНУЮ: frontier/xhigh (Exec = manual, `plan-exec` пинит sonnet/medium ниже предписанного и обязан отклонить этот item по гейту п. 2)

| Параметр | Значение |
|:--|:--|
| Model class | `frontier` |
| Effort | `xhigh` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `opus` (Claude) или `gpt-5.6-sol` (Codex) — по §3 Routing через checked mapping |
| Thinking | `xhigh` — терминальный вердикт фазы после ремедиации, заход 2/2 из бюджета, самосертификация запрещена |
| Context | `NEW SESSION — шаг-не-item` (`plan-audit`-класс — читает план с диска заново) |
| Суть | Свежий frontier/xhigh аудитор пересчитывает ремонт P3.6–P3.10, проверяет честность F1/наблюдаемости/layer-2-знаменателя, выносит GREEN/REMEDIATE/ROLLBACK — заход 2/2, третий по канону становится решением владельца/INCIDENT. |

```
/model opus
/effort xhigh
/task:plan-run 2026.07.24-AGENT-RELIABILITY P3.11
```

**Done:**

- **P3.10 закрыт 🟠 Done with deviations** (item-commit `a84bf171`) — живой парный
  layer-2 прогон на объявленном P3.9 множестве (5/31), **10/10 диспатчей** (5 кейсов
  × 2 дерева — `PRE_PLAN_SHA 7479972f` / HEAD `802a8317`), маршрут `sonnet/high` по
  §3 Routing строки P3.10 (D46), 0 ретраев, суммарная стоимость **$2.052801**.
  - **first_pass_success: baseline 2/5=0.4, candidate 5/5=1.0.** Оба critical-кейса
    честно красны на baseline (`task.task_contract`/`analyst.trace` не существуют на
    pre-plan дереве — доставлены позже P2/P3.1 ЭТИМ же планом) и зелены на candidate
    (реальный `pre_mutation: block:ROUTE_UNDERSHOOT`, реальная trace-запись
    `completeness=1.0`). Один control (`control-predecessor-produced-path`) честно
    красен на baseline не из-за ложного блока, а потому что его вход
    (`artifacts/P0.1/verification-report.json`) произведён item'ом P0.1 ЭТОГО плана и
    физически не существовал на pre-plan дереве.
  - **F6** `trace_completeness` = 1/1 = 1.0 (единственная реально произведённая
    трасса — тонкая выборка, явно помечено). **F8**
    `first_pass_success_delta_vs_paired_baseline` = +0.6 (+60pp) ≥ +30pp. **F9**
    `context_input_per_success_ratio` = 0.4234 ≤ 50% (формула D86 дословно, три
    слагаемых напечатаны раздельно). **F10** `owner_intervention_ratio` = честный
    `unknown` (`owner_question` структурно `unmappable` — D83-ловушка, не измерение).
  - Все четыре несут `scope: declared-subset 5/31` — ни одно НЕ объявлено `met` для
    полной приёмки фазы. **D#-предложение (Вариант A — принять declared-subset как
    финальное измерение / Вариант B — признать терминальную приёмку недостижимой на
    этом инструментальном поколении) — решение за P3.11**, не за этим item'ом
    (`findings/P3.10-layer2-paired.md` § 5).
  - Known Deviations: item-коммит несёт недекларированный
    `artifacts/P3.10/run_layer2_paired.py` (orchestration-скрипт — ТЗ называло только
    выходные артефакты; прецедент P3.4/P3.9 декларирует свой скрипт явно — вероятный
    пропуск черновика, не намеренное ограничение).
  - `git worktree list --porcelain | grep -c 'skm-p3.10'` → **0** (проверено дважды:
    сразу после прогона и повторно на анализе).
- **Items P3.1–P3.9 НЕ реопенены** — продукты пересчитаны P3.5, реконсилированы P3.6.

**Remaining:**

- **P3.11** ⬜ терминальный аудит фазы, **заход 2/2 — последний из бюджета**. Читает
  D#-предложение P3.10 (§5 отчёта) и решает Вариант A/B; пересчитывает честность F1
  (P3.8), дисциплину наблюдаемости (P3.9, `unmappable` не зачтён зелёным),
  declared-subset знаменатель layer-2 (P3.10, не повышен из `unknown`/`deferred`),
  отсутствие worktree-остатков.
- **P4** ⬜ — **не стартует до GREEN**.

**Sources of truth:**

- `findings/P3.10-layer2-paired.md` — полный отчёт захода: методология, разбор по
  кейсам, F6/F8/F9/F10 с провенансом, D#-предложение, границы.
- `artifacts/P3.10/layer2-paired.json` — полный артефакт (dispatch_meta/usage/
  normalized/graded_cases/floors); `artifacts/P3.10/layer2-manifest.json` — сжатая
  версия; `artifacts/P3.10/raw/{baseline,candidate}/<case_id>/` — сохранённое сырьё
  всех 10 диспатчей.
- `phases/P3.md` — `## Phase Status` (11 items), P3.10 Completion Notes/Pending
  Work/Known Deviations, ТЗ P3.11, блок `## Audit P3 — 2026-07-26` (исторический,
  не правится).
- `plan.md` — §0 Meta (v1.20.1), §3 Routing, §4 Status Board (`4/11`), D82–D87, §6.

**Open risks:**

- **GREEN на объявленном множестве 5/31 недостижим без правки контракта приёмки**
  (не снято этим item'ом — решение принимает P3.11, см. D#-предложение выше).
- **F6 на знаменателе 1** — статистически ничтожно; следующий producer, расширяющий
  наблюдаемость карты, обязан пересчитать F6 на бОльшем числе трасс.
- **`contract_ref`/`finding_refs` не заполняются P3.4-харнесом** (находка P3.8) —
  остаток F1; носитель не назван.
- **`verify_result_manifest.py` self-hash re-drift** (D87) — ожидаемо, не новая находка.
- **Остаточный lint вне диффа:** `plan-lint` — 0 ERROR при 1 WARN (строка Update Log
  P1.4, 303 символа при пороге 300), открыт с предыдущих handoff'ов.
- **`analyst`/`harness` package-API minor bumps** и CLI-подключение
  `analyst metrics`/`skiller eval` — долги с P3.1/P3.2/P3.3.
- **P0 phase-index row** (`task:plan-close … P0`) — все items P0 терминальны, строка
  доски остаётся `🟡`; открыто с ранних handoff'ов.
- **Codex-сторона наблюдаемости не пробовалась** (acting provider — Claude, D33/D50) —
  унаследованный долг P3.9/P3.10.

**Workarounds / Deferred / Open questions:**

- **Пустые каталоги-родители одноразовых worktree'ев** (`/tmp/skm-p3.9.rYq0Th` и
  аналогичные из P3.10 — `/tmp/skm-p3.10-*`) могли остаться на диске: `rmdir` жёстко
  запрещён локальным хуком вне `safe-dirs.json`. Регистраций `skm-p3.10` в
  `git worktree list --porcelain` — **0** (проверено дважды); тот же класс остатка,
  что раскрыл P3.4/P3.9.
- **Codex-сторона наблюдаемости не пробовалась** (acting provider — Claude, D33/D50).
  Паритет — предмет `provider_capability_matrix`.
- **`docs-sync` follow-up** (`packages/task/CLAUDE.md`, описание compiler/enforcement
  seam) — долг P3.1, не тронут.
