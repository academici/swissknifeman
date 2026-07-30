# HANDOFF — 2026-07-30 — after P2.1

**Next:** «ЗАПУСК ВРУЧНУЮ: implementation/high»

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | high — §3 Routing строка P2.2 (`implementation/high`, `Exec = manual`, D39/D47: effort выше пина `plan-exec`) |
| Context | continue (/clear) — ручной item под `task:plan-run` |
| Суть | P2.2 — первый КОД паритета: мультиповерхностный диспетчер `.codex/hooks/lifecycle.py` + четыре наблюдателя класса A по вердиктам P2.1, уровни манифеста синхронно |

Перед запуском выставить сессию: `/model sonnet`, затем `/effort high` (команда `task:plan-run`
модель НЕ пинит — Routing-гейт сверяет ФАКТИЧЕСКУЮ модель сессии, недобор = ROUTING-BLOCKED).

````
/task:plan-run 2026.07.29-HARNESS-AGNOSTIC P2.2
````

Если предпочтителен ручной прогон без команды — тот же item по промпту:

````
Исполни item P2.2 плана 2026.07.29-HARNESS-AGNOSTIC вручную (Exec=manual, implementation/high —
сессия sonnet/high; /task:plan-exec пинит sonnet/medium и по Routing-гейту отклонит item).

Порядок чтения (ровно этот, без повторов):
1) plans/2026.07.29-HARNESS-AGNOSTIC/plan.md — §0 Meta, §1 Context, §2 Execution Rules,
   §3 Routing (строка P2.2), §4 Status Board, §5 D86–D89
2) plans/2026.07.29-HARNESS-AGNOSTIC/handoff.md (этот файл)
3) plans/2026.07.29-HARNESS-AGNOSTIC/phases/P2.md — Phase Context + P2.1 Completion Notes
   (вход item'а) + P2.2 целиком
4) Required Reads item'а P2.2 (в указанном там порядке; пункт 1 —
   root/contracts/codex-parity-verdicts-v1.md, читать §1, §2 строки 1–4, §3.1–§3.4, §8)

Дом плана — repo:/home/vostrikov/projects/packages/swissknifeman, но по Execution Rules (§2)
все работы ведутся в worktree swissknifeman-next (ветка next/harness-agnostic) — запускай
сессию именно там.

Перед мутацией и перед закрытием собери Task Contract (task.task_contract.build +
route_evidence.capture_actual("implementation", "high", source="self-attested",
model="sonnet") — actual_route ЭТОЙ сессии) и убедись, что pre_mutation/pre_final = "allow";
красный код — см. таблицу в packages/task/commands/plan-exec.md п.2/п.7.

Исполняй СТРОГО Scope Included P2.2, не трогай Scope Excluded. Уровень манифеста и binding
меняются ОДНИМ коммитом и одним item'ом (иначе HARNESS_CAPABILITY_MANIFEST_INVALID).
Пометь Status: 🟡 In progress до работы, journal.append --result in-progress перед началом.

По завершении: прогони ВСЮ Validation P2.2 построчно, закрой item по топологии plan-protocol
§7 (item-коммит по Files P2.2 → bookkeeping → перезапись handoff.md → plan-lint --baseline
HEAD → bookkeeping-коммит), обнови Status Board/Update Log/Last Updated, append журнал
финал-записи. Строка `Session: <model>/<effort>` в отчёте и Update Log ОБЯЗАТЕЛЬНА (D47).
Отчёт — в формате Expected Output plan-exec, launch-block следующего шага — P2.3.
````

