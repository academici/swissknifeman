# Аудит инструкций, продолжения исполнения и незавершённого roadmap

Дата: 2026-09-16. Short ID: `SKM-IA`. Автор: текущий Codex root, GPT-6 по конфигурации сессии; независимый Sol review не запускался.
База: `17f31648abe5ab90fcfda034e220e32d57b1f41e`.
Статус: исследование и статический аудит завершены; реализация 16 сентября зафиксирована в
приложении «Результат реализации» ниже.
Это отдельное исследовательское задание по запросу владельца, не executable plan и не phase audit.

## Вывод

Разделять инструкции по задаче нужно. Однако повторяющиеся остановки нельзя объяснить
только объёмом промпта или слабостью модели. Обнаружены три независимые группы причин:

1. Общий протокол заставляет исполнителя читать правила авторинга, аудита и передачи управления.
2. Runtime местами проверяет состояние в неправильном порядке и смешивает готовность
   отдельного пункта с admission всего последовательного batch.
3. Исправления исходников не всегда доходят до реально установленного provider hook.

Минимальная целевая система: короткие общие принципы, один выбранный режим работы,
компактный контекст текущего разрешённого объёма, инструкции по специальности по необходимости,
общие детерминированные операции подготовки/закрытия/продолжения. Успех определяется
acceptance всего запрошенного объёма. Перестановка заголовков не создаёт технического приоритета
над системными инструкциями платформы и не гарантирует завершения.

## 1. Что осталось в roadmap

Источники статуса: [живой каталог](../../roadmap/README.md), исходные incident records,
[результат 15 сентября](../2026.09.15-roadmap-field-fixes/README.md).
Архивный исходник сохраняет исторический статус; более поздний отчёт задания определяет остаток.

| Запись | Реальный остаток на момент аудита |
| --- | --- |
| [16 сентября: bundle/admission](../../roadmap/2026.09.16-SKM-PLAN-BUNDLE-ADMISSION-GAP.md) | Новая диагностика, Task-source remediation отсутствует. Bundle до snapshot, prose в Inputs, несогласованные views, batch scope, circular admission, evidence anchors, чужой run-report. Файл был untracked до аудита и сохранён без изменений. |
| [15 сентября: open-run final](../../roadmap/archive/2026.09.15-task-open-run-final-admission-regression.md) | `check-open` реализован и проверен локальными integration tests. Consumer rollout, recovered-session binding и полный native final path не приняты. Архив не означает отсутствие этого остатка. |
| [15 сентября: ресурсы CoreX](../../roadmap/archive/2026.09.15-corex-p3-local-resource-efficiency.md) | Частично исправлены parser/template/selected-item measurement. Открыты RSC-01 telemetry, RSC-04 стоимость повторного корпуса, RSC-05 current/future admission, RSC-06 recoverable finalize, RSC-07 volatile digests; RSC-09/10/11 требуют адресной проверки контрактов и field evidence. Точная диспозиция RSC-01…12 — в отчёте 15 сентября. |
| [14 сентября: session continuity](../../roadmap/2026.09.14-owner-session-continuity-regression.md) | Код и локальная доставка подтверждены предыдущим заданием; нужен поведенческий acceptance. Не реализовывать повторно по одному имени файла. |
| [14 сентября: owned dirty tree](../../roadmap/2026.09.14-task-owned-dirty-worktree-continuity.md) | Аналогично: field acceptance сохранения baseline и продолжения без ложного owner gate. |
| [14 сентября: native final](../../roadmap/2026.09.14-task-terminal-command-emission-regression.md) | Реальный вывод правильного fragment/launch там, где действительно есть handoff. Сохранённый receipt сам по себе не доказывает вывод в чат. |
| [14 сентября: Unicode bundle](../../roadmap/2026.09.14-task-unicode-cross-plan-bundle-regression.md) | Parser исправлен; consumer-domain authority остаётся отдельным условием. Не считать любой последующий missing bundle повтором Unicode-дефекта. |
| [Design vs exec](../../roadmap/plan-design-vs-exec-status-check.md) | Историческое предложение частично устарело: проверка подробности/готовности уже есть в `commands/plan-design.md:19` и протоколе §7. Сначала проверить нынешний путь выбора, не добавлять второй router. |
| [Lesson capture](../../roadmap/plan-lesson-capture.md) | В записи один замер потери post-closure owner finding; второй подтверждённый случай этим аудитом не установлен. |
| [Locale corpus](../../roadmap/2026.08.15-locale-corpus-after-field-validation.md) | Ждёт конкретного field effect; сплошной перевод не является лечением ложных финалов. |
| [Notify diet](../../roadmap/upstream-notify-diet-fork.md) | Ждёт измеренного drift/полезной диеты; `strategy: fork` уже существует. |
| [Memory hub service](../../roadmap/2026.07.25-memory-hub-service.md) | Отложен до многопользовательской/многомашинной потребности, ACL либо измеренной проблемы масштаба. Триггер здесь не проверялся. |

