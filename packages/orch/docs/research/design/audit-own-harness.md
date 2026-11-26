# Аудит A: доработать собственный Harness

**Вердикт:** технически обоснованный вариант, особенно при приоритете точного контроля над Task, структурированными событиями и локальными процессами. Однако это разработка и сопровождение runtime, а не небольшая правка prompt. Предпочтителен, если сравнительный пилот покажет, что готовый CAO требует слишком много обходных механизмов или не обеспечивает нужную наблюдаемость и восстановление.

Основа: [аудит текущего кода](repository-audit.md). Предложения ниже ещё не реализованы.

## 1. Что означает «свой harness уровня CAO»

Нужный результат — управляемый из терминала исполнитель: выбирает ready item из Task либо принимает свободное поручение, собирает его authoritative input, разрешает stage routes, запускает отдельные native CLI, показывает события, выполняет checks, сохраняет состояние и завершает item через Task API.

Ему не обязательно воспроизводить весь CAO: inbox, assign/handoff между произвольными агентами, cron, глобальную discovery сеть и полноценный веб-интерфейс. Для описанного пользователем сценария достаточно конфигурируемого pipeline и ограниченного DAG work units. Это уменьшает объём реализации, сохраняя полезную функциональную эквивалентность.

Базовые сценарии должны быть простыми: «сделай P2.3», «реализуй сам без передачи кода», «frontend design на сильной модели, bounded units на economy», «проверь этот diff в Claude-only reviewer». Ревью и плановая привязка не становятся обязательными для всех запусков.

## 2. Что переиспользовать

| Механизм | Текущее состояние | Действие |
| --- | --- | --- |
| JSON plan/schema/lifecycle | Уже реализованы Task | Вызывать существующий API |
| Deterministic context + scout | Есть и проверены локальными тестами | Добавить упаковку для роли и runtime policy обязательности |
| Unit DAG, scope, route, acceptance | Уже есть в Task | Связать с процессным dispatch и receipts |
| Canonical skills/commands | Есть Skiller и Task renderers | Сохранить, добавить engine bindings |
| Harness worker/gates | Работающий Claude-specific путь | Вынести общий process interface, сохранить полезные проверки |
| Artifex journal/authority/worktree patterns | Есть, текущий admission специализирован | Выбрать проверяемые компоненты; не объявлять их универсальными заранее |
| Multi-provider live stream | Нужного общего пути пока нет | Реализовать native adapters |
| Crash recovery всех side effects | Для нового pipeline не доказано | Сделать минимальное устойчивое state storage и reconciliation |

Нельзя одновременно оставить две независимые очереди, два механизма retry и два владельца worktree. Перед реализацией нужно выбрать **один** runtime owner: расширять Artifex как ядро с facade Harness либо развивать Harness driver и переносить только необходимые механизмы Artifex. Решение зависит от проверки совместимости текущего Artifex с реальными Task v4 units; название пакета здесь вторично.

## 3. Native structured adapters вместо чтения экрана

У всех трёх продуктов документирован машинный интерфейс. Это позволяет строить локальный Python runtime без Node-зависимости в ядре, читая построчные события дочерних процессов. Существующие аккаунты остаются авторизованы через native CLI, если выбранный режим действительно использует их текущий login. Доступность конкретной модели и расход квоты всё равно проверяются на аккаунте.

| Провайдер | Начальный интерфейс | Что ещё проверить |
| --- | --- | --- |
| Claude Code | `-p` и `--output-format stream-json`; native session ID | Нужные flags для событий; загрузку skills/plugins; разрешения и resume |
| Codex | `exec --json`, либо native SDK | Event schema/version, thread resume, sandbox, effective model/effort |
| Grok Build | `-p --output-format streaming-json`; для диалога ACP `grok agent stdio` | Версию официального CLI, event shape, effort, permissions, completion |

