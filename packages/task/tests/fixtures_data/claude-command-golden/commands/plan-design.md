---
description: "План-протокол: создать/детализировать мастер-план в plans/ — новый план, фаза Pn, ТЗ подпункта Pn.m, развёртка черновика (from-draft), финальное закрытие дыр (finish) или пересборка roadmap. Пинит Opus/high."
argument-hint: "[new <название> | <PLAN-ID> [Pn[.m] | finish | roadmap] | from-draft <файл>]"
model: opus
effort: high
---
Это ПРОЕКТИРОВАНИЕ мастер-плана (plan-протокол). Ввод пользователя: «$ARGUMENTS».
Модель/effort запинены (Opus/high) — не переключай вручную. SSOT протокола — скилл
`plan-protocol` (general): схемы, статусы, эскалация, routing-матрица, refine-цикл (§7);
шаблоны — его `snippets/{plan,phase,handoff,launch-block}-template.md`. Ты пишешь план,
который дешёвая модель исполнит БЕЗ доступа к этому чату.

## DESIGN-ROOT-TERMINAL (authoring/execution boundary)

`task:plan-design` заканчивается после записи плана, final handoff и delivery
receipt. Launch-block — только маршрутизированная рекомендация, а не авторизация
на исполнение. Текущий design root НЕ вызывает successor command, НЕ спавнит
исполнителя и НЕ начинает `plan-audit`/`plan-exec`/`plan-run`/Workflow — даже если
successor уже ready или исходный бриф упоминал последующую реализацию. Исполнение
начинается только отдельным routed invocation после design-result. Любой runnable
successor из design handoff несёт `Context: cold-start-root: design-root-terminal`
и native launch с моделью и effort именно successor'а.

## DecisionRequest и isolated-child-return (P6.3)

Свободная проза не является каналом уточнения или авторизации. Когда дальнейший шаг требует
недостающего факта либо права действия, команда строит transient action по
`decision-request` v1, передаёт его единственному резолверу `task.plan_authority.authorize()` и
исполняет закрытый исход: `delegated` — продолжить только exact canonical action;
`approval_required` — материализовать `DecisionRequest` через `plan-decisions.py request` и
припарковать subject; `denied` — записать отказ и остановиться. Durable request всегда несёт
continuation identity, timeout из authority frame и объявленные варианты `escalate`/`reject`.
Уточнение авторазрешимо только закрытым allowlist систем-записей с provenance; после ответа intent
канонизируется и классифицируется заново. Модельная память, чат и свободный текст не дают approval.

Модельное суждение выполняется только как provider-neutral `isolated-child-return`: после risk
trigger либо повторного durable fingerprint root строит закрытый capsule `return-judgement` v1,
проверяет capability, независимо выбирает свежего reviewer с actor/context, отличными от executor,
и делает ровно один вызов. Full parent transcript, unrelated history, self-review и второй sample
запрещены. Capability absence даёт `cold-start-root: capability-missing`. Reviewer применяет
неизменяемый ассет `return-judgement@1.0.0`
(`packages/task/prompts/return-judgement-rubric-v1.md`,
SHA-256 `63323e5565fa2c321354e36ebe47624f37f86c3c3372ba01efaedcc61b6c2e1e`); root валидирует schema,
передаёт запись детерминированному reducer и продолжает исходный run. Неоткалиброванная пара
`model_id × rubric_sha256` и order-sensitive swap трактуются как `INSUFFICIENT_EVIDENCE`.
Raw provider flags допустимы только в additive adapter/projection.

## Continue-first block gate (v1)

Небольшое отклонение не открывает новый design pass. Procedural/transient/dependency,
tool-noise, stale projection и bounded local reversible defect чинятся inline и фиксируются
nonterminal `local-repair`; original gate повторяется. Если после минимального
воспроизведения остаётся material block candidate, запиши `block-candidate`, собери
closed `block-candidate/v1`; для 100% external-кандидатов сначала verified RAG.
Один свежий reviewer, отличный от executor, в `isolated-child-return` применяет
`block-confirmation-rubric-v1`, после чего root вызывает `task.plan_blocking.evaluate()`. Только
`terminal-block` после `JUSTIFIED` разрешает Blocked/escalation; неподтверждённый
кандидат возвращается в repair/evidence без новой фазы дизайна.

