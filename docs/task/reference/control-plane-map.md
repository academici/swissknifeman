# Task: что является правилом, а что вычисляется

Task включается только явной командой владельца. Обычное исправление живёт в Git diff и проходит затронутые проверки без plan carriers. Эта карта нужна для сопровождения явно включённого плана: при изменении правила сначала ищите источник истины, затем его потребителей. Количество модулей само по себе не показывает, нужен ли новый шаг для агента.

## Словарь для исполнителя

| Термин | Что он означает здесь | Что с ним делать |
|---|---|---|
| Carrier | Файл с определённой ролью в плане: авторский контракт, история, производный вид или передача | Сначала установить класс по таблице ниже; не считать любой файл новым источником истины |
| Admission / gate | Проверка допустимости конкретного перехода, например design → start | Читать `code` отказа и исправлять указанный вход; gate не выполняет item за агента |
| Authority | Право на действие с данным эффектом | Проверять на границе записи/публикации; успешный route или тест не создаёт полномочие |
| Route evidence | Доказательство фактически запущенных provider/model/effort для вызова | Сверять с объявленным semantic Routing; запись в плане не доказывает фактический запуск |
| Snapshot / fingerprint | Снимок выбранных входов и его хэш | После изменения design-файла старый audit не переносится на новый fingerprint |
| Bundle | Восстанавливаемый набор входов выбранного item | Строить при старте item; не создавать все bundles на design |
| Projection / view | Производный status, state или receipt | Перестраивать владельцем writer из исходных данных; не исправлять вручную как контракт |
| Journal event | Append-only факт о переходе или результате | Не переписывать старую строку; повреждение истории устранять поддержанным forward repair |
| Reconcile / terminal | Сведение доказательств к закрывающему исходу item | Закрывать только после реально выполненных объявленных проверок |
| Baseline lint | Снимок уже известных ошибок вне редактируемой фазы | Не скрывает новую ошибку и не превращает старую ошибку в разрешение на общий finish |

На обычном пути агенту достаточно выбранного item spec и его входов: `prepare` возвращает контекст, затем агент меняет продукт, выполняет объявленные проверки и закрывает item. Термины выше нужны для объяснения отказа или изменения Task, а не как список ручных операций на каждый fix.

## Один путь от design к исполнению

| Шаг | Источник истины | Проверка | Эффект |
|---|---|---|---|
| Design фазы | `plan.md`, `phases/Pn/Pn.md`, `phases/Pn/Pn.m.md`, решения владельца | Парсер фазы, локальные diagnostics | Меняются только авторские carriers |
| Finish всего плана (опционально) | Все объявленные фазы + `roadmap.md` | Полный lint, coverage, Routing/execution sheet | `plan-design` event `item_id=finish` с fingerprint исходных design-файлов |
| Общий design audit (только `**Design Audit:** required` или по запросу) | Тот же fingerprint, независимая оценка целого плана | `plan-work.py design-gate`; journal append проверяет fingerprint и наличие finish | `plan-audit` event `item_id=design`; при `required` только `audit-green` открывает execution |
| Start item | Выбранная группа Routing и route evidence текущего вызова | `plan_work.prepare` / `plan_recovery.start`: фаза и item детализированы (phase-scoped gate), authority, dependencies, bundle inputs | Один durable start; bundle материализуется для выбранного item |
| Closure | Реальные validation/evidence и terminal decision | `task_contract`, `terminal_policy`, `plan_reconcile` | Один terminal journal event, затем обновление видов |

По умолчанию gate phase-scoped: execution требует детализированных фазы и item, а не всего плана; остальные фазы могут оставаться skeleton/backlog. Строгий whole-plan режим (finish + GREEN audit по fingerprint) включается строкой `**Design Audit:** required` в `plan.md`; ниже описан именно он. Планы с `execution-sheet/v1` используют design gate уже сейчас. Для планов с датой от 2026-09-24 gate действует и без marker, поэтому его нельзя обойти удалением строки из нового плана. Планы 2026-09-22, начавшие исполнение до этого изменения и не имеющие marker, остаются на прежнем пути; marker у старого плана означает осознанное включение нового контракта. Пока хотя бы одна объявленная фаза остаётся skeleton, `plan-run` получает typed refusal. После исправления design нужно снова выполнить finish и audit на новом fingerprint. Сам `Next` не даёт права на старт.

## Классы данных

