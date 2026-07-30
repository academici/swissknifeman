# Artifex — тонкая обвязка исполнения планов (остаток супервизор-трека)

**Статус:** ⬜ отложено, критерий не сработал
**Дата:** 2026-07-30
**Провенанс:** `plans/archive/2026.07.18-FOREMAN/` (план-донор, терминален `🟠` 2026-07-29:
фаза P1 частично сдана кодом, фазы P2–P7 `⛔ Skipped by decision`) · вердикт пере-скоупа —
`plans/archive/2026.07.29-HARNESS-AGNOSTIC/root/executor-layer-rescope-v1.md` (item P4.1, D38/D90).

## Суть

Внешний CLI-драйвер, который гоняет items плана свежими headless-сессиями и не принимает
содержательных решений сам: очередь items из Status Board → запуск воркера (`claude -p` /
`codex exec`) → дефенсивный parse отчёта → переход по ЧУЖОЙ машине решений
(`execution-state-machine-v1`) → запись в run-folder и пер-плановый журнал → эскалация владельцу
на границе.

Остаток, у которого нет дома в живом дереве (14 items донора, `executor-layer-rescope-v1.md` §3):

1. **Каркас пакета** `packages/artifex/` по раскладке `packages/skiller/` (донор P2.1).
2. **Ядро цикла**: `plan_reader` (Status Board + `handoff.md` `**Next:**`), `worker` (запуск
   воркера под таймаутом, дефенсивный JSON-parse) (P2.2)
   (предусловие — переиздание parse-подмножества, см. §Ограничения).
3. **State + retry-лестница** tier1 transport / tier2 semantic / tier3 quota (P2.3).
4. **Run-folder**: `state.json` (атомарная запись), событийный `journal.jsonl`, resume-by-folder,
   crash recovery (P2.4; парный sealed-контракт донора `root/contracts/artifex-run-folder.md`).
5. **Unattended-профиль**: pattern-scoped allowlist и маппинг «тип запуска → `--permission-mode`»
   поверх готовых `settings.yolo.json` / `policy/max-permissive.json` (P3.1).
6. **Поведенческий канон супервизора** сверх `plan-protocol`: критерии «остановиться самому»,
   дисциплина машиночитаемого отчёта (P3.3 — половина предмета уже канон, см. §Ограничения).
7. **Каналы эскалации** в мессенджеры (канал-агностик слой + envelope) и эскалация драйвера
   ATTENTION/RED с паузой очереди (P4.1/P4.2 донора); **опционально** — remote-approve и
   блокирующий Q&A (P4.3 донора).
8. **Репортинг итогов прогона** в память mAInd поверх `packages/maind/lib/maind/memory.py`
   (P4.4 донора).
9. **Раскатка** как agent-pack `artifex` поверх живого `harness agent-packs` + документация
   пакета (P6.1/P6.2).
10. **Боевой unattended-пилот** — приёмка, а не первый шаг (P6.3).

Отменено по существу и в остаток НЕ входит: собственный прогресс-движок, решающая логика
continue/point-fix/escalate, rulebook правил прогресса, отдельный лог решений (фаза P5 донора,
его D49) и стратегический канон Brain (фаза P7 донора — объект вне репозитория).

## Зачем

Болевой кейс донора: длинная exec-волна плана требует ручного запуска каждого item'а и ручного
разбора «дошло / упало / уперлось в квоту». Обвязка снимает ритуал, не отнимая решений: решения
принадлежат замороженным контрактам `2026.07.24-AGENT-RELIABILITY`, а плану — его протокол
закрытия (два коммита, переписанный handoff, атрибутированный `plan-lint`).

## Ограничения

- **Несущая зависимость `decide` НЕ является живой.** Функция
  `decide(state, event, payload, profile)` заморожена спекой
  (`plans/archive/2026.07.24-AGENT-RELIABILITY/root/contracts/execution-state-machine-v1.md`
  § The decision function), но в дереве существует только как ДАННЫЕ:
  `artifacts/P2.1/state-transition-cases.json` (89 207 B, 135 ячеек) + валидатор тотальности
  `validate_state_cases.py` (34 637 B) — оба ВНУТРИ архива плана, на `dde9382a`. **Предусловие
  остатка:** внесение машины решений в живой пакет — отдельная работа с собственным владельцем;
  до неё «обвязка потребляет `decide`» — фигура речи, а не адрес.
- **Приёмка AR формально не выполнена** (его D88/D89, долги — D92). Четыре поимённых
  `[UNVERIFIED]` — `contract_ref`/`finding_refs` не заполняются (`F1 = 0.96`), знаменатель
  наблюдаемости 5/31, канала `owner_question` нет (`F10 = unknown`), Codex-сторона не пробовалась.
  Перечень с адресами — `executor-layer-rescope-v1.md` §4; строитель обязан прочитать его ДО
  проектирования, а не после.