В сегодняшней записи есть важное внутреннее уточнение: первоначальная рекомендация проверять
все admission-ready items позднее ограничена запретом массового materialize будущих пунктов.
Принять следует разделение: статическая корректность объявлений при дизайне; реальная готовность
и materialization выбранного исполняемого фронта при запуске. Не превращать «будет готов» в
требование существования будущего результата сейчас.

## 2. Наблюдения с привязкой к исходникам

### F1 — Major: установленный Codex hook отстаёт от генератора

В текущем root `.codex/terminal-admission.env.ini` содержит `MODE=on`, а `.codex/hooks.json`
регистрирует `.codex/hooks/lifecycle.py`. Его `_terminal_admission()` на строках 412–419
возвращается при отсутствии `payload.terminal_admission` до обращения к Task.
В [генераторе](../../packages/harness/lib/harness/hooks.py) на строках 649–667 уже есть
`check-open` до этого return. В установленном dispatcher `check-open` отсутствует.

Это подтверждённый source/runtime drift текущего репозитория, не предположение о CoreX.
Без специального payload установленный путь не проверяет открытый run. Наличие `MODE=on`
не доказывает наличия нового поведения. Сам перехват финала текущим приложением не воспроизводился.
Причина совпадает с явной границей вчерашнего отчёта: rollout не выполнялся.
Исправлять через owning generator/installer; затем проверять actual native Stop на целевом runtime.
Ручная правка generated dispatcher не является решением. В рамках аудита runtime не изменялся.

### F2 — Major: open item и незавершённый workset — разные условия

[terminal_admission.pre_final_open_runs](../../packages/task/lib/task/terminal_admission.py)
на строках 433–478 перебирает journal subjects текущей provider session и запрещает final,
если latest execution event имеет `in-progress`. Не начатый следующий участник batch не создаёт
такого event. После закрытия первого участника и до старта второго этот конкретный guard
не может доказать незавершённость всего запроса. Optional lease проверяется отдельно и
не превращает отсутствие open item в доказательство выполнения workset.

Это статически подтверждённый пробел покрытия guard, согласующийся с сегодняшним incident
`P5.2 P5.3`; exact native transport этого incident здесь не replayed. Сохранять разрешённый
набор и его остаток нужно через существующие batch/run/checkpoint carriers. Проверка завершения
должна видеть весь набор, включая ещё не начатые пункты. Пустой open-run список — недостаточный критерий.

### F3 — Major: рекомендованный последовательный batch проверяется как одновременно готовый

[task_contract.admit_batch](../../packages/task/lib/task/task_contract.py) на строках 807–849
при `recommended` без receipt перебирает все `requested`, проверяя каждый bundle,
producer readiness и terminal evidence producer. Если второй участник зависит от результата
первого, legitimate старт первого может получить `BATCH_STALE` из-за второго.

Today's incident описывает этот случай; код подтверждает механизм. Правильное разделение:
admit разрешённое membership/order, затем проверить ready frontier для запуска. После каждого
закрытия продвигать completed prefix и проверять следующего потребителя. Не фабриковать GREEN
producer и не считать произвольно изготовленный receipt универсальным обходом admission.

### F4 — Major: snapshot предшествует восстановлению необходимых ему projections

[plan_context.capture](../../packages/task/lib/task/plan_context.py) на строках 131–148
валидирует request и читает пять файлов; отсутствующий bundle становится `PLAN_CONTEXT_TRUNCATED`.
[plan_recovery.start](../../packages/task/lib/task/plan_recovery.py) также использует capture;
`materialize_next_ready` генерирует одного successor после terminal producer, что не покрывает
любой допустимый прямой вход в незапущенную фазу.
[plan_gates.lint_bundle_freshness](../../packages/task/lib/task/plan_gates.py):789 фильтрует
ready items по активной фазе. Эти пути имеют разную область готовности.

Нужен preparation для выбранного входа: validate request → разобрать source declarations →
восстановить допустимые derived carriers → capture. Проза в Inputs требует точного diagnosis;
механически однозначное перенесение текста допустимо только с сохранением источников,
обязательств и authority. Не всякая prose-entry автоматически безопасна для удаления.

### F5 — Major: общий protocol смешивает режимы и несёт неоднозначные остановки