## Путь чтения существующего плана

Для режима, адресующего существующий item, сначала прочитай поле `Layout` в `## 0. Meta`;
исполняется только явный `Layout | v2` (отсутствующий или `v1` возвращает
`PLAN_LAYOUT_V1_RETIRED`). РОВНО пять обязательных слотов:

1. `plans/<PLAN-ID>/plan.md` — identity, Context, Execution Rules и §3 Routing;
2. `plans/<PLAN-ID>/phases/<Pn>/<Pn>.md` — только Phase Context;
3. `plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.md` — полное ТЗ выбранного item;
4. `plans/<PLAN-ID>/bundles/<Pn.m>.json` — объявленные digest-qualified inputs;
5. `plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.state.md` — byte-fresh item state.

В v2 `handoff.md` НЕ входит в обязательный путь: состояние выбранного item берётся только из
fresh item state. Повторное чтение запрещено; режим `new` не имеет существующего plan input и
начинается с брифа владельца.

## Режимы (по $ARGUMENTS)

1. **`new <название>`** — новый план: после анализа брифа оцени объём и объяви дизайн-бюджет
   в `## 0. Meta`: `Design Passes: 1/N — <обоснование>` (SKILL §5: ≤3 фаз/≤10 items → 1;
   4–7 фаз/15–35 items → 2; кросс-репо/ядро экосистемы/высокая неопределённость → 3);
   каждый следующий прогон — НОВАЯ сессия, финал прогона: k++ в Meta + Update Log-строка
   «что сделано / куда не дотянулись / фокус следующего» + handoff.Next с этим фокусом.
   Выбери `PLAN-ID` по датовому канону (SKILL D16):
   `<ГГГГ>.<ММ>.<ДД>-<КОДОВОЕ-ИМЯ>`, напр. `2026.07.10-SETTINGS-DOCTOR` (legacy
   `[A-Z][A-Z0-9-]+` — только back-compat уже существующих планов, для новых НЕ использовать),
   создай `plans/<ID>/brief/00-brief.md` — исходное сообщение владельца, переформулированное
   БЕЗ потери мыслей (слой 0, ОБЯЗАТЕЛЕН — без него `plan-lint` ERROR и план не проходит
   утверждение; всё выясняемое дальше дописывай датированными блоками в
   `brief/01-refinements.md`), затем `plans/<ID>/plan.md` по шаблону (секции 0–6 +
   опциональные `## 7. Contracts`/
   `## Обсуждение` — заводи, только если план их несёт), скелеты фаз `plans/<ID>/phases/Pn.md`
   (Phase Context со скелет-маркером — фиксированная строка
   `> СКЕЛЕТ — не детализирован, разворачивается /task:plan-design <ID> Pn` —
   + Phase Status + items-скелеты; каждый item несёт ВСЕ 16 полей строками (при маркере
   пустые поля легальны, включая Code Guidance = «—», но САМИ ПОЛЯ обязаны быть — иначе
   ERROR `plan-lint`)) и `handoff.md` (Next: первый item;
   заголовок стартового handoff — `# HANDOFF — <дата> — after P0.0`: bootstrap-канон,
   закрытых items ещё нет, а линт требует строго `after Pn.m`).
   **Полная детализация — дефолт, конвейер ПОФАЗНЫЙ (SKILL §5):** скелеты `new` —
   промежуточное состояние авторинга; до первого exec ВСЕ фазы доводятся до DoR.
   Штатный конвейер: `new` (вид сверху: скелеты+контракты — здесь задаются вопросы,
   выравнивающие ВСЁ) → `<PLAN-ID> P0` … `<PLAN-ID> Pn` — каждая фаза ОТДЕЛЬНОЙ
   командой/сессией: фазы слабо связаны, вопросы и утверждение владельцем происходят
   ВНУТРИ захода фазы; проектировать 5+ фаз одним потоком — риск ошибок и смешанных
   согласований (допустимо только для малых планов ≤3 фаз или по явному выбору владельца)
   → финал `<PLAN-ID> finish` (режим 5: закрытие дыр; roadmap — его последний шаг) →
   `/task:plan-audit <ID> design` → exec. Exec по живым скелетам — только по явной
   D-записи (волатильная фаза).
   **Contract-first (опционально, скилл `plan-protocol` §5):** можно запечатать ВСЕ фазы
   скелет-маркерами и вписать в каждый `Phase Context` контракт-блок
   `> **Контракт фазы (contract-first).** Потребляет: … · Производит: … · Границы: …`
   (что фаза берёт от предыдущих / отдаёт следующим / сознательно не трогает); детали items —
   just-in-time при `<PLAN-ID> Pn`. Плюс перечисли coupling-поверхность (файлы/канон, трогаемые
   ≥2 фазами) в `## 5. Decision Log`. Контракт-блок опционален (отсутствие ≠ дефект).
   **Constitution-гейт (план нового Axioma-проекта/пакета):** ДО фиксации стека и несущих
   архитектурных решений в плане прогони `axioma-doctrine` → `ecosystem-reuse-gate`
   (аналог constitution-check spec-kit, RAG:✅ P5.1 §1); reuse-вердикт зафиксируй в
   `## 5. Decision Log`.
   Затем создай/обнови `plans/ACTIVE.md` (в корне `plans/`, НЕ внутри `plans/<ID>/`) —
   канонический формат 4 строки: `# ACTIVE`, пустая строка, `**Active:** <PLAN-ID>`,
   `**Updated:** <YYYY-MM-DD>` (файла нет — создай; есть — перезапиши по канону, указав
   новый `PLAN-ID`). Если ACTIVE указывал на другой незакрытый план — допиши ЕМУ в
   `## 0. Meta` поле `Paused By: <новый PLAN-ID>, <YYYY-MM-DD>` (+строка в его Update Log):
   перехват ACTIVE не бывает молчаливым. Смену Active зафиксируй строкой в
   `## 6. Update Log` нового плана.
