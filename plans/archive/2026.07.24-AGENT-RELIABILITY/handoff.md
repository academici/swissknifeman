# HANDOFF — 2026-07-26 — after P4

**Next:** terminal: план закрыт

| Параметр | Значение |
|:--|:--|
| Model class | — |
| Effort | — |
| Capabilities | — |
| Model | — |
| Thinking | — |
| Context | `НОВАЯ сессия` |
| Суть | План `2026.07.24-AGENT-RELIABILITY` закрыт `🟠 Done with deviations` (19/36 items 🟢, пять фаз терминальны). Следующая работа — ДРУГОЙ план: `2026.07.25-ECO-OPT`, НОВОЙ сессией (решение владельца 2026-07-26). Этот план больше не исполняется; архивация — отдельным заходом `close: task:plan-close archive 2026.07.24-AGENT-RELIABILITY`, когда владелец решит |

**Что дальше по экосистеме (решение владельца 2026-07-26).** Очередь D10/D11 подтверждена:
`ECO-OPT` идёт раньше `FOREMAN`. Внутри ECO-OPT предложено вынести вперёд «субстрат
автоматизации» — **P8.3** (`CHECKPOINTED`: отказ с точной командой возобновления), **P8.1**
(отчёт закрытия фазы с классом свидетельства), **P9.1/P9.2** (гейт review-gate с содержанием,
роли ревью как данные): они окупаются сразу даже при ручных carrier-прогонах и являются
контрактной основой для будущего драйвера Artifex. Отдельно: `FOREMAN P1.5` (re-пин контракта
P0.2) разблокирован терминальностью P1/P2 этого плана — дешёвая уборка одним item'ом.

**Долги этого плана без носителя** (обязаны получить его в ECO-OPT P8 либо в новом плане):
дефект точности `_lint_write_site_codes_44` (ложный ERROR на цитате чужих кодов + симметричный
fail-open), дыра гейта `verify_claim_verdicts.py` (символ после `::` не валидируется) и
mis-cite H06, недоказанная закрытость публикации `docs/provider-support.md`
(`scripts/provider-docs.py` падает на пути архивированного плана).

**СОЗНАТЕЛЬНЫЙ ПРОПУСК (назван, не скрыт).** Терминальный `task:plan-audit
2026.07.24-AGENT-RELIABILITY P4` (frontier/xhigh) НЕ выполнялся — владелец закрыл план и
перешёл к следующему. Фаза P4 закрыта по git-фактам и вердиктам ревью прогона; независимого
adversarial-аудита фазы нет. Захотеть его позже — он остаётся запускаемым как есть.

**Done:**