[Канонический protocol](../../packages/skiller/skills/general/plan-protocol/SKILL.md)
и [Task runtime](../../packages/task/runtime/plan-protocol/SKILL.md) побайтно совпадают:
34 122 bytes, 470 строк. Все три команды design/exec/run требуют его чтения.
Общий файл включает authoring metadata, phase assurance, audit consent, repair schemas,
runtime API, handoff formatting и `DESIGN-ROOT-TERMINAL`.

В §4 обычный repairable failure требует продолжения, а §7 одновременно использует
`fails closed` для missing carrier и reproduced acceptance failure. Эти положения совместимы
при трактовке «не совершать защищённую запись до исправления», но не объясняют одинаково ясно,
что отказ операции не означает terminal ответ владельцу.
§6 отдельно запрещает design-root исполнять successor даже при первоначальном запросе,
упоминающем последующую реализацию. Это сознательная локальная политика, не требование OpenAI
или Anthropic; она шире сохранения отдельно запрошенной design-only границы.

Причинность «именно эта фраза вызвала конкретный final» не доказана. Доказаны совместная загрузка
и потенциально конкурирующие трактовки. Убрать нерелевантные режиму процедуры из обязательного
чтения; определить fail-closed на уровне операции и явные условия завершения invocation.
Пересмотр design-root boundary — отдельное решение о семантике, не скрытая косметическая правка.

### F6 — Major: закрытие остаётся набором зависимых операций

[plan-exec](../../packages/task/commands/plan-exec.md):72 и §6 протокола требуют journal,
changed projections, item/eligible phase close, successor, delivery. Сегодняшняя запись
фиксирует terminal journal со stale owner views; RSC-06 вчера оставлен частично открытым.
`materialize_next_ready()` может вернуть `None` на `unresolvable_entry`.

Претензия не к наличию доказательств. Проблема — обязанности модели вручную координировать
восстановление после частичного успеха. Нужна одна идемпотентная последовательность поверх
существующих владельцев состояния с resume от durable события. «Одна операция для агента»
не означает ложное обещание ACID-транзакции между всеми файлами и внешними действиями.

### F7 — Major: диагностический report нельзя считать принадлежащим проекту по каталогу

[core.runs.find_run_report](../../core/runs.py):110 выбирает JSON по session имени или mtime
и декодирует его без проверки внутренней identity. Сегодняшний incident фиксирует чужой
report в каталоге CoreX и ложные RED-причины. Сам helper не доказывает отсутствие всех
проверок у каждого caller, поэтому глобальная уязвимость всех consumers не заявляется.

Проверить identity project/session/provider в пути использования отчёта; чужой или stale
report означает недостоверность диагностики, а не дефект продукта. Отсутствующий telemetry
не должен превращаться в нулевую стоимость или доказанный блок исполнения.

### F8 — Minor: живой каталог скрывает существенные остатки за архивной диспозицией

16 сентября файл ещё не отражён в таблице, а записи 15 сентября перемещены в archive с
остатками в task report. Это объясняет, почему владелец вспоминает «ещё вчерашний незавершённый».
Один индекс должен показывать implementation / delivery / field acceptance раздельно,
со ссылкой на одного владельца остатка. Не создавать для каждого уровня отдельный backlog.

### F9 — Major: CoreX design seal инвалидируется обычным execution bookkeeping

Дополнительный пример владельца в ходе аудита: P5.4–P5.6 остановлены до product writes
из-за missing bundles, `DESIGN_PENDING: finish does not cover all stable design inputs`
и Q-P2-014/015/020/021/022. Выполнена адресная read-only проверка живого CoreX
`/home/vostrikov/projects/packages/corex`, HEAD `b939435d04abb4ee2611ecee2925b24ad03b6de8`.
Рабочее дерево содержит текущую работу другого исполнителя; оно не изменялось.
План: `2026.09.15-№1-COREX-FLEXCRM-REMAINING`.

В его `scripts/task-check.py:12` функция `design_inputs()` рекурсивно включает ВСЕ файлы
`brief`, `research`, `decisions`, а также `open-questions.md` и все item specs.
В `design_ready():95` требуется полное равенство множества текущих путей и прежней seal-таблицы,
затем совпадение всех hashes. Перед каждым item это обязательный `--check design`.

Фактический read-only запуск дал exit 1 с точным сообщением владельца. Сравнение:

```text
expected_count = 669; sealed_count = 668
unsealed = decisions/D38-p5-wakeup-adoption.md
removed = []
changed = decisions/_archive.md, decisions/_current.md, decisions/_index.md,
          open-questions.md, phases/P4/P4.7.md, phases/P4/P4.8.md,
          phases/P5/P5.2.md, phases/P5/P5.3.md
bundles/P5.4.json, P5.5.json, P5.6.json = absent
```