2. **`<PLAN-ID> Pn`** — спроектировать фазу: заполнить `## Phase Context` (5–10 строк,
   самодостаточно — фаза исполнима без чтения других фаз; скелет-маркер убрать) и разложить
   на items `### Pn.m — Title` со всеми полями; синхронизировать Status Board в plan.md.
   Финал режима — обязательный refine-цикл + DoR-чеклист (ниже).
   **Журнал (D21, P1.1):** append ОДНУ запись (item_id = `Pn` — фаза, не item; design-сессия
   не закрывает item'ы, `result` честно отражает это) — `python3 -m task.journal append
   --plan-dir plans/<PLAN-ID> --plan <PLAN-ID> --item Pn --command plan-design --actor
   opus/high --session-id "$(python3 packages/task/scripts/plan-session.py current --id)"
   --result in-progress --note "фаза детализирована до DoR"`.
   **Reconcile контракт-блока (contract-first, скилл `plan-protocol` §5):** если фаза несёт
   контракт-блок `> **Контракт фазы (contract-first).**`, при детализации сверь его `Потребляет`
   с `Производит` уже закрытых фаз; расхождение → обнови блок + D# (`supersedes D#` при отмене
   раннего решения). Дёшево — скелет не терминален.
   **Реопен фазы** (Pn уже терминальна 🟢/🟠) — четыре шага обязательны (пропуск = находка
   аудита): (1) Status фазы → `🟡` синхронно в Status Board `plan.md` и `## Phase Status`;
   (2) version bump плана; (3) D-запись о причине реопена; (4) `## Phase Handoff` реопененной
   фазы ИНВАЛИДИРУЕТСЯ — блок не удаляется, его первой непустой строкой ставится маркер
   ДОСЛОВНО `> УСТАРЕЛ — фаза реопенена <D#>` (снимает его только `plan-close` при следующем
   закрытии фазы). `handoff.md` в этом случае пишется с заголовком `after Pn` (не `Pn.m`).
