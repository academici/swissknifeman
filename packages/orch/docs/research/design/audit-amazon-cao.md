# Аудит B: встроить AWS Labs CLI Agent Orchestrator

**Вердикт:** первый кандидат для ограниченного пилота как внешнего engine. Он уже управляет native CLI и даёт inspectable terminal sessions. Интеграция с Task и безопасное завершение Git/plan lifecycle остаются нашей работой. Утверждение «готовый CAO сразу устраняет нестабильность» не доказано.

Основной продукт — [awslabs/cli-agent-orchestrator](https://github.com/awslabs/cli-agent-orchestrator), сокращённо CAO. Это локальный open-source инструмент, а не обязательная облачная служба AWS. Apache-2.0; заявленный стартовый runtime — Python, tmux и отдельный cao-server.

## 1. Какой CAO исследован

| Канал | Зафиксированное состояние 2026-10-05 |
| --- | --- |
| GitHub main | `c31dc281ec1f215cef898c2ed919a0ce507afd08` |
| Последний проверенный GitHub release | `v2.5.1`, commit `d98243e7149912bf66cb7572e77629ffa0c650af`, опубликован 2026-09-11 |
| Последний PyPI release | `2.5.0`, опубликован 2026-08-28 |

Источники: [release](https://github.com/awslabs/cli-agent-orchestrator/releases/tag/v2.5.1), [PyPI](https://pypi.org/project/cli-agent-orchestrator/), [снимок версий](research/cao-versions.json), [сравнение поверхностей](research/cao-release-surface.json).

Python workflows, `cao_workflow`, Grok provider и script runner присутствуют и в проверенном tag. Некоторые agent-plugin компоненты присутствуют только в main; даже там механизм feature-gated и по умолчанию отключён. Не смешивать его с обычной native загрузкой наших CLI plugins. Между tag и main существенно менялись Codex/Grok parsers. **Установка latest из PyPI не эквивалентна изученному main.** Пилот должен фиксировать artifact/commit и версии трёх CLI, затем отдельно проверять преимущества более нового кода.

## 2. Что получаем готовым

CAO запускает отдельные процессы разных CLI, организует terminals, profiles и MCP-инструменты общения агентов. Для данного сценария полезнее Python-workflow с фиксированной последовательностью шагов, чем свободное поведение supervisor-модели. Пользовательский plan item компилируется в явные стадии, а модели исполняют bounded задания.

В документации workflow есть запуск с inputs/run ID, status, cancel, resume. Python shim предоставляет `step`, `run_step`, `get_inputs`; workflow способен ветвиться обычным Python. Однако YAML engine сейчас исполняет sequential workflow: другие типы могут валидироваться как reserved, что не означает исполнение. Python concurrency требует устойчивых step IDs и ответственности автора script. [Workflows](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/docs/workflows.md), [shim](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/src/cao_workflow/__init__.py).

Наблюдаемость — главное практическое преимущество: процессы можно смотреть в живых terminals, а status/UI помогают видеть запуск. В стандартном backend CAO всё равно определяет часть состояний по TUI output. Это не тот же уровень событий, что native JSON-RPC/JSONL. Экспериментальный herdr backend не следует автоматически считать проверенной заменой tmux. [Configuration](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/docs/configuration.md).

## 3. Модель и effort: одинаковый смысл, разные bindings

| Swiss Knife Man provider | CAO provider | Документированный binding |
| --- | --- | --- |
| `claude-code` | `claude_code` | Profile `model`; `claudeConfig.effort`; отдельный native-agent путь |
| `codex` | `codex` | Profile `model`; `codexConfig.model_reasoning_effort`; `codexProfile` |
| `grok` | `grok_cli` | Profile `model`; в просмотренном provider нет аналогичного явного effort binding |

Источники: [agent profile](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/docs/agent-profile.md), [Claude provider](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/src/cli_agent_orchestrator/providers/claude_code.py), [Codex provider](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/src/cli_agent_orchestrator/providers/codex.py), [Grok provider](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/src/cli_agent_orchestrator/providers/grok_cli.py).

Это исправляет ошибку Perplexity Q07 про отсутствие Claude effort. В то же время поддержка `--effort` самим Grok не доказывает, что его передаёт CAO. Неизвестный frontmatter параметр нельзя считать работающим. Если профиль требует effort, которого engine не умеет установить/наблюдать, запуск должен сообщить об этом; нельзя молча подменять capability значением из prompt.

Canonical route берётся из Task catalog/плана; CAO profile — генерируемая проекция. Перед запуском сохраняются requested и resolved route, argv/config digests, затем доступное native evidence. Профиль с названием economy ещё не доказывает реальный economy model. Подписки, entitlement, quota и fallback конкретных CLI проверяются отдельно; CAO не превращает любой Grok login в доступ ко всем coding models.

## 4. Permissions и skills не универсальны

Стандартные launch defaults у Claude/Codex разрешительные. Claude умеет native tool deny; у Codex CAO role allowlist сама по себе prompt-level и не заменяет sandbox. Для Codex нужен соответствующий named profile/native config. Grok имеет собственную систему mapped restrictions. Встроенный `workflow_scout` допускает shell: одно слово scout не делает роль read-only. [Tool restrictions](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/docs/tool-restrictions.md), [Codex integration](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/docs/codex-cli.md), [Claude integration](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/docs/claude-code.md).

Нам нужны минимальные stage profiles, проверенные на целевой версии. Reviewer получает diff/reads и не получает plan-finalizer authority. Разрешённый shell способен писать файлы даже при запрещённом специализированном Edit tool. Реальные read-only требования должны обеспечиваться native/OS controls и тестом, а не описанием роли.

CAO skills поддерживают discovery и on-demand `load_skill`; поведение зависит от провайдера. Profile `skills` ограничивает advertised catalog, но не является общей ACL на загрузку всех установленных skills. При использовании native Skiller plugins нельзя параллельно объявлять CAO владельцем того же тела skill. [Skills](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/docs/skills.md).

Первый пилот лучше строить на native Swiss Knife Man delivery, а CAO profile содержит короткое stage assignment и ссылки на artifacts. Для будущего Claude-only reviewer этот же canonical skill можно доставить другим adapter, сохранив checks и result contract. Полная универсальность фронтматтера, hook semantics и permissions не обещается.

## 5. Resume: что действительно восстанавливается

При resume Python script выполняется сверху. Для agent step сервер сверяет identity/fingerprint и может вернуть сохранённый завершённый результат без нового агента. Поэтому две фразы одновременно верны: script повторно исполняется; completed agent step может replay. [Authoring guide](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/docs/workflow-scripts-authoring-guide.md).

`step(..., recovery=...)` требует явную recovery policy. Совместимый `run_step` допускает другой путь задания options, поэтому не стоит смешивать оба API в новых templates. Policy `idempotent` — обещание автора шага, не доказательство безопасности. `reconcile` в просмотренной реализации не даёт полноценного универсального reconciliation: соответствующая семантика ещё не реализована отдельно от retry. `manual`/неизвестный исход требует остановки и решения.

Fingerprint включает имя профиля и execution-affecting inputs, но имя не фиксирует автоматически содержимое profile. В нашей receipt необходим собственный hash profile/instructions. При thread fanout задаются явные устойчивые `step_id`; порядковый counter не должен зависеть от race.

Replay возвращает исторический terminal ID, который может уже не быть живым. Shim не поддерживает `reuse_terminal_id` в workflow identity path. Resume нельзя рекламировать как «всегда продолжает прежнего работающего агента». Повторный запуск и возврат предыдущего результата — разные операции.

Git commit, создание worktree, команды tests и вызовы `plan.py finish` обычным Python находятся вне agent-step memoization. При resume они снова выполнятся, если автор не предусмотрел сверку. Нужны effects с ключом run/stage/input hash, атомарными receipts и фактическим reconciliation. Автоматическое «repeat git commit» недопустимо; repository HEAD и plan event должны подтверждать уже выполненное действие. Общий алгоритм: [architecture contract](architecture-contract.md).

## 6. Где durability ограничена просмотренным кодом

[script_runner](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/src/cli_agent_orchestrator/services/script_runner.py) имеет journal и orphan reconciliation. В просмотренных ветках запись begin-step выполнена best-effort; при ошибке логируется деградация resumability. Здесь есть важная тонкость: текущий journal уже имеет поле `terminal_id`, но script recorder вызывает `begin_step` без terminal ID. Fallback sweep читает это поле через `getattr`; комментарии об отсутствии колонки уже отстают от schema. Поэтому проверять надо сохранность связи **во время in-flight окна**, а не объявлять, что journal вообще не имеет terminal IDs. Гарантия reclaim всех orphan terminals после потери registry из просмотренного пути не следует. Это вывод чтения кода, **не воспроизведённый здесь runtime crash**. [Journal](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/src/cli_agent_orchestrator/services/workflow_journal.py).

Отмена workflow script и teardown agent terminals — разные механизмы. Остановка script process не доказывает прекращение всех descendant CLI/tools. Пилот должен убить server/script/CLI в разных точках и проверить остаточные процессы, terminal state и повторные эффекты. Наличие команды `cancel` само по себе недостаточно для обещания kill-tree guarantees.

Вместо самостоятельного огромного durable supervisor поверх CAO сначала проверяются эти границы. Если для нужного уровня гарантий потребуется повторить scheduler/journal/process registry в нашем пакете, преимущество внешнего движка может исчезнуть.

## 7. Предлагаемая интеграция

```text
Поручение пользователя
    → Task binding или свободное задание
    → immutable execution input + runtime policy
    → CAO Python workflow
        → deterministic context pack
        → economy context agent
        → strong design/implementation
        → optional bounded economy units
        → deterministic checks
        → optional independent review
        → deterministic Task/Git finalizer
```

CAO владеет порядком стадий и CLI processes. Task владеет plan readiness/status/acceptance. Skiller владеет canonical content и publication. Наш adapter готовит inputs/profiles, проверяет source drift и нормализует результаты; он не запускает второй независимый scheduler.

Не следует передавать generic `task:plan-run` каждому маленькому CAO worker: эта команда предназначена для выполнения пункта и может включать собственную orchestration/lifecycle responsibility. Под стадийный запуск нужна ограниченная command/role projection: реализовать unit, вернуть artifacts, не закрывать parent. Это новая интеграционная поверхность, а не существующая автоматическая возможность CAO.

Core пакета остаётся stdlib-only Python. CAO — установленный внешне инструмент/служба, связанный через CLI/HTTP, а не новая обязательная pip runtime dependency Task. Workflows с `cao_workflow` живут в engine-specific integration boundary. Для стороннего consumer нельзя hardcode monorepo paths.

Native subagents могут выполнять bounded внутреннюю работу. Верхнеуровневый сменный provider dispatch остаётся у CAO workflow. Grok native workflows/subagents в CAO по умолчанию отключены; opt-in требует ясного ownership, иначе получим два workflow engines в одном run. [Grok integration](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/docs/grok-cli.md).

## 8. Миграция и отказ от миграции

Первый adapter — только один item, последовательные стадии, без auto-merge/publish. Затем recovery/effect checks и только после них отдельные units. Текущий Harness driver остаётся fallback отдельного запуска; один item не должен одновременно принадлежать обоим исполнителям.

При успешном пилоте можно прекратить развитие дублирующего process scheduler. Это не требует немедленного удаления Harness installer, Artifex contracts или старых journals. Депрекация становится отдельным решением после parity и миграции активных запусков.

Выбрать B стоит, если live terminals и готовый multi-CLI lifecycle дают ощутимую пользу, routes/skills загрузились корректно, а recovery gaps закрываются небольшим deterministic adapter. Отвергнуть — если целевые версии постоянно ломают TUI parsing, точный route невозможно проверить, cancel/resume теряют контролируемость или наш wrapper вынужден заново реализовать CAO.

Сравнение проверяется [пилотом](pilot-and-claude-handoff.md). Надёжность, экономия и совместимость текущих аккаунтов здесь не объявлены измеренными. Альтернативный путь: [свой runtime](audit-own-harness.md).