**Что сделано этим заходом (ручной прогон, frontier/high).** P2.1 закрыт `🟢` (item-коммит
`ed306ca6`) — запечатан `root/contracts/codex-parity-verdicts-v1.md` (`status: sealed (P2.1)`,
`version: v1`). По каждой из 17 записей `unsupported` у Codex — ровно один вердикт из закрытого
перечня, названный нативный носитель, требуемая evidence (`scope`/`claim`, `verified_at` ставит
исполняющий item) и черновик `limitations`. Распределение: **12 `closed-by-adapter` · 5
`claude-only` · 0 `intent-withdrawn`**. Проба C3 по всем 17 (`production_requirements()`): 170
строк требований всего, по каждой записи 2 строки, **строгих 0** — то есть `claude-only` был
структурно легален для ВСЕХ 17, и объём закрытия продиктован наличием носителя (анти-подгонка),
а не пробой. Четыре D-записи: **D86** (OQ-6 — дом логики: генерируемый диспетчер, один
генератор, вызов единственного вердикт-ядра `safe-dirs` вместо копии), **D87** (OQ-3 закрыта
измерением ПРОТИВ посылки развилки: обе «нереализованные интенции» реализованы кодом, у
`daemon-safety` есть и установка `apply-permissions.sh:71-73`, и регистрация
`settings.global.json` — класс E снят, обе `closed-by-adapter`), **D88** (премиса
«инвертированная семантика `SubagentStop`» опровергнута first-party обеими сторонами — риск
строки review-gate понижен), **D89** (bounded closure как законная форма `adapted` + пол
интерпретатора `tomllib`/3.11 против матрицы `3.9…3.13`).

**Вердикты по классам (вход P2.2–P2.4):**
- **Класс A → P2.2** (все `closed-by-adapter`): `lifecycle.command-log` (`PreToolUse ^Bash$`) ·
  `lifecycle.run-report` (`SessionEnd`; транскрипт НЕ парсится — формат Codex `[UNVERIFIED]`) ·
  `lifecycle.router` (`UserPromptSubmit`, поле `prompt`) · `lifecycle.memory` (`SessionStart`;
  проверка «старый контур цел» обязательна — состояние остаётся за skiller в `~/.swissknifeman`).
- **Класс B → P2.3** (все `closed-by-adapter`): `lifecycle.pack-guard` (`PreToolUse
  ^apply_patch$`; лок читается уже существующий, зависимости от P2.4 нет) ·
  `lifecycle.changelog-gate` (`PreToolUse ^Bash$`) · `lifecycle.review-gate` (`SubagentStop` —
  ПРЯМАЯ проекция по D88) · `security.safe-dirs` (`PreToolUse` + вызов единственного ядра;
  половина `sandbox_workspace_write` отклонена с причиной — ось песочницы принадлежит
  `lifecycle.auto-approval`) · `lifecycle.daemon-safety` (обе половины) ·
  `lifecycle.git-guardrails` (Codex-половина; Claude-половина — честная причина при
  `unsupported`).
- **Класс C/D → P2.4**: `settings.audit` и `agent-packs.lifecycle` — `closed-by-adapter` в
  НАЗВАННОЙ границе (D89); `lifecycle.notification`, `workflows.status`,
  `analytics.legacy-migration`, `context.output-style`, `context.plans-directory` —
  `claude-only` с причинным классом («носитель вне проектного скоупа» · «объекта отчёта у Codex
  нет» · «интенция неприменима» · «носителя нет» ×2).

**Session:** Claude Opus 5/high (frontier/high, `Exec = manual` — совпадает с §3 Routing строкой
P2.1; перебора/недобора нет).

**Done:** P0 целиком (5/5 терминальны) · P1 целиком (7/7 терминальны: P1.1/P1.4/P1.6/P1.7 `🟢`,
P1.2/P1.3/P1.5 `🟠`) · аудит фазы P1 пройден дважды · блок follow-up P2.6–P2.9 исчерпан
(P2.6/P2.7/P2.8 `🟢`, P2.9 `🟠`) · **P2.1 `🟢` — контракт вердиктов запечатан, обе развилки фазы
(OQ-3, OQ-6) закрыты, ни одной записи `unsupported` без вердикта.**

**Карта «item → коммит» (P1–P2; item-коммит | сопутствующие bookkeeping):**
P1.1 `fd5183af` | `340d0846` · P1.2 `e574fdda` | `d1e393af` · P1.3 `b02e48be` | `4ae56350`
(bookkeeping), `5996d92d` (дозапись журнала), `b191a19c` (Known Deviations) · P1.4 `1e0262a4` |
`d5482b37` · P1.5 `c3b3a8a3` (принятие) + `4647ad4b` (гейт) | `d052698f` · P1.6 `d5e01ef7`
(канон+рендер) + `eb64ea6c` (гейт покрытия) | `4416322e` · P1.7 `003180bf` | `a8abbf9e`,
`7d4f12b7` · P2.6 `317622c0` + `23c1090c` (item-коммит) · P2.7 `e16082a1` · P2.8 `a264a339` ·
P2.9 `ffda7173` · **P2.1 `ed306ca6` (контракт вердиктов, item-коммит)**.