3. **`<PLAN-ID> Pn.m`** — довести один item до исполняемого ТЗ: дозаполнить все поля
   до уровня «sonnet исполнит без вопросов». Финал режима — refine-цикл + DoR-чеклист (ниже).
   **Журнал (D21, P1.1):** append ОДНУ запись — `python3 -m task.journal append --plan-dir
   plans/<PLAN-ID> --plan <PLAN-ID> --item <Pn.m> --command plan-design --actor opus/high
   --session-id "$(python3 packages/task/scripts/plan-session.py current --id)"
   --result in-progress --note "ТЗ item'а доведено до DoR"`.
   **Историческое исключение (D51):** schema-invalid существующую journal-строку нельзя
   переписывать или компенсировать event'ом. Только explicit Owner D# может дописать
   `journal-exceptions.jsonl` через `python3 -m task.journal exception --plan-dir
   plans/<PLAN-ID> --target-line N --invalid-fields friction --owner-decision D# --actor
   <actor> --reason "..."`; writer и linter fail closed на любом неexact target/hash/field.
4. **`from-draft <файл>`** — мост встроенного plan mode Claude Code → протокол (событие
   ExitPlanMode не существует — авто-хука нет, мост ручной, но одношаговый). `<файл>` —
   плоский одобренный черновик `plans/<slug>.md` (конвенция: плоский `.md` в `plans/`, кроме
   `ACTIVE.md`/`README.md`, — черновик plan mode; `plan-lint` их видит и подсказывает этот
   режим WARNING'ом). Прочитай черновик целиком, предложи `PLAN-ID` по датовому канону из
   даты конвертации + slug'а (upper-kebab; напр. `plans/pilot-azg.md` →
   `2026.07.16-PILOT-AZG`) — **финальный ID подтверждает
   человек** перед созданием файлов. Затем разверни черновик в `plans/<ID>/` по тем же
   шаблонам скилла `plan-protocol`, что и режим `new` (`plan.md` все секции 0–6, скелеты
   `phases/Pn.md` со скелет-маркером, `handoff.md`): черновик НЕ переносится как есть —
   транскрибируется (все 16 полей каждого item'а, **Code Guidance обязателен**, как в режиме
   `new`). В `## 5. Decision Log` нового плана зафиксируй происхождение отдельной строкой:
   `D1 | <YYYY-MM-DD> | Источник — черновик plans/<slug>.md | bootstrap-транскрипция
   одобренного черновика plan mode`. После записи файлов **удали черновик** `plans/<slug>.md`
   (история — в git, дублей не держим). Финал — как у `new`: создай/обнови `plans/ACTIVE.md`
   в корне `plans/` по канону 4 строки (`**Active:** <новый PLAN-ID>`,
   `**Updated:** <YYYY-MM-DD>`), допиши `Paused By` предыдущему активному плану
   + строка в `## 6. Update Log` нового плана.
5. **`<PLAN-ID> finish`** — финальное закрытие дыр после детализации ПОСЛЕДНЕЙ фазы
   (вывод «конфликты устранены» делается, только когда видны ВСЕ подробности).
   Шаги: (0) гейт дизайн-бюджета — `Meta Design Passes: k/N`: при k<N остановись и предложи
   следующий прогон (finish при недоборе прогонов — только по явной D-записи владельца);
   (1) гейт — скелет-маркеров нет ни в одной фазе (есть → назови фазы и остановись:
   сначала `<PLAN-ID> Pn`); (2) **сквозной reconcile**: контракт-блок каждой фазы —
   `Потребляет` производится предыдущими; coupling-hotspot'ы D-лога против фаз; артефакты
   design-items (матрицы/спеки/ADR) — каждый производитель существует до потребителя;
   Required Reads указывают на существующие файлы; расхождение → правка фаз + D#
   (`supersedes` при отмене раннего решения); (3) DoR-свип всех фаз (чеклист ниже, включая
   бриф-трассировку по research/00-user-intent); (4) ТОЛЬКО когда дыры закрыты — последним
   шагом собрать `roadmap.md` (механика режима 6); (5) version bump + Update Log +
   `plan-lint`. Historical schema-invalid journal row не «гасится» compensating event:
   append-only сохраняется через owner D# + `task.journal exception` sidecar по канону
   plan-protocol §2, затем lint обязан быть перепроверен. Финал сообщения — launch-block на
   `/task:plan-audit <PLAN-ID> design`
   (Opus/xhigh, NEW SESSION). Найдены дыры, которые не закрыть этим заходом, → отчёт
   владельцу + launch-block на `<PLAN-ID> Pn` проблемной фазы, roadmap НЕ собирается.