| Класс | Конкретные носители | Последствие отсутствия |
|---|---|---|
| Авторский контракт | `plan.md`, индексы фаз, item specs, `roadmap.md`, принятые решения | Нельзя доказать scope, dependency или маршрут; исправляется автором |
| Durable история | `journal.jsonl` | Нельзя утверждать start, finish, audit GREEN или terminal outcome; не восстанавливается из prose |
| Внешнее доказательство | Provider route/authority, owner grant, live validation | Нельзя изготовить из локального cache; запрашивается у источника на соответствующей границе |
| Восстанавливаемый вид | `status.md`, item states, decision views, bundles | Перестраивается детерминированным owner writer; stale вид не становится новым правилом |
| Передача/диагностика | Handoff receipt, context snapshot, diagnostic baseline | Привязывает конкретную передачу или попытку; его отсутствие не должно создавать новый product scope |

Optional design dossier (`research/Pn-design.md`, verified retrieval note, examples, capture/no-search record) появляется только когда компактного контракта недостаточно для свежего исполнителя. Если dossier объявлен, finish проверяет набор и ссылки. Не создавайте четыре пустых файла на обычную фазу. Изменение выбранного dossier после GREEN audit меняет design fingerprint.

## Владельцы инвариантов

| Инвариант | Владелец решения | Потребители |
|---|---|---|
| Допустимый item, группа и semantic route | `task_contract` + объявленный Routing | `plan_admission`, `plan_work`, provider adapter |
| Очередность producer → consumer | `plan_recovery` и `plan_readiness` | start, handoff, lint |
| Полнота design и актуальность общего audit | `plan_readiness.design_snapshot/design_gate` + journal event | `plan_work.prepare`, `plan_recovery.start`, `plan_delivery` |
| Полномочие на запись и закрытие | `task_contract`, `terminal_policy` | start, reconcile, delivery |
| Доказанный terminal outcome | `journal` | item state, status, receipt, downstream |
| Byte-fresh generated file | `plan_projection` + writer конкретного вида | lint, context snapshot, delivery |

`plan_delivery` представляет допустимое продолжение и проверяет handoff. Он не должен выводить новый законный переход из свободного текста `Next`. `command_render` представляет provider-команду; он не должен придумывать другой Routing. `plan_weight` измеряет reads/context, но не владеет authority. Если два модуля самостоятельно решают один из инвариантов, сначала устраните это дублирование; перенос файлов ради меньшего числа модулей не является целью.

## Где смотреть при отказе

0. `PLAN_DESIGN_INCOMPLETE` в phase-scoped режиме относится к фазе/item запуска: детализировать её (`task:plan-design <ID> Pn`). Пункты 2–4 применимы только при `Design Audit: required`.
1. `PLAN_DESIGN_INCOMPLETE`: проверить объявленные фазы, skeleton marker, обязательные поля item spec и открытые clarification.
2. `PLAN_DESIGN_FINISH_MISSING`: выполнить `finalize-design --finish` на текущих authored carriers; он не выполняет item.
3. `PLAN_DESIGN_AUDIT_MISSING` или `PLAN_DESIGN_AUDIT_NOT_GREEN`: проверить последний design audit в journal и исправить его замечания.
4. `PLAN_DESIGN_AUDIT_STALE`: сравнить fingerprint из `plan-work.py design-gate --plan-dir <dir>` с последним audit event; изменение authoring-файла требует нового finish/audit.
5. `PLAN_JOURNAL_INVALID`: в append-only истории есть строка вне схемы; установить её источник и применить поддержанный forward repair или историческое исключение. Не редактировать строку молча и не принимать её за GREEN.
6. После GREEN проверять уже локальные route, authority, producer readiness и bundle. Не перезапускать общий design audit из-за обычного тестового сбоя item.

## Проверка стоимости

`plan-work.py` выводит диагностические `metrics.wall_ms` и `metrics.payload_bytes` для каждого вызова. `payload_bytes` считает JSON до добавления самого metrics-блока; это размер возвращаемого контекста, не число provider tokens. Для локального design отдельно считайте число full lint вызовов и записанных bundles. Для item start считайте captures, journal scans, state/bundle writes и затронутые validation runs. Измеряйте один и тот же небольшой и длинный план до/после изменения. Точные provider tokens и денежная стоимость доступны только при настоящем provider receipt; не выводите их из размера локального файла. Cache или persistent index оправданы только после профиля, который показывает повторную работу на неизменных inputs.
