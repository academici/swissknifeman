# Сравнительный пилот и передача Claude Code

Ниже конкретное задание для следующего этапа. Пилот **ещё не запускался**; он потребует authenticated CLI runs и расхода соответствующих аккаунтов. Это не незаметное продолжение текущего документального аудита.

## Что сравниваем

| Вариант | Что использовать | Что не подменять |
| --- | --- | --- |
| Baseline | Strong native CLI, deterministic Task context, одинаковые checks | Не сравнивать сложный pipeline с baseline без нужного review |
| A | Минимальный native JSONL runner с одним runtime owner | Не разрабатывать весь аналог CAO до измерения |
| B | Pinned CAO Python workflow + небольшой Task adapter | Не накладывать scheduler Artifex сверху |
| C, если нужен JS | Pinned Vercel HarnessAgent и проверенный sandbox/auth | Не считать docs sandbox example локальным CLI запуском |

Сначала baseline и B; A проверяется узким spike на тех же inputs и failure cases. Если оба требуют неподходящего объёма работы, резерв — Agent Orchestrator. Включать все кандидаты в первый платный эксперимент необязательно.

## Предварительная проверка capabilities

Зафиксировать version/commit/artifact каждого engine и native CLI, cwd, native auth route без вывода credentials, разрешённые models и profiles. CAO baseline — tag `v2.5.1`; затем отдельно проверить изученный main, если parser fixes нужны целевым CLI. Различие PyPI/GitHub записано в [версии](research/cao-versions.json).

Для каждого провайдера выполнить маленькие probes: structured/terminal output, requested model/effort, effective native restrictions, skill loading, session ID, completion, timeout, quota classification. Это платные/аккаунтные проверки следующего этапа, не результаты текущей работы. У Grok в CAO нужно отдельно решить отсутствие явного effort binding.

Учесть parallel migration edits из [source ledger](research/concurrent-source-changes.json): missing historical route должен приводить к явному решению о запуске, а non-shell validation procedure нельзя автоматически превратить в выдуманную команду или exit 0.

Протестировать plan-bound read и свободный reviewer без Task. Установленные commands должны разрешаться через реальный consumer entrypoint; запрещено принимать успех только в monorepo, если заявлена переносимость.

## Шесть типов representative задач

1. Маленький локальный исправляемый bug с ясным regression check.
2. Механическое изменение нескольких файлов с независимыми work units.
3. Backend задача с зависимостями и сложным invariant.
4. Frontend component с состояниями, responsive behavior и визуальной приёмкой.
5. Review-only diff без изменения canonical plan.
6. Plan item с завершением units и автоматическим lifecycle фазы, на disposable plan/repo.

Использовать реальные типичные задачи проекта, а не задачи, искусственно удобные одному engine. Исходный repo/base commit, requirements, inputs, checks, skills и policy одинаковы. Для первого сигнала — три независимых повтора каждого типа в сравниваемых вариантах. Если результаты близкие, выборка расширяется; 18 runs не доказывают долгосрочную надёжность.

У frontend дешёвому исполнителю давать bounded unit с design contract. Отдельный вариант оставляет full implementation сильной модели. Reviewer включается одинаково во всех вариантах соответствующей задачи; в остальных выключен. Все changes остаются в disposable worktrees до приёмки.

## Метрики

| Группа | Что записать |
| --- | --- |
| Качество | Acceptance pass, tests, реальные defects, scope violations, frontend criteria |
| Экономика | Известные input/output/cache usage, API cost либо subscription quota; unknown отдельно |
| Задержка | Полное время, запуск CLI, модельные стадии, ожидание лимитов |
| Ремонт | Повторы, strong escalation, ручное время владельца, число незапланированных handoffs |
| Наблюдаемость | Видны ли stage/route, tool output, блокировка, причина остановки, последнее событие |
| Сопровождение | Объём adapter code, fixes в engine, version-specific exceptions, recovery logic |
| Переносимость | Тот же input/checks на втором backend, reviewer без plan dependency |

Не оценивать надёжность количеством stars или размером README. Не присваивать скрытые нулевые costs неизвестному usage. Считать стоимость принятого результата с неудачными runs в знаменателе затрат.

## Failure injection и ожидаемая реакция