6. **`<PLAN-ID> roadmap`** — лёгкая пересборка ТОЛЬКО исполнительской карты (без
   полного свипа): после изменения/добавления/закрытия фаз, смены Routing или re-design'а.
   Шаги: гейт на скелеты (как в finish) → перечитать Status Board + Phase Status всех фаз →
   пересобрать `roadmap.md` по `snippets/roadmap-template.md` (закрытые items пометить,
   батчи/workflow/solo с обоснованиями выгоды/границы, гейты владельца, launch-block'и групп;
   сначала пробуй adjacent-группу одной фазы с общими reads/setup/validation и ставь `solo`
   только при конкретной несовместимости/hard boundary/context-budget; roadmap не
   переопределяет Routing §3) → строка Update Log. Если с последнего `finish`/`audit design`
   менялись КОНТРАКТЫ фаз (не только статусы) — предупреди владельца, что нужен новый
   `finish`, а не только пересборка карты.

## Conflict-impact assessment before a stop

До `Blocked`/escalation/re-design исполнитель обязан сделать короткую оценку, а не считать
любой конфликт новым дизайном: (1) воспроизвести signal на минимальном scope; (2) назвать
затронутые package/file/contract surfaces и проверить current source, generators и focused
tests; (3) классифицировать изменение как local reversible, cross-package, frozen/public,
authority или acceptance/safety; (4) оценить rollback и validation. Local reversible repair,
не меняющий declared scope/public or frozen semantics и укладывающийся в текущий item, выполняется
в той же сессии и фиксируется в Completion Notes/Known Deviations с impact. `plan-design` или
owner-gate допустимы только для доказанной cross-package/frozen/public/authority boundary,
невыполнимого acceptance или отсутствующего safe rollback. Нельзя парковать item только из-за
старой projection, tool-noise, generated-carrier mismatch или предположения о blast radius.

**Compiler (P2.2).** `§3 Routing`, портируемость (D26/D47) и precedence/conflict-разрешение
компилируются одним модулем — `packages/task/lib/task/task_contract.py`
(`root/contracts/task-contract-v1.md`, `root/contracts/plan-portability-v1.md`). Пишешь
здесь Routing/tier-признаки item'а — не пересказывай сами предикаты второй прозой; их
владелец компилятор, эта команда только производит вход для него.

## Схема (компактная выжимка — на случай отсутствия скилла)

- `plan.md`: `## 0. Meta` (таблица: Plan ID / Title / Version / Status / Document Type /
  Authoring Model / Last Updated / Repository / Related Packages / Execution Mode /
  Target Operator Models / Approval Owner; необязательные: `Home` — `brain`|`repo:<путь>`,
  `Paused By` — кто перехватил ACTIVE и когда) · `## 1. Context` (5–15 строк, самодостаточно) ·
  `## 2. Execution Rules` (выжимка ≤20 строк) · `## 3. Routing` — канон-таблица
  `| Batch | Items | Model class/effort | Exec | Review | Почему |` (SKILL §5): для нового
  layout-v2 плана `Batch`/`Review` обязательны, каждый item получает stable batch ID или `solo`;
  `solo` требует конкретной причины, а связные adjacent items одной фазы группируются при
  экономии повторного чтения/setup/validation; колонка **Exec** — enum `plan-exec` |
  `manual` | `plan-design`; пустая ячейка = дефолт-деривация (`model ≤ sonnet` И `effort ≤
  medium` → `plan-exec`, иначе `manual`); design/contract-item'ы получают `Exec = manual`
  явно; пустая секция = дефолты SSOT-матрицы ·
  `## 4. Phase Index & Status Board` (`Phase | Title | Items 🟢/всего | Status`) ·
  `## 5. Decision Log` (`D# | Дата | Решение | Почему`) · `## 6. Update Log` (append-only:
  `Дата | Кто | Что`; «Что» ≤ 2 строк, канон
  `<item> закрыт: <1 строка сути> — детали см. phases/Pn.md <item> Completion Notes`,
  пересказ Completion Notes запрещён) · `## 7. Contracts` (ОПЦИОНАЛЬНАЯ — только у планов,
  экспортирующих/потребляющих замороженные контракты; линтер опознаёт секцию по ЗАГОЛОВКУ,
  не по номеру — занят 7, ставь под свободным) · `## Обсуждение` (ОПЦИОНАЛЬНАЯ, БЕЗ номера,
  последней секцией: каждая развилка несёт `**Статус:** Resolved → D# | Decision pending |
  Exploration`; всё, что ≠ `Resolved` — запись в `open-questions.md`).