**Remaining:** паритет P2.2–P2.5 (4) → P3 (6) → P4 (5) → P5 (3). Итого **18 из 35** items плана
ещё не исполнено.

**Sources of truth:** `root/contracts/codex-parity-verdicts-v1.md` (**sealed v1** — вход
P2.2–P2.5: §1 дом логики, §2 таблица 17 вердиктов, §3 evidence и `limitations` построчно, §4
OQ-3, §5 опровергнутая премиса, §6 bounded closure, §7 самопроверка 15/15, §8 hand-off по
items) · `root/contracts/provider-parity-definition.md` (**sealed v1**, планка вердикта) ·
`plan.md` (§3 Routing — девять строк фазы P2, §5 D1–D89, §6 Update Log с картой хешей, §7
Contracts — обе строки Exported теперь `sealed`, §4 Status Board — P2 `4/9 🟡`) ·
`phases/P2.md` (P2.1 Completion Notes — прогоны и числа; P2.2–P2.5 ТЗ) ·
`findings/03-rag-codex-capability-surfaces-2026-07-29.md` (Ф9/Ф10/Ф11/Ф12 — first-party
поверхности Codex) · `research/06-codex-parity-triage-groundwork.md` (кандидатная карта; классы
E двух записей ОТМЕНЕНЫ D87) · `configs/provider-capabilities.json` (17 записей, contract/catalog
`1.0.0`) · `roadmap.md` (v0.10.0, 35 items) · `journal.jsonl`.

**Open risks:**
- **Проза P2.3 несёт опровергнутую премису** («семантика `block` у `Stop`/`SubagentStop`
  инвертирована относительно Claude» — `Why` + Implementation Rules): отменена D88, текст НЕ
  правился (вне `Files` P2.1). Исполнитель P2.3 обязан читать §5 и строку 7 контракта вердиктов
  как приоритетный носитель. Тот же режим у класса E двух записей в `research/06` §1 (отменён
  D87).
- **Три долга, созданные триажем, дома НЕ получили** (`Files` P2.1 — один файл): замер формата
  транскрипта Codex (снял бы ограничение `run-report`; требует живого прогона — против D3) ·
  opt-in операторский флаг для Claude-половины `git-guardrails` · проекция `writable_roots` из
  того же allowlist'а как аддитивная правка `lifecycle.auto-approval`. Дом всех трёх —
  `roadmap/`, заведение — отдельный item либо заход `plan-design`.
- **Объём P2.4:** два bounded-closure ряда (`settings.audit`, `agent-packs.lifecycle`) —
  крупнейшая работа фазы, и оба падают на P2.4 вместе с пятью текстовыми рядами. Не несёт одним
  item'ом → разбиение через `plan-design`, а НЕ понижение вердикта до `claude-only` (D89 п.1).
- **Пол интерпретатора:** `tomllib` — stdlib с Python 3.11, матрица CI — `3.9…3.13`
  (`.github/workflows/test.yml:15`). Codex-аудитор слоёв читает содержимое только на 3.11+, иначе
  рапортует слой нечитаемым; свой парсер TOML и бамп пола — вне фазы (D89 п.2).
- **`plan-lint` WARN нового рода на `phases/P2.md`** (surfaced P2.6, сохраняется): DoR-чеклист
  фазы цитирует синтаксис маркера уточнения дословно в двух пунктах, и при статусе фазы вне
  `⬜ Not started` линтер читает цитату как открытый маркер. WARN, не ERROR — гейт `K=0` не
  задет; правка — кандидат ближайшего design-захода.
- **Фраза-находка A7 осталась в двух местах `phases/P1.md`** вне `Files` P2.9 (историческая цитата
  аудита захода 2 + архивный launch-block) — Known Deviation P2.9.
- **Посторонний незакоммиченный дифф в дереве не убран и не тронут:** `roadmap/README.md` (M) +
  untracked `roadmap/2026.07.29-launch-block-command-row.md`. Живучесть подтверждена четвёртый
  заход подряд — не наш предмет.
