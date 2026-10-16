# Фактическое состояние репозитория и проверка исходного диалога

Исследование 2026-10-05, исходный HEAD: `34a6c0f3342290cb5e5a3c2d0be106838a4ae455`. Пользователь сообщил о сбоях Codex/Grok; в этой работе конкретные сбойные сессии не воспроизводились. Причину каждого зависания нельзя установить по общей архитектуре. Ниже — проверяемое устройство пакетов и места, где действительно есть разрыв между желаемым процессом и кодом.

Во время финальной проверки появились параллельные правки Task, сделанные вне этого аудита. [Ledger](research/concurrent-source-changes.json) различает HEAD, inspected hashes и позднюю рабочую копию. Они сохранены; тестовые результаты относятся к моменту запуска. Поздние изменения поддерживают migrated missing-route/non-shell validation cases, поэтому следующий compiler audit должен учитывать их отдельно, а не считать любой historical item готовым к автоматическому model launch.

## Task уже значительно ближе к нужному контракту, чем предполагает диалог

Канонический план имеет файловую раскладку v4 и JSON Schema с идентификаторами v1. Это разные номера: версия расположения документов не равна версии каждого schema marker. Есть план, brief, фазы, items, decisions, knowledge documents, журнал и work units. Их не нужно заменять новым независимым YAML TaskSpec только ради внешнего движка. Источники: [schemas](../packages/task/schemas/plan/v1/plan.schema.json), [unit schema](../packages/task/schemas/plan/v1/unit.schema.json), [store](../packages/task/lib/task/plan/store.py).

[context.collect](../packages/task/lib/task/plan/context.py) собирает JSON с item, фазой, brief, применимыми решениями, upstream dependencies, reads, lessons, knowledge documents и units. Это уже детерминированный подготовитель контекста. Он не означает «все исходники проекта целиком»: обычные reads могут содержать путь и метаданные, поддерживаемые документы — содержимое или выбранную секцию. Markdown-представления самого плана исключаются как human view. Обязательный read и красивый render плана не взаимозаменяемы.

Существующий контракт запрещает молчаливое обрезание материала. [13 тестов контекста](../packages/task/tests/engine/test_context.py) прошли, включая проверки полноты больших данных. Поэтому предложение «урезать context до N токенов» без отдельного согласованного изменения контракта было бы регрессией. Можно добавить индекс, выборку для роли и дозагрузку, сохранив полный pack и проверяемую полноту обязательного ввода.

[Scout](../packages/task/lib/task/plan/scout.py) уже запускает economy-модель выбранного провайдера по [routing config](../packages/task/configs/command-routing.json). В текущем конфиге есть Claude и Codex, а отдельного Grok scout нет. Claude scout запускается без tools, Codex — с read-only sandbox. Здесь ограничения сильнее одного пожелания в prompt. Результат фильтруется до карты путей/символов и unknowns; scout не является источником истины. При его ошибке процесс может продолжиться без карты. Если пользователь выбирает профиль «scout всегда обязателен», это должна быть отдельная явная runtime-политика; текущий мягкий fallback ей не соответствует. [23 существующих теста scout](../packages/task/tests/engine/test_scout.py) прошли.

[Units](../packages/task/lib/task/plan/units.py) уже имеют зависимости, write sets, route, режимы `self/delegate/either`, checks и переходы `todo → dispatched → returned → accepted/reworked/rejected`. Их orchestration policy наследуется от plan к phase и item. Проверяются route и допустимость параллелизма. Однако функция dispatch фиксирует назначение и brief: **она сама не порождает процесс агента**. Исполнитель всё ещё должен соединить этот переход с реальным запуском и последующим приёмом результата. [20 существующих тестов units](../packages/task/tests/engine/test_units.py) прошли.

`plan.py` уже имеет машинный JSON-вывод и команды `show`, `next`, `start`, `context`, `unit`, `finish` и другие. `finish` проводит жизненный цикл, включая соответствующее завершение фазы/плана. В интеграции надо вызывать реальные операции и проверять ответ; изобретённая команда `plan-close-phase` не является существующей возможностью. Источники: [CLI](../packages/task/lib/task/plan/cli.py), [lifecycle](../packages/task/lib/task/plan/lifecycle.py).

Есть [workflow template library](../packages/task/workflows/README.md), включая [dev-slice](../packages/task/workflows/wf-dev-slice.js) с bounded tests-to-green и optional review. Она работает с globals конкретного Workflow runtime, а не является самостоятельным универсальным multi-provider process driver. Эти semantics надо переиспользовать при backend design; отсутствие готового общего executor не означает отсутствия workflow-шаблонов.

Текущая [plan-run command](../packages/task/commands/plan-run.md) уже требует один scoped commit на item, native subagent своего провайдера и сохранение модели текущей сессии. Independent reviewer включается явно; флаг `--review` имеет отдельный финальный review смысл. Внешний cross-provider workflow должен получить отдельную согласованную integration command: нельзя считать новые stage roles уже разрешённой семантикой этой команды или молча потерять требование commit.

## Harness содержит runtime, но пока не нужный универсальный конвейер

В [harness/run](../packages/harness/lib/harness/run/__init__.py) уже есть детерминированная очередь, pre-launch gate, снимки состояния и журнал результата. Это опровергает общий тезис, что вся оркестрация обязательно выполняется моделью.

Существующий [worker](../packages/harness/lib/harness/run/worker.py) привязан к `claude-code` и вызову `task:plan-run`. Он собирает argv из канонического routing, различает timeout/quota/error и использует `subprocess.run(capture_output=True)`. В такой форме живой stdout пользователь получает после завершения; это конкретный источник непрозрачности. `_run_wave` обходит очередь последовательно. Готового общего механизма «economy → frontend → bounded implementation → optional Grok review» в этом driver нет.