- `phases/Pn.md`: `# Pn — Title` → `## Phase Context` (скелет-маркер, если фаза не
  детализирована) → `## Phase Status` (`ID | Title | Status | Updated`) → items →
  `## Phase Handoff`.
- Item: заголовок СТРОГО `### Pn.m — Title`; поля СТРОГО строками `**Поле:** значение`,
  в этом порядке: Status, Intent, Why, Scope Included, Scope Excluded, Inputs, Files,
  Required Reads, Implementation Rules, Code Guidance, Validation, Deliverables,
  Completion Notes, Pending Work, Known Deviations, Escalation Needed.
  Пустое значение — канонический символ «—» (не пустая строка, не «N/A»);
  у `Escalation Needed` — и ТОЛЬКО у него — маркер `no` равноправен «—».
- Статусы — РОВНО 6 канонических строк, байт-в-байт:
  `⬜ Not started` · `🟡 In progress` · `🟢 Done` · `🟠 Done with deviations` ·
  `🔴 Blocked` · `⛔ Skipped by decision`. Гейты статусов: коммит-гейт закрытия +
  DoR-гейт перевода фазы в исполнение (SKILL §6).
- `handoff.md`: заголовок — две формы (SKILL §8): `# HANDOFF — <ISO-дата> — after Pn.m`
  (закрыт item) либо `# HANDOFF — <ISO-дата> — after Pn` (закрыта/проаудирована/
  ре-дизайнена/реопенена ФАЗА) + Next / Done / Remaining / Sources of truth / Open risks /
  Workarounds-Deferred-Open questions; перезаписывается целиком. Next — в форме
  launch-block, самодостаточный из холодной сессии (SKILL §8).
- Раскладка 2.0: обязательны `plan.md`/`phases/`/`handoff.md`; опционально `findings/`,
  `research/`, `artifacts/` (судьба — архив), `root/` (судьба — docs проекта),
  `open-questions.md` (протокол спорного — SKILL §3).

## Требования к качеству