- **Половина поведенческого канона уже сдана** каноном `plan-protocol` (§6 статусы, §8
  handoff/эскалация) и friction-маркерами `packages/task/lib/task/journal.py`: обвязке нужны
  только супервизорные директивы СВЕРХ него — второй носитель канона запрещён.
- **Носитель философии отменён.** `.artifex/policy.toml` (sealed-контракт донора
  `artifex-policy-schema.md`) отменён как «не тот субъект»: политика ПРОГОНА per-project ≠ флотский
  канон политики спавна. Флотская схема запечатывается заново фазой P4 плана
  `2026.07.29-HARNESS-AGNOSTIC` (P4.2/P4.3, дом данных
  `packages/harness/configs/common/agent-packs/`) — обвязка её ПОТРЕБЛЯЕТ, а не заводит свою.
- **PreToolUse-политика уже живая** (`packages/harness/configs/claude-code/hooks/auto-approve/`:
  декларативный `config.json`, три режима, per-project override). Второй хук того же класса не
  заводится — обвязка настраивает существующий.
- **Каналы мессенджеров с нуля**: живой notify-хук умеет только локальный десктоп
  (`notify-send`/`osascript`), Telegram/MAX в дереве отсутствуют.
- **Квота и биллинг**: пилот донора упирался в исчерпание учёток; экономика прогона — часть
  приёмки, а не следствие.
- **Parse-контракт донора историчен — переиздание подмножества обязательно.**
  `plans/archive/2026.07.18-FOREMAN/root/contracts/driver-plan-protocol.md` запинен на
  `plan-protocol` v2.8.0 @ `2cf26e8`, живой канон на 2026-07-30 — v2.21.0; якорь 3 §4 (enum форм
  `Next`) сломан переходом канона на провайдер-нейтральные семантические формы (замер —
  `plans/archive/2026.07.29-HARNESS-AGNOSTIC/research/03-foreman-absorption-inventory.md` §3, решение —
  его D93). Документ оставлен ИСТОРИЧЕСКИМ и как спека парсера не используется.
  **Предусловие п. 2 «Ядро цикла»:** до первой строки `plan_reader` parse-подмножество
  переиздаётся против канона ТОГО дня — пин на КОММИТ, не на «latest», — и закрывается не
  измеренный вопрос «чем парсится прогон Codex» (§2 контракта знает только `claude -p`).

## Критерий внедрения

Внедрять по факту измеренной проблемы, а не «на вырост». Достаточно ЛЮБОГО из трёх — каждый
проверяем событием или числом:

1. **Замер ручного ритуала**: ≥ 20 закрытий items подряд в журналах `plans/*/journal.jsonl`,
   где каждое требовало ручного запуска, И доля прогонов, потребовавших вмешательства владельца
   между items, ниже 25 % (то есть 3 из 4 запусков были механическим ритуалом).
   Проверка — `analyst`/`grep` по журналам, число печатается в спеку.
2. **Машина решений стала живой**: `decide` (или его эквивалент по замороженной спеке) существует
   импортируемым модулем в `packages/**` — тогда снята несущая зависимость, и обвязка
   действительно «тонкая».
3. **Решение владельца по экономике**: измеренная стоимость exec-волны из журнала (`cost_usd`)
   против стоимости Workflow-марафона показывает выигрыш ≥ 2× на сопоставимой фазе — тогда
   обвязка окупается прогоном, а не надеждой.

Пока ни один не сработал (2026-07-30): машина решений — данные в архиве, ручной ритуал не
замерен числом, экономика не сравнивалась.

## Связи

- `plans/archive/2026.07.29-HARNESS-AGNOSTIC/root/executor-layer-rescope-v1.md` — вердикт по 24 items
  донора, замер входа, поимённые `[UNVERIFIED]`, граница «строим / не строим».
- `plans/archive/2026.07.18-FOREMAN/` — провенанс: `phases/P2.md`–`phases/P7.md` (тексты дизайна
  сохранены как история), `root/contracts/{artifex-run-folder,driver-plan-protocol}.md`,
  `research/01-p2-driver-architecture.md`, `findings/headless-*`, `findings/perplexity-supervisor-*`,
  `findings/perplexity-telegram-hooks-*`, `findings/perplexity-max-messenger-channels-*`.
- `plans/archive/2026.07.24-AGENT-RELIABILITY/root/contracts/` — `execution-state-machine-v1.md`,
  `risk-review-loop-budget-v1.md` (§ Authority profiles: `owner-gated` / `self-host`),
  `unified-agent-trace-v1.md`, `reliability-acceptance-v1.md`.
- `roadmap/codex-subagent-offload.md` — второй водитель (Codex CLI напрямую): обвязка обязана
  запускать воркера обоих провайдеров, а не только `claude -p`.
- Живые механизмы, которые обвязка ПЕРЕИСПОЛЬЗУЕТ, а не строит: `harness agent-packs`
  (`packages/harness/lib/harness/agentpacks.py`), auto-approve хук, `run-report/_usage.py`,
  `packages/task/lib/task/journal.py`, `packages/maind/lib/maind/memory.py`.