- **P4.3 закрыт `🟠 Done with deviations`** (item-коммит `e0c7269c`; статус ИСПРАВЛЕН этим
  bookkeeping-заходом с ошибочного `🟢` по ревью-вердикту **ATTENTION**) — терминальный item
  фазы и плана.
  - **Доки:** `docs/control-surface.md` — три слоя источника (canonical → generated →
    effective), кто владеет каждым, чем проверяется read-only, правило «дрейф `generated`
    чинится перегенерацией, а не правкой файла»; измеренное качество (`5/31`, `F1 = 0.96`,
    `F10 = unknown`) печатается числом, не «ok». `docs/task/plan-structure.md` — компилируемые
    тиры портируемости, правило классификации и его владелец, пять отказов линтера, провенанс
    против execution input **по роли**, пять требований `committed-bundle`, закрытый enum
    proof-классов, машинный гейт кодов границ (P4.4). `docs/task/methodology.md` — «вердикт
    аудита ≠ приёмка плана». `docs/reference.md` — одна своя строка: внешний аудит
    `core`/provider адъюдицирован по коду (3 accept / 11 reject / 2 unknown), соседние разделы
    не переформатированы (И2). `docs/rejected-optimizations.md` — три несущих отклонения с
    опровергающим их кодом. `packages/analyst/docs/architecture.md` — публичные `analyst.trace`
    и `analyst.metrics`, package-API `0.2.0`.
  - **Не правлено сознательно (все прочитаны, причина названа на файл):**
    `docs/provider-support.md`, `packages/task/docs/reference/provider-commands.md`,
    `packages/harness/docs/reference/provider-harness.md` — generated;
    `packages/skiller/docs/guide/troubleshooting.md` — владелец текста P4.2, сверен и актуален;
    `docs/routing.md` — расхождений с деревом нет.
  - **Owner packet** — `artifacts/P4.3/owner-decision-packet.md`: приёмка объявлена формально
    НЕ выполненной первым предложением; недоказанное — первым разделом и числами; каждый
    остаточный долг — с носителем; отрепетированный откат и его измеренная цена; **ровно одно**
    решение G1 с рекомендацией **HOLD** и четырьмя фальсифицируемыми критериями, которые её
    изменят.
  - **Закрытость публикаций доказана командами** (не фразой): render `--check` и
    `registry --check` — no-op; diff-scope guard по адаптерам/bootstrap-деревьям/обоим
    marketplace'ам — пусто; приватный `repository-bootstrap@0.2.0` пересчитан из своего lock'а —
    **27** проекций (26 class-A + class-B `workflow-craft`), один общий lock, **0** обычных
    marketplace-записей. Ничего не перегенерировано и не сверсионировано.
  - **Validation** — восемь команд, все зелёные: четыре `validate.sh` (skiller 474 теста, task
    «plan-lint: OK (14 планов, 0 ошибок)», harness, analyst 256 тестов), два `--check`,
    diff-guard, `plan-lint` по плану (0 ERROR / 1 унаследованный WARN).
  - **Коды границ:** `pre_mutation: allow`, `pre_final: allow`
    (`content_hash 503f71945702b101503be3d4a0a924224b805e59b11555d8e7aa5503d24c6a47`, EXIT=0),
    маршрут исполнителя `frontier/high` (D75).
  - **Ревью-вердикт ATTENTION — три находки, все Minor/Nit, никакого Blocker:**
    (1) арифметика Files в Known Deviations 3 была неверна («7» вместо фактических «5»
    нетронутых путей) — исправлено; (2) статус `🟢` держался при собственноручно помеченной
    [Major/evidence] дыре (недоказанная закрытость `docs/provider-support.md`) — статус
    исправлен на `🟠`; (3) `docs/task/plan-structure.md` (продукт item'а) приписывает пять
    отказов портируемости `plan_lint`, реально это `task_contract.portability_lint` — правка
    текста дока названа будущим долгом (Known Deviations 7), не чинится задним числом здесь.

**Remaining:**

- **Закрытие фазы P4** — `task:plan-close … P4` (таблицы, `## Phase Handoff`, docs-sync
  решение), затем терминальный `task:plan-audit … P4` (frontier/xhigh, НОВАЯ сессия).
- **G1 — единственный действующий Owner-гейт.** Вход для ответа собран:
  `artifacts/P4.3/owner-decision-packet.md` § 6. Рекомендация агента — **HOLD**. Решение
  принимает ВЛАДЕЛЕЦ; агент его не исполняет. Ни `push`, ни `tag`, ни релиз, ни раскатка на
  флот/consumers, ни `plans/2026.07.18-FOREMAN` этим прогоном не тронуты.
- **Новая находка P4.3 (долг с носителем):** `scripts/provider-docs.py` —
  генератор/чекер `docs/provider-support.md` — читает `plans/2026.07.19-DUAL-PROVIDER/…` после
  архивации плана и падает `FileNotFoundError`; `scripts/test-provider-docs.py` — 4 ошибки;
  скрипт не подключён ни к одному `validate.sh`. Ремонт — владельцу скрипта, не этому item'у
  (D27/D31). Следствие: `docs/provider-support.md` доказанно закрытой НЕ объявляется.
- **Правка атрибуции портируемости** в `docs/task/plan-structure.md` (Known Deviations 7) —
  будущий item, трогающий этот файл.
- **Ремонт предиката `_lint_write_site_codes_44`** (Major ложный ERROR + Minor ложный пропуск,
  находки ревью P4.4) — в packet'е § 4.3, носитель назван.
- **Ремонт гейта `verify_claim_verdicts.py`** (не проверяет символ после `::`) и **исправление
  цитаты H06** — в packet'е § 4.3, носитель назван.
- **FP-1/FP-2/FP-3 и H15/H16** — в packet'е §§ 4.5/4.6 с владельцами и названным недостающим
  доказательством.
- **Долги измерения D88 п. 6а–6г** (producer для F1, расширение знаменателя 5/31, канал для
  F10, Codex-сторона) — packet § 4.1, носитель у всех один: будущий план.
- **Строка доски P0** остаётся `🟡` при терминальных items — снимается `task:plan-close … P0`,
  вне фазы P4.
- **Архивация** — после терминального закрытия, независимо от go или hold по G1.

**Sources of truth:**

- `phases/P4.md` — `## Phase Status` (P4.1 `🟠`, P4.2 `🟢`, P4.3 `🟠`, P4.4 `🟠`, P4.5 `🟢`),
  `### P4.3` Completion Notes/Known Deviations 1–8 — полная запись закрытия и исправления.
- `artifacts/P4.3/owner-decision-packet.md` — терминальное измеренное свидетельство и вход G1.
- `plan.md` — §4 Status Board (`P4 2/5, 🟡 In progress`), §6 Update Log, §0 Meta
  `Version 1.21.7`.
- `journal.jsonl` — последняя запись `item_id: "P4.3", command: "plan-close",
  result: "closed-deviations"`.
- `research/10-p4-entry-gate-and-composition.md` — основание решений захода (D89–D93).

**Open risks:**

1. **Приёмка формально не выполнена и этим планом выполнена не будет** (D88/D89): `F1 = 0.96`
   при `== 1.0`, `F10 = unknown`, layer-2 измерен на `5/31`. Packet объявляет это первым
   предложением; риск — что при пересказе скоуп потеряется и packet прочитают как «плагин
   надёжен».
2. **`docs/provider-support.md` не подтверждена командой** — её чекер неисполним (см. выше).
   До ремонта нельзя утверждать, что ВСЕ generated-страницы закрыты; закрыты те, что
   перечислены в Scope Included P4.3 и доказаны выводом `--check`.
3. **Гейт P4.4 не покрывает items этой фазы** (cutoff `2026-07-27` в будущем относительно даты
   закрытия `2026-07-26`, D91) — печать кодов границ остаётся ручной дисциплиной; плюс сам
   предикат несёт названный дефект точности.
4. **`pre_mutation` P4.3 посчитан не строго до первой мутации** (раскрыто в Known Deviations 1);
   значение проверяемо идентично досмутационному — спека item'а на момент замера была
   байт-в-байт равна HEAD.
5. Долги без носителя (D92) не изменились; полный список — packet § 4.

**Workarounds / Deferred / Open questions:**

- Посторонний untracked-каталог `.swissknife/` в рабочем дереве — не тронут этим заходом.
- `docs-sync` follow-up (`packages/task/CLAUDE.md` про compiler/enforcement seam) — долг P3.1,
  в `Files` P4.3 не входил; носитель — ближайший будущий item, трогающий этот файл (packet § 4.3).
- Литерал `GREEN` в `docs/task/methodology.md` — имя вердикта аудита в enum `plan-audit`, а не
  утверждение о приёмке; вместо правки канона добавлен разделяющий абзац.

## Архивация (2026-07-29)

План перенесён `plans/2026.07.24-AGENT-RELIABILITY` → `plans/archive/2026.07.24-AGENT-RELIABILITY`.

**Чек-лист миграции `root/` → docs:** пропущен по прецеденту — `root/contracts/` (9 frozen-
контрактов) и `root/provider-core-hypotheses.md` **остаются в архиве**, а не мигрируют в
`docs/`: тот же паттерн уже применён к `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/`
(осталось в архиве, читается функциональным кодом через `core.repo.resolve_plan_dir`/
`scripts/provider-docs.py::resolve_plan_dir`, устойчивый к обеим локациям). Контракты этого
плана — те же по природе (frozen-спеки, узкий predicate/schema материал, не Diátaxis-проза для
читателя проекта) — тот же путь.

**Осталось в архиве:** `artifacts/`, `findings/`, `research/`, `brief/`, `root/` (contracts +
provider-core-hypotheses.md), `workflows/`, `index.md`, `roadmap.md`, `journal.jsonl`, `plan.md`,
`phases/*`.

**Реестры/ссылки обновлены** на `plans/archive/2026.07.24-AGENT-RELIABILITY/...`:
`packages/skiller/skills/repository-bootstrap/package-architecture/SKILL.md` и `SKILL.ru.md`
(единственные markdown-ссылки на `root/contracts/semantic-identity-ownership-v1.md`).
`plans/ACTIVE.md` уже указывал `—` до архивации.

**Портабельность кода (не docs-ссылка, но того же класса риска):**
`packages/task/tests/test_task_contract.py` зашивал `plans/2026.07.24-AGENT-RELIABILITY/...`
напрямую — исправлено на `core.repo.resolve_plan_dir(REPO_ROOT, "2026.07.24-AGENT-RELIABILITY")`
ДО переноса (коммит `68dff7db`, тесты зелёные: `72 passed`). Прочие ссылки на
`root/contracts/...`/`plans/2026.07.24-AGENT-RELIABILITY` в `packages/{task,harness,analyst}/lib`
— docstring-цитаты провенанса (`<PLAN-ID> Pn.m`), не файловые пути кода; правки не требуют
(канон D3: полный `<PLAN-ID>` остаётся grep-адресным после архивации).