- **Каждый item исполним sonnet'ом без доп. контекста**: Required Reads конечны и
  упорядочены (не «посмотри по репо»), **Code Guidance обязателен** (стиль решения,
  запреты, обязательные тесты, запрещённые shortcuts — то, что дешёвая модель не выведет
  сама; формулировки бери из `snippets/code-guidance-patterns.md` — анти-подгонка,
  анти-самообман, if-then эскалация к D# — не изобретай заново), Validation — конкретные
  команды (что прогнать и что считается зелёным).
- **Никаких самовольных допущений.** Спорное/неоднозначное место — либо маркер
  `[NEEDS CLARIFICATION: <вопрос>]` прямо в тексте, либо вопрос владельцу; молча принятое
  допущение — дефект. Принятые решения фиксируй в `## 5. Decision Log`; правку плана
  отметь строкой в `## 6. Update Log`; долгоживущее спорное — в `open-questions.md`
  по протоколу SKILL §3.
- **D-запись, отменяющая/заменяющая ранее принятое решение** (`supersedes D#`, «отменяет
  D#», «отменён»/«отменена»/… — форма роли, а не буквальная строка), несёт инлайн-подполе
  `**Consequences:**` внутри той же ячейки `Решение` — чем платим за отмену/замену (SKILL
  §6). Пятая колонка D-лога не заводится (шапка — литерал реестра, правка означала бы
  переписывание шапки во всех планах флота). При `Closure Protocol | v1` и дате записи ≥
  канонической cutoff-дате правила (SKILL §6) — машинный ERROR (`plan_lint.py`), но
  дисциплина обязательна независимо от того, включён ли Closure Protocol на этом плане.
- **RAG-маркеры на несущих — enum ТРЁХ значений (SKILL §7).** Каждый load-bearing
  факт/вердикт в Intent/Why/Implementation Rules и в D-логе несёт РОВНО один: `RAG:✅
  <дата/суть запроса>` (внешний факт верифицирован RAG-лестницей context7 → perplexity →
  WebSearch); `RAG:— (repo-grounded: <файл:строка>)` (repo-grounded/внутреннее правило —
  внешней верификации не требует; НЕ годится ни для одного внешнего факта); `[UNVERIFIED]`
  (не проверено, риск принят явно). Несущий пункт без маркера = дефект схемы, находка аудита.
- **Слои знаний обязательны (SKILL §16): ничего несущего не остаётся только в чате.**
  Во ВСЕХ режимах (включая `new`): (0) слой 0 — бриф владельца в `plans/<PLAN-ID>/brief/`
  (00-brief.md — переформулировка входа без потери мыслей; уточнения/решения по ходу —
  датированными блоками в 01-refinements.md; гейт plan-lint); (1) слой 1 — всё внешнее (RAG-выжимки с источником-URL
  + датой + вердиктом, recon-отчёты субагентов, выжимки исходных документов и их вложения) —
  в `plans/<PLAN-ID>/findings/` В ТОМ ЖЕ ходе, когда получено; (2) слой 2 — твой авторский
  синтез (анализы, целевые структуры, доменные модели, тест-стратегии, user-intent выжимка
  требований владельца с трассировкой «мысль → куда ушла») — в `plans/<PLAN-ID>/research/`,
  каждый синтез ссылается на файлы слоя 1; (3) слой 3 — D-записи ссылаются на файлы слоёв
  1–2. Items указывают файлы слоёв в `Inputs`/`Required Reads`; при детализации фазы её
  research-файлы читаются первыми. Цепочка «сырьё → синтез → решение» обязана
  восстанавливаться из файлов плана без этой сессии; несущий факт только в чате — дефект.
- **Кап делегирования.** Субагент-разведчик заводится только под крупный, реально независимый
  и параллелимый трек разведки (широкое многофайловое чтение репо, отдельная грань внешнего
  поиска). Что доделаешь сам за несколько тул-вызовов — не делегируй; хватает одного
  разведчика — запускай одного, а не нескольких; число спавнов держи низким. Субагент
  «перепроверь мою же работу» запрещён — DoR-чеклист и refine-цикл ниже ведёшь сам.
  RAG-ступень (`context7`/`perplexity-web`) капом НЕ ограничена: это инструмент, а не субагент.
- Phase-first: items не прыгают между фазами; фазы закрываются последовательно.
- **Тайм-гейтовый Deliverable — отдельный item.** Если часть Deliverables требует
  календарного окна (накопить данные, дождаться прод-недели) И от неё зависит Inputs
  более позднего item'а — выдели её в собственный follow-up item (доска честно покажет
  его открытым), а не оставляй хвост в Pending Work: downstream-исполнитель читает
  Status Board, а не прозу закрытого item'а.

## Refine-цикл и DoR (обязательный финал режимов `Pn`/`Pn.m`)

Канонический контур (SKILL §7): design → self-audit по DoR-чеклисту → правка → повтор
до 0 маркеров `[NEEDS CLARIFICATION]`.

**Клинч рефайна** (фикс одной фазы/item'а рябит в другую) — не гоняй per-change (thrash)
и не копи до big-bang: рефайни **средним батчем вокруг ОДНОГО coupling-hotspot'а**,
интеграционная валидация DoR ПОСЛЕ КАЖДОГО батча, финальная консолидация одним проходом;
пустой feasible-set → удали вариант (SBD, не патчь), стратегия декомпозиции → эскалация к
Perplexity. Полный канон RECOVERY-дисциплины + критерий остановки — **SKILL §7 «RECOVERY
при клинче»** (носители — контракт-блок §5 / батчинг §9, не дублируй).

Перед выдачей «фаза готова» прогони DoR-чеклист:
маркеры сняты; Scope Included/Excluded фазы заполнены; Alternatives несущих решений —
в D-логе; Open Questions разнесены по статусам; несущие факты несут RAG-маркеры;
внешние факт-классы фазы перечислены, у каждого — источник;
**§3 Routing покрывает каждый item фазы ПОСТРОЧНО шестью обязательными колонками**;
каждый item классифицирован как stable Batch либо `solo`; у `solo` названа граница, у batch —
конкретный reuse-выигрыш, группа adjacent, phase-local и с единым Exec; launch использует
максимум route/review и union capabilities;
тир модели — по Tier policy §9 (верхний тир ТОЛЬКО при открытых design-решениях/необратимой
цене ошибки; «effort high+» тир НЕ поднимает); диапазон-строка легальна лишь для однородных
items (один риск-класс, одна фраза «почему» истинна для каждого — SKILL §9 «Гранулярность»),
design/contract-item'ы несут `Exec = manual`; **план экспортирует/потребляет
замороженные контракты → `## 7. Contracts` заполнена**; **каждая развилка
`## Обсуждение` несёт `**Статус:**`**, всё, что ≠ `Resolved` — в `open-questions.md`;
**скелет-items несут все 16 полей**; **бриф синхронизирован** — слой 0 (`brief/`) дополнен
выясненным в этом заходе, каждая мысль брифа, относящаяся к фазе, покрыта item'ом или
D-записью; **roadmap.md собран/обновлён**, если этот заход завершил детализацию всех фаз
(гейт plan-lint: детализирован без roadmap = ERROR). Фаза, ушедшая в exec без DoR, =
находка plan-audit.
Финальный гейт перед стартом исполнения ВСЕГО плана — `/task:plan-audit <PLAN-ID> design`
(pre-exec ревью: полнота покрытия брифа, слепые зоны, связность слоёв знаний).

**Pre-mortem для high-stakes** (фискалка/платежи/tenant-isolation/ядро экосистемы):
перед закрытием фазы дизайна — раунд по протоколу Klein: «план провалился через
6–12 мес — почему»; независимая запись причин → кластеризация → mitigations с owner
в Risks/D-лог.

## Финал

Прогони линтер: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan-lint.py" plans/<ID>`
(переменная не задана или скрипта нет — предупреди и пропусти, не блокер).
Красное линтера почини в созданных файлах.
После final handoff, но до `final`, собери
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan-delivery.py" --plan-dir plans/<ID>
--subject design --kind handoff`. Ненулевой exit означает stale/missing persisted Next:
почини handoff и не выводи `final`. Финал печатает `Delivery receipt: <compact JSON>`
и `Рекомендация следующего шага:` с exact `recommendation` receipt.
После этих строк срабатывает `DESIGN-ROOT-TERMINAL`: верни управление владельцу и не
исполняй напечатанную команду в этом root.

**Expected output:** список созданных/изменённых файлов + число items + вердикт
DoR-чеклиста (режимы `Pn`/`Pn.m`) + **финал сообщения — ПОЛНЫЙ launch-block следующего
шага** (SKILL §8, форма `snippets/launch-block-template.md`): таблица
`| Параметр | Значение |` с рядом строк `Batch / Model / Thinking / Context / Суть /` `| Команда |`
(последней) — строка `| Команда |` несёт голую команду и, когда она выражает следующий шаг
целиком, является всем ответом;
отдельный code-block ОПЦИОНАЛЕН (появляется, когда шаг реально отличается от строки —
напр. Workflow-оркестрация ниже с NEW SESSION). Строка «Готово к: …» без таблицы и
(строки `Команда` либо code-block'а) = дефект (владелец не должен переспрашивать
модель/настройки). Какая команда в блоке —
зависит от DoR-пункта «заявленная оркестрация» (SKILL §7 критерий: N≥3 items с
независимым scope и детерминированной Validation, либо длинная автономная цепочка с
внешним состоянием): фаза БЕЗ оркестрации → `/task:plan-exec <ID> Pn.m` (Model/Thinking —
из §3 Routing, дефолт Sonnet/medium); фаза С заявленной оркестрацией (workflow-скрипт
готов в `plans/<ID>/workflows/`) → `Workflow({scriptPath: "plans/<ID>/workflows/wf-….js"})`
с пометкой NEW SESSION (session-restart discipline, SKILL §8), не `plan-exec`;
режим `new` (все фазы — скелеты) → `/task:plan-design <ID> P0` (Opus/high).