- **Слепота `_validate_conflicts` к дублю СМЫСЛА** (`instructions.py:1005-1022`): зелёный
  `validate_catalog()` НЕ доказывает отсутствия дубля common-правила внутри provider-extension.
  Дом правки — `roadmap/`, спека НЕ заведена.
- **Фикстурный `provenance` СОВМЕСТИМОСТИ не отражает миграцию P1.2** — нужен отдельный item со
  строкой `packages/harness/tests/test_instruction_compatibility.py` в `Files`; не заведён.
- **Order-sensitivity `apply_instructions` к порядку `--authorize` и неинформативная диагностика
  `INSTRUCTION_WRITE_FORBIDDEN` не починены** — дом заведён P2.8
  (`roadmap/instruction-authorize-order.md`), реализация отложена по критерию (D84).
- **Двенадцать корневых и пакетных руководств УПРАВЛЯЕМЫЕ**: ручная правка блоков между
  маркерами запрещена навсегда — только фрагменты + повторный прогон, иначе `managed-drift`.
- **Гейт `[9/9]` живёт только в `packages/harness/scripts/validate.sh`** — `analyst`/`task` в CI
  не покрыты (OQ-9); локальный прогон ≠ CI (R2).
- **`packages/skiller/scripts/validate.sh` на дереве КРАСНЫЙ** (долг P0.5, material-отклонение
  P1.5); `scripts/test-provider-docs.py` и `scripts/public-hygiene.py` — предсуществующе красные
  (первый — из-за битой ссылки `roadmap/self-learning-memory.md` в `README.md`, известное
  состояние по `provider-parity-definition` §6.3, не регрессия items P2.x).
- **`vitepress build` в дереве не прогоняется** — `node_modules` отсутствуют.
- **Аудит design-фазы исчерпан** — дефект в ТЗ P2.2–P2.5 и P3–P5 всплывёт на исполнении.
- **Маршруты мягче:** items с `effort high` идут через `plan-run` (D47) — строка
  `Session: <model>/<effort>` в отчёте и Update Log обязательна.
- Общий state `~/.swissknifeman`/`~/.maind` изоляцией не покрыт — риск принят владельцем (D4).
- **P5.2 — единственная необратимая внутрь граница плана** (R1).
- Портируемость (`plan-portability-v1.md`): host-специфичные пути запрещены в
  `Inputs`/`Required Reads`/`Validation` — действует на P5.1–P5.3.

**Workarounds/Deferred/Open questions:**
- workarounds: правка общего `plans/verify-citations-known-exceptions.json` (D54) — дом
  design-коммит, не `Files` какого-либо item'а.
- deferred: замер формата транскрипта Codex · opt-in флаг Claude-половины `git-guardrails` ·
  проекция `writable_roots` из allowlist'а · правка `_validate_conflicts`/схемы `obligations` ·
  починка order-sensitivity `apply_instructions` (дом заведён P2.8) · фикстурный `provenance`
  P1.2 · изоляция общего state (OQ-5) · тонкая обвязка супервизора (P4.1, D38) · round-trip гейт
  живым прогоном Codex (D3) · структурный перебор листинга Codex (OQ-7) · общий differ канона
  ролей (OQ-8) · машинные гейты PROMOTE-CANDIDATE · `skiller registry` не прогнан (P0.5) ·
  раскатка на потребителей (D45) · push/PR/тег и публикация доков (D41) · расширение CI на
  `analyst`/`task` (OQ-9) · русский канон скиллов в `.gitignore` (Р5) · раскатка adoption-режима ·
  удаление pre-image'ов P1.5 · починка архивных упоминаний A7 в `phases/P1.md`. **Снято из
  deferred:** ничего (P2.1 долгов не закрывал — он их назвал).
- open_questions: OQ-7 структурный перебор бюджета обнаружения (P3.4) · OQ-8 дрейф канона ролей
  (Deferred) · OQ-9 CI не покрывает `analyst`/`task` (Deferred). **OQ-3 закрыта D87, OQ-6 закрыта
  D86** (обе — этим заходом); OQ-2 закрыта D71, OQ-1 — D31, OQ-4 — D27. Новых открытых вопросов
  триаж не добавил: все развилки разбора закрыты D86–D89 по режиму Р6/D14.
