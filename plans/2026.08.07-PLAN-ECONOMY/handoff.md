# HANDOFF — 2026-08-07 — after P0.1

**Next:** run-item: task:plan-exec 2026.08.07-PLAN-ECONOMY P0.2

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | medium |
| Capabilities | — |
| Context | continue (/clear) — ручной item |
| Суть | P0.1 закрыт (🟠, калибровка + артефакт заморожены). P0.2 — независимый solo item того же батча: измерить лимит одного чтения инструментом среды как параметр (не литерал). `Exec = plan-exec`, пин команды (sonnet/medium) удовлетворяет Routing без перебора |
| Команда | `/task:plan-exec 2026.08.07-PLAN-ECONOMY P0.2` |

**Done:** Design (4/4 прогона, `plan-audit design` GREEN-путём через ATTENTION+узкий finish, AUDIT-CAP исчерпан, владелец принял старт exec) — см. предыдущий handoff в истории git. **P0.1 закрыт `🟠 Done with deviations`** (`task:plan-run`, sonnet/high, item-коммит `5d29d42e`): `packages/task/lib/task/token_estimate.py` (оценщик СВЕРХУ, D14) + `packages/task/scripts/calibrate-token-estimate.py` (дифференциальный харнесс, D92) + артефакт `packages/task/configs/token-estimate-calibration.json` (14/14 файлов реального корпуса флота приняты, 0 отбраковок дрейфа, `bound.violations=0`, рыхлость p95=1.17 при гейте ≤1.6, `tokenizer.model_id=claude-sonnet-5`) + `plans/2026.08.07-PLAN-ECONOMY/artifacts/P0/calibration-probe-log.json` + 15 unit-тестов (все зелёные) + строка `CHANGELOG.md`. Диагностированная (не подгонянная) находка: ставка класса `other` сошлась к 0.0 на этом корпусе — см. Completion Notes P0.1 для полного разбора. Отклонение: item-коммит несёт `CHANGELOG.md` вне списка `Files` (Deliverables требовали строку в нём, Files её не перечисляли — spec-gap, не решение исполнителя) → `🟠`.

**Remaining:** P0.2–P0.5 (P0 сейчас 0/5 — P0.1 закрыт `🟠`, счётчик Status Board считает только `🟢`), затем P1–P6 по `roadmap.md`. P0.3→P0.4→P0.5 строго последовательны; P0.2 независим от P0.1 (оба solo этого батча).

**Sources of truth:** `plan.md` (Meta, Context, Execution Rules, `## 3. Routing` по 45 items, Status Board — P0 0/5, D1–D106, `## 7. Contracts`, `## Обсуждение`) · `phases/P0.md`–`phases/P6.md` · `roadmap.md` · `research/00`–`research/11` · `findings/00`–`findings/03`, `05`, `08`–`11`, `13`, `14` · `brief/00-brief.md`, `brief/01-refinements.md` · `journal.jsonl` (последняя запись — P0.1 `closed-deviations`) · `packages/task/configs/token-estimate-calibration.json` (новый SSOT ставок токен-оценщика) · `plans/2026.08.07-PLAN-ECONOMY/artifacts/P0/calibration-probe-log.json` (сырые пробы калибровки).

**Open risks:**
- **Ставка класса `other` (эмодзи/псевдографика/CJK) = 0.0 в замороженном артефакте калибровки.** Диагностировано двумя независимыми методами (совместная NNLS и residual-фит) — не подгонка, статистический предел ЭТОГО корпуса (счётчик `other` мал и коррелирован с `cyrillic`/`ascii_other`). `bound.violations=0` на калибровочном корпусе подтверждён; риск — файл ВНЕ корпуса с непропорционально высокой долей `other` относительно виденного (11–559 символов/файл в калибровке) может недооцениваться сильнее, чем предполагает `safety_multiplier`. Если P0.4 (замер по всему флоту) найдёт такой файл — это сигнал для P0.5 (заморозка порога) или повторной калибровки, не немедленный блокер.
- **Пре-существующий дефект среды (НЕ создан этим item'ом, вне Scope P0.1):** `plans/.claude/` и `plans/__pycache__/` (untracked/gitignored, датированы 2026-08-05/06 — до старта плана) ошибочно распознаются `plan_lint.py` как каталоги планов → 4 ERROR полного `packages/task/scripts/validate.sh`. Не входит в диф P0.1 (`K=0` по `--baseline HEAD`, см. Lint ниже); чинится в owning-источнике (`.gitignore`/раскладка `plans/`), не `token_estimate`.
- Прежние риски (перенос якоря D92 частично снят фактом успешной калибровки; остальные — без изменений): список потребителей раскладки не исчерпан (P2.1); долг бампа `driver-plan-protocol-v2` (после P6.5); гейт веса канона `SKILL.md` 91 329 байт (P6.5); `review_policy.py` единственная поведенческая правка P2.1; P2.1 — девять модулей, самый тяжёлый item; числа P0.2–P0.5 ещё не измерены; `phases/P6.md` — самый тяжёлый файл плана (см. историю); приёмка P6.8 самохостящаяся; P6.5 удаляет 230 RU-источников; пересечение с `2026.08.02-PROVIDER-CONTRACT-LOCALE`; enum `Next` не покрывает `finish`/`roadmap` до P6.5; D43/D58/D71 честно ослабили доказательную опору; правки последних заходов не проходили независимого design-ревью (первый контроль — само исполнение); дефект среды `.swissknife/analyst/**/*.ndjson` вне `.gitignore`.

**Workarounds/Deferred/Open questions:**
- Workarounds: нет.
- Deferred: без изменений от предыдущего handoff (миграция флота D3, компактификация EN-канонов, `artifex` compiler правка, бамп `driver-plan-protocol-v2`, реестр носителей раскладки, `count_tokens` как альтернативный источник калибровки для обладателя ключа Console, запрет ссылки на соседний пункт, кластер «шов без субъекта», N-судейская свёртка, экономика прогона среза, прозаические сокращения путей).
- Open questions: нет.
