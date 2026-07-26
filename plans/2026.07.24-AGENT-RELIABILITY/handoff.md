# HANDOFF — 2026-07-26 — after P3

**Next:** design: task:plan-design 2026.07.24-AGENT-RELIABILITY P4

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — переопределение входного гейта фазы по названному D88-долгу, не открытое проектирование |
| Context | NEW SESSION — шаг-не-item |
| Суть | Переопределить входной гейт P4 («не стартует до GREEN», D81) по D88: measured-scope Owner packet ЛИБО объявление плана терминальным на 🟠. Items фазы P4 не создавать без этого решения. |

```
/task:plan-design 2026.07.24-AGENT-RELIABILITY P4
```

**Done:**

- **Фаза P3 закрыта 🟠 Done with deviations** (`plans/2026.07.24-AGENT-RELIABILITY/phases/P3.md`,
  `## Phase Handoff`) — **5/11 items 🟢** (P3.2, P3.4, P3.5, P3.9, P3.11), **6/11 🟠** (P3.1, P3.3,
  P3.6, P3.7, P3.8, P3.10). Audit cap фазы исчерпан (2/2, `risk-review-loop-budget-v1.md` §
  Loop budget) — названный долг **D88**: полная терминальная приёмка `reliability-acceptance-v1.md`
  недостижима на этом инструментальном поколении.
  - Доказано: Unified Agent Trace v1, paired reliability metrics/digest, behavioral eval-адаптер
    (byte-identical кросс-сверка), шесть self-host канареечных кейсов в disposable worktree,
    харнес живого диспатча с измеренным множеством наблюдаемых кейсов (5/31 mappable), парный
    живой layer-2 прогон (F6=1.0, F8=+0.6, F9=0.4234), два независимых terminal-аудита.
  - НЕ доказано: F1=0.96 (не 1.0, единственный остаточный critical), F10=`unknown` (канала
    `owner_question` нет вовсе), 26/31 кейсов банка структурно `unmappable`.
  - Docs-sync: не требуется (items правили только `plans/**`/`packages/{analyst,harness,skiller}`
    lib/tests, без нового процесса/фичи для `docs/` корня проекта).
- **Items P3.1–P3.11 не реопенены** — записи сверены по git-фактам, статусы items не менялись
  этим закрытием (уже несли финальные значения из P3.6/P3.11).

**Remaining:**

- **Гейт P4** — «не стартует до GREEN» (D81) не удовлетворим на этом инструментальном поколении
  (D88 п.5). Нужен отдельный заход `plan-design … P4`: переопределить вход как measured-scope
  Owner packet ЛИБО объявить план терминальным на `🟠`. Внутри P3 решения нет.
- **Ремонт находки Ф2** (захода 2, PROMOTE-CANDIDATE) — машинный гейт в
  `packages/task/lib/task/plan_lint.py` («item `🟢`/`🟠`, закрытый после доставки write-site,
  обязан нести оба кода `pre_mutation`/`pre_final` в Completion Notes»); носитель — отдельный
  item ВНЕ фазы P3, не третий проход по записи закрытых items.

**Sources of truth:**

- `phases/P3.md` — `## Phase Status` (11 items, 5/11 🟢), `## Phase Handoff` (переписан этим
  закрытием), оба блока `## Audit P3` (историчны, не правились).
- `plan.md` — §0 Meta (v1.20.3), §4 Status Board (`P3 5/11 · 🟠 Done with deviations`), **D88**
  (§5), §6 Update Log.
- `findings/P3.11-terminal-audit-2.md` — полный отчёт второго захода: находки Ф1–Ф4, классы
  доказательства, решение развилки layer-2.

**Open risks (перенесены из D88 п.6 + находки Ф2/Ф3/Ф4 захода 2, носители названы):**

1. `contract_ref`/`finding_refs` не заполняются харнесами P3.4/P3.9 → остаток F1=0.96. Носитель —
   будущий producer layer-2, вне этого плана.
2. Карта `event-mapping-v1.json` наблюдает 10/20 типов событий и 2/22 outcome-путей → знаменатель
   layer-2 остаётся 5/31. Носитель — расширение наблюдаемости карты, отдельный будущий план/item.
3. F6 на знаменателе 1 — статистически ничтожно. Тот же будущий носитель, что п.1/2.
4. Codex-сторона наблюдаемости не пробовалась (acting provider — Claude, D33/D50). Тот же
   будущий носитель.
5. **Ф2 (PROMOTE-CANDIDATE):** ни один из пяти items P3.6–P3.10 не печатает коды
   `pre_mutation`/`pre_final`, хотя все пять пересчитаны маршрутом исполнителя → `allow`/`allow`.
   Носитель — машинный гейт в `plan_lint.py`, отдельный item вне фазы P3.
6. **Ф3 (Minor/evidence):** `findings/P3.10-layer2-paired.md:29` («единственное различие сторон —
   дерево») неточно — носитель: одна строка формулировки при следующей правке отчёта.
7. **Ф4 (Nit/evidence):** замороженный `bank-manifest.json` называет производителем layer-2
   несуществующий «P3.3 paired run» (факт — P3.9/P3.10, D82). Носитель — только § Correction
   procedure владельца P0.3 (бамп `bank_version`/`grader_version`).
8. **Гейт P4 «не стартует до GREEN» не удовлетворим на этом инструментальном поколении** (D88
   п.5) — носитель: отдельный заход `plan-design … P4`.
- Остаточный lint вне диффа: 0 ERROR при 1 WARN (строка Update Log P1.4, 303 символа при пороге
  300), открыт с предыдущих handoff'ов.
- `analyst`/`harness` package-API minor bumps и CLI-подключение `analyst metrics`/`skiller eval` —
  долги с P3.1/P3.2/P3.3.
- P0 phase-index row (`task:plan-close … P0`) — все items P0 терминальны, строка доски остаётся
  `🟡`; открыто с ранних handoff'ов.

**Workarounds / Deferred / Open questions:**

- Посторонний untracked-каталог `.swissknife/` в рабочем дереве — не тронут этим закрытием.
- F5 `hook_reference_resolution` остаётся `cross-checked` (фикстуры P0.4, вне скоупа
  ремедиации P3.6–P3.10). Rollback-репетиция P3.4 не переигрывалась по той же причине (создала
  бы ровно тот worktree-остаток, который вменяла F6).
- Пустые каталоги-родители одноразовых worktree'ев (`/tmp/skm-p3.9.*`, `/tmp/skm-p3.10-*`) могли
  остаться на диске (`rmdir` запрещён локальным хуком вне `safe-dirs.json`); регистраций в
  `git worktree list --porcelain` — 0 (проверено обоими заходами аудита).
- `docs-sync` follow-up (`packages/task/CLAUDE.md`, описание compiler/enforcement seam) — долг
  P3.1, не тронут.
