# HANDOFF — 2026-08-07 — after P0.2

**Next:** `/task:plan-design 2026.08.07-PLAN-ECONOMY P0.2`

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | — |
| Context | NEW SESSION — шаг-не-item |
| Суть | P0.2 эскалирован (🔴 Blocked): зонд лимита одного чтения в ЭТОЙ среде даёт отказ Read-инструмента в БАЙТАХ/КБ («File content (313.6KB) exceeds maximum allowed size (256KB)»), а не в токенах, как специфицируют Inputs item'а (`research/02-…` §4, `findings/00-…` §7 — токенный формат «59596 tokens / 25000»). Owner-решение нужно о единице `read-limit` (байты/токены/обе) и о последствии для D2(б) и формы артефакта |
| Команда | `/task:plan-design 2026.08.07-PLAN-ECONOMY P0.2` |

**Done:** Design (4/4 прогона, `plan-audit design` GREEN-путём, владелец принял старт exec) —
см. предыдущий handoff в истории git. **P0.1 закрыт `🟠 Done with deviations`**
(`task:plan-run`, sonnet/high, item-коммит `5d29d42e`): `token_estimate.py` + калибровочный
харнесс + артефакт `token-estimate-calibration.json` (14/14 файлов приняты, `bound.violations=0`,
p95=1.17) + probe-log + 15 unit-тестов + строка `CHANGELOG.md`. Известное отклонение: item-коммит
несёт `CHANGELOG.md` вне `Files` (spec-gap Files↔Deliverables) → `🟠`.

**P0.2 эскалирован `🔴 Blocked`** (`task:plan-exec`, sonnet/medium, без item-коммита — работа
не производила deliverables): зонд выполнен дважды на реально превышающих файлах
(`plans/2026.08.03-ARTIFEX-SUPERVISOR/plan.md` 321084 байт, `plans/2026.08.07-PLAN-ECONOMY/plan.md`
299.6KB) — оба раза Read-инструмент отказал текстом
`File content (<N>KB) exceeds maximum allowed size (256KB). Use offset and limit parameters…`.
Формат байтовый (размер файла на диске), не токенный, как ожидали Inputs item'а. Code Guidance
item'а прямо запрещает подгонять байтовое число под предписанное поле `limit_tokens` — зафиксировано
дословно и эскалировано, артефакт `read-limit.json` не создан.

**Remaining:** P0.2 (design-решение о единице лимита), затем P0.3–P0.5 (P0.3 зависит от формы
артефакта P0.2 — Inputs P0.3 читает `read-limit.json`), затем P1–P6 по `roadmap.md`.

**Sources of truth:** `plan.md` (Meta, Context, Execution Rules, `## 3. Routing`, Status Board —
P0 0/5, D1–D106, `## 7. Contracts`, `## Обсуждение`) · `phases/P0.md`–`phases/P6.md` (P0.2 несёт
эскалационный blockquote и Completion Notes с дословным текстом обоих отказов) · `roadmap.md` ·
`research/00`–`research/11` (`research/02-…` §4 — предпосылка, разошедшаяся с наблюдением) ·
`findings/00`–`03`, `05`, `08`–`11`, `13`, `14` (`findings/00-…` §7 — прежнее наблюдение, другой
формат) · `journal.jsonl` (последняя запись — P0.2 `escalated`) ·
`packages/task/configs/token-estimate-calibration.json` (SSOT ставок токен-оценщика, P0.1).

**Open risks:**
- **НОВОЕ (P0.2): формат отказа Read-инструмента в ЭТОЙ среде — байты/КБ размера файла, а не
  токены модели.** `research/02-p0-measurement-design.md` §4 и `findings/00-plan-read-weight-2026-08-07.md`
  §7 специфицировали и наблюдали токенный отказ (`59596 tokens / 25000`); зонд ЭТОЙ сессии дважды
  воспроизвёл байтовый отказ (`313.6KB / 256KB` на `plans/2026.08.03-ARTIFEX-SUPERVISOR/plan.md`;
  `299.6KB / 256KB` на собственном `plan.md`). Байтовый лимит файла на диске и токенный лимит модели
  НЕ конвертируются фиксированным коэффициентом (UTF-8: кириллица/эмодзи — несколько байт на символ,
  переменное число токенов на символ) — риск того, что калибровка P0.1 (токен-оценщик) отвечает не на
  тот вопрос, который реально задаёт гейт чтения этой среды. Требует owner-решения (`plan-design
  P0.2`): единица `read-limit` (байты / токены / обе отдельными полями) и последствие для D2(б).
- **Ставка класса `other` (эмодзи/псевдографика/CJK) = 0.0 в замороженном артефакте калибровки P0.1** —
  без изменений от предыдущего handoff (диагностировано, не подгонка; риск на файлах вне корпуса
  с непропорционально высокой долей `other`).
- **Пре-существующий дефект среды:** `plans/.claude/` и `plans/__pycache__/` ошибочно распознаются
  `plan_lint.py` как каталоги планов → 4 ERROR полного `validate.sh`; вне Scope P0.1/P0.2, чинится в
  owning-источнике.
- Прежние риски без изменений: список потребителей раскладки не исчерпан (P2.1); долг бампа
  `driver-plan-protocol-v2`; гейт веса канона `SKILL.md`; `review_policy.py` единственная поведенческая
  правка P2.1; P2.1 — самый тяжёлый item; числа P0.3–P0.5 ещё не измерены (и теперь зависят от
  design-решения P0.2); `phases/P6.md` — самый тяжёлый файл плана; приёмка P6.8 самохостящаяся;
  P6.5 удаляет 230 RU-источников; пересечение с `2026.08.02-PROVIDER-CONTRACT-LOCALE`; enum `Next`
  не покрывает `finish`/`roadmap` до P6.5; D43/D58/D71 честно ослабили доказательную опору; правки
  последних заходов не проходили независимого design-ревью; дефект среды
  `.swissknife/analyst/**/*.ndjson` вне `.gitignore`.

**Workarounds/Deferred/Open questions:**
- Workarounds: нет.
- Deferred: без изменений от предыдущего handoff (миграция флота D3, компактификация EN-канонов,
  `artifex` compiler правка, бамп `driver-plan-protocol-v2`, реестр носителей раскладки, `count_tokens`
  как альтернативный источник калибровки, запрет ссылки на соседний пункт, кластер «шов без субъекта»,
  N-судейская свёртка, экономика прогона среза, прозаические сокращения путей).
- Open questions: **новый** — единица измерения `read-limit` (байты vs токены) в этой среде, см.
  Open risks выше; маршрутизируется в `plan-design P0.2`.