[plan_reader](../packages/harness/lib/harness/run/plan_reader.py) читает Task через JSON-команды и знает monorepo paths. Для подключения Swiss Knife Man к стороннему harness нужен установленный entrypoint или capability discovery, а не ожидание, что у потребителя обязательно есть `packages/task/...`.

При выборе CAO сохраняются другие функции Harness: настройка окружения, permissions, hooks, MCP, provider instructions и agent packs. Runtime driver можно заменить независимо от этой части. Название пакета не должно заставлять удалять полезный установщик.

## Artifex нельзя оценивать по одному README

У Artifex уже есть [compiler](../packages/artifex/lib/artifex/compiler.py), [scheduler](../packages/artifex/lib/artifex/scheduler.py), [authority](../packages/artifex/lib/artifex/authority.py), [worktrees](../packages/artifex/lib/artifex/worktree.py), [telemetry](../packages/artifex/lib/artifex/telemetry.py) и проверки replay. Компилятор использует Task JSON и Harness dry-run, фиксирует source hashes и бюджеты. Это существенные активы, если развивать свой исполнитель.

Но просмотренный [provider activity port](../packages/artifex/lib/artifex/activity.py) требует admission/authority artifacts специальных фаз. [dispatch.verify_task](../packages/artifex/lib/artifex/dispatch.py) принимает специальный `provider-readiness-smoke`, привязанный к `P3.4`, и отвергает generic parent manifests. Это подтверждает **узкий текущий путь допуска провайдера**, а не готовность запускать любой современный Task unit.

Отсюда два отдельных вывода: «Artifex ничего не умеет» неверно; «Artifex можно подключить как универсальный runtime без проверки совместимости» тоже не доказано. Для варианта A надо выбрать, какие его механизмы использовать, и проверить реальный v4 plan, а не суммировать возможности разных тестовых контуров. Для варианта B можно оставить исходники и их опыт, не запускать scheduler параллельно CAO и не делать преждевременную депрекацию.

## Источник истины инструкций уже существует

| Слой | Канонический источник | Что генерируется |
| --- | --- | --- |
| Task command content | [packages/task/commands](../packages/task/commands/plan-run.md) | Provider-команды и wrappers |
| Маршрутизация и capabilities | [command-routing.json](../packages/task/configs/command-routing.json), [command_catalog.py](../packages/task/lib/task/command_catalog.py) | Проверяемые mappings и reference |
| Provider rendering | [command_render.py](../packages/task/lib/task/command_render.py) | Claude/Codex/Cursor/Grok projections |
| Skills | [packages/skiller/skills](../packages/skiller/skills/) | Plugin/consumer/bootstrap delivery |
| Root/provider instructions | [harness instructions](../packages/harness/lib/harness/instructions.py) | Общие semantic blocks и provider extensions |

`render-provider-commands.py --check --root .` прошёл без расхождений. `generate-provider-instructions.py --check` подтвердил актуальность provider instructions reference; это **не** доказательство, что все установленные плагины и все запущенные сессии загрузили нужный текст. [Результаты](research/local-checks.json).

Provider-файлы внешне похожи, потому что содержат проекции одного смысла. Удалить эти проекции — значит лишить CLI нужного формата. Исправлять следует ручной drift, повторную доставку одного skill, разное толкование permissions и избыточную native-specific семантику в canonical command. Последнее требует отдельного содержательного аудита; один подсчёт одинаковых строк его не доказывает.

## Где исходный диалог требует поправок

| Утверждение или предпосылка | Проверка | Следствие |
| --- | --- | --- |
| Task нужно сначала превратить в машинный JSON-контракт | Уже есть schemas, context, units и JSON CLI | Делать экспортную проекцию, не второй план |
| Основная оркестрация целиком неявная и модельная | Harness и Artifex имеют deterministic код; `plan-run` действительно часть обязанностей отдаёт модели | Отделить конкретный процессный разрыв от общих догадок |
| JS/Python SDK означает только оплачиваемый API | Native Codex SDK и CLI используют native runtime; Vercel добавил HarnessAgent; Pydantic поддерживает отдельный Codex OAuth provider | Рассматривать auth и runtime каждого адаптера отдельно |
| Grok не имеет пригодного machine interface | Есть streaming-json и ACP в официальных документах | У варианта A есть альтернатива TUI-парсингу |
| CAO resume даёт прозрачное exactly-once всей задачи | Memoization относится к workflow steps; обычный Python и side effects требуют отдельной сверки | Нужны receipts для Git и Task, неизвестный исход нельзя превращать в успех |
| У CAO нет Claude effort | Есть `claudeConfig.effort`, также в проверенном tag | Сверять код; не доверять старым ответам Q07 |
| Completed Python step при resume всегда запускает агента заново | Shim и workflow journal умеют replay | Q08 устарел в этой части; сам script всё равно исполняется сверху |
| Профиль skills/allowedTools гарантирует одинаковую изоляцию | Advertised skills и provider restrictions имеют разные semantics | Capability contract должен отражать фактические ограничения |
| Harness/Artifex следует сразу удалить | Не следует из источников; installer и plan machinery остаются полезны | Замена исполнительного пути отдельно от удаления пакетов |

Первичные внешние ссылки и точные pins собраны в [sources](research/sources.md); исходные ответы, включая неверные, сохранены в [Perplexity log](research/perplexity-log.md). Текущий аудит не утверждает, что именно перечисленные архитектурные ограничения вызвали все пользовательские зависания.