D38 — принятое разрешение для уже исполнявшихся P5.2/P5.3. `_archive/_current/_index` —
генерируемые decision views. Поэтому текст «stable design inputs» не соответствует фактической
области проверки: она содержит изменяемое состояние исполнения. Изменения item specs отдельно
могут быть содержательными; они требуют delta assessment, а не автоматического удаления из seal.
Но обновление generated index само по себе не доказывает необходимость нового дизайна.

Это уточняет RSC-07 и F5/F6: причина находится также в **проектном checker**, а не только
в shared Task skill. Доставка нового SKM не исправит такой consumer checker автоматически.
Нужны stable normative inputs отдельно от volatile projections, квалификация изменённого
содержательного scope и повторное использование неизменных доказательств. Простая перепечатка
всех текущих hashes без проверки смысла изменений не является честным восстановлением review.

У всех трёх item `Inputs` снова содержит свободную процедурную прозу, что совпадает с F4.
Генерация этих bundles в текущей проверке не запускалась; их отсутствие подтверждено,
а ошибка генератора взята из нового сообщения владельца и сопоставлена с объявлениями.
P5.6 явно зависит от actual GREEN P5.1–P5.5: его полная runtime readiness до P5.4/P5.5
не должна быть условием старта всего последовательного запроса P5.4–P5.6.

В `findings/P2-gate-requests.md` Q-P2-014/015 и Q-P2-020/021/022 имеют `proposal` и требуют
отдельного matching receipt до adoption. D38 относится только к Q-P2-018/019, P5.2/P5.3.
P5.1 engine qualification подтверждает source/license/upstream proof, но отдельно оставляет
CoreX binding/schema acceptance следующим items. Отсутствие всех возможных grants во всех
внешних сессиях здесь не доказано. Исполнитель обязан сначала найти и сопоставить уже выданное
разрешение, а не спрашивать повторно и не считать фразу `proposal` вечным запретом.

Правильная реакция на такой preflight состоит из трёх разных действий:

1. Самостоятельно восстановить однозначные plan-owned carriers и квалифицировать seal delta.
2. Запустить разрешённый ready frontier, оставив будущие зависимости будущим пунктам.
3. Для действительно отсутствующего решения подготовить точный candidate/compatibility/evidence,
   сверить с существующей authority и только затем вынести один оставшийся вопрос владельцу.

`artifacts/design-finish.md` заявляет verified review, но явно сохраняет actual adoption gates.
Это не обещание полной execution readiness всех 78 items. Системный UX-дефект — подавать такой
результат как «план готов к беспрепятственному выполнению», не показывая заранее карту реально
остающихся решений и не обеспечивая automatic repair обычных execution deltas.

К acceptance будущего исправления добавить: после GREEN producer и добавления законного
adoption decision следующий пункт не получает общий `DESIGN_PENDING` из-за generated views;
настоящая несовместимая правка contract по-прежнему обнаруживается. Проверять отдельно
дизайн-корректность, разрешённый execution scope и текущую готовность frontier.

## 3. Что говорят первичные источники

Проверено 2026-09-16. Perplexity опрошен дважды: сначала о hierarchy/discovery/stopping,
затем с критикой предлагаемого разделения и проверкой failure modes. Его синтез использован
как список направлений проверки, не как доказательство. Открыты официальные страницы:

| Источник | Проверенный факт и практический вывод |
| --- | --- |
| [OpenAI: model guidance](https://developers.openai.com/api/docs/guides/latest-model#instruction-following) | Документация прямо связывает неясные/конфликтующие skills с ранними остановками и советует явно сохранять приоритет пользовательских указаний над skill guidelines. Это поддерживает гипотезу, но не устанавливает причину нашего конкретного incident. |
| [OpenAI: AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) | Discovery global + root→cwd, один подходящий файл на каталог, override precedence, project-doc cap по умолчанию 32 KiB. Это порядок загрузки инструкций, а не возможность поставить файл выше системных ограничений. |
| [OpenAI: skills](https://learn.chatgpt.com/docs/build-skills) | Первичный список metadata и загрузка тела при выборе; explicit и implicit invocation. Доступные skills ещё не означают, что все тела загружены. Два одинаковых имени не сливаются. |
| [Claude Code: memory](https://code.claude.com/docs/en/memory) | CLAUDE.md — контекст, а не строго исполняемая конфигурация; рекомендуются краткость и path-scoped rules. Imports сами по себе не экономят startup context. |
| [Claude Code: skills](https://code.claude.com/docs/en/skills) | Тело загружается при вызове и остаётся в истории между turns. `disable-model-invocation: true` запрещает автоматический выбор; это не таймер выгрузки уже прочитанного текста. |
| [OpenAI: hooks](https://learn.chatgpt.com/docs/hooks#stop) | Stop `decision: block` создаёт continuation prompt; `continue: false` другого matching hook имеет приоритет. Регистрация и фактический вызов должны быть проверены. |
| [Claude Code: hooks](https://code.claude.com/docs/en/hooks#stop) | Stop может требовать продолжение, но после 8 последовательных блокировок host заканчивает turn. API failure идёт через StopFailure, не через обычный Stop. Hook не гарантирует бесконечный непрерываемый запуск. |

Не переносить настройки одного provider в другой механически. В частности, упомянутый
Perplexity ключ Codex `allow_implicit_invocation` на открытой текущей странице skills не найден:
не использовать его как подтверждённое основание миграции без проверки schema установленной версии.
Не путать лимит project AGENTS.md с размером прочитанного SKILL.md: 34 КБ protocol не доказывают
нарушения лимита AGENTS. Точные provider role priorities проверяются отдельно от порядка файлов;
проектные слова «верхний слой» не меняют system/developer authority.

## 4. Предлагаемое разделение

Это проектное предложение аудита, не уже включённая политика.

| Слой | Содержание | Когда доступно |
| --- | --- | --- |
| Общие принципы проекта | Довести разрешённый результат до acceptance; честные доказательства; сохранять чужую работу; локальный обратимый repair; реальные границы authority | Всегда, короткий текст |
| Выбранный режим | Design, execute или review: цель, допустимые действия, критерий завершения | Одна явно выбранная команда/задача |
| Контекст исполнения | Разрешённый workset, текущий item, зависимости, acceptance, область изменений, доказательства и remaining | При execution; восстанавливается из существующих carriers |
| Специальные инструкции | Язык, framework, миграции, безопасность, API, схемы конкретного изменяемого компонента | По изменяемому риску и месту работы |
| Runtime | Admission, materialization, close/reconcile, recovery, completion verdict | Код/CLI; агент получает краткий результат и следующий допустимый шаг |

Разделение по режиму — не запрет исполнителю думать. Исполнитель выбирает алгоритм,
группирует проверки, исправляет тесты и локальные дефекты, сохраняя цель и контракт.
Дизайн нужен, когда обнаружен действительно новый неразрешённый результат/контрактный выбор,
а не когда нужно принять обычное инженерное решение внутри уже одобренных границ.

### Что оставить исполнителю

Короткий контракт: восстановить разрешённый набор; подготовить первый готовый пункт;
выполнить и проверить; закрыть и согласовать state; продолжить remaining. Независимые чтения
и проверки можно batch; зависимые записи и проверки producer/consumer — последовательно.
Внутри разрешённого объёма item/phase transition сам по себе не требует нового процесса.
Batch не должен расширять authority или отменять реальные атомарные/публичные ограничения.

Не загружать исполнителю authoring templates, правила назначения ID, полную механику
phase-audit consent и дизайнные terminal launch процедуры. Дать ссылки на них соответствующим
режимам. Общие schema definitions могут оставаться единым источником для кода; это не означает
обязанность модели каждый раз прочитывать весь schema handbook.

### Как определять необходимость дизайна

Уже существует [plan_repair.evaluate](../../packages/task/lib/task/plan_repair.py):216,
в том числе `design-required`. Не добавлять отдельного обязательного LLM-судью на каждый шаг.
Использовать существующую классификацию, упростив нормальный путь:

- Однозначный generated drift, отсутствующий вывод генератора, локальная ошибка теста:
  repair → affected validation → continue.
- Недостаточно фактов: адресная проверка → классификация; неопределённость сама по себе не design.
- Новая цель, несовместимое расширение frozen/public contract или отсутствующая authority:
  сохранить точный вопрос, варианты и затронутый остаток; продолжить независимую разрешённую работу.
- Явно заказанный design-only/review-only результат: вернуть именно его без начала реализации.

Перед переносом авторинга из общего protocol сохранить значение существующих frozen contracts.
Нельзя под видом оптимизации забыть обязательную validation, удалить неудобный source input
или ослабить security. Но оформление отчёта и full protocol reread не должны заменять продуктовую работу.

### Загрузка и время жизни

Skill metadata → выбранное тело → нужные references уже поддерживаются платформами.
Главная работа здесь — сделать тела действительно узкими и устранить дубли в exec/run/protocol.
Файл, прочитанный при дизайне в этом же разговоре, не исчезает автоматически после выбора execute.
Поэтому правила должны явно ограничивать собственную область действия, а resume должен приносить
короткий контекст текущего режима. Новая сессия оправдана измеренным context/capability boundary
или запросом владельца; делать её обязательной ради каждой смены команды слишком дорого.

## 5. Почему одного «не останавливайся» мало

Completion нужно вычислять по разрешённому workset и его acceptance, а не по последнему
GREEN item или наличию красивого final. Отдельно различать завершение результата, допустимое
возвращение управления владельцу и техническое прерывание процесса.

Нормальное исполнение: ready item → реализация/проверка → durable terminal → reconcile →
следующий разрешённый ready item. Final разрешён после всего запрошенного результата либо
честной подтверждённой границы/owner stop. Crash/API failure сохраняет незавершённый результат
и возможность resume; не превращается в success. Бесконечно блокировать Stop без материального
прогресса нельзя: это перенос сбоя в дорогой цикл, а у provider есть собственные пределы.

Current close и future start требуют отдельных verdict. Неготовность будущего внешнего
consumer не должна отменять достоверное закрытие текущего результата; она определяет
дальнейшее продолжение. И наоборот, успешное закрытие producer не разрешает начать consumer
без его реальных обязательных входов.

## 6. Как измерить эффект без нового дорогого ритуала

Из [полевого отчёта CoreX](../../roadmap/archive/2026.09.15-corex-p3-local-resource-efficiency.md):
5 compactions, из них 3 до первого product START; 3 467 194 символа tool output;
13 мин 5 с после terminal второго пункта. Это сильное свидетельство процессных расходов,
но не эксперимент о причинности instruction overload. 46,5 млн cumulative input нельзя
называть свежим расходом: 97,04% были cached; оценки цены и обещанного процента экономии нет.

Предлагаемый первый эксперимент: небольшой фиксированный набор сценариев, одинаковые
repo snapshots, provider/model/effort, scope, checks и инструменты. Сравнивать исходный baseline,
только prompt split, только runtime fixes, затем сочетание. Не менять одновременно модель,
разрешения и задачу. По три повторения на сценарий — первичный сигнал, не статистическая гарантия.

| Сценарий | Проверяемый результат |
| --- | --- |
| Два зависимых пункта одним запросом | Первый стартует без terminal evidence, которое ещё должен создать; второй выполняется без нового owner turn |
| Первый закрыт, второй ещё не стартовал | Completion guard видит remaining workset |
| Missing selected bundle | Preparation восстанавливает его либо выдаёт точную repair diagnosis до snapshot |
| Новый execution decision + обновлённый generated decision index | Нет полного design replay; содержательный contract delta проверяется отдельно |
| Inputs содержит path + prose | Нет fabricated future evidence; сохраняются смысл и источники |
| Terminal journal, stale views, interruption | Идемпотентный resume; один durable start/terminal, согласованный статус |
| Dirty baseline и обычный failed check | Локальный repair без redesign/новой сессии, чужие изменения сохранены |
| Новый реальный контрактный выбор | Design escalation адресная; нет неразрешённой реализации |
| Один явно запрошенный item выполнен | Честный final, соседний item не выполняется самовольно |
| Owner stop / external wait / API failure | Нет fabricated GREEN и бесконечного Stop-loop; есть корректный resumable результат |
| Compaction/resume/model change | Сохранены authority, remaining и current evidence; route проверяется по существующему механизму |
| Чужой run-report | Диагностика отвергает чужую identity, не красит продукт |
| Обычный вопрос вне Task | Никакого навязанного plan lifecycle |

Основные метрики: false finals, лишние owner turns, ненужные design launches,
повторные чтения неизменных источников, время до product START, post-terminal time,
fresh/cached/output tokens раздельно, compactions, actual instruction bytes.
Отдельно считать runtime crashes и восстановление. Успех первой квалификации: все обязательные
сценарии корректны и ни один отрицательный authority/security сценарий не стал permissive.
Затем хотя бы один реальный consumer batch на каждом используемом provider; source unit tests
не подменяют эту acceptance. Целевые проценты экономии устанавливать после сопоставимого baseline.

## 7. Кто делает и в каком порядке

Этот аудит выполняет текущий root: контекст уже собран, повторять исследование другой моделью
с нуля сейчас невыгодно. Sol полезен для одного независимого ревью конкретного design/diff:
проверить, не потеряны ли authority, recovery и весь разрешённый workset при упрощении.
Сравнительный benchmark Astra/Sol не проводился; рекомендация о разделении ответственности,
а не утверждение о превосходстве модели. Обычную реализацию можно поручить Sol по ограниченному
контракту и проверять результат теми же сценариями.

Рекомендуемый порядок будущей работы:

1. Довести уже имеющийся `check-open` до целевого runtime и проверить actual Stop;
   добавить completion coverage remaining workset и recovered session. Не обещать исправление
   всех ложных финалов одним обновлением hook.
2. Устранить admission/preparation/finalization причины F3/F4/F6 существующими владельцами;
   проверить fault/restart и current-close vs future-start.
3. Разделить common/design/execute/review content у canonical source, регенерировать adapters;
   для design-root-terminal принять явно сформулированное решение о границе.
4. Провести компактное сравнение и реальные consumer runs; закрывать field acceptance по факту.

Объединять связанные исправления по общей причине и проверке, не плодить item на каждый
reason code. Это очередь предложений, не разрешение на rollout или изменение consumer contracts.

## 8. Покрытие и ограничения проверки

Прочитаны живой roadmap/index, сегодняшняя диагностика, вчерашняя диспозиция и ресурсные
измерения, relevant incident addenda, Task commands/protocol, ключевые admission/context/
recovery/terminal/lint/repair seams, source hook generator и установленный Codex dispatcher.
Другие отложенные темы классифицированы по их записанным triggers, без fleet inventory.
Все рабочие consumer installations и исходные чужие transcripts заново не сканировались.
После дополнительного сообщения владельца адресно прочитан CoreX P5.4–P5.6, его D4/D38,
P2 gate/catalogue, P5.1 qualification, design-finish и owning checker; его design failure
воспроизведён read-only, точное сравнение seal приведено в F9.

В этом аудите выполнено:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/task/lib:packages/task/tests:. \
  python3 -m unittest test_terminal_admission test_task_contract.BatchRoutingAdmissionTests
22 tests — OK, 0.173 s.
```

Это существующие ограниченные tests: они подтверждают текущие покрытые ветви, а не закрывают
перечисленные пробелы. Полная package qualification и native behavioral runs не выполнялись:
runtime/package code не менялся. Изменены только отчёт, навигация roadmap и provenance источников.
Новых runtime dependencies, правил, generated carriers, release или consumer rollout нет.
`git diff --check` прошёл; локальные ссылки самого аудита проверены без missing targets.
Более широкий filesystem-only scan двух существующих индексов обнаружил пять старых ссылок
на отсутствующие пути (три LEAN-EXECUTION, две skill-rules-sidecar) и один site route
`/analyst/guide/pathologies`, который этим способом не проверяется. Полная link qualification
сайта не заявляется; эти прежние ссылки данным заданием не изменялись.

Контрольные SHA-256 на момент чтения:

- canonical и runtime `plan-protocol/SKILL.md`: `7428a1bbec8783ad28d4c2bf902b44930e8f3f9d6a948f1c37e63434d1b72ada`;
- установленный `.codex/hooks/lifecycle.py`: `f583d95d29eb12299aa7f47801a4e3830db5784d315a5e6ffb96e36139a78979`.

Root AGENTS.md: 9 004 bytes; CLAUDE.md: 9 390; plan-exec: 8 854; plan-run: 5 552;
plan-design: 2 436. Это размеры файлов, не число токенов текущего запроса и не полная стоимость
always-on context. Нужен provider-visible inventory для полного attribution.

## 9. Результат реализации — 2026-09-16

Рекомендации F1–F9 реализованы как одно ограниченное задание без запуска продуктовых
CoreX P5.4–P5.6, публикации релиза или fleet rollout. Существующие dirty worktrees SwissKnifeMan
и CoreX сохранены; чужие product/plan изменения не откатывались и не переписывались.

| Finding | Реализованный результат |
|:--|:--|
| F1 | Codex lifecycle renderer получил versioned adapter `1.1.0`; owning Harness installer обновил `.codex/hooks/lifecycle.py` и provider lock. Установленный dispatcher вызывает `check-open` до optional lease. |
| F2 | `pre_final_open_runs()` читает session-bound batch receipts и запрещает final с `TASK_WORKSET_INCOMPLETE`, если после terminal producer остался незапущенный member без legitimate terminal boundary. |
| F3 | Recommended batch связывает ordered owner-requested membership пустым completed prefix и проверяет только текущий frontier. Prefix продвигается лишь по durable terminal evidence; обратный порядок отклоняется. |
| F4 | `plan_recovery.prepare()` выполняет validate → state/bundle materialize → readiness → snapshot → live freshness. Неразрешимое объявление возвращает `PLAN_BUNDLE_UNRESOLVABLE`, exact entry и exact recovery command; concurrent journal change остаётся fail-closed. |
| F5 | Обязательные инструкции разделены на `common-principles.md`, `design-mode.md`, `execution-mode.md`, `review-mode.md`. Полный protocol остаётся canonical on-demand reference; Claude/Codex projections регенерированы owning generator (`task.codex-command/1.0.15`). |
| F6 | Добавлен `task.plan_reconcile.reconcile_terminal()` и CLI `plan-reconcile.py`: lock, terminal truth, state/decision/status owners, один ready successor bundle, freshness и receipt. Повтор после прерывания идемпотентен, journal не дублируется. |
| F7 | Legacy run-report сверяется по session/provider и, когда caller знает identity, project ID; `cwd` и абсолютные `files_changed` проверяются независимо. Конфликт даёт `RUN_REPORT_PROJECT_MISMATCH`, `ATTENTION` и исключает чужие RED-причины. |
| F8 | Живой roadmap теперь различает source/local runtime GREEN и оставшийся field acceptance. |
| F9 | В owning CoreX checker generated decision views, `open-questions.md` и item-scoped execution grants исключены из design seal. Design/phase decisions, brief/research, validators и все item specs остаются содержательными inputs; их изменение по-прежнему ломает seal. |

Design lint dry-renderит каждый nonterminal `admission_state=ready` + `admission_pass=true`
item, включая будущую неактивную фазу, но не сохраняет его bundle. Persistent materialization
остаётся ограниченной выбранным frontier. Это закрывает противоречие между исходной рекомендацией
roadmap и запретом массово создавать будущие carriers.

### Qualification и адресные сценарии

Финальные зелёные прогоны:

```text
bash packages/task/scripts/validate.sh       — 1107 tests, OK (1 skipped)
bash packages/maind/scripts/validate.sh      — 559 tests, OK
bash packages/harness/scripts/validate.sh    — 656 tests, OK
bash packages/skiller/scripts/validate.sh    — 700 tests, OK; registry/checks GREEN
bash packages/analyst/scripts/validate.sh    — 262 tests, OK
python3 -m unittest discover -s core/tests   — 284 tests, OK
CoreX scripts/test-design-guards.py           — 17 tests, OK
CoreX scripts/task-check.py --check design    — PASS
Task provider renderer --check                — no-op
Harness Codex lifecycle dry-run               — clean/noop
docs-sync --check                             — все package copies свежи
Task standalone docs build                    — PASS
mAInd standalone docs build                   — PASS
umbrella docs build                           — PASS
git diff --check (оба репозитория)             — PASS
```

Адресная regression matrix подтверждена отдельными тестами: recommended frontier + empty prefix;
remaining workset после GREEN первого member; missing deterministic bundle repair; exact prose
entry diagnosis; future-phase dry render; interrupted reconciliation + retry без второго journal
event; foreign report → ATTENTION без RED. Первый вызов future-phase теста содержал неверное имя
test class; корректный exact selector и полный Task corpus прошли.

Установленный `.codex/hooks/lifecycle.py` дополнительно вызван напрямую с provider-shaped Stop
payload на изолированном временном проекте. Без open work он вернул allow/no output; с durable
`in-progress` — `TASK_OPEN_RUN_FINAL_FORBIDDEN`; с terminal первым member и незапущенным вторым —
`TASK_WORKSET_INCOMPLETE`. Это проверка фактических установленных байтов, не fabricated product
receipt. SHA-256 dispatcher: `2defe1978bcf0cb91889a5ca4132a7ef98812de101c0728c238f366371497448`.

При qualification были три исправленных transient failure: устаревший Task literal обнаружил
оставшуюся adapter-фразу capture-before-prepare; PTY ошибочно активировал prompt Skiller installer
(повтор без TTY GREEN); Analyst absolute-path fixture корректно попал под новый provenance guard и
был заменён на portable relative paths. Aggregate docs build также выявил source links в `tasks/`
вне VitePress `srcDir`; они явно классифицированы рядом с уже разрешёнными `roadmap/` links.

### Оставшиеся границы

- Реальный consumer/provider conversation с выполнением двух product items и transport-level final
  не запускался: это оставшийся field acceptance, а не source defect. Синтетический native Stop
  replay покрывает installed dispatcher и Task CLI, но не утверждает, что уже открытая provider
  session перечитала регистрацию hook.
- Перенос незавершённого workset в новую provider session требует явного recovery binding; текущий
  completion guard намеренно session-bound и не угадывает authority по чужой сессии.
- CoreX P5.4–P5.6 не исполнялись и их product acceptance не заявляется. Исправлен только owning
  design checker и его seal/tests; release и fleet rollout остаются вне scope.
- Existing Skiller warning baselines (description debt, pressure coverage и discovery budget)
  сохранены как warnings; они не были расширением этого задания.

Canonical/runtime protocol после генерации совпадают: SHA-256
`8d90360f04009ab98d2709c28676ecc73caf6dd59fe3aa5cc0f30b7d2f5422b7`.
