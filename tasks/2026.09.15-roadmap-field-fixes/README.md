# Свежий roadmap: ограниченные полевые исправления, 2026-09-15

Запрос владельца: разобрать незавершённые записи за 14–15 сентября, исправить полезное
в этой сессии без дорогого нового цикла проектирования; эффект оценивать на проектах.
Это обычное ограниченное задание, не executable master plan.

## Решение

Четыре записи 14 сентября уже содержат реализацию и подтверждённую локальную доставку:
session continuity, owned dirty worktree, terminal command emission, Unicode cross-plan bundle.
Повторять их реализацию оснований нет. Две записи 15 сентября содержат новые дефекты.
Проверены owning Python-модули, канонический snippet, генератор provider-команд и оба
Stop-адаптера. Исходные полевые материалы сохранены; новый результат не подменяет их.

Сделаны небольшие исправления причин, которые можно проверить локально. Тяжёлые изменения
контрактов закрытия, чтения и измерения ресурсов оставлены явным остатком: их механическая
реализация целиком противоречила бы заданному ограничению расходов.

## Диспозиция CoreX

| ID | Решение и результат | Остаток |
|:--|:--|:--|
| RSC-01 | Не менять телеметрию в этом задании. Нулевой run-report не доказывает экономность. | Codex acquisition/compaction accounting в harness/core; отдельный сопоставимый thread fixture. |
| RSC-02 | Исправлен канонический decision template: YAML, обязательные поля, точные заголовки, reciprocal supersession. Реальный parser проверяет канон и доставленный Task runtime. Перед terminal append проверяются существующие decision records. | Проверить отсутствие ручного schema repair на проекте. |
| RSC-03 | Unnumbered reads и Files разделяются по `;`; backticks/аннотации сохраняются. Неоднозначная Files-проза отклоняется с actionable error. Closure отвергает пустой/missing-only anchor; тест ловит изменение настоящего файла. | Это ограниченный repair, не общая AST. Globs, declared deletion/planned-output states и полнота смешанных existing/missing anchors требуют отдельного контракта. |
| RSC-04 | Сохранён существующий read reuse; новый capsule protocol не добавлялся. | Проверять incremental unread отдельно от nominal corpus; не менять strict budget без решения владельца контракта. |
| RSC-05 | Не менять current/future admission в обход policy. | Следующий приоритет при повторе: отделить valid local terminal от запрещённого future START, тестируя оба verdict одновременно. |
| RSC-06 | Устранён один конкретный late failure: невалидный decision больше не обнаруживается впервые после terminal append. | Общий recoverable finalize coordinator и fault injection не реализованы. |
| RSC-07 | Не менять accepted digests и plan-owned seals автоматически. | Развести normative/volatile inputs у владельца конкретного consumer check. |
| RSC-08 | `only_item` измеряет выбранный пункт. Остальные дают лишь symbolic producer index: порядок, статус, deliverables; результат admission сохранён. | Parsing/index остаётся общим; invocation-wide cache и persistent cache не добавлены. |
| RSC-09 | Не переопределять чужие Validation contracts. | Убирать дубли только при доказанном совпадении invariant/profile/environment и актуальном receipt. |
| RSC-10 | Во время исправления выходы проверок сохранялись в файлы с отдельными exit codes. Дополнительный framework не нужен: правила batch/dependencies уже есть. | Эффект guidance измерять в реальных запусках; это не объявлено runtime-исправлением. |
| RSC-11 | Не добавлять новый evidence runner без конкретного потребителя. | Сначала использовать существующие progress/receipt API; counts получать из machine state. |
| RSC-12 | История решений выбирает membership в `items`, показывает все affected items. | Исторические записи `items: [design]` автоматически не перепривязываются; новые repair events не введены. |

## Open-run final

В существующий Task terminal admission добавлен `check-open`. Включённые Claude/Codex
Stop-адаптеры вызывают его **до** проверки optional `terminal_admission` payload/lease.
Он читает живые `plans/*/journal.jsonl` текущего проекта, связывает записи с provider
session и использует канонический `latest_execution_event`. Открытое состояние даёт
`TASK_OPEN_RUN_FINAL_FORBIDDEN`, даже если receipt и payload отсутствуют. Observation
`local-repair` не закрывает run. Минимальный local admission record хранит item/run/state/reason,
без текста ответа. Journal продукта не меняется. Проверка receipt для существующего lease сохранена.

Проверка subprocess действительно проходит через сгенерированный Codex dispatcher и Claude
Stop entrypoint с реальным worktree-local Task CLI. Это repository integration, **не** запуск
реального model transport. Отдельно проверены чужая сессия, отсутствие Task, закрытый/blocked
run и неизменность execution journal.

Остаток остаётся открытым: включение и доставка hook в consumer runtime, явная привязка
recovered run к новой provider session, нестандартная топология планов, полный путь exact
structured waiting/owner-stop handoff без request payload. Открытый `waiting-external` сам по
себе не становится исключением: действующий lease также запрещает его final. Нельзя заявлять
полный acceptance исходного carrier или гарантированный перехват каждого model final.

## Измерение и проверки

Matched синтетический fixture: 78 пунктов, один выбранный, три запуска каждого режима.
Старый путь «измерить всё и выбрать» сравнивался с новым scoped path на одном корпусе и
одном Measurer. Полный выбранный record совпал, включая admission.

- Вызовы `measure_item`: **78 → 1**.
- Медиана локального измерения: **0,686 → 0,016 с**.
- [Машинные результаты](evidence/measurement.json). Это не оценка экономии всей CoreX-сессии.

Первый полный Task qualification выявил ещё не пересозданные provider/golden artifacts;
исправлены owning renderer. Harness qualification выявил зависимость conformance-теста
от установленного `.codex/hooks/lifecycle.py` рабочего репозитория: после изменения генератора
dry-run закономерно обнаруживал drift. Тест теперь устанавливает hook в temporary project и
проверяет relative/absolute targets и отсутствие любых записей при dry-run. Это дополнительное
улучшение из наблюдаемого сбоя; локальную пользовательскую конфигурацию тест не меняет.

Skiller qualification также обнаружил `RELEASE_IMMUTABLE_TUPLE: package.harness@0.4.2`: runtime-изменение требовало новой версии. Harness API подготовлен как `0.4.3`; опубликованные bytes не заменялись.

Финальные результаты qualification записаны в [validation.txt](evidence/validation.txt).
Docs обновлены: roadmap, Task templates/continue-first, CHANGELOG. Consumer rollout и публикация
релиза этим заданием не выполнялись; локальные исходники готовы к дальнейшей доставке.

## Что проверить на проектах

На следующем обычном CoreX/Edufy run: нет schema/semicolon repairs; выбранный weight не
измеряет остальные items; partial success остаётся progress при открытом run; blocked/future
admission не называется GREEN. Приоритет следующего изменения — RSC-05, если future budget
снова мешает закрыть уже выполненный scope. Архитектуру capsule/finalize/telemetry расширять
по отдельному воспроизводимому случаю, сохраняя проверенные здесь исправления.