Источники: [Claude headless](https://code.claude.com/docs/en/headless), [Codex non-interactive](https://learn.chatgpt.com/docs/non-interactive-mode), [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk), [Grok scripting](https://docs.x.ai/build/cli/headless-scripting).

Не надо начинать с наиболее сложного двустороннего протокола. JSONL обычно достаточно для отдельной стадии. App-server или ACP добавляются, если требуется steering, approvals или продолжение сложного диалога. У Codex документация помечает app-server command/WebSocket transport как experimental и отдельно различает stable API surface и методы за `experimentalApi`. Native SDK, `exec`, transport и отдельный RPC method надо оценивать по своим контрактам. [App-server](https://learn.chatgpt.com/docs/app-server).

Для Claude нельзя без проверки ставить `--bare` на все запуски: этот режим меняет discovery и auth, включая использование subscription OAuth. Если требуются наши native plugins и текущая подписка, режим запуска выбирается по соответствующему контракту, а не по общей рекомендации для API-скриптов. [Headless guide](https://code.claude.com/docs/en/headless).

## 4. Наблюдаемость

Каждый запуск должен печатать cwd, task/stage, resolved provider/model/effort, режим permissions, PID/session, начало и завершение проверок. stdout/stderr передаются сразу; исходные события хранятся рядом с нормализованным журналом. Исключение из JSON parser не превращается в «агент думает» или успешное завершение.

Нужны различимые состояния: старт процесса, ожидание модели, tool execution, вопрос пользователю, quota block, timeout, cancelled, unknown outcome. «Процесс жив» и «задача движется» — разные признаки. Heartbeat и последний meaningful event лучше одной анимации.

Structured stream позволяет показывать console progress, но не обещает доступ ко всем внутренним рассуждениям модели. Пользователь должен видеть доступные действия, сообщения и результаты. Для первоначального варианта достаточно `run/status/watch/cancel/resume`-поведения; это проектные операции, не новые существующие команды пакета.

Если нужен полноценный attach к интерактивной CLI-сессии, CAO имеет готовое преимущество. Собственный JSONL runner даёт лог и управление процессом, но интерактивный терминальный UX придётся разрабатывать отдельно. Нельзя выдавать `tail` журнала за полноценный terminal attach.

## 5. State и recovery

Нужен один устойчивый state store с run/stage/attempt identities и ссылками на artifacts. Выбор между SQLite и аккуратными atomic files делается после проверки существующего Artifex store; вводить оба без необходимости не стоит. Native CLI session ID сохраняется отдельно от engine run ID.

Для stage вход фиксируется хешами Task snapshot, base commit, policy, instructions, provider route и mandatory reads. Изменение canonical plan или worktree в момент resume требует решения о новом запуске, а не повторного использования старого успешного результата.

Последовательность завершения должна быть проверяема: результат агента → actual diff/scope → command checks → durable acceptance evidence → Task transition. Crash между двумя последними шагами восстанавливается через effect receipt и сверку фактического состояния. Ни subprocess exit 0, ни фраза «готово» не дают разрешение закрыть план.

Cancel должен остановить дерево процессов, отметить незавершённые операции и сохранить их неизвестный исход. Resume native session не является откатом файлов или повторным безопасным Git commit. Такие эффекты требуют отдельного кода и reconciliation независимо от интерфейса модели.

## 6. Как делить работу между моделями

Pipeline задаётся profile policy из [общего контракта](architecture-contract.md). Python сначала собирает обязательный context pack. Economy scout строит карту контекста, отмечая неизвестное. Сильная модель получает требования и релевантный код, затем либо реализует всё, либо выдаёт конкретные work units.

Для frontend полезная граница проходит между дизайн-решениями и ограниченной механической реализацией. Передача простого JSX/CSS может окупиться, если заданы assets, состояние компонентов, responsive behavior и критерии приёмки. Если слабый исполнитель вынужден заново придумывать UX, сильная модель фактически делает работу дважды.

Units с `mode=self` не передаются. Минимальный route из плана не снижается ради экономии. Review включается выбранным профилем либо явным поручением. Закрытие фазы и штатные Git-операции выполняет deterministic finalizer; дешёвая модель может готовить описание изменения, но не решает, прошли ли checks.

Повторы ограничены на уровне стадии и всей задачи. Неисправимый парсер, неподдерживаемая capability или quota block не лечатся бесконечными «попробуй ещё». Сильная эскалация означает новый явно записанный route, не скрытый fallback.

## 7. Цена собственного пути

Большая часть доменной логики уже существует, но process integration, event normalization, recovery, тестирование CLI versions и пользовательская консоль требуют сопровождения. Structured API снижает зависимость от экранных regex; он не устраняет изменение event schema, проблемы auth, недоступность моделей и ошибки agent output.

Дополнительная стоимость — мы сами поддерживаем три adapter contracts и их capability matrix. Версии CLI должны быть pin/recorded; auto-update во время run нежелателен. Нужны реальные compatibility probes вместо перечисления поддерживаемых продуктов в README.

Срок «за пару дней/неделю» по этому аудиту не обоснован. Пилот должен сначала показать стоимость одного end-to-end stage и одного crash scenario. После этого можно оценить работу по реальным неизвестным.

## 8. Когда выбрать A

Выбирать собственный runtime разумно, если:

- точный Task lifecycle и structured events важнее полноценного interactive attach;
- CAO ломается на целевых версиях CLI или требует большого fork;
- Task/Artifex reuse действительно сокращает работу и проходит реальные v4 fixtures;
- команда готова владеть compatibility/recovery и не ожидает, что они исчезнут благодаря native JSON;
- пилот показывает сопоставимую надёжность и меньшую общую стоимость сопровождения.

Не выбирать его только потому, что Python «проще», или потому что внешний движок теоретически может сломаться. Это сравнение реальных объёмов работы. Противоположный вариант и его ограничения: [аудит CAO](audit-amazon-cao.md).

## 9. JavaScript-вариант собственного слоя

Если отдельный Node sidecar приемлем, Vercel HarnessAgent способен уменьшить adapter work: есть опубликованные packages для Claude, Codex и Grok. Но текущая документация считает harness packages экспериментальными, а эти adapters используют sandbox bridges; это не прямой drop-in для локального `cwd` с теми же процессами и конфигами. Auth auto-detection также может выбрать API/Gateway вместо подписки. [Overview](https://ai-sdk.dev/docs/ai-sdk-harnesses/overview), [adapters](https://ai-sdk.dev/docs/ai-sdk-harnesses/harness-adapters), [registry snapshot](research/vercel-harness-surface.json).

Такой sidecar остаётся внешним engine adapter, сохраняя stdlib-only Python core пакета. Для данного пользователя CAO и Python JSONL runner ближе к требованию локальной консоли; Vercel следует проверить отдельно, если унификация SDK и UI важнее локального terminal attach. Он не исключён из исследования и не объявлен зрелым только по документации.