| Случай | Ожидаемый результат |
| --- | --- |
| Убить CLI во время tool execution | Unknown/failed outcome; dependent stages не стартуют, diff сохраняется |
| Убить workflow script/наш runner | Остаточные процессы обнаруживаются, resume не создаёт параллельный duplicate worker |
| Убить CAO server после terminal launch | Связь с orphan terminal восстанавливается либо явно фиксируется неизвестный исход |
| Crash после commit/Task effect до receipt | Reconcile фактическое состояние; второй effect не выполняется вслепую |
| Прервать запись journal/disk-full | Явная resumability degradation; отсутствие receipt не становится success |
| Изменить plan/profile/skills при resume | Source drift обнаруживается; старый replay не выдаётся за результат новых instructions |
| Изменить порядок завершения parallel units | Устойчивые step/unit identities; результат не перепутан |
| Подать quota/auth/provider error | Отличается от task failure; нет скрытого model downgrade |
| Агент пишет вне scope или reviewer редактирует код | Нарушение обнаруживается, acceptance не проходит |
| CLI изменил TUI/event format | Явная несовместимость/unknown, без ложного success |
| Duplicate запуск одного item | Один владелец workspace/lifecycle; второй run не пишет plan одновременно |
| Cancel во время долгого shell tool | Проверены descendants, terminals и locks, не только workflow PID |

Нужны реальные process/tree/state проверки. Модельный ответ «отмена успешна» не является результатом этой проверки.

## Предлагаемые gates выбора

Это критерии для согласования перед пилотом, а не доказанные пороги отрасли:

- **Корректность:** ни один непринятый результат не закрывает item; все mandatory acceptance проходят.
- **Восстановление:** нет неучтённого повторного commit/Task mutation; ambiguous effects останавливают run с диагностикой.
- **Routes:** обязательные provider/model/effort установлены или запуск явно отказал; отсутствует скрытое понижение.
- **Контекст:** все mandatory reads доступны, completeness текущего Task не ухудшена.
- **Наблюдаемость:** владелец видит доступный stream/terminal и может определить зависшую стадию.
- **Экономика:** использовать splitting лишь для классов задач, где total accepted cost/quota/время дают повторяемую пользу при сопоставимом качестве.
- **Сопровождение:** CAO adapter не воспроизводит целиком scheduler; own runner не скрывает недостающий recovery за happy-path demo.

При нарушении correctness/recovery gate выбранный engine не становится основным. Если ошибки устранимы малыми upstream fixes, повторяются соответствующие failed cases. Если требуется большой fork, обновляется comparison of maintenance cost и рассматривается A. Производственная миграция и удаление старого driver — после успешной parity, не до неё.

## Как передать пакет Claude Code

Начать с [README](README.md), [аудита репозитория](repository-audit.md), обоих audits и [архитектурного контракта](architecture-contract.md). Для спорного claim перейти к pinned primary code из [sources](research/sources.md). Raw Perplexity ответы использовать как discovery; Q04 пустой, Q07/Q08 содержат исправленные ошибки, Q08/Q09 не вернули structured source list.

Готовое поручение:

> Проведи независимый архитектурный review папки orch/ для выбора orchestration Swiss Knife Man. Сейчас нужна проверка и уточнение решения, без внедрения, запуска платных агентов или миграции. Сверь существующие Task context/scout/units/lifecycle и canonical provider projections. Сравни два audits: own native structured runner и CAO workflow backend. Проверь pinned CAO main и v2.5.1: replay/fingerprint, profile contents, recovery policy, cancel/orphans, permission semantics, model/effort и skill delivery. Проверь новую альтернативу Vercel HarnessAgent и её sandbox/auth ограничения. Не предполагай, что Task пока Markdown-only или что JavaScript означает API-only. Отдельно оцени минимальную reuse Artifex против его specialised admission path. Для каждого несогласия дай code/doc evidence и укажи, меняет ли оно выбор engine. Сохрани review в orch/claude-review.md, а новые исходные исследования — в orch/research/. Разделяй подтверждённый факт, кодовый вывод и гипотезу. Заверши уточнённым выбором и минимальным пилотом; не заменяй конкретный verdict списком всех возможных frameworks.

## Вопросы, на которых второе мнение особенно полезно

1. Достаточно ли CAO journal/cancel для нашего bounded workflow, или adapter неизбежно превращается в второй supervisor?
2. Какая часть Artifex реально применима к Task v4, и какие старые assumptions надо убрать прежде reuse?
3. Нужен ли пользователю interactive attach или достаточно структурированного live stream? Это способно изменить выбор A/B.
4. Какие task classes окупают cheap implementation и какие теряют качество из-за handoff?
5. Влияет ли текущий Vercel local/basic sandbox surface на shortlist, если Node sidecar разрешён?
6. Можно ли доказать portability тем же reviewer input на другом harness без переписывания canonical command?

Общие выводы про экономию и надёжность до этого этапа остаются гипотезами. Проверка дизайна вторым агентом и фактический runtime benchmark решают разные вопросы.
