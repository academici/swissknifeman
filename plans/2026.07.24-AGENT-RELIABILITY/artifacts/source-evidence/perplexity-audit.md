# Аудит репозитория swissknifeman

Статус: живой документ, итерационное пополнение.
Источник первичного обзора: структура репозитория, список модулей `core/`, корневые каталоги, а также детальный просмотр хука `packages/harness/configs/claude-code/hooks/run-report/_lib.py`.

## Как работать с этим аудитом

Этот файл задуман как единый корневой документ аудита. Дальше каждая новая итерация должна:

1. Брать один конкретный раздел.
2. Проводить глубокий анализ только по нему.
3. Обновлять соответствующий раздел этого файла.
4. При необходимости добавлять подразделы:
   - наблюдения;
   - риски;
   - рекомендации;
   - quick wins;
   - refactoring roadmap;
   - вопросы для верификации.

## Первичный срез репозитория

По корневой структуре видно, что репозиторий организован как монорепо/оркестратор для AI-агентов и связанных developer workflows. В корне присутствуют каталоги `.agents`, `.claude-plugin`, `.claude`, `.codex`, `.github`, `configs`, `core`, `docs`, `packages`, `plans`, `roadmap`, `scripts`, а также документы `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `README.md`, `CHANGELOG.md`, конфиги `config.example.json`, `.mcp.json.example`, `pyrightconfig.json`, `ruff.toml`, `safe-dirs.example.json` [cite:18].

В каталоге `core/` присутствует большой набор модулей, включая `cli.py`, `project.py`, `repo.py`, `provider.py`, `provider_artifact.py`, `provider_config.py`, `provider_lock.py`, `provider_manifest.py`, `provider_registry.py`, `pathology.py`, `io.py`, `http.py`, `env.py`, `paths.py`, `proc.py`, `block.py` и `__init__.py`, что указывает на развитое ядро для orchestration/runtime/config-resolution/lock-management [cite:18].

Важная находка первичного обзора — крупный hook-библиотечный файл `packages/harness/configs/claude-code/hooks/run-report/_lib.py`, который реализует защитный построчный JSONL-парсинг транскриптов, сбор tool metrics, фиксацию error loops, rereads, retrieval-вызовов, protected writes, workflow relaunch сигналов и usage aggregation с graceful degradation при частичной недоступности зависимостей [cite:17].

## Общая оценка

### Сильные стороны

- Репозиторий выглядит как инженерно зрелая система, а не набор ad-hoc скриптов: есть отдельные слои для конфигурации, lock/manifest/provider-логики, хук-инфраструктуры, агентных каталогов и эксплуатационной документации [cite:18].
- В `run-report/_lib.py` явно видна defensive engineering культура: построчная обработка больших транскриптов, лимиты на память и длины списков, пропуск битых данных без падения, fallback-ветки для отсутствующих компонентов и best-effort extraction при нестабильной внешней схеме [cite:17].
- Наличие `plans/`, `roadmap/`, `CHANGELOG.md`, `CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md` указывает на проект с высокой операционной плотностью, где разработчик думает не только о коде, но и о процессах сопровождения [cite:18].

### Основные системные риски

- Размер и количество `provider_*` модулей уже по одному списку файлов намекают на возможную перегрузку доменной модели и расползание ответственности между registry, manifest, config, artifact и lock слоями [cite:18].
- Крупные хук-файлы, особенно `run-report/_lib.py`, могут со временем превращаться в неформализованные центры бизнес-логики и телеметрии, где схема событий, парсинг, агрегация и аналитика смешиваются в одном месте [cite:17].
- Обилие управляющих директорий (`.agents`, `.claude`, `.codex`, `.claude-plugin`, `packages`, `configs`) создаёт риск пересекающихся контрактов между агентами, хук-системой и runtime-конфигурацией, если эти зоны не документированы одной непротиворечивой моделью [cite:18].

## Разделы для поэтапной проработки

### 1. Архитектура репозитория

#### Итерация 1 — углублённая проработка

Архитектурно репозиторий выглядит не как обычная Python-библиотека, а как многослойный локальный AI-agent harness, где в одном монорепо сосуществуют: runtime-ядро (`core/`), доставляемые пакеты и интеграции (`packages/`), пользовательские и системные конфигурации (`configs/`, `.claude`, `.codex`, `.claude-plugin`, `.agents`), а также операционный knowledge layer (`docs/`, `plans/`, `roadmap/`, `README.md`, `CLAUDE.md`, `AGENTS.md`, `CHANGELOG.md`) [cite:18]. Такая форма сильна для скорости эволюции, но быстро приводит к архитектуре “много вертикальных срезов без одной формальной карты”, когда проект хорошо понятен автору, но всё дороже в сопровождении для второго разработчика [cite:18].

По корневой структуре уже можно выделить по крайней мере шесть bounded contexts: `core/` как runtime/domain ядро; `packages/` как каталог поставляемых интеграций и harness-specific компонентов; `.claude`/`.codex`/`.agents`/`.claude-plugin` как agent ecosystem layer; `configs/` и example-json файлы как configuration surface; `scripts/` как operational automation layer; `docs/`/`plans/`/`roadmap/`/корневые markdown-файлы как knowledge and governance layer [cite:18]. Проблема не в самом количестве контекстов, а в том, что их границы не выражены на уровне явной архитектурной документации, а значит реальные зависимости между ними приходится восстанавливать из структуры и кода [cite:18].

#### Карта слоёв

##### A. Runtime/domain core

Модуль `core/` выглядит как фактическое сердце системы: в нём сосредоточены `project.py`, `repo.py`, `provider.py`, `provider_registry.py`, `provider_manifest.py`, `provider_lock.py`, `provider_config.py`, `provider_artifact.py`, а также сопутствующие `cli.py`, `env.py`, `http.py`, `io.py`, `paths.py`, `proc.py`, `pathology.py`, `block.py` [cite:18]. Уже по именованию видно, что здесь смешаны как минимум четыре разных ответственности: доменная модель провайдеров, orchestration/runtime flows, инфраструктурные адаптеры и CLI-facing coordination [cite:18].

Это значит, что `core/` сейчас, вероятно, выполняет роль одновременно domain layer, application layer и infra layer. Такая компоновка допустима на ранней стадии, но на зрелом проекте она обычно приводит к двум проблемам: рост “god modules” и зависимость почти всех сценариев от одного общего набора утилит и резолверов [cite:18].

##### B. Agent ecosystem layer

Наличие одновременно `.agents`, `.claude`, `.codex` и `.claude-plugin` показывает, что репозиторий поддерживает несколько способов описывать поведение агентов, окружения и vendor-specific интеграции [cite:18]. Это важный архитектурный плюс, потому что проект явно не завязан на один-единственный execution surface, но это и один из главных рисков: одинаковые intent-правила, workflow hints и safety assumptions могут быть дублированы сразу в нескольких экосистемах [cite:18].

Если эти каталоги являются разными представлениями одной и той же модели, проекту нужен единый canonical schema/source-of-truth и генерация производных артефактов. Если же это автономные подсистемы, тогда им нужны чёткие compatibility boundaries, version policy и карта ownership; без этого архитектура неизбежно накапливает дрейф [cite:18].

##### C. Hook and harness layer

Файл `packages/harness/configs/claude-code/hooks/run-report/_lib.py` показывает, что значимая часть operational intelligence вынесена в hook-слой, а не в изолированную доменную библиотеку [cite:17]. Этот код не просто парсит события, а восстанавливает структуру прогона, usage-метрики, re-read hotspots, error loops, retrieval-активность, protected writes, workflow relaunch-сигналы и dev-loop артефакты, причём делает это с защитой от schema drift и битых входов [cite:17].

Архитектурно это означает, что hook layer уже стал не тонкой интеграцией, а существенной частью системы наблюдаемости и анализа поведения агентов. Такой подход жизнеспособен, но без явного разделения на adapter/parser/metrics/reporting слои делает hooks потенциальным центром бизнес-логики второго порядка — то есть логики о поведении системы, которая не формализована как основная доменная модель [cite:17].

##### D. Configuration surface

Наличие `config.example.json`, `.mcp.json.example`, `safe-dirs.example.json`, а также директорий `configs/` и `.github/` указывает на широкую конфигурационную поверхность системы [cite:18]. Чем шире эта поверхность, тем важнее чётко развести: runtime config, operator config, security policy, local-machine bootstrap, provider registry config и generated lock/manifests [cite:18].

Пока по структуре видно скорее обратное: конфиги распределены по нескольким местам, и без детального чтения невозможно сразу понять, какие из них являются пользовательскими, какие системными, а какие производными. Это архитектурный smell discoverability, даже если технически всё работает [cite:18].

##### E. Knowledge and governance layer

В одном репозитории одновременно присутствуют `README.md`, `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, а также целые каталоги `docs/`, `plans/`, `roadmap/` и `RESEARCH/` [cite:18]. Это выглядит как зрелая knowledge architecture, но на практике такие структуры часто перерастают в “документационный лес”, где трудно быстро ответить на простой вопрос: какой документ является входной точкой, какой — operational handbook, какой — author-only brain dump, а какой — normative spec [cite:18].

Архитектурно документация здесь уже не просто сопутствующий слой, а полноценный контур управления системой. Поэтому её надо рассматривать как часть архитектуры, а не как вторичную зону [cite:18].

#### Границы ответственности

На текущем уровне видимости проект похож на modular monolith с частично размытыми boundaries, а не на набор хорошо изолированных пакетов [cite:18]. Основное достоинство такой формы — высокая скорость изменения: можно быстро добавлять новые hooks, providers, config contracts и агентные сценарии, не тратя недели на formal package boundaries [cite:18]. Основной недостаток — каждая новая фича повышает связанность репозитория и усложняет reasoning о том, какой слой за что отвечает [cite:18].

Предварительно границы выглядят так:

- `core/` — должен быть domain/application runtime, но, вероятно, уже частично содержит infra helpers и coordination code [cite:18].
- `packages/` — должен быть distribution/integration layer, но уже содержит runtime-significant hooks [cite:17][cite:18].
- `.claude` / `.codex` / `.agents` / `.claude-plugin` — должны быть adapter-specific delivery layers, но могут скрывать параллельные модели агентного поведения [cite:18].
- `configs/` и example JSON files — должны быть config entrypoints, но, вероятно, не имеют одной явно видимой taxonomy [cite:18].
- `docs/`, `plans/`, `roadmap/`, `RESEARCH/` — knowledge/governance layer, который уже влияет на практическое сопровождение и therefore belongs to architecture [cite:18].

#### Архитектурные запахи

##### 1. Directory-level overloading

Слишком много смыслов сосредоточено в верхнем уровне репозитория: рядом лежат runtime-код, agent configs, hooks, планы, roadmap, research, docs и operational metadata [cite:18]. Для автора это удобно, но для команды это повышает стоимость навигации и делает архитектурную карту неявной [cite:18].

##### 2. Potential dual sources of truth

Одновременное наличие `core/provider_*`, `packages/.../hooks/...`, `.claude*`, `.agents`, `.codex`, `configs/` и множества docs почти наверняка означает, что часть системных правил выражена и в коде, и в конфиге, и в документации [cite:17][cite:18]. Сам по себе duplication не всегда вреден, но без централизованной модели он рождает drift и “договорённости по памяти” [cite:18].

##### 3. Hook gravity

`run-report/_lib.py` уже демонстрирует, как hook-инфраструктура может начать поглощать сложную аналитическую логику: schema adaptation, signal extraction, grouping rules, fallback semantics, protected-write detection [cite:17]. Это smell не потому, что код плохой, а потому, что значимая семантика системы начинает жить в интеграционном слое, где её труднее тестировать и концептуально переиспользовать [cite:17].

##### 4. Implicit architecture

Даже по богатой структуре репозитория нельзя сразу однозначно ответить: что является canonical runtime graph, где описан lifecycle провайдера, где зафиксирована схема агентной экосистемы и где формально описана стратегия hook/schema versioning [cite:17][cite:18]. Это главный архитектурный дефицит первого впечатления: система кажется зрелой, но не достаточно self-explanatory [cite:17][cite:18].

#### Target architecture

Целевую архитектуру для такого проекта стоит строить не как микросервисную декомпозицию, а как строго оформленный modular monolith с явными пакетными границами и one-way dependencies. Практически это означает, что нужно не “распиливать всё на много реп”, а формально выделить несколько стабильных архитектурных колец внутри текущего монорепо [cite:18].

Предлагаемая целевая схема:

- `domain/` или логически выделенный доменный слой внутри `core/`: provider model, manifest/lock invariants, project/repo model, state transitions.
- `application/`: orchestration use-cases, CLI workflows, install/update/sync/validate операции.
- `infra/`: file I/O, subprocess, HTTP, environment, path resolution, external tool shims.
- `adapters/agents/`: `.claude`, `.codex`, `.agents`, plugin-specific packaging как delivery adapters поверх общей модели.
- `adapters/hooks/`: hook-specific ingestion/parsing/reporting поверх общих telemetry contracts.
- `docs/architecture/`: canonical архитектурные карты, contracts, invariants, glossary.

Ключевой принцип: agent- и hook-экосистемы должны стать адаптерами над ядром, а не местами, где живёт самостоятельная копия доменной истины. Документация при этом должна перейти от “распределённой памяти автора” к модели “single source of navigation, multiple audience-specific views” [cite:17][cite:18].

#### Roadmap реорганизации

##### Этап A — сделать архитектуру видимой

- Добавить `docs/architecture/overview.md` с картой слоёв, dependency rules и glossary.
- Добавить `docs/architecture/repo-map.md` с назначением каждой корневой директории.
- Зафиксировать canonical terminology: provider, manifest, lock, artifact, hook, workflow, agent pack, managed path, protected write.

##### Этап B — развести слои

- Отделить domain model провайдеров от infra helpers и от CLI coordination.
- Вынести hook parsing contracts в отдельную library-style область, чтобы hooks были thin entrypoints.
- Явно отделить user-editable configs от generated artifacts и от shipped templates.

##### Этап C — унифицировать agent ecosystem

- Определить canonical agent definition schema.
- Сделать vendor-specific директории производными адаптерами или по крайней мере задокументированными variant layers.
- Установить policy на versioning и drift detection между `.claude`, `.codex`, `.agents`, `.claude-plugin` [cite:18].

##### Этап D — уменьшить архитектурную энтропию

- Сократить число root-level entrypoints, где это возможно.
- Перенести часть author-centric материалов из корня в более предсказуемые зоны (`docs/`, `internal/`, `research/`).
- Ввести архитектурные decision records для крупных реорганизаций.

#### Quick wins

- Добавить один короткий архитектурный документ уровня “как устроен repo за 5 минут” [cite:18].
- Ввести таблицу ownership по корневым каталогам [cite:18].
- Описать, какие директории являются runtime, какие generated, какие user-facing, какие internal-only [cite:18].
- Явно описать, почему hook-логика живёт в `packages/harness/...`, и что в ней считается stable contract, а что best-effort telemetry [cite:17].

#### Ключевые вопросы для следующей верификации

- Является ли `core/` настоящим domain core, или это historical catch-all слой?
- Что в проекте является canonical source of truth для provider lifecycle?
- Являются ли `.claude`, `.codex`, `.agents`, `.claude-plugin` разными представлениями одной модели или независимыми integration surfaces?
- Какие файлы/директории генерируются, а какие редактируются вручную?
- Где формально описаны compatibility guarantees для hooks и telemetry schema?

### 2. Python core quality

#### Итерация 2 — углублённая проработка

Даже без полного построчного чтения всех модулей уже видно, что `core/` — очень плотный пакет с широким диапазоном ответственности: здесь одновременно живут CLI, project/repo orchestration, environment/path/process helpers, HTTP/I/O utilities, а также целый кластер `provider_*` модулей, включая особенно крупные `provider_lock.py` и `provider_manifest.py` [cite:18]. Это сильный сигнал, что качество Python-ядра здесь нужно оценивать не только по стилю кода, но прежде всего по архитектурной связности, степени процедурного дрейфа и явности контрактов между модулями [cite:18].

Ключевая гипотеза после первой архитектурной итерации подтверждается: `core/` с высокой вероятностью является не просто “ядром”, а исторически накопленным coordination layer, где постепенно осели domain logic, orchestration logic, infra helpers и часть UX-level поведения [cite:18]. Такая форма часто даёт быстрый throughput на одного автора, но дорого обходится при масштабировании, потому что почти любой новый сценарий начинает проходить через один и тот же пакет и один и тот же набор утилит [cite:18].

#### Первичная карта модулей

##### Coordination / application-facing

- `cli.py` — интерфейсный входной слой, но по расположению внутри `core/` уже подозрительно близок к доменной логике [cite:18].
- `project.py`, `repo.py` — вероятные orchestrator-модули верхнего уровня, связывающие filesystem, config resolution и provider operations [cite:18].

##### Provider domain cluster

- `provider.py`
- `provider_artifact.py`
- `provider_config.py`
- `provider_lock.py`
- `provider_manifest.py`
- `provider_registry.py` [cite:18]

Сам факт, что вокруг одного доменного существительного существует шесть отдельных модулей, означает хорошую попытку разнести ответственность. Но размеры некоторых файлов, особенно `provider_lock.py` (66 KB), `provider_manifest.py` (27 KB), `provider_artifact.py` (18 KB), `provider_config.py` (11 KB) и `provider_registry.py` (11 KB), также показывают, что это уже не маленькие value-object helpers, а насыщенный orchestration subdomain [cite:18].

##### Infra / utility cluster

- `env.py`, `http.py`, `io.py`, `paths.py`, `proc.py`, `block.py` [cite:18].

Эти модули выглядят как слой адаптеров и утилит. Проблема в том, что пока он не отделён архитектурно от coordination/domain кода, а значит любой из этих модулей может постепенно превращаться из тонкого helper в неявный cross-cutting dependency [cite:18].

##### Suspicious utility / catch-all candidate

- `pathology.py` выделяется уже одним названием и размером около 16 KB [cite:18]. Пока без полного чтения нельзя утверждать его роль, но сам нейминг похож на признак “сложной диагностической/служебной зоны”, которая часто вырастает вне чистой доменной модели и потом становится catch-all местом для проблемных кейсов [cite:18].

#### Основные выводы по качеству ядра

##### 1. Вероятный coordination-heavy core

Судя по составу пакета, `core/` сочетает роли application service layer и infra convenience layer, а не реализует строгое domain core в DDD-смысле [cite:18]. Это не обязательно ошибка, но это означает, что технический долг будет накапливаться не только в отдельных функциях, а в самой форме пакета: разработчику всё труднее понимать, где должны жить новые правила и куда именно помещать новые сценарии [cite:18].

##### 2. Provider cluster может быть фактическим доменом проекта

Размеры и детализация `provider_*` модулей намекают, что именно они, а не `cli.py` или `project.py`, содержат главную сложность системы [cite:18]. Если это так, то вокруг провайдеров уже существует реальный домен со state transitions, merge/resolution логикой, артефактами, lock-файлами и registry-процедурами, но он, вероятно, ещё не оформлен как явная доменная модель с чёткими инвариантами и интерфейсами [cite:18].

##### 3. Procedural drift наиболее вероятен в крупных файлах

Очень крупные Python-модули почти всегда со временем накапливают длинные linear workflows, условные ветвления, ad-hoc validation и локальные helper-функции, которые были удобны на момент написания, но затем стали частью скрытого API [cite:18]. Без строгого разделения на pure state transitions, persistence/adapters и orchestration shell, такие модули начинают вести себя как сценарные движки, которые сложно тестировать по инвариантам и сложно безопасно рефакторить [cite:18].

##### 4. Utility-first evolution может маскировать скрытую связанность

Наличие `env.py`, `io.py`, `paths.py`, `proc.py`, `http.py` — это нормально, но если coordination-код напрямую зависит от этих модулей без тонких интерфейсов, то infra-детали просачиваются в доменную логику [cite:18]. В результате функции выглядят “простыми” локально, но реальные side effects и operational assumptions размазаны по всему пакету [cite:18].

#### Возможные smell-классы

##### God modules

`provider_lock.py` и `provider_manifest.py` уже по размеру являются кандидатами в god modules [cite:18]. Не потому, что большой файл всегда плохой, а потому, что в системах конфиг-резолвинга и lock generation такие файлы быстро начинают совмещать parsing, normalization, validation, merge policy, error rendering, filesystem persistence и backward compatibility rules [cite:18].

##### Hidden protocols

Если `provider_*`, `project.py`, `repo.py` и `cli.py` общаются через ad-hoc словари, loosely shaped dict payloads или implicit file conventions, то внутри `core/` уже существует скрытый протокол без формально описанного контракта [cite:18]. Это один из самых дорогих видов технического долга, потому что код “работает”, но изменение любого поля или порядка resolution ломает смежные сценарии неочевидным образом [cite:18].

##### Utility leakage

Когда `paths.py`, `io.py`, `env.py` и `proc.py` не ограничены тонкой ролью, они начинают формировать альтернативный domain language: логика проекта становится не про provider state, а про то, какой path собрать, какой env прочитать и какой proc вызвать [cite:18]. Тогда доменная модель оказывается скрытой за инфраструктурной механикой [cite:18].

##### Catch-all diagnostics

`pathology.py` с высокой вероятностью либо очень полезный diagnostic layer, либо симптом того, что часть неукладывающихся кейсов уже была вытеснена в отдельный технический карман [cite:18]. Во втором случае это может означать, что доменная модель не покрывает проблемное пространство достаточно явно [cite:18].

#### Качество API внутри ядра

На уровне архитектурных признаков больше всего хочется проверить четыре качества:

- Явные ли типы входов/выходов у `core/` API, или большая часть связей завязана на dict/list payloads и файловые контракты.
- Есть ли разделение между pure calculation и side-effecting procedures.
- Отделены ли error types от human-readable error formatting.
- Можно ли вызывать доменную логику без CLI и без реального filesystem/process окружения.

Если хотя бы на два из этих вопросов ответ окажется отрицательным, текущее ядро уже нуждается в целевом выделении application services и domain services как отдельных слоёв. Иначе любой новый функционал продолжит утрамбовывать `core/` как универсальный procedural hub [cite:18].

#### Целевая модель качества для `core/`

Для такого проекта хорошим target state будет не “больше абстракций вообще”, а строгое разделение по ролям:

- Domain layer: provider state, lock/manifest invariants, registry rules, artifact model.
- Application layer: install/update/sync/resolve/validate workflows.
- Infra layer: filesystem, subprocess, HTTP, environment, path resolution.
- Interface layer: CLI and hook entrypoint adapters.

Ключевой критерий качества: доменную операцию должно быть можно протестировать без CLI, без реального shell и без неявного чтения глобального состояния процесса. Если это сейчас невозможно, значит `core/` хранит слишком много coordination noise [cite:18].

#### Refactoring map

##### Phase 1 — сделать ядро наблюдаемым

- Составить таблицу всех модулей `core/`: ответственность, импортируемые зависимости, side effects, приблизительный уровень связности.
- Отдельно отметить публичные функции, которые реально вызываются снаружи пакета.
- Выделить все функции, которые одновременно читают/пишут файлы, валидируют конфиг и принимают доменные решения.

##### Phase 2 — изолировать infra

- Перевести `env.py`, `io.py`, `paths.py`, `proc.py`, `http.py` в clearly-named infra namespace или логический слой.
- Минимизировать прямые обращения к ним из доменных модулей.
- Вводить small adapter interfaces там, где сейчас side effects встроены в расчёт.

##### Phase 3 — декомпозировать provider cluster

- Разделить state model, resolution logic, persistence logic и rendering/diagnostic logic.
- Убрать ad-hoc coupling между `provider_lock.py`, `provider_manifest.py`, `provider_registry.py` и CLI-facing сценарием.
- Формализовать invariants и сделать их test-first контрактами.

##### Phase 4 — очистить coordination слой

- Свести `project.py` и `repo.py` к application services, а не к коллекциям mixed helpers.
- Сделать `cli.py` thin adapter, который только распаковывает ввод, вызывает use-case и форматирует результат.
- Вынести explain/diagnostics в отдельные presenter/formatter utilities, если они сейчас перемешаны с логикой.

#### Quick wins

- Зафиксировать ownership и intended responsibility для каждого `core/*.py` в коротком internal doc [cite:18].
- Пометить самые крупные файлы как кандидаты на decomposition backlog: `provider_lock.py`, `provider_manifest.py`, `provider_artifact.py`, `pathology.py` [cite:18].
- Начать добавлять typed result objects там, где сейчас используются свободные словари между модулями.
- Явно разделять pure functions и file/process-mutating functions хотя бы соглашением по именованию и расположению.

#### Long-term refactors

- Выделить provider domain в отдельный под-пакет с формальными инвариантами.
- Вынести infra adapters из `core/` в отдельную архитектурную зону.
- Перестроить `cli.py` вокруг явных application use-cases.
- Превратить diagnostic/problem-analysis код в отдельный bounded context, если `pathology.py` действительно служит этой цели.

#### Следующие проверки

- Построчно разобрать `provider_lock.py`, `provider_manifest.py`, `provider_registry.py`, `provider.py`, `provider_config.py`, `provider_artifact.py`.
- Проверить `cli.py`, `project.py`, `repo.py` на смешение orchestration и domain logic.
- Понять реальную роль `pathology.py`.
- Проверить, используются ли dataclasses, TypedDict, Protocol, custom exceptions или ядро в основном держится на dict-oriented contracts.

### 3. Provider / manifest / registry / lock model

#### Итерация 3 — углублённая проработка

По составу `core/` видно, что provider subsystem — один из главных доменных центров проекта: вокруг него выделены отдельные модули `provider.py`, `provider_registry.py`, `provider_manifest.py`, `provider_lock.py`, `provider_config.py`, `provider_artifact.py`, причём часть из них уже очень крупная [cite:18]. Это почти наверняка означает, что именно здесь живёт основная stateful логика системы: определение провайдера, разрешение его конфигурации, построение manifest/lock представлений, работа с registry и подготовка артефактов [cite:18].

Архитектурно это сильный знак зрелости домена, но одновременно и главный риск: когда один домен распадается на несколько крупных файлов без явно описанной модели жизненного цикла, система начинает зависеть от неформальных соглашений между модулями [cite:18]. В таких случаях баги редко живут в одной функции; они обычно живут в переходах между config, registry, manifest, lock и artifact слоями [cite:18].

#### Предварительная доменная модель

На текущем уровне видимости provider subsystem можно описать как конвейер из нескольких представлений одного и того же сущностного объекта — провайдера [cite:18]. Предположительно, эти представления таковы:

- **Provider definition** — что такое провайдер как логическая единица, какие у него identity/metadata/тип/источник [cite:18].
- **Provider config** — пользовательские и системные параметры, влияющие на резолвинг и установку [cite:18].
- **Provider registry view** — внешний или внутренний каталог доступных провайдеров и версий [cite:18].
- **Provider manifest** — декларативное или вычисленное описание того, что должно быть установлено/доставлено [cite:18].
- **Provider lock** — зафиксированное воспроизводимое состояние после резолвинга [cite:18].
- **Provider artifacts** — материальные результаты установки/синхронизации/генерации, необходимые рантайму или интеграционным слоям [cite:18].

Если эта модель близка к фактической реализации, то проект уже имеет полноценный package-management-like subdomain. А такие домены всегда требуют очень жёсткой формализации инвариантов и точек истины: иначе manifest, lock и artifact начинают описывать одно и то же, но с разной степенью полноты и в разное время [cite:18].

#### Вероятный жизненный цикл провайдера

Даже до детального чтения кода можно восстановить вероятный lifecycle:

1. Провайдер определяется в конфиге или registry-driven источнике [cite:18].
2. Его параметры и overrides резолвятся через config layer [cite:18].
3. Из этого состояния строится manifest как желаемая спецификация [cite:18].
4. Затем происходит resolution/selection и фиксируется lock-state как воспроизводимый результат [cite:18].
5. После этого генерируются или подтягиваются artifacts, которые используются runtime или hook/agent слоями [cite:18].
6. Повторные операции сравнивают текущее состояние с lock/manifest и решают, нужен ли update, repair, reinstall или drift correction [cite:18].

Если именно так устроен поток, то самый критичный архитектурный вопрос звучит так: **какой шаг является source of truth для последующих шагов** [cite:18]. В зрелых системах manifest и lock выполняют разные роли: manifest фиксирует intent, а lock фиксирует resolved reality. Если в проекте это разделение не железобетонное, начинается очень дорогая ambiguity [cite:18].

#### Возможные точки истины

##### Вариант 1 — config-first truth

Если главной истиной выступает конфиг, то manifest/lock/artifact являются производными. Плюс такого подхода — высокая прозрачность для пользователя. Минус — всё, что вычислено позднее, легко становится несогласованным с исходной конфигурацией, если нет строгой пересборки и drift detection [cite:18].

##### Вариант 2 — manifest-first truth

Если manifest является канонической описательной моделью, а config лишь сырьём для его построения, система становится архитектурно чище. Но тогда нужен очень понятный pipeline generation, потому что разработчику должно быть ясно, когда manifest пересчитывается, можно ли его редактировать вручную и кто отвечает за backward compatibility [cite:18].

##### Вариант 3 — lock-first operational truth

Если фактически именно lock-файл определяет рабочее состояние системы, то проект уже близок к package manager semantics. Это хорошо для воспроизводимости, но без ясного разграничения “желаемое” vs “разрешённое/установленное” состояние пользователь быстро теряет понимание, почему система выбрала именно это [cite:18].

На данном этапе самый вероятный риск — не чисто неправильный выбор одной точки истины, а **смешанная truth model**, когда разные команды и модули по-разному трактуют приоритет config, manifest и lock [cite:18].

#### Вероятные зоны дублирования ответственности

##### 1. Registry vs config resolution

`provider_registry.py` и `provider_config.py` потенциально пересекаются в вопросе: где именно принимается решение, какой provider candidate считается допустимым [cite:18]. Если часть ограничений задаётся конфигом, а часть проверяется в registry layer, нужна очень чёткая граница — иначе selection policy будет размазана по двум местам [cite:18].

##### 2. Manifest vs lock normalization

`provider_manifest.py` и `provider_lock.py` могут дублировать normalization, identity resolution, dependency flattening и validation [cite:18]. Это классический smell для package-like доменов: сначала правила пишут для manifest generation, потом те же проверки ещё раз появляются при lock materialization, а затем третья версия живёт в update/sync flow [cite:18].

##### 3. Artifact layer как скрытый второй lock

`provider_artifact.py` особенно опасен архитектурно, если в нём зашиты implicit assumptions о том, что уже должно быть резолвлено и как именно выглядит final state [cite:18]. В таком случае артефакты перестают быть чистым выводом и становятся вторым operational source of truth, который может расходиться с lock-state [cite:18].

##### 4. Provider identity scattering

Если identity провайдера определяется частично в `provider.py`, частично в registry, частично в manifest serialization и частично в artifact naming, то система почти неизбежно сталкивается с edge-cases вокруг rename, aliasing, migration и backward compatibility [cite:18]. Identity должна быть одной и жёстко нормализованной, иначе все остальные слои становятся хрупкими [cite:18].

#### Скрытые инварианты, которые почти наверняка существуют

Даже без чтения конкретных функций у такого домена обычно есть обязательные инварианты. Если они не зафиксированы тестами и схемами, они живут как неявное знание автора [cite:18]. Для `swissknifeman` почти наверняка критичны такие инварианты:

- Один provider identity должен детерминированно маппиться между config, registry, manifest, lock и artifact слоями [cite:18].
- Одна и та же входная конфигурация должна давать воспроизводимый lock-state при неизменных внешних зависимостях [cite:18].
- Lock должен быть строже manifest: lock фиксирует resolved selection, а не просто повторяет intent [cite:18].
- Artifact generation не должна менять доменное решение; она должна только материализовать уже принятое состояние [cite:18].
- Reload/sync/update должны быть идемпотентными относительно уже зафиксированного корректного lock-state [cite:18].
- Ошибки registry/config/lock drift должны быть различимы и объяснимы пользователю [cite:18].

#### Проблемные state transitions

##### Config -> Manifest

Самая частая проблема здесь — implicit defaults и скрытые normalization rules. Если manifest generation не полностью explainable, пользователь не понимает, почему итоговая спецификация выглядит именно так [cite:18].

##### Manifest -> Lock
n
Здесь основной риск — nondeterministic resolution, особенно если registry-данные, версии, availability или порядок обхода влияют на выбор результатов [cite:18]. Любая недетерминированность в этом переходе бьёт прямо по воспроизводимости [cite:18].

##### Lock -> Artifact

Если artifact generation допускает дополнительное ветвление или “умные” поправки, которые не отражены в lock-state, система становится трудно диагностируемой: формально lock один, фактически материализованное состояние другое [cite:18].

##### Existing state -> Reconcile

Для повторных запусков критичен reconcile flow: как система понимает, что уже установлено, что сломано, что устарело, что можно переиспользовать, а что надо пересобрать [cite:18]. В таких местах обычно живёт самый дорогой операционный долг, потому что код начинает учитывать исторические исключения и миграции [cite:18].

#### Риск-профиль подсистемы

| Риск | Вероятность | Влияние | Почему |
|---|---|---|---|
| Смешанная truth model между config/manifest/lock | Высокая [cite:18] | Высокое [cite:18] | Слишком много близких по смыслу слоёв без подтверждённой явной модели [cite:18] |
| Дублирование validation/normalization логики | Высокая [cite:18] | Высокое [cite:18] | Наличие нескольких крупных `provider_*` модулей естественно провоцирует повторение правил [cite:18] |
| Artifact layer хранит неявные operational assumptions | Средняя [cite:18] | Высокое [cite:18] | Артефактный слой часто становится вторым скрытым состоянием системы [cite:18] |
| Слабая explainability resolution pipeline | Средняя [cite:18] | Высокое [cite:18] | Пользователь не видит, почему выбран именно такой lock-result [cite:18] |
| Недостаточная идемпотентность reconcile/update flows | Средняя [cite:18] | Очень высокое [cite:18] | Повторные прогоны в package-like домене быстро обрастают edge-cases [cite:18] |
| Provider identity drift между слоями | Средняя [cite:18] | Высокое [cite:18] | Идентичность провайдера — фундамент всех последующих переходов [cite:18] |

#### Рекомендации

| Область | Рекомендация | Эффект |
|---|---|---|
| Source of truth | Формально зафиксировать, что именно считается intent-state, resolved-state и materialized-state | Устраняет концептуальную неоднозначность [cite:18] |
| Provider identity | Ввести единый canonical identity object/shape | Снижает drift между слоями [cite:18] |
| Manifest/lock boundary | Явно описать различие между декларативной спецификацией и зафиксированным результатом | Улучшает explainability и reproducibility [cite:18] |
| Artifact semantics | Сделать artifacts чистой функцией от lock-state или явно описанного install-plan | Убирает скрытое второе состояние [cite:18] |
| Resolution pipeline | Добавить explain/trace режим для показа шагов нормализации и выбора | Облегчает отладку и поддержку [cite:18] |
| Tests | Сформировать golden/invariant tests на переходы config -> manifest -> lock -> artifact | Защищает от регрессий по критическим доменным путям [cite:18] |

#### Target model

Целевая модель для provider subsystem должна быть не “много helper-модулей вокруг провайдера”, а формально описанный state machine с четырьмя главными уровнями [cite:18]:

1. **Intent state** — пользовательская или проектная конфигурация.
2. **Resolved state** — lock-представление после выбора конкретных версий/источников/вариантов.
3. **Materialization plan** — детальный план действий по доставке или обновлению.
4. **Materialized state** — фактически размещённые артефакты и зафиксированный operational result.

Manifest при этом должен быть либо частью intent-state, либо строго определённым промежуточным canonical document, но не “ещё одним видом истины наравне со всеми” [cite:18]. Самое главное здесь — у каждого уровня должен быть свой owner, свой формат и свой набор инвариантов [cite:18].

#### Обязательные тестовые инварианты

Следующий слой зрелости для этой подсистемы — жёсткие contract tests. Минимальный набор выглядит так:

- Одинаковый config всегда даёт одинаковый manifest при одинаковой версии кода [cite:18].
- Одинаковый manifest и одинаковое registry-state всегда дают одинаковый lock [cite:18].
- Lock serialization/deserialization является lossless [cite:18].
- Artifact generation детерминирована относительно lock-state [cite:18].
- Reconcile повторного запуска над уже корректным state ничего лишнего не меняет [cite:18].
- Invalid config, unavailable registry entry, corrupted lock и artifact drift дают разные, распознаваемые классы ошибок [cite:18].
- Rename/migration сценарии provider identity явно покрыты backward compatibility тестами [cite:18].

#### Что добавлять следующими итерациями внутри этого раздела

Этот раздел теперь зафиксирован на уровне архитектурной модели и рисков, но для качественного аудита его нужно дорастить до уровня кода. Следующие подпункты для углубления:

- фактический lifecycle по коду;
- конкретные публичные функции каждого `provider_*` модуля;
- таблица “кто за что отвечает” между manifest/lock/registry/config/artifact;
- список повторяющихся validation rules;
- набор конкретных refactoring steps по модульной декомпозиции.

### 4. CLI / UX / developer ergonomics

#### Итерация 4 — углублённая проработка

По структуре репозитория CLI почти наверняка является главным операционным интерфейсом ко всей системе: в `core/` есть `cli.py`, рядом лежат `project.py`, `repo.py`, конфиги, provider-модули и operational scripts, а значит именно командная оболочка должна собирать все эти доменные и инфраструктурные слои в понятные пользовательские сценарии [cite:18]. Для такого типа проекта CLI — не “тонкая удобная надстройка”, а фактически runtime console для локального AI-agent harness, поэтому требования к UX здесь выше, чем у обычного dev-tool скрипта [cite:18].

На текущем уровне обзора главный вопрос к CLI не в том, “удобны ли флаги”, а в том, может ли интерфейс объяснить сложность системы. В проекте есть provider lifecycle, config surface, hook/harness инфраструктура, agent ecosystems и, вероятно, drift/reconcile сценарии; если CLI не умеет делать эти процессы прозрачными, то пользователь вынужден читать исходники и markdown-файлы вместо того, чтобы работать с системой через explainable commands [cite:18].

#### Роль CLI в этом проекте

Для `swissknifeman` CLI, вероятно, выполняет сразу несколько ролей [cite:18]:

- Точка входа для основных workflows.
- Фасад над provider/config/manifest/lock операциями.
- Инструмент bootstrap и сопровождения локального окружения.
- Диагностический интерфейс при поломках hooks, providers, configs и generated artifacts.
- Объясняющий слой, который должен раскрывать внутреннюю модель системы человеку.

Если хотя бы одна из этих ролей реализована слабо, то стоимость эксплуатации инструмента заметно растёт. Для сложного локального harness-а отсутствие explainability почти равнозначно отсутствию UX [cite:18].

#### Наиболее вероятные UX-проблемы

##### 1. CLI может быть слишком thin-wrapper

Если `core/cli.py` в основном маршрутизирует argv в внутренние функции без отдельного UX-проектирования, то у пользователя остаётся плохая видимость доменных состояний и переходов [cite:18]. Такой CLI технически “работает”, но не помогает понять, что именно система собирается сделать, какие файлы затронет, какие state transitions сейчас происходят и почему операция завершилась тем или иным результатом [cite:18].

##### 2. CLI может быть слишком coupled к внутренней структуре

Если команды повторяют модульную структуру кода вместо пользовательских задач, интерфейс неизбежно становится author-centric [cite:18]. Например, для проекта такого класса пользователю чаще нужны сценарии вроде `validate`, `doctor`, `resolve`, `status`, `sync`, `repair`, `explain`, `trace`, а не набор команд, отражающих внутренние слои реализации [cite:18].

##### 3. Ошибки домена и ошибки инфраструктуры могут смешиваться

В системах с файлами, процессами, сетевыми источниками и generated artifacts типовая проблема — одинаково плохо объясняются и неверный config, и отсутствие файла, и сломанный provider selection, и конфликт lock-state [cite:18]. Если CLI не различает error classes, то любой failure превращается в “что-то пошло не так”, после чего разработчик вынужден дебажить вручную [cite:18].

##### 4. Недостаток recoverability

Для инструмента этого типа критично не только сообщить об ошибке, но и подсказать путь восстановления: что проверить, какой файл посмотреть, какую команду запустить следующей, можно ли выполнить repair, можно ли сделать dry-run, есть ли safe rollback path [cite:18]. Если этого нет, CLI становится не интерфейсом продукта, а пультом запуска внутренних процедур [cite:18].

#### Каким должен быть хороший CLI для такого домена

Хороший CLI для `swissknifeman` должен быть построен вокруг пользовательских вопросов, а не вокруг внутреннего устройства репозитория [cite:18]. В реальной эксплуатации человек обычно хочет понять одно из пяти:

- Что у меня установлено и в каком состоянии?
- Что система собирается сделать дальше?
- Почему она выбрала именно такое решение?
- Что сейчас сломано?
- Как безопасно восстановиться?

Если эти пять вопросов не закрываются первоклассными командами, интерфейс не соответствует сложности домена [cite:18].

#### Желаемые классы команд

##### Status-oriented

CLI должен иметь богатый `status`/`list`/`show` слой: текущее состояние providers, lock/manifest drift, установленные artifacts, источники конфигурации, активные overrides, связанный runtime context [cite:18]. Статус-команды особенно важны потому, что без них reconcile-системы выглядят как чёрный ящик [cite:18].

##### Validation-oriented

Отдельный слой команд должен отвечать только за проверку: `validate config`, `validate lock`, `validate manifest`, `validate repo`, `validate environment` [cite:18]. Важный принцип здесь — validate не должен мутировать систему; иначе пользователь боится его запускать [cite:18].

##### Diagnostic-oriented

Для такого инструмента почти обязательны `doctor`, `trace`, `explain`, `debug report` команды [cite:18]. Они нужны не “для красоты”, а потому что проект уже оперирует сложными связями между провайдерами, конфигами, хуками и агентными слоями [cite:17][cite:18].

##### Mutation-oriented

Изменяющие команды вроде install/update/sync/repair/reconcile должны уметь работать в безопасных режимах: preview, dry-run, diff, explain-plan [cite:18]. Без этого каждая мутация выглядит как доверительный прыжок веры [cite:18].

#### Explainability как обязательное свойство

После предыдущей итерации по provider model особенно видно, что CLI обязан уметь объяснять resolution pipeline [cite:18]. Минимально полезные explain-сценарии:

- Почему был выбран именно этот provider variant.
- Какие input-конфиги и overrides участвовали в решении.
- Чем текущий manifest отличается от lock-state.
- Почему reconcile считает состояние корректным или сломанным.
- Какие файлы/директории будут изменены следующим запуском.

Это не nice-to-have, а основная защита от operational confusion в сложном локальном orchestrator tool [cite:18].

#### Error model

CLI для такого проекта должен иметь хотя бы следующие классы ошибок, различимые и текстово, и по exit codes [cite:18]:

- **User input/config error** — неверный параметр, конфликтующий config, отсутствующее обязательное поле.
- **Environment error** — нет директории, нет прав доступа, отсутствует бинарь/зависимость.
- **Resolution error** — не удалось подобрать provider/variant/version/state.
- **Drift error** — фактическое состояние не совпадает с lock/manifest expectations.
- **Internal/tool bug** — ситуация, которую пользователь не может исправить сам.

Если всё это сейчас маппится на один exception-flow, значит CLI теряет половину своей пользы как продукта [cite:18].

#### Recoverability

Хороший operational CLI всегда говорит не только “что сломалось”, но и “что делать дальше” [cite:18]. Для `swissknifeman` ожидается такой recovery UX:

- Сообщение о проблеме.
- Класс ошибки.
- Конкретный затронутый объект: provider, manifest, lock, artifact, path, config key.
- Команда следующего действия: `doctor`, `validate`, `status`, `repair`, `explain`.
- При возможности — автоматический safe suggestion.

Без этой цепочки даже сильный внутренний движок воспринимается как хрупкий [cite:18].

#### Приоритетный backlog улучшений

##### P0

- Ввести явные команды `status`, `validate`, `doctor`, `explain`, `trace`, если части из них отсутствуют [cite:18].
- Разделить ошибки по классам и сделать разные exit codes [cite:18].
- Добавить dry-run/plan режим для mutating команд [cite:18].
- Научить CLI показывать, какие конфиги и слои повлияли на принятое решение [cite:18].

##### P1

- Сделать `cli.py` thin adapter поверх application use-cases, если сейчас он тянет coordination logic в себя [cite:18].
- Унифицировать help-систему: короткое описание сценария, примеры, опасные эффекты, related commands [cite:18].
- Добавить machine-readable output modes для automation/CI, если это релевантно [cite:18].
- Ввести человекочитаемые diff/explain outputs для manifest/lock drift [cite:18].

##### P2

- Добавить guided repair flows.
- Добавить интерактивные confirm/prompt режимы там, где они безопасны и уместны.
- Ввести snapshots/debug bundles для сложных failure cases.

#### Целевая форма CLI

Архитектурно CLI должен быть разделён на три части [cite:18]:

- **Command parser** — только парсинг аргументов и маршрутизация.
- **Use-case invocation layer** — явный вызов доменных/application операций.
- **Presenter/reporting layer** — человекочитаемый или machine-readable вывод, плюс error rendering.

Самая частая ошибка зрелых внутренних инструментов — перемешивать эти три роли в одном файле `cli.py`. Если это происходит здесь, рефакторинг CLI принесёт эффект далеко за пределами UX: он также снизит связанность ядра и улучшит тестируемость [cite:18].

#### Какие команды особенно нужны проекту такого класса

Ниже — минимальный набор интерфейсных сценариев, которые хорошо соответствуют домену репозитория [cite:18]:

| Команда/режим | Назначение | Почему важна |
|---|---|---|
| `status` | Показать текущее состояние системы | Убирает эффект чёрного ящика [cite:18] |
| `validate` | Проверить config/manifest/lock/env без мутаций | Создаёт безопасную точку диагностики [cite:18] |
| `doctor` | Выявить наиболее вероятные operational проблемы | Снижает стоимость дебага [cite:18] |
| `explain` | Объяснить, как принято текущее решение | Критично для provider resolution [cite:18] |
| `trace` | Показать пошаговый pipeline операции | Нужен при сложных reconcile/update сценариях [cite:18] |
| `plan` / `dry-run` | Показать будущие изменения без применения | Защищает от неожиданных мутаций [cite:18] |
| `repair` | Безопасно исправить известные несогласованности | Повышает recoverability [cite:18] |
| `report` / `debug-bundle` | Собрать состояние для анализа проблем | Ускоряет поддержку и self-debugging [cite:18] |

#### Что важно проверить дальше по коду

Этот раздел пока построен по архитектурным признакам, но следующая стадия должна проверить реализацию на уровне исходников. Особенно важно выяснить:

- Реально ли `cli.py` thin или в нём уже живёт orchestration logic.
- Есть ли единый error rendering layer.
- Как устроена help-система и есть ли примеры сценариев.
- Какие команды уже существуют и какие из перечисленных классов отсутствуют.
- Есть ли preview/dry-run и explain/trace режимы или их придётся проектировать с нуля.

### 5. Hooks и event processing

#### Итерация 5 — углублённая проработка

Hook layer в `swissknifeman` уже нельзя считать просто glue-кодом вокруг Claude Code. По крайней мере один подтверждённый файл — `packages/harness/configs/claude-code/hooks/run-report/_lib.py` — реализует крупный защитный парсер транскриптов, метрики использования, детектирование rereads, error loops, retrieval-вызовов, protected writes, workflow relaunch-сигналов и best-effort dev-loop extraction [cite:17]. Это значит, что hook subsystem здесь выполняет роль не только интеграционного, но и аналитического слоя системы [cite:17].

Архитектурно это сильная сторона, потому что проект пытается извлекать operational intelligence прямо из агентных прогонов. Но это же и главный риск: hooks начинают становиться местом, где живёт вторичная бизнес-логика — логика анализа поведения системы, её качества и безопасности — без явного доменного оформления [cite:17].

#### Что уже подтверждено по коду

`run-report/_lib.py` явно построен как resilience-first библиотека: он парсит JSONL построчно, избегает загрузки всего транскрипта в память, молча пропускает битые строки и неизвестные события, ограничивает размеры коллекций (`_MAX_FAILURES`, `_MAX_FILES`, `_MAX_WORKFLOWS`, `_MAX_READS`, `_MAX_ERROR_LOOPS`, `_MAX_RETRIEVAL_QUERIES`, `_MAX_SUBAGENTS`) и специально деградирует без падения, если рядом недоступен `_usage.py` [cite:17]. В файле также присутствует version marker `SCHEMA = 2`, а сама логика подчёркивает, что внешняя схема транскрипта официально не зафиксирована и должна переживать аддитивные изменения [cite:17].

Функция `parse_events(...)` делает очень много за один проход: считает инструменты, связывает `tool_use` и `tool_result`, классифицирует bash-команды как test/lint, собирает tool failures, строит workflow summary, ищет workflow relaunch-группы, агрегирует maind memory/graph сигналы, считает rereads по `Read/Grep/Glob`, детектирует error loops, собирает retrieval activity и одновременно кормит usage-аккумулятор [cite:17]. Сам по себе такой one-pass подход эффективен, но именно он превращает hook parser в highly coupled aggregation engine [cite:17].

#### Сильные стороны текущего hook-подхода

##### 1. Defensive engineering

Для внешних event streams такая защита очень уместна: проект явно понимает, что транскрипты могут быть большими, частично битыми и эволюционировать без жёсткого контракта [cite:17]. Построчная обработка, best-effort extraction, fallback при отсутствии `_usage.py` и отказ от аварийного падения — это инженерно зрелый выбор для production-like hook среды [cite:17].

##### 2. Богатая телеметрия

Hook не ограничивается “логированием факта запуска”, а восстанавливает реальную картину сессии: tools, failures, workflows, reads, retrieval, memory/graph activity и protected writes [cite:17]. Это даёт сильную основу для диагностики качества агентных запусков и для дальнейшей продуктовой аналитики [cite:17].

##### 3. Runtime isolation awareness

В самом описании файла прямо отражено понимание ограничений среды хуков: невозможность опираться на PYTHONPATH монорепо, необходимость vendor-copy `_usage.py`, работа в автономном режиме внутри `~/.claude/hooks` и приоритет “никогда не бросать наружу” [cite:17]. Это важный архитектурный плюс, потому что интеграционные ограничения учтены явно, а не случайно [cite:17].

#### Ключевые риски

##### 1. Hook gravity

`run-report/_lib.py` уже аккумулирует parsing, schema adaptation, telemetry extraction, heuristic classification, partial domain semantics и reporting payload assembly [cite:17]. Это означает высокий риск того, что hook layer начнёт становиться скрытым центром архитектуры: не только наблюдать поведение системы, но и определять, что считать “правильным” поведением [cite:17].

##### 2. Silent degradation

Файл сознательно построен по fail-open стратегии: битые строки и отсутствующие поля пропускаются, `_usage.py` может отсутствовать, неизвестные типы событий не роняют отчёт [cite:17]. Для живучести это правильно, но без secondary alerting/quality flags такая стратегия очень легко приводит к тихой потере сигнала: отчёт формально есть, но часть данных отсутствует, и пользователь об этом может не узнать [cite:17].

##### 3. Heuristic creep

Классификация тестов и линтов в bash строится через regex-паттерны `TEST_PAT` и `LINT_PAT`, retrieval-инструменты определяются эвристикой `_retrieval_tool`, repeated queries — через `similar_ratio`, maind-вызовы — по суффиксам имени инструмента, devloop данные — через поиск JSON-фрагментов с ключами `tool_failures`, `workarounds`, `deferred`, `open_questions`, `results`, `verify` [cite:17]. Всё это полезно, но в сумме означает, что значительная часть поведения системы определяется эвристиками, а не жёсткими контрактами [cite:17].

##### 4. One-pass coupling

Однопроходный парсинг хорош по производительности, но он повышает сцепление разных задач внутри одной функции [cite:17]. Когда один и тот же проход одновременно обслуживает usage, workflow summary, failure tracking, retrieval metrics и protected writes, любое изменение схемы или нового сигнала становится более рискованным для всей функции [cite:17].

##### 5. Vendor drift

`_usage.py` в хук-каталоге описан как вендоренная копия `core/usage.py`, которую нужно синхронизировать отдельным скриптом `scripts/sync-usage.sh` [cite:17]. Это практически прямой сигнал architectural duplication: часть критичной логики сознательно копируется в интеграционную среду, а значит возникает отдельный риск drift между оригиналом и hook-runtime копией [cite:17].

#### Event schema strategy

С одной стороны, наличие `SCHEMA = 2` говорит о попытке формализовать выходной контракт хука [cite:17]. С другой стороны, внутри кода постоянно подчёркивается, что входная схема транскриптов нестабильна и парсер должен переживать аддитивные изменения [cite:17]. Это означает, что hook subsystem живёт между двумя разными мирами:

- **Входной мир** — слабоструктурированный, дрейфующий, partially trusted event stream.
- **Выходной мир** — собственный стабилизируемый telemetry/report contract [cite:17].

Это правильная общая стратегия, но ей не хватает ещё одного элемента: явной normalization boundary. Сейчас эта boundary, судя по файлу, встроена в сам парсер и не отделена в отдельный слой [cite:17].

#### Fail-open vs fail-closed

Текущий `run-report` очень явно ориентирован на fail-open: никогда не ронять хук, переживать битые строки, не зависеть жёстко от `_usage.py`, пропускать неизвестные события [cite:17]. Для post-run analytics это разумно. Но если похожая модель используется и в safety-критичных хуках, это уже может быть опасно [cite:17].

Для hook architecture такого проекта нужна классификация самих хуков по policy:

- **Observation hooks** — можно fail-open, но с quality flags.
- **Advisory hooks** — fail-open или soft-fail с предупреждением.
- **Enforcement hooks** — fail-closed или at least explicit-blocking при нарушении invariant [cite:17].

Без такой классификации одинаковая инженерная привычка “не падать” начинает распространяться и на сценарии, где нужно наоборот жёстко останавливать действие [cite:17].

#### Где hook-код уже стал центром логики

`run-report/_lib.py` показывает как минимум четыре зоны, где hook layer уже несёт substantial semantics [cite:17]:

- Определяет, какие tool patterns интерпретировать как test/lint активность.
- Определяет, какие последовательности ошибок считать error loop.
- Определяет, какие инструменты и запросы считать retrieval-сигналом.
- Определяет, какие пути считать protected writes через чтение `skills-lock.json` и `.claude/agent-pack.lock.json` [cite:17].

Последний пункт особенно важен: hook не просто наблюдает события, а интерпретирует project policy через managed/protected path semantics [cite:17]. Это уже прямая бизнес-логика второго уровня — operational policy logic [cite:17].

#### Целевая схема рефакторинга hooks

Чтобы hook layer не превратился в неконтролируемую смесь интеграции и аналитики, его стоит декомпозировать на четыре чётких слоя.

##### 1. Adapter layer

Только чтение внешнего input-а: stdin, transcript files, hook runtime env, sidecar directories, project cwd [cite:17]. Здесь не должно быть доменной аналитики — только извлечение сырого материала [cite:17].

##### 2. Parser / normalization layer

Перевод дрейфующего входного event stream в внутренние нормализованные события с минимальным, но стабильным набором полей: `ToolUse`, `ToolResult`, `WorkflowEvent`, `ReadEvent`, `RetrievalEvent`, `FileMutationEvent` и т.п. Сейчас большая часть этой логики смешана с агрегацией внутри `parse_events(...)` [cite:17].

##### 3. Domain metrics layer

Отдельные pure-ish агрегаторы для usage, rereads, error loops, retrieval, policy violations, workflow relaunch, memory/graph signals [cite:17]. Каждый агрегатор должен быть тестируем отдельно и не зависеть от деталей исходного JSONL формата [cite:17].

##### 4. Reporting layer

Сбор итогового schema-versioned output, выставление quality flags, заполнение `usage=None` и прочих degraded fields, явная маркировка partial completeness [cite:17]. Именно здесь должно быть принято решение, как отображать fail-open деградацию пользователю [cite:17].

#### Критические улучшения

##### P0

- Отделить normalization от aggregation внутри `run-report` [cite:17].
- Ввести `quality_flags`/`partial_data` indicators, чтобы fail-open не означал silent success [cite:17].
- Зафиксировать input-event contract assumptions и покрыть их golden fixtures [cite:17].
- Минимизировать vendor drift вокруг `_usage.py`, по возможности через общий генерационный pipeline или checksum validation [cite:17].

##### P1

- Разнести эвристики по именованным policy-модулям: test detection, lint detection, retrieval detection, protected path detection [cite:17].
- Ввести отдельные typed/normalized event objects вместо ad-hoc dict handling everywhere [cite:17].
- Добавить observability для самой деградации: сколько строк пропущено, сколько событий непонятно, какие блоки usage недоступны [cite:17].

##### P2

- Построить hook taxonomy: observation, advisory, enforcement [cite:17].
- Вынести reusable hook SDK/helper layer для повторного использования между разными hook entrypoints [cite:17].
- Подготовить replay harness для прогонки исторических транскриптов через новые версии парсеров [cite:17].

#### Список критичных рисков

| Риск | Почему критичен |
|---|---|
| Silent data loss in fail-open mode | Отчёты могут выглядеть валидными при частичной потере телеметрии [cite:17] |
| Heuristic drift | Regex и best-effort классификаторы со временем расходятся с реальностью инструментов [cite:17] |
| Hook gravity | Хук-слой начинает хранить operational policy и вторичную бизнес-логику [cite:17] |
| Vendor sync drift | Вендоренная `_usage.py` может расходиться с основным исходником [cite:17] |
| Parser coupling | Изменение одного сигнала повышает риск сломать весь one-pass aggregator [cite:17] |
| Missing policy taxonomy | Неясно, какие хуки могут fail-open, а какие обязаны блокировать действие [cite:17] |

#### Что нужно проверить следующими итерациями

- Полный список hook entrypoints в `packages/harness/configs/claude-code/hooks/` и рядом с ними [cite:18].
- Есть ли кроме `run-report` safety/enforcement hooks и как они себя ведут при ошибках.
- Насколько общий pattern `_lib.py + thin wrapper` повторяется в других hooks.
- Есть ли golden tests или replay fixtures для event parsing.
- Где ещё project policy интерпретируется внутри hook-кода.

### 6. Agents и orchestration

#### Итерация 6 — углублённая проработка

По корневой структуре уже видно, что `swissknifeman` живёт не в одной агентной экосистеме, а сразу в нескольких: `.agents`, `.claude`, `.claude-plugin`, `.codex`, а также `packages/` и `configs/` как потенциальные точки доставки и оркестрации агентных конфигураций [cite:18]. Архитектурно это означает, что проект, вероятно, строится не просто как “набор промптов”, а как multi-surface agent distribution system, где один и тот же intent может быть представлен в нескольких vendor- или harness-specific формах [cite:18].

Это стратегически сильный ход: проект не замыкается на одном runtime и может эволюционировать вместе с Claude Code, Codex и собственными механизмами поставки. Но именно здесь и возникает один из самых дорогих рисков — drift между представлениями одной и той же агентной модели в разных каталогах и форматах [cite:18].

#### Что можно утверждать уже сейчас

Наличие `.claude` и `.claude-plugin` одновременно говорит о сосуществовании по крайней мере двух слоёв: локальной Claude-oriented конфигурации и plugin/distribution surface для Claude-экосистемы [cite:18]. Наличие `.codex` показывает, что проект ориентирован не только на Claude runtime, а значит часть агентной логики, навыков или workflow descriptions, вероятно, переносится или адаптируется между экосистемами [cite:18]. `.agents` в такой картине выглядит либо как более абстрактный каталог определений агентов, либо как отдельный delivery format/registry layer [cite:18].

Добавим к этому уже подтверждённую роль hooks и agent-pack lock semantics: в `run-report/_lib.py` явно есть логика чтения `.claude/agent-pack.lock.json`, причём файлы из паков считаются protected, если они не помечены `user_owned` [cite:17]. Это важный признак того, что agent ecosystem здесь уже не просто набор markdown-инструкций, а управляемый distribution pipeline с notion of ownership, managed files и policy-aware delivery [cite:17].

#### Вероятная модель агентной системы

На текущем уровне видимости агентную подсистему стоит мыслить как многослойную модель [cite:17][cite:18]:

1. **Canonical intent layer** — абстрактное описание роли агента, его назначения, допустимых действий, предпочтительной среды, safety boundaries и expected outputs.
2. **Vendor adaptation layer** — адаптация этого intent под Claude, Codex и, возможно, другие runtimes через разные форматы каталогов и файлов [cite:18].
3. **Distribution layer** — plugin/pack/system, который доставляет эти определения в пользовательское окружение [cite:17][cite:18].
4. **Execution-adjacent layer** — hooks, lock-файлы, managed paths и runtime-специфичные механизмы сопровождения [cite:17].

Если эта схема близка к реальности, то главная архитектурная задача проекта — удерживать эти уровни согласованными. Как только canonical intent перестаёт быть единым, остальные слои начинают эволюционировать вразнобой [cite:18].

#### Основная проблема: дублирование intent

В multi-agent / multi-runtime системах intent drift почти всегда начинается с полезного компромисса: сначала делается “почти тот же агент” для другой платформы, потом ему чуть-чуть меняют формулировки, потом добавляют platform-specific условия, а затем обнаруживается, что Claude-версия, Codex-версия и plugin-версия одного и того же агента уже ведут себя как три разных сущности [cite:18]. По текущей структуре репозитория именно этот риск выглядит одним из самых вероятных [cite:18].

Типовые формы drift здесь могут быть такими:

- Разные системные инструкции у агента с одинаковым именем в `.claude` и `.codex` [cite:18].
- Отличающиеся tool boundaries и safety hints между plugin-delivered и repo-local definitions [cite:18].
- Один и тот же workflow описан одновременно как agent, command, config template и doc section [cite:18].
- Agent pack lock фиксирует одно представление, а пользователь редактирует другое [cite:17][cite:18].

#### Orchestration как отдельный домен

Судя по структуре репозитория, здесь важно различать “агентов” и “оркестрацию агентов”. Наличие `.agents`, `.claude`, `.codex`, hooks, пакетов и lock-семантики намекает, что проект работает не только с единичными агентами, но и с системой их установки, обновления, совмещения и, возможно, вызова в рамках workflow [cite:17][cite:18].

Это означает, что orchestration-domain здесь включает как минимум следующие вопросы:

- Где агент определяется.
- Как он доставляется в среду.
- Как его версия и владелец фиксируются.
- Какие файлы считаются managed.
- Как отличить user-owned от system-owned assets.
- Что происходит при обновлении, конфликте, ручной правке или удалении.

Эти вопросы нельзя оставлять только на уровне “как получилось в файловой структуре”; они требуют явного контракта системы [cite:17][cite:18].

#### Ownership model

Самая интересная архитектурная находка, уже подтверждённая кодом, — различение managed и user-owned файлов через `.claude/agent-pack.lock.json` [cite:17]. Это хороший знак: проект понимает, что агентные артефакты не все одинаковы и что политика владения должна влиять на поведение системы [cite:17].

Но отсюда вытекает и большая ответственность: ownership model должна быть единообразной во всех agent-related слоях. Если `user_owned`, `managed`, `protected`, `installed_path`, `target` и аналогичные атрибуты трактуются по-разному в разных частях репозитория, пользователь будет регулярно сталкиваться с неожиданным поведением при синхронизации и обновлении [cite:17].

#### Где оркестрация может быть хрупкой

##### 1. Vendor-specific branching

Чем больше различий между `.claude`, `.codex`, `.claude-plugin` и `.agents`, тем выше риск, что любая новая фича потребует многократного ручного обновления нескольких представлений [cite:18]. Это прямой путь к version drift и operational inconsistency [cite:18].

##### 2. Pack/install/update lifecycle

Если agent packs имеют собственные lock-файлы и managed targets, то lifecycle их установки и обновления уже сложнее, чем просто “скопировать файл” [cite:17]. В такой системе нужны ясные правила: что считается upgrade, что считается локальной модификацией, когда возникает конфликт, и кто выигрывает — пользователь или поставка [cite:17].

##### 3. Prompt/skill/workflow overlap

В agent-oriented репозиториях одна и та же мысль часто живёт сразу в нескольких формах: агент, команда, skill, doc, workflow script, hook-assumption [cite:18]. Без canonical contract это приводит к semantic duplication: формально сущности разные, но intent у них один и тот же [cite:18].

##### 4. Hidden orchestration logic

Часть оркестрации может быть зашита не в явные “agent managers”, а в provider subsystem, hooks, scripts или install/update flows [cite:17][cite:18]. Это опасно тем, что общую модель нельзя увидеть в одном месте; она распределена между несколькими слоями [cite:17][cite:18].

#### Unified contract для agent definitions

Для такого проекта нужен единый канонический контракт описания агента — не обязательно один физический формат для всех рантаймов, но один смысловой schema-core [cite:18]. Минимальный набор полей такого контракта должен включать:

- `id` — глобально устойчивый идентификатор агента.
- `name` — человекочитаемое имя.
- `purpose` — назначение.
- `capabilities` — что агент умеет.
- `constraints` — что ему запрещено или ограничено.
- `inputs` / `outputs` — ожидаемые формы взаимодействия.
- `runtime_targets` — для каких экосистем есть адаптации.
- `dependencies` — какие skills, tools, hooks, configs, packs нужны.
- `ownership` / `delivery_mode` — managed, user-owned, generated, local-only.
- `version` / `compatibility` — семантика изменений и совместимости.

Важен не сам список полей, а принцип: vendor-specific файлы должны быть производными от этого semantic core, а не параллельными источниками истины [cite:18].

#### Roadmap унификации

##### Этап A — сделать карту экосистем видимой

- Составить таблицу всех agent-related директорий: `.agents`, `.claude`, `.claude-plugin`, `.codex`, package/config зоны [cite:18].
- Для каждой директории описать: audience, runtime, owner, mutation model, source-of-truth status [cite:18].
- Явно отметить, что является canonical, а что — generated/delivered/adapted [cite:18].

##### Этап B — выделить semantic core

- Описать unified agent definition schema на уровне документации, а затем в коде/конфиге [cite:18].
- Проверить, какие атрибуты уже присутствуют имплицитно в существующих каталогах и lock-файлах [cite:17][cite:18].
- Отделить agent identity от platform-specific packaging [cite:18].

##### Этап C — снизить drift

- Ввести проверку согласованности между Claude- и Codex-представлениями одного агента [cite:18].
- Добавить tooling, которое показывает, какие agent definitions разошлись между runtime-targets [cite:18].
- По возможности генерировать vendor-specific variants из единого источника, а не поддерживать вручную [cite:18].

##### Этап D — формализовать lifecycle

- Описать install/update/remove/reconcile поведение для agent packs [cite:17].
- Зафиксировать правила конфликта между managed и user-owned файлами [cite:17].
- Сделать explain-команду или отчёт по ownership/delivery state, чтобы пользователь понимал, почему конкретный файл защищён или обновлён [cite:17].

#### Основные риски

| Риск | Вероятность | Влияние | Почему |
|---|---|---|---|
| Intent drift между `.claude`, `.codex`, `.agents`, `.claude-plugin` | Высокая [cite:18] | Высокое [cite:18] | Несколько агентных поверхностей почти всегда ведут к расхождению поведения [cite:18] |
| Неясный source of truth для agent definitions | Высокая [cite:18] | Высокое [cite:18] | Структура намекает на несколько возможных канонических слоёв [cite:18] |
| Ownership ambiguity при pack/update flows | Средняя [cite:17][cite:18] | Высокое [cite:17][cite:18] | Уже есть protected/user-owned semantics, но не видно единой модели на уровне всей системы [cite:17] |
| Semantic duplication между agents/skills/docs/workflows | Высокая [cite:18] | Среднее [cite:18] | Один intent может жить в нескольких артефактах сразу [cite:18] |
| Hidden orchestration logic spread across repo | Средняя [cite:17][cite:18] | Высокое [cite:17][cite:18] | Оркестрация может быть размазана между hooks, providers, configs и scripts [cite:17][cite:18] |

#### Рекомендации

| Область | Рекомендация | Эффект |
|---|---|---|
| Agent schema | Ввести единый semantic core для agent definitions | Снижает intent drift [cite:18] |
| Runtime targets | Формализовать, какие каталоги являются canonical, а какие adapter layers | Делает архитектуру самообъяснимой [cite:18] |
| Ownership | Единообразно описать managed/user-owned/generated semantics | Уменьшает неожиданные обновления и конфликты [cite:17] |
| Drift detection | Добавить tooling для проверки расхождений между runtime-представлениями | Снижает ручной операционный долг [cite:18] |
| Lifecycle | Описать install/update/remove/reconcile model для agent packs | Повышает predictability системы [cite:17] |

#### Что нужно проверить следующими итерациями

- Реальный состав файлов внутри `.agents`, `.claude`, `.claude-plugin`, `.codex` [cite:18].
- Как именно agent packs описываются и обновляются.
- Где в коде определяется lifecycle managed vs user-owned agent files [cite:17].
- Существуют ли генераторы/синхронизаторы между экосистемами или всё поддерживается вручную [cite:18].
- Есть ли уже формальный schema-core для agents, но просто плохо видимый извне [cite:18].

### 7. Конфиги и безопасность

#### Итерация 7 — углублённая проработка

По структуре репозитория и уже подтверждённым кодовым фрагментам безопасность в `swissknifeman` нельзя рассматривать как отдельный внешний concern. Она встроена в саму модель проекта: есть `config.example.json`, `.mcp.json.example`, `safe-dirs.example.json`, lock-файлы, managed/protected semantics, агентные пакеты и hooks, которые анализируют пересечение изменений с защищёнными путями [cite:17][cite:18]. Это означает, что security posture здесь складывается не из одной-двух проверок, а из целого набора policy decisions, распределённых между конфигами, delivery-пайплайнами и runtime-поведением [cite:17][cite:18].

Уже в `run-report/_lib.py` подтверждено, что проект различает protected writes и вычисляет их через чтение `skills-lock.json` и `.claude/agent-pack.lock.json`: managed skill directories и non-user-owned pack targets трактуются как защищённые пути [cite:17]. Это сильный архитектурный сигнал: система пытается защитить части собственного доставленного/управляемого слоя от несанкционированных изменений, а значит у неё уже есть зачатки policy-aware filesystem security model [cite:17].

#### Какие security semantics уже видны

На текущем уровне можно уверенно говорить как минимум о следующих семантиках [cite:17][cite:18]:

- **Managed** — файлы или директории поставляются и сопровождаются системой, а не пользователем [cite:17].
- **User-owned** — файлы допускают пользовательский контроль и не должны считаться защищёнными наравне с managed assets [cite:17].
- **Protected writes** — запись в определённые пути является событием, которое должно быть видно в аналитике и, вероятно, в отдельных политиках [cite:17].
- **Safe dirs / trusted dirs** — проект явно думает о границах допустимых рабочих директорий через `safe-dirs.example.json` [cite:18].
- **Config surface** — часть поведения задаётся через JSON-конфиги и therefore относится к attack surface, а не только к настройкам удобства [cite:18].

Это уже больше, чем обычно есть у локального AI-agent tool. Но одновременно это значит, что безопасность системы может быть такой же сложной, как и её архитектура: неявные исключения, исторические компромиссы и распределённые договорённости здесь особенно опасны [cite:17][cite:18].

#### Threat model для локального AI-agent harness

Для такого проекта базовая модель угроз должна строиться не вокруг “внешнего хакера”, а вокруг следующих осей [cite:17][cite:18]:

##### 1. Prompt-to-file escalation

Агент получает инструкции из промптов, документов, hook-контекста и конфигов, после чего способен инициировать операции над файлами. Главный риск — незаметный переход от текстового воздействия к файловой мутации в чувствительных путях [cite:17][cite:18]. Если система не различает clearly user-editable, generated, managed и protected области, атака или ошибка быстро превращается в persistence-layer проблему [cite:17].

##### 2. Config poisoning

Так как в проекте много конфигурационных поверхностей, вредоносное или просто ошибочное изменение конфига может поменять не только поведение одной команды, но и модель доверия всей системы [cite:18]. Это особенно опасно для safe dirs, runtime targets, agent packs, provider sources и policy flags [cite:18].

##### 3. Pack / plugin supply drift

Наличие `.claude-plugin`, agent packs и managed delivery semantics означает риск поставки нежелательных изменений через seemingly legitimate update path [cite:17][cite:18]. Даже если это не внешний supply-chain attack, это может быть internal drift: обновление доставило более широкие права, чем ожидалось, или перезаписало локальные соглашения [cite:17][cite:18].

##### 4. Privilege drift

Если разные слои системы по-разному трактуют, что разрешено user-owned, что managed, а что protected, возникает privilege drift: операция, заблокированная в одном месте, оказывается допустимой в другом [cite:17]. Для локального harness-а это особенно коварно, потому что пользователь доверяет инструменту и не всегда видит, какие policy assumptions реально сработали [cite:17].

##### 5. Telemetry-assisted blind spots

Fail-open дизайн hooks полезен для живучести, но с точки зрения безопасности опасен тем, что policy-signals могут быть потеряны молча [cite:17]. Например, protected write может быть задетектирован не всегда, degraded telemetry может не донести часть контекста, а пользователь получит “успешный” отчёт без полного сигнала [cite:17].

#### Основные security surfaces

##### Config files

`config.example.json`, `.mcp.json.example`, `safe-dirs.example.json` и, вероятно, другие JSON-конфиги определяют, какие рантаймы, директории, источники и режимы поведения допустимы [cite:18]. Это делает их policy-bearing assets: любой серьёзный конфиг-файл в таком проекте должен считаться security-relevant [cite:18].

##### Lock files

`skills-lock.json` и `.claude/agent-pack.lock.json` уже влияют на интерпретацию защищённых путей [cite:17]. Значит, lock-файлы здесь выполняют не только функцию воспроизводимости, но и частично функцию authorization metadata — по крайней мере для managed assets [cite:17].

##### Agent definitions and packs

Поскольку агентные файлы описывают поведение, доступные действия и окружение, они сами по себе являются частью security boundary [cite:17][cite:18]. Компрометация или несанкционированное изменение agent definitions может иметь тот же эффект, что и изменение кода политики [cite:18].

##### Hook layer

Hook-код уже интерпретирует protected paths и собирает диагностические сигналы [cite:17]. Если в проекте есть и enforcement hooks, то hook subsystem становится полноценной policy enforcement surface [cite:17]. Даже если enforcement пока не обнаружен, observation hooks уже формируют security visibility [cite:17].

#### Главные риски

##### 1. Unsafe writes

Самый прямой риск — возможность записи в чувствительные пути без достаточно жёсткого preflight-контроля [cite:17]. Если проект умеет лишь постфактум замечать protected writes в аналитике, но не всегда умеет предотвращать их на уровне операций, защита остаётся диагностической, а не превентивной [cite:17].

##### 2. Policy split-brain

Если semantics `managed`, `user_owned`, `protected`, `safe`, `trusted` определяются в нескольких местах, система неизбежно рискует получить split-brain политику [cite:17][cite:18]. Тогда один слой считает файл защищённым, другой — обычным, третий — user-editable [cite:17]. Это хуже, чем отсутствие политики, потому что создаёт ложное чувство безопасности [cite:17].

##### 3. Config drift as security drift

В проектах такого класса конфиг-дрейф почти всегда превращается в security drift: меняются не только параметры, но и trust boundaries [cite:18]. Если нет validate/doctor-проверок специально для security-sensitive config, пользователь может незаметно жить в деградировавшем или более опасном режиме [cite:18].

##### 4. Ownership ambiguity

Уже подтверждённая семантика `user_owned` хороша, но если пользователь не видит ясно, какой файл сейчас считается managed, а какой пользовательским, любое обновление или reconcile воспринимается как потенциально опасное [cite:17]. Непрозрачный ownership — это и UX-проблема, и security-проблема одновременно [cite:17].

##### 5. Prompt injection through trusted context

Для AI-agent harness особенно важна угроза, когда вредоносный или просто нерелевантный текст попадает в trusted context: docs, generated files, config comments, agent definitions, sidecar artifacts [cite:17][cite:18]. Если downstream agent or hook treats this context as trustworthy guidance, появляется путь к нежелательным действиям с файлами и окружением [cite:17][cite:18].

#### Hardening plan

##### P0 — обязательно

- Сделать единую glossary/model для `managed`, `user_owned`, `protected`, `safe`, `trusted` и использовать её во всех слоях [cite:17][cite:18].
- Ввести preflight policy check для mutating операций по чувствительным путям, а не полагаться только на post-run detection [cite:17].
- Добавить явный security-oriented `validate`/`doctor`, который проверяет safe dirs, lock metadata, ownership conflicts, managed path integrity [cite:17][cite:18].
- Сделать security-relevant config changes видимыми через diff/explain output [cite:18].
- Для degraded hook telemetry добавлять quality/security flags, чтобы потеря сигнала не выглядела как нормальный успех [cite:17].

##### P1 — сильное усиление

- Формализовать threat model в `docs/security/` или `docs/architecture/security.md` [cite:18].
- Ввести policy tests на protected writes и ownership resolution [cite:17].
- Вынести чувствительные policy checks из scattered helpers в единый policy engine/module [cite:17][cite:18].
- Добавить explain-команду, показывающую почему путь считается safe/protected/user-owned [cite:17][cite:18].
- Проверять целостность lock-файлов и согласованность installed paths/targets перед reconcile/update [cite:17].

##### P2 — долгосрочно

- Добавить tamper-evident markers или integrity metadata для критичных managed assets.
- Ввести replayable audit trail для security-sensitive mutations.
- Рассмотреть policy-as-code слой для filesystem and pack ownership rules.

#### P0/P1 security actions

| Приоритет | Действие | Зачем |
|---|---|---|
| P0 | Централизовать semantics managed/user_owned/protected/safe/trusted | Убирает policy split-brain [cite:17][cite:18] |
| P0 | Блокировать опасные writes preflight-проверкой | Переводит защиту из диагностической в превентивную [cite:17] |
| P0 | Добавить security validate/doctor | Делает trust drift обнаруживаемым [cite:18] |
| P0 | Показывать explain/diff для security-sensitive config changes | Повышает прозрачность изменений [cite:18] |
| P0 | Маркировать degraded telemetry security-флагами | Убирает ложное чувство защищённости [cite:17] |
| P1 | Задокументировать threat model | Делает security assumptions явными [cite:18] |
| P1 | Вынести policy checks в единый модуль | Снижает риск рассинхронизации правил [cite:17][cite:18] |
| P1 | Добавить policy tests и integrity checks | Делает регрессии видимыми [cite:17] |
| P1 | Добавить explain для ownership/path policy | Уменьшает operational confusion [cite:17] |

#### Целевое состояние

Зрелая версия security model для `swissknifeman` должна выглядеть так: policy vocabulary едина; config/lock/agent-pack semantics непротиворечивы; mutating operations проходят preflight authorization checks; observability показывает не только события, но и качество самого security-сигнала; пользователь всегда может понять, почему конкретный файл считается безопасным, защищённым или управляемым [cite:17][cite:18].

Главная идея здесь простая: для локального AI-agent harness безопасность — это не отдельный модуль, а свойство согласованности между конфигами, ownership model, mutation policy, hooks и explainability. Если хотя бы один из этих слоёв слаб, вся система защищена хуже, чем кажется [cite:17][cite:18].

#### Что проверить следующими итерациями

- Точные поля и семантику `safe-dirs.example.json`, `config.example.json`, `.mcp.json.example` [cite:18].
- Где ещё кроме `run-report` реализуются policy checks по protected/managed assets [cite:17].
- Есть ли real enforcement hooks, а не только observation hooks [cite:17].
- Как update/reconcile/install flows принимают решения о перезаписи файлов.
- Есть ли уже security docs или policy tests, просто неочевидно расположенные [cite:18].

### 8. Наблюдаемость и telemetry

#### Итерация 8 — углублённая проработка

По уже подтверждённым фрагментам кода видно, что `swissknifeman` относится к редкому классу agent tooling, где observability не ограничивается логами “запустилось/не запустилось”. В `packages/harness/configs/claude-code/hooks/run-report/_lib.py` реализован насыщенный telemetry extraction pipeline: usage агрегируется через отдельный модуль `_usage.py`, события транскрипта нормализуются best-effort образом, считаются tool invocations, failures, rereads, retrieval signals, protected writes, workflow relaunch patterns, memory/graph activity и dev-loop summary [cite:17]. Это уже не просто техлогирование, а попытка построить operational model поведения агента и среды [cite:17].

Такой уровень наблюдаемости — очень сильная сторона репозитория. Но одновременно он создаёт новый класс обязательств: как только telemetry используется для понимания качества, безопасности и эффективности работы системы, ей уже нельзя быть “примерно полезной”. Она должна иметь качество, версионирование, объяснимость деградации и ясные границы достоверности [cite:17].

#### Что уже видно по текущей telemetry-модели

Из подтверждённого hook-кода можно уверенно выделить несколько уровней сигналов [cite:17]:

- **Resource / usage layer** — токены, usage-агрегация, fallback при отсутствии `_usage.py` [cite:17].
- **Tool activity layer** — tool uses, tool results, bash-классификация, test/lint сигналы [cite:17].
- **Failure layer** — tool failures, error loops, limited failure collections [cite:17].
- **Retrieval / memory layer** — retrieval queries, repeated query heuristics, maind memory/graph indicators [cite:17].
- **Mutation / policy layer** — protected writes и работа с managed paths [cite:17].
- **Workflow layer** — workflow summary, relaunch grouping, попытки извлечь dev-loop структуру [cite:17].

Это зрелая многослойная модель сигналов. Проблема не в том, что сигналов мало, а в том, что чем их больше, тем выше требования к semantic clarity и data quality [cite:17].

#### Сильные стороны текущей observability

##### 1. Попытка измерять не только usage, но и поведение

Большинство agent инструментов останавливаются на подсчёте токенов и стоимости. Здесь же telemetry пытается увидеть паттерны: rereads, retrieval loops, failure clustering, workflow relaunch, protected writes [cite:17]. Это намного ценнее для эксплуатации, потому что позволяет отвечать не только на вопрос “сколько система потребила”, но и на вопрос “как она работала” [cite:17].

##### 2. Resilience-first сбор сигналов

Построчный JSONL parsing, лимиты на размеры аккумуляторов, пропуск битых строк и устойчивость к отсутствию `_usage.py` делают систему живучей в реальном мире [cite:17]. Для telemetry, работающей рядом с агентным рантаймом, это разумный выбор, потому что сама система наблюдаемости не должна становиться причиной падения основного workflow [cite:17].

##### 3. Начатое версионирование output schema

Наличие `SCHEMA = 2` в hook library — хороший признак того, что автор уже мыслит telemetry-output как контракт, а не как случайный dict [cite:17]. Это важная основа для будущей эволюции format compatibility, diffing и downstream consumers [cite:17].

#### Главные blind spots

##### 1. Нет явной confidence model

Сейчас best-effort philosophy очень сильна: часть строк может быть пропущена, `_usage.py` может отсутствовать, неизвестные события не мешают работе, некоторые dev-loop сигналы извлекаются эвристически [cite:17]. Но при этом не видно формальной confidence model: насколько полон отчёт, какие подсистемы надёжны, какие поля частично вычислены, какие сигналы деградировали [cite:17]. Без этого telemetry рискует выглядеть более точной, чем она есть на самом деле [cite:17].

##### 2. Silent partial failure

Система явно предпочитает не падать, и это правильно для эксплуатации. Но без quality indicators fail-open превращается в silent partial failure: часть сигналов теряется, а downstream или пользователь может продолжать считать отчёт полноценным [cite:17]. Это особенно опасно, когда telemetry используется для security, quality analysis или decision support [cite:17].

##### 3. Heuristic observability

Многие полезные метрики зависят от эвристик: regex для test/lint, similarity для repeated queries, name-based recognition retrieval tools, JSON-fragment hunting для dev-loop summary [cite:17]. Эвристическая наблюдаемость лучше нуля, но без маркировки heuristic-derived fields и без regression fixtures она со временем дрейфует [cite:17].

##### 4. Входной schema drift

Сам код прямо исходит из того, что входная transcript schema не зафиксирована и должна переживать аддитивные изменения [cite:17]. Это реалистично, но значит, что telemetry core постоянно балансирует на границе schema drift. Если drift не отслеживается отдельно, система будет адаптироваться молча, иногда ценой потери точности [cite:17].

##### 5. Вендорный разрыв вокруг usage

Vendor-copy `_usage.py` — это не только проблема hook architecture, но и проблема observability integrity [cite:17]. Если usage logic начинает расходиться между основным модулем и hook-runtime копией, числа usage/стоимости/агрегации могут стать inconsistent между разными контекстами системы [cite:17].

#### Observability должна отвечать на пять вопросов

Для такого репозитория качественная наблюдаемость должна уметь объяснять пять вещей [cite:17][cite:18]:

1. Что произошло в сессии.
2. Насколько этому описанию можно доверять.
3. Что пошло не так и где именно.
4. Какие паттерны поведения агента были неэффективны или опасны.
5. Что оператору делать дальше.

Сейчас первая часть уже выглядит сильно развитой: проект умеет реконструировать насыщенную картину сессии [cite:17]. Самые слабые, по архитектурным признакам, части — доверие к полноте сигнала и операционное объяснение деградации [cite:17].

#### Target observability model

Целевая модель наблюдаемости для `swissknifeman` должна быть четырёхслойной.

##### 1. Raw event layer

Сырой transcript / hook input / runtime context с минимальной потерей и с понятной provenance-моделью [cite:17]. На этом уровне нужно уметь сказать, что реально пришло из внешней системы, а не только что удалось понять [cite:17].

##### 2. Normalized event layer

Стабильные внутренние типы событий с versioned schema и explicit fallbacks [cite:17]. Именно сюда надо вынести boundary между внешним дрейфующим миром и внутренним контрактом анализа [cite:17].

##### 3. Derived metrics / signals layer

Отдельно вычисляемые usage, rereads, retrieval, failures, loops, protected writes, workflow quality indicators [cite:17]. Каждый derived signal должен иметь metadata: source, confidence, heuristic/non-heuristic flag, completeness [cite:17].

##### 4. Reporting / operator layer

Человекочитаемый и machine-readable output, который не только показывает сигнал, но и маркирует его качество: `complete`, `partial`, `degraded`, `heuristic`, `unavailable` [cite:17]. Без этого telemetry не помогает оператору принимать решения responsibly [cite:17].

#### Что нужно добавить в quality model telemetry

Наблюдаемость в этом проекте должна измерять не только поведение агента, но и собственное качество [cite:17]. Минимальный набор meta-signal полей:

- `data_completeness` — полон ли отчёт.
- `skipped_lines` / `invalid_events_count` — сколько входа не удалось разобрать.
- `missing_usage_backend` — доступен ли usage parser [cite:17].
- `heuristic_fields` — какие поля получены эвристически.
- `schema_assumptions_version` — на какой входной предпосылке основан разбор.
- `confidence_by_section` — степень доверия по usage / workflow / retrieval / mutation / failures.

Это особенно важно потому, что сейчас система явно богата сигналами, но бедна сигналами о качестве самих сигналов [cite:17].

#### Explainability telemetry

Telemetry должна быть explainable не меньше, чем CLI или provider resolution [cite:17][cite:18]. Для оператора полезно не только видеть факт “retrieval query повторилась”, но и понимать, по какому правилу система посчитала её повторной; не только видеть “protected write”, но и понимать, какой lock/source path сделал путь защищённым [cite:17]. Если explainability отсутствует, богатая телеметрия превращается в semi-magical diagnostics [cite:17].

#### Observability priorities

##### P0

- Добавить quality flags и completeness indicators ко всем крупным разделам отчёта [cite:17].
- Явно маркировать heuristic-derived signals [cite:17].
- Зафиксировать versioned normalized event contract, а не только финальную schema-версию отчёта [cite:17].
- Минимизировать drift между `_usage.py` copy и основным usage-кодом [cite:17].

##### P1

- Ввести replay fixtures и regression tests для исторических transcript samples [cite:17].
- Показывать operator-facing explain snippets: почему сигнал классифицирован именно так [cite:17].
- Добавить telemetry about telemetry: skipped lines, unknown event types, degraded parsers [cite:17].
- Разделить “жёсткие” сигналы и “эвристические” сигналы в output schema [cite:17].

##### P2

- Подготовить machine-readable downstream contract для аналитики/дашбордов.
- Ввести более формальную trace/session model поверх raw transcripts.
- Рассмотреть интеграцию с OpenTelemetry-подобной терминологией, если система будет расти дальше [cite:17].

#### Риски

| Риск | Почему это важно |
|---|---|
| Telemetry looks more complete than it is | Пользователь может принимать решения на основе частично утраченного сигнала [cite:17] |
| Heuristic drift | Полезные метрики незаметно теряют точность со сменой паттернов инструментов [cite:17] |
| Schema drift on input | Внешние изменения транскриптов могут ломать точность без явного падения [cite:17] |
| Usage inconsistency | Вендорный `_usage.py` может давать расходящиеся цифры относительно основного кода [cite:17] |
| Weak operator explainability | Богатый отчёт труднее интерпретировать и проверять [cite:17] |

#### Что проверить следующими итерациями

- Где в репозитории живёт основной `usage.py` и как именно он синхронизируется с hook-копией [cite:17].
- Есть ли ещё reporting/telemetry модули кроме `run-report` [cite:18].
- Какие поля включает финальный output schema и кто его потребляет дальше.
- Есть ли golden tests, fixtures или snapshot comparisons для отчётов.
- Есть ли operator-facing документы, объясняющие смысл telemetry-полей.

### 9. Документация и knowledge architecture

#### Итерация 9 — углублённая проработка

По уже восстановленной архитектурной картине видно, что `swissknifeman` — это не маленький utility repo, а сложная система с несколькими поддоменами: provider model, hooks, telemetry, agent orchestration, ownership semantics, CLI workflows и security policy [cite:17][cite:18]. Для репозиториев такого класса документация перестаёт быть вспомогательным слоем и становится частью инженерной архитектуры: именно она удерживает модель системы в человеческом масштабе [cite:18].

Если knowledge architecture слабая, то фактический source of truth смещается в код, lock-файлы, названия каталогов и исторические соглашения. По текущему состоянию аудита именно это и выглядит главным риском для `swissknifeman`: проект, похоже, уже богаче своей явной документации, а значит значительная часть знаний живёт имплицитно [cite:17][cite:18].

#### Почему здесь документация критична

У проекта уже есть признаки высокой когнитивной нагрузки:

- несколько agent ecosystems (`.agents`, `.claude`, `.claude-plugin`, `.codex`) [cite:18];
- policy-bearing lock/config files и ownership semantics [cite:17][cite:18];
- hook-layer с существенной аналитической и частично policy-семантикой [cite:17];
- CLI, который потенциально должен объяснять сложную внутреннюю модель [cite:18];
- provider subsystem с несколькими близкими по смыслу представлениями состояния [cite:18].

Для такой системы документация нужна не “чтобы было удобно начать”, а чтобы вообще можно было понять, где заканчивается один домен и начинается другой [cite:18]. Без этого новые участники и даже сам автор спустя время будут принимать решения на основе неполной ментальной модели [cite:18].

#### Какие knowledge surfaces уже просматриваются

По структуре репозитория знания, вероятно, распределены между несколькими поверхностями [cite:17][cite:18]:

- `README` как входная точка [cite:18];
- `docs/` как место более длинных объяснений [cite:18];
- example-конфиги (`config.example.json`, `.mcp.json.example`, `safe-dirs.example.json`) как полу-документация поведения [cite:18];
- lock-файлы как неочевидные носители policy и ownership knowledge [cite:17];
- hook-код, где фактически зашиты определения protected writes, telemetry heuristics и runtime assumptions [cite:17];
- naming and folder structure, которые сами по себе служат “документацией по умолчанию”, если явных текстов не хватает [cite:18].

Это типичная ситуация для быстро растущих инструментальных репозиториев: knowledge architecture существует, но она распределённая и неформальная [cite:18].

#### Главная проблема: knowledge locked in implementation

Наиболее серьёзный риск не в том, что “мало markdown-файлов”, а в том, что знания зашиты в implementation details [cite:17][cite:18]. Уже по проведённым итерациям видно несколько конкретных примеров:

- Семантика `managed`, `user_owned`, `protected` в явном виде проявляется через hook-код и lock-файлы, а не через центральный policy document [cite:17].
- Различие между agent-related каталогами пока легче вывести из структуры, чем прочитать как формальную модель [cite:18].
- Наблюдаемость и качество telemetry currently лучше понимаются через `run-report/_lib.py`, чем через operator-facing docs [cite:17].
- Provider lifecycle и truth model приходится реконструировать архитектурно, а не читать из одного canonical description [cite:18].

Когда знание спрятано таким образом, документация начинает неизбежно отставать, потому что она не является owner-слоем модели [cite:18].

#### Что должна делать хорошая knowledge architecture здесь

Для `swissknifeman` documentation system должна решать минимум пять задач [cite:18]:

1. **Orientation** — быстро объяснять, что это за система и из каких доменов она состоит.
2. **Operation** — помогать запускать, диагностировать и безопасно сопровождать систему.
3. **Architecture** — описывать внутренние модели: providers, hooks, agents, ownership, telemetry, security.
4. **Policy** — делать явными правила, которые сейчас размазаны по коду и lock/config artifacts [cite:17][cite:18].
5. **Change resilience** — снижать drift между evolving codebase и ментальной моделью команды [cite:18].

Если хотя бы одна из этих задач не закрыта, документация начинает работать только как onboarding-слой, но не как архитектурная память проекта [cite:18].

#### Discoverability

Для крупного tool-repo discoverability важнее количества документов [cite:18]. Даже хорошая документация бесполезна, если непонятно:

- с какого файла начинать;
- где high-level overview, а где deep technical reference;
- какой документ актуален, а какой исторический;
- где canonical source of truth, а где derived notes;
- какие docs адресованы пользователю, а какие мейнтейнеру.

Судя по структуре и по количеству смысловых слоёв, `swissknifeman` особенно уязвим к проблеме “всё документировано понемногу, но ничего нельзя быстро найти” [cite:18].

#### Explainability gap

По уже проведённому аудиту видно, что проект довольно богат сложными внутренними семантиками: truth models, ownership, protected writes, telemetry confidence, agent delivery layers [cite:17][cite:18]. Если эти модели не вынесены в отдельные explanatory documents, README и examples неизбежно начинают перегружаться деталями или, наоборот, слишком сглаживают картину [cite:18].

Это создаёт explainability gap: пользователь видит интерфейсы и файлы, но не видит системную логику, которая за ними стоит [cite:18]. А именно в таких проектах explainability документации должна быть почти такой же важной, как explainability CLI [cite:18].

#### Anti-drift пригодность

Хорошая documentation architecture должна быть устойчива к drift. Для этого важно различать как минимум три типа документов [cite:18]:

- **Stable conceptual docs** — доменные модели и архитектурные принципы; они меняются редко.
- **Operational docs** — install/update/troubleshooting/runbooks; они меняются чаще.
- **Generated or validated reference docs** — схемы, команды, каталоги, matrix-представления; их лучше частично генерировать или хотя бы проверять [cite:18].

Если всё это смешано в README или в нескольких длинных guide-файлах, обновлять знания становится слишком дорого. В итоге код меняется быстрее, чем docs, и знание снова утекает в implementation [cite:18].

#### Target knowledge architecture

Для `swissknifeman` логично строить документацию как многоуровневую систему.

##### 1. Entry layer

- `README.md` — только смысл проекта, 3–5 главных сценариев, как начать, куда идти дальше [cite:164][cite:166].
- Короткая карта репозитория и ссылка на архитектурные документы [cite:164].

README не должен быть местом, где хранится вся внутренняя модель проекта; GitHub сам рекомендует использовать README прежде всего для быстрого понимания полезности проекта и старта, а не как единственный контейнер длинной документации [cite:164][cite:166].

##### 2. Architecture layer

Отдельные canonical docs, минимум:

- `docs/architecture/overview.md`
- `docs/architecture/providers.md`
- `docs/architecture/hooks.md`
- `docs/architecture/agents.md`
- `docs/architecture/security.md`
- `docs/architecture/telemetry.md`

Это как раз те домены, которые уже пришлось восстанавливать через аудит, а значит они достаточно важны, чтобы иметь собственные документы [cite:17][cite:18].

##### 3. Operations layer

- install / bootstrap / update / repair
- troubleshooting / doctor / validate
- safe mutation rules
- managed vs user-owned behavior

Этот слой нужен не для красоты, а чтобы эксплуатационные знания не были зашиты только в CLI help и исходниках [cite:18].

##### 4. Reference layer

- config reference
- lock/reference semantics
- directory map
- command map
- hook/event schema reference

Этот слой особенно важен, потому что проект содержит много policy-bearing artifacts. Их лучше описывать как справочники, а не размазывать по narrative-guides [cite:17][cite:18].

#### Top documentation priorities

##### P0

- Зафиксировать один **Architecture Overview** документ, который объясняет все основные подсистемы и их связи [cite:18].
- Отдельно задокументировать ownership/security semantics: `managed`, `user_owned`, `protected`, `safe`, `trusted` [cite:17][cite:18].
- Вынести provider lifecycle и truth model в canonical architecture doc [cite:18].
- Создать operator-facing doc по telemetry/report fields, quality flags и degraded modes [cite:17].
- Сделать карту agent ecosystems и объяснить различия `.agents`, `.claude`, `.claude-plugin`, `.codex` [cite:18].

##### P1

- Разделить onboarding docs и maintainer docs [cite:18].
- Добавить runbooks для `validate`, `doctor`, `repair`, reconcile/update scenarios [cite:18].
- Сделать config/lock reference с указанием, какие поля security-sensitive [cite:17][cite:18].
- Явно отметить source-of-truth статус для major docs и generated references [cite:18].

##### P2

- Проверять консистентность docs against codebase хотя бы простыми CI-правилами.
- Частично генерировать directory maps / command maps / schema references.
- Ввести ADR-подобный слой для фиксации архитектурных решений, если проект продолжит расти [cite:168][cite:172].

#### Риски слабой документации

| Риск | Почему это опасно |
|---|---|
| Knowledge trapped in code | Новые участники и future-self автора понимают систему только через чтение исходников [cite:17][cite:18] |
| Policy ambiguity | Ownership/security semantics трактуются по-разному в разных местах [cite:17][cite:18] |
| Onboarding drag | Даже сильный инженер слишком долго собирает ментальную модель проекта [cite:18] |
| Drift between docs and runtime | CLI, hooks, configs и packs эволюционируют быстрее текстов [cite:18] |
| README overload or under-explanation | Главный входной файл либо перегружен, либо бесполезно краток [cite:164][cite:166] |

#### Что проверить следующими итерациями

- Реальный состав `docs/`, README и architecture-oriented markdown-файлов [cite:18].
- Есть ли уже runbooks, troubleshooting docs, operator docs и schema references.
- Какие example-конфиги фактически выполняют роль документации.
- Есть ли CI-проверки или conventions, препятствующие drift между docs и кодом.
- Какие части текущего аудита можно затем превратить в постоянные architecture docs.

### 10. Тестируемость и quality gates

#### Итерация 10 — углублённая проработка

Почти все уже найденные риски в `swissknifeman` в конечном итоге упираются в один и тот же фундаментальный вопрос: какие инварианты проекта реально защищены автоматическими проверками, а какие пока существуют только в голове автора или в историческом поведении системы [cite:17][cite:18]. Для репозитория с provider lifecycle, hook telemetry, ownership semantics, multiple agent ecosystems и policy-sensitive file operations тестируемость — это не “покрыть функции”, а формализовать саму архитектурную правду проекта [cite:17][cite:18].

Именно поэтому здесь недостаточно классического набора `unit + немного integration`. Проекту нужны такие quality gates, которые ловят не только баги реализации, но и drift доменной модели: расхождение между config и lock semantics, деградацию hook parsing, изменения ownership policy, несогласованность agent definitions между runtime surfaces, и потерю explainability в CLI/output contracts [cite:17][cite:18].

#### Какие типы тестов здесь обязательны

##### 1. Domain invariant tests

Для provider/model/policy слоёв важнее всего инварианты, а не отдельные ветки кода [cite:18]. Примеры таких тестов:

- одинаковый config даёт одинаковый canonical manifest [cite:18];
- одинаковый manifest и одинаковое registry-state дают одинаковый lock [cite:18];
- lock serialization/deserialization не теряет смысловых полей [cite:18];
- ownership resolution детерминирована для managed/user-owned/protected assets [cite:17];
- reconcile над уже корректным состоянием идемпотентен [cite:18].

Это не столько unit-тесты, сколько contract/invariant suite для ядра системы [cite:18].

##### 2. Golden tests

Для проекта этого типа golden tests особенно ценны там, где есть сложный текстовый, JSON- или report-output, который должен оставаться понятным и стабильным [cite:176]. В `swissknifeman` это особенно актуально для:

- hook reports и telemetry outputs [cite:17];
- CLI explain/status/doctor outputs [cite:18];
- manifest/lock materialization outputs [cite:18];
- generated agent/runtime artifacts, если они должны быть стабильны между версиями [cite:17][cite:18].

Golden tests хороши именно тем, что позволяют быстро видеть не только “сломалось/не сломалось”, но и смысловые изменения в контрактах вывода [cite:176].

##### 3. Replay fixtures

Для hook/event/telemetry слоя критичны replay tests на реальных или синтетических transcript samples [cite:17]. Уже подтверждённый `run-report/_lib.py` построен как best-effort parser сложного JSONL потока; это значит, что самый важный класс регрессий здесь — не исключение, а тихое изменение interpretation semantics [cite:17]. Поэтому нужны replay fixtures, где исторические или специально сконструированные транскрипты прогоняются через парсер, а затем сравниваются normalized events, derived metrics и quality flags [cite:17].

##### 4. Snapshot / schema tests

Там, где проект опирается на versioned outputs или многослойные конфиги, нужны snapshot/schema tests. Наличие `SCHEMA = 2` в telemetry hook — уже сигнал, что schema evolution является частью домена [cite:17]. Следовательно, стоит проверять:

- schema backward compatibility;
- presence/absence и типы ключевых полей;
- маркировку degraded/unavailable/heuristic sections;
- стабильность machine-readable output для downstream tooling [cite:17].

##### 5. Property-like tests

Некоторые части системы лучше ловятся не примерами, а свойствами. Это особенно касается normalize/resolve/reconcile логики [cite:18]. Например:

- сериализация и десериализация являются взаимно согласованными;
- перестановка порядка несущественных входных записей не меняет результат;
- повторный запуск reconcile не меняет корректное состояние;
- protected path classification монотонна относительно расширения managed set [cite:17].

Даже без полноценного property-based фреймворка такие проверки можно писать как small generative suites [cite:177].

#### Где проект особенно нуждается в тестах

##### Provider subsystem

Именно здесь лежат самые дорогие доменные инварианты: truth model, reproducibility, drift detection, identity mapping, reconcile logic [cite:18]. Это зона для invariant tests + golden tests на manifest/lock outputs + migration tests для rename/backward compatibility [cite:18].

##### Hooks и telemetry

Это зона для replay fixtures, schema tests и degrade-mode tests [cite:17]. Нужно специально проверять битые строки, неизвестные события, отсутствие `_usage.py`, oversized transcripts, эвристические кейсы retrieval/rereads/error loops и expected quality flags [cite:17].

##### CLI

CLI требует contract tests по exit codes, error classes, help/explain semantics и safe mutation previews [cite:18]. Здесь важно тестировать не только “команда отрабатывает”, но и то, что пользователю даётся правильное объяснение и recoverability path [cite:18].

##### Config / ownership / policy

Это, вероятно, одна из самых недооценённых тестовых поверхностей. Нужны table-driven tests, где разные комбинации config, lock metadata и path ownership проверяют, что политика классификации consistent across codebase [cite:17][cite:18]. Если этого нет, security и mutation behavior будут дрейфовать незаметно [cite:17].

##### Agent ecosystem

Для `.agents`, `.claude`, `.codex`, `.claude-plugin` и pack semantics нужны consistency tests: один semantic core не должен расходиться между runtime surfaces без явного разрешения [cite:18]. Здесь подойдут snapshot/golden tests и drift-detection checks между platform variants [cite:18].

#### Target testing pyramid

Для `swissknifeman` разумная пирамида тестирования выглядит не стандартно, а доменно-ориентированно.

##### Основание

- pure unit tests для helpers, parsers, classifiers, serializers [cite:177];
- table-driven tests для config/policy/ownership combinations;
- invariant tests для provider/domain transitions [cite:18].

##### Средний слой

- integration tests для CLI -> application -> filesystem interactions [cite:18];
- replay tests для hooks/telemetry [cite:17];
- cross-surface consistency tests для agents/configs/locks [cite:17][cite:18].

##### Верхний слой

- end-to-end сценарии bootstrap / install / update / reconcile / report [cite:18];
- smoke tests на реальных минимальных workspace fixtures;
- compatibility tests на upgrade/migration paths [cite:18].

Важно, что в этом проекте середина пирамиды особенно важна. Если ограничиться только unit tests, большая часть архитектурного риска останется вне контроля [cite:17][cite:18].

#### P0 quality gates

##### 1. Invariant suite for providers and ownership

Без этого проект не сможет безопасно эволюционировать в части truth model, reconcile и managed/user-owned semantics [cite:17][cite:18]. Это должен быть обязательный CI-gate [cite:18].

##### 2. Replay regression suite for hooks/telemetry

Каждое изменение hook parser или telemetry aggregation должно прогоняться на наборе исторических/синтетических transcript fixtures [cite:17]. Это главный способ поймать silent semantic regressions [cite:17].

##### 3. Golden outputs for CLI and reports

Статус, explain, doctor, report и schema-bearing outputs должны иметь golden coverage, чтобы смысловые изменения были видны code review сразу [cite:176][cite:18].

##### 4. Policy consistency checks

Проверки managed/protected/user-owned classification должны исполняться как отдельный gate, а не растворяться среди обычных unit tests [cite:17]. Это отдельный класс регрессий, слишком дорогой для ручной проверки [cite:17].

##### 5. Schema/version compatibility checks

Любой versioned output — особенно telemetry/report schema и lock-like structures — должен проверяться на совместимость и ожидаемые деградации [cite:17][cite:18].

#### Рекомендуемые quality gates в CI

| Gate | Что проверяет | Почему это P0/P1 |
|---|---|---|
| Invariant tests | truth model, determinism, idempotency | Ловит самые дорогие доменные регрессии [cite:18] |
| Hook replay suite | transcript parsing, derived signals, degraded modes | Ловит silent telemetry regressions [cite:17] |
| Golden output checks | CLI/report/manifest outputs | Делает contract drift видимым [cite:176][cite:18] |
| Policy tests | ownership/protected path rules | Защищает security-sensitive semantics [cite:17] |
| Schema checks | versioned outputs and machine-readable contracts | Предотвращает downstream breakage [cite:17] |
| Smoke E2E | bootstrap/install/report minimal scenarios | Подтверждает, что система жива целиком [cite:18] |

#### Что ещё важно как gate, помимо тестов

Quality gates для такого проекта не должны ограничиваться pytest-runner сам по себе, даже если pytest отлично масштабируется для сложных сценариев [cite:177]. Помимо обычных тестов нужны ещё:

- drift checks между agent surfaces;
- docs/code consistency checks для ключевых architecture contracts;
- lock/config integrity checks;
- по возможности command-map/help consistency validation;
- pre-merge safety checks на изменения policy-bearing файлов [cite:17][cite:18].

Git hooks и CI обычно рассматриваются как первая линия автоматической защиты качества, и для `swissknifeman` это особенно верно, потому что значительная часть риска живёт именно в mutation-sensitive и policy-sensitive изменениях [cite:181].

#### Типовые пробелы, которые стоит закрыть

Если смотреть на уже найденные зоны риска, самые вероятные текущие тестовые пробелы таковы [cite:17][cite:18]:

- Недостаток replay fixtures для hooks.
- Недостаток formal invariants для provider/lock/manifest model.
- Отсутствие quality indicators в golden outputs telemetry/reporting.
- Слабая проверка policy/ownership semantics.
- Недостаточная проверка drift между multi-runtime agent definitions.

Даже если часть тестов уже есть, эти поверхности слишком критичны, чтобы оставлять их непокрытыми или покрытыми косвенно [cite:17][cite:18].

#### Целевое состояние

Зрелая test strategy для `swissknifeman` должна делать видимыми не только баги кода, но и смысловые регрессии архитектуры [cite:17][cite:18]. Хороший итоговый признак зрелости здесь такой: если меняется provider semantics, hook interpretation, ownership policy, agent surface mapping или operator-facing output, CI должен показать это как явное, объяснимое изменение — а не как случайный побочный эффект спустя недели эксплуатации [cite:17][cite:18].

Именно это превращает тесты в quality gates, а не просто в набор проверок корректности функций [cite:17][cite:18].


### Итерация 11

- Углублён раздел «Тестируемость и quality gates».
- Сформулированы обязательные типы тестов: invariant, golden, replay, snapshot/schema, property-like.
- Предложена доменно-ориентированная testing pyramid и набор P0 quality gates.
- Зафиксированы критичные regression surfaces для providers, hooks, CLI, policy logic и agent ecosystems.


### 11. Master roadmap и приоритизация

#### Итерация 11 — сводный слой

После десяти итераций уже можно уверенно сказать, что `swissknifeman` не выглядит как случайный набор утилит. Это амбициозная orchestration-система вокруг локальных AI-agent workflows, у которой уже есть собственные доменные модели: providers, agent distribution, ownership semantics, hook telemetry, protected mutation policy и CLI-facing operational surface [cite:17][cite:18]. Главная сила проекта — в глубине этих моделей. Главная слабость — в том, что они пока слишком сильно распределены между кодом, хуками, lock/config артефактами и неявными соглашениями [cite:17][cite:18].

Поэтому master roadmap должен быть направлен не на “сделать больше фич”, а на снижение архитектурной неоднозначности. На текущем этапе проекту важнее stabilizing and clarifying work, чем расширение функциональности: система уже достаточно сложна, чтобы стоимость drift, скрытых инвариантов и policy рассинхронизации начала расти быстрее, чем ценность новых возможностей [cite:17][cite:18].

#### Единая карта рисков

Все предыдущие разделы в сущности сводятся к нескольким мета-рискам.

##### 1. Distributed truth

Одна и та же доменная истина распределена между несколькими слоями: config, manifest, lock, artifacts, hooks, agent surfaces, naming conventions и документацией [cite:17][cite:18]. Это создаёт риск того, что разные части системы принимают решения на основе разных “канонических” представлений [cite:17][cite:18].

##### 2. Policy ambiguity

Semantics `managed`, `user_owned`, `protected`, `safe`, `trusted` уже присутствуют в системе, но пока слишком вероятно, что они живут не в одном explicit policy layer, а в нескольких implementation-specific местах [cite:17][cite:18]. Для mutation-sensitive harness это один из самых опасных видов неоднозначности [cite:17].

##### 3. Heuristic drift

Hooks, telemetry и часть operational intelligence уже зависят от эвристик: regex-классификации, similarity rules, best-effort extraction, schema-tolerant parsing [cite:17]. Это оправдано инженерно, но без replay/golden/quality flags эвристики будут постепенно расходиться с реальным поведением системы [cite:17].

##### 4. Cross-surface drift

Проект, похоже, поддерживает несколько agent/runtime поверхностей одновременно: `.agents`, `.claude`, `.claude-plugin`, `.codex` [cite:18]. Это даёт гибкость, но создаёт постоянный риск drift между представлениями одного и того же intent [cite:18].

##### 5. Knowledge trapped in implementation

Слишком много критичных смыслов уже приходится восстанавливать из кода, каталогов и lock semantics, а не читать из одного архитектурного слоя документации [cite:17][cite:18]. Это напрямую увеличивает стоимость сопровождения и снижает масштабируемость проекта как для команды, так и для future-self автора [cite:18].

#### P0 / P1 / P2 / P3 приоритизация

##### P0 — стабилизация критичных инвариантов

Это задачи, без которых проект рискует дрейфовать быстрее, чем развивается [cite:17][cite:18]:

- Зафиксировать source-of-truth model для provider/config/manifest/lock/artifact lifecycle [cite:18].
- Централизовать semantics `managed` / `user_owned` / `protected` / `safe` / `trusted` [cite:17][cite:18].
- Ввести invariant tests и replay/golden suites для providers, hooks, telemetry и policy logic [cite:17][cite:18][cite:176].
- Добавить quality/completeness flags в telemetry/reporting [cite:17].
- Ввести preflight policy checks для mutation-sensitive операций [cite:17].

##### P1 — прояснение и объяснимость

Это слой, который делает систему управляемой человеком, а не только автором [cite:18]:

- Разделить CLI на parser / use-case / presenter слои и усилить `status`, `validate`, `doctor`, `explain`, `trace`, `dry-run` сценарии [cite:18].
- Описать architecture overview, provider model, hooks, agents, security и telemetry как canonical docs [cite:17][cite:18].
- Ввести explain outputs для ownership/path policy и provider resolution [cite:17][cite:18].
- Явно маркировать heuristic-derived и degraded telemetry fields [cite:17].

##### P2 — декомпозиция и снижение связности

После стабилизации и прояснения можно безопасно уменьшать structural coupling [cite:17][cite:18]:

- Разделить hook layer на adapter / normalization / domain metrics / reporting [cite:17].
- Декомпозировать `core/` вокруг явных domain/application/infra boundaries [cite:18].
- Выделить unified semantic core для agent definitions и снизить ручной drift между runtime surfaces [cite:18].
- Вынести policy engine из scattered helpers в центральный модуль [cite:17][cite:18].

##### P3 — масштабирование и productization

Только после предыдущих слоёв имеет смысл усиливать “платформенность” проекта [cite:17][cite:18]:

- Генерация/синхронизация vendor-specific agent definitions из canonical core [cite:18].
- Более формальные dashboards/analytics над telemetry [cite:17].
- Policy-as-code, richer CI gates, compatibility matrices, migration tooling.
- Продвинутая operator UX и self-diagnostics.

#### Phased roadmap

##### Фаза 1 — Stabilization

Цель: перестать терять контроль над доменными и policy-инвариантами [cite:17][cite:18].

- Формализовать provider truth model.
- Формализовать ownership/security vocabulary.
- Ввести mandatory invariant tests.
- Ввести hook replay suite.
- Ввести telemetry quality flags.
- Включить basic security/ownership validate checks.

##### Фаза 2 — Clarification

Цель: сделать систему explainable и discoverable [cite:17][cite:18].

- Architecture overview docs.
- Canonical docs по providers/hooks/agents/security/telemetry.
- Explainable CLI outputs.
- Operator docs по degraded modes, policy semantics и recovery paths.
- Явная документация, где canonical, а где generated/delivered layers.

##### Фаза 3 — Decomposition

Цель: снизить structural coupling без потери функциональности [cite:17][cite:18].

- Refactor hook parsing pipeline.
- Refactor `core/` into clearer boundaries.
- Separate policy engine.
- Separate agent semantic core from runtime packaging.
- Reduce vendor drift around `_usage.py` and related logic [cite:17].

##### Фаза 4 — Scaling

Цель: подготовить проект к росту как платформы, а не как personal power-repo [cite:18].

- Cross-runtime generation/sync tooling.
- Advanced CI policy gates.
- Richer machine-readable observability contracts.
- Migration/upgrade tooling.
- Architectural decision tracking and long-term compatibility governance.

#### Top-10 самых опасных архитектурных проблем

| # | Проблема | Почему это опасно |
|---|---|---|
| 1 | Нет явно зафиксированной truth model для provider lifecycle | Любая новая логика может усиливать conflict между config, manifest, lock и artifacts [cite:18] |
| 2 | Ownership/policy semantics распределены по нескольким слоям | Security и mutation behavior рискуют стать непредсказуемыми [cite:17][cite:18] |
| 3 | Hook layer уже несёт substantial business/policy semantics | Интеграционный слой превращается в скрытый центр архитектуры [cite:17] |
| 4 | Telemetry fail-open без достаточно явной confidence model | Оператор может доверять неполному или деградировавшему сигналу [cite:17] |
| 5 | Vendor drift вокруг `_usage.py` | Usage and telemetry integrity могут незаметно расходиться [cite:17] |
| 6 | Drift между `.agents`, `.claude`, `.claude-plugin`, `.codex` | Один агентный intent может стать несколькими разными сущностями [cite:18] |
| 7 | CLI может быть недостаточно explainable для сложности домена | Пользователь вынужден читать код вместо использования продукта [cite:18] |
| 8 | Knowledge architecture отстаёт от фактической сложности системы | Архитектурное знание застревает в implementation details [cite:17][cite:18] |
| 9 | Недостаток invariant/replay/golden quality gates | Semantic regressions будут обнаруживаться слишком поздно [cite:17][cite:18][cite:176] |
| 10 | `core/` рискует оставаться coordination-heavy hub | Рост будет увеличивать связанность быстрее, чем предсказуемость [cite:18] |

#### Сводный backlog

| Проблема | Риск | Рекомендуемое действие | Ожидаемый эффект | Зависимости |
|---|---|---|---|---|
| Provider truth ambiguity | Расхождение intent/resolved/materialized states [cite:18] | Описать и зафиксировать canonical state machine для providers | Снижает доменную неоднозначность и улучшает тестируемость [cite:18] | Нет |
| Split policy semantics | Непредсказуемые writes и ownership conflicts [cite:17][cite:18] | Вынести единый policy vocabulary и central policy resolver | Снижает security drift [cite:17] | Частично зависит от provider/agent docs |
| Hook gravity | Логика продолжит накапливаться в интеграционном слое [cite:17] | Разделить hook pipeline на adapter/normalize/metrics/reporting | Улучшает модульность и replay-тестируемость [cite:17] | Желательна telemetry schema ясность |
| Silent telemetry degradation | Решения принимаются на неполном сигнале [cite:17] | Добавить quality flags, confidence markers, degrade reporting | Делает observability trustworthy [cite:17] | Нет |
| Usage vendor drift | Несогласованность usage numbers [cite:17] | Минимизировать copy-based sync, добавить integrity/sync checks | Повышает консистентность telemetry [cite:17] | Hook refactor helpful |
| Agent intent drift | Divergence между runtime surfaces [cite:18] | Ввести semantic core и drift-detection tooling | Снижает дублирование и стоимость сопровождения [cite:18] | Нужна карта agent ecosystems |
| Weak CLI explainability | High support/debug cost [cite:18] | Ввести explain/status/trace/doctor/dry-run oriented UX | Повышает operability и self-service [cite:18] | Желательны docs and policy clarity |
| Knowledge trapped in implementation | Slow onboarding and high author dependency [cite:17][cite:18] | Создать architecture docs и reference layers | Уменьшает bus factor и cognitive load [cite:18] | Нет |
| Weak regression safety net | Semantic bugs доживают до runtime [cite:17][cite:18] | Запустить invariant + replay + golden CI suite | Ловит критичные regressions рано [cite:176] | Нужно зафиксировать contracts |
| Coordination-heavy core | Сложность растёт нелинейно [cite:18] | Разделить core по domain/application/infra boundaries | Улучшает maintainability и локальность изменений [cite:18] | Лучше делать после clarification |

#### Практический порядок исполнения

Если переводить roadmap в реальную последовательность работ, наиболее рациональный путь выглядит так [cite:17][cite:18]:

1. Сначала закрепить **инварианты и vocabulary** — provider truth model, ownership/policy semantics, telemetry quality model [cite:17][cite:18].
2. Затем повесить на это **quality gates** — invariant tests, replay fixtures, golden outputs, policy checks [cite:17][cite:18][cite:176].
3. После этого прояснить систему для человека — docs, CLI explainability, operator workflows [cite:18].
4. Только затем делать глубокую структурную декомпозицию hooks/core/agent surfaces [cite:17][cite:18].
5. И лишь потом идти в расширение платформенных возможностей и автоматизацию генерации/sync [cite:18].

Это важно, потому что попытка начать с глубокого рефакторинга без фиксации инвариантов почти наверняка ухудшит ситуацию: проект очень насыщен скрытыми смыслами, а не просто техническим шумом [cite:17][cite:18].

#### Критерий успеха

Успешный следующий этап для `swissknifeman` — это не “код стал красивее”. Успех будет означать другое: система сможет сама объяснять свою доменную модель, защищать свои критичные инварианты, показывать качество собственных сигналов и безопасно эволюционировать без постоянной зависимости от неявного знания автора [cite:17][cite:18].

Именно это превратит репозиторий из мощного персонального инструмента в по-настоящему устойчивую и масштабируемую agent orchestration platform [cite:17][cite:18].


### 12. Implementation plan по PR-этапам

#### Итерация 12 — перевод аудита в исполнение

После сводной приоритизации следующий логичный шаг — превратить аудит из аналитического документа в план внедрения. Для `swissknifeman` это особенно важно, потому что многие проблемы проекта не решаются одним “большим рефакторингом”. Наоборот, слишком крупные изменения здесь опасны: они затрагивают policy semantics, hook telemetry, provider truth model и multi-surface agent ecosystem одновременно [cite:17][cite:18]. Значит, правильная стратегия — не massive rewrite, а последовательность небольших PR-этапов с жёстко очерченным смыслом, измеримым эффектом и понятной обратной связью [cite:17][cite:18].

GitHub сам по себе ориентирует процесс изменений вокруг pull requests как обсуждаемых и проверяемых единиц интеграции, а также поддерживает стандартизацию через шаблоны, protected branches и required checks [cite:203][cite:210]. Для проекта такого класса это особенно полезно: PR должен быть не просто контейнером коммитов, а носителем одной архитектурной гипотезы и одного measurable improvement step [cite:203][cite:210].

#### Принципы исполнения

Перед списком PR-этапов полезно зафиксировать несколько принципов внедрения.

- Один PR — одна архитектурная цель. Не смешивать, например, hook refactor и agent semantic core в одной ветке [cite:203].
- Сначала contracts, потом refactor. Сначала описать/зафиксировать truth model, schema, vocabulary и tests, а уже затем передвигать код [cite:17][cite:18].
- Любой PR, меняющий policy-bearing semantics, должен сопровождаться explainable diff: что именно изменилось в поведении системы [cite:17][cite:18].
- Риски silent regressions должны закрываться replay/golden/invariant gates в том же PR или раньше [cite:17][cite:176].
- Большие инициативы лучше открывать как draft PR или PR-series, чтобы видеть cumulative direction до финального merge [cite:203].

#### Поток исполнения по волнам

Вместо “сразу всё” проекту лучше идти волнами. Ниже — рекомендуемая очередность.

##### Волна A — Contracts first

Цель: зафиксировать vocabulary, truth models и contracts до любых серьёзных перемещений кода [cite:17][cite:18].

##### Волна B — Safety net

Цель: поставить тестовые и quality gates, чтобы следующие изменения не ломали скрытые инварианты [cite:17][cite:176].

##### Волна C — Explainability

Цель: сделать систему понятнее оператору и мейнтейнеру через docs и CLI-facing diagnostics [cite:18].

##### Волна D — Structural decomposition

Цель: уменьшить сцепление core/hooks/agents слоёв после того, как система уже защищена contracts и gates [cite:17][cite:18].

##### Волна E — Scaling automation

Цель: добавить генерацию, drift-detection и richer orchestration tooling, когда foundation уже стабилен [cite:18].

#### Рекомендуемая серия PR

| PR | Название | Цель | Основной результат | Риск |
|---|---|---|---|---|
| PR-01 | Provider truth model ADR | Зафиксировать intent/resolved/materialized model | Canonical doc + glossary + state machine [cite:18] | Низкий |
| PR-02 | Ownership & policy vocabulary | Централизовать `managed/user_owned/protected/safe/trusted` | Security/policy glossary + reference semantics [cite:17][cite:18] | Низкий |
| PR-03 | Invariant test harness | Ввести доменные инварианты как CI gate | Provider/policy invariant suite [cite:17][cite:18] | Средний |
| PR-04 | Hook replay fixtures | Закрыть silent regressions в telemetry hooks | Replay fixture suite + baseline outputs [cite:17] | Средний |
| PR-05 | Telemetry quality flags | Сделать деградацию видимой | `complete/partial/degraded/heuristic` markers [cite:17] | Средний |
| PR-06 | CLI diagnostics baseline | Усилить status/validate/doctor/explain UX | Минимальный explainability surface [cite:18] | Средний |
| PR-07 | Architecture docs spine | Сформировать persistent knowledge architecture | docs/architecture/* baseline [cite:18][cite:164] | Низкий |
| PR-08 | Hook pipeline split | Разделить parsing/normalization/metrics/reporting | Снижение hook gravity [cite:17] | Высокий |
| PR-09 | Usage sync hardening | Минимизировать drift вокруг `_usage.py` | Integrity checks or generation flow [cite:17] | Средний |
| PR-10 | Agent semantic core map | Выделить canonical model для agents | Cross-runtime contract draft [cite:18] | Средний |
| PR-11 | Cross-surface drift checks | Проверять расхождения `.claude/.codex/.agents` | Drift detection gate [cite:18] | Средний |
| PR-12 | Core boundary refactor | Разделить coordination-heavy `core/` | Better domain/application/infra split [cite:18] | Высокий |

#### Детализация PR-этапов

##### PR-01 — Provider truth model ADR

**Проблема:** provider subsystem сейчас выглядит как домен со смешанной truth model между config, manifest, lock и artifact слоями [cite:18].

**Что делать:**
- Добавить architecture doc с явной state machine.
- Определить source of truth для каждого перехода.
- Явно различить desired state, resolved state, materialized state [cite:18].

**Definition of done:**
- Есть canonical markdown-документ.
- В документе есть glossary и lifecycle diagram/text map.
- Все основные provider-related модули привязаны к этой модели хотя бы ссылками или комментариями.

##### PR-02 — Ownership & policy vocabulary

**Проблема:** semantics `managed`, `user_owned`, `protected`, `safe`, `trusted` критичны для безопасности, но слишком вероятно распределены по нескольким слоям [cite:17][cite:18].

**Что делать:**
- Добавить central policy glossary.
- Явно описать разрешённые и запрещённые mutation scenarios.
- Привязать lock/config semantics к этому словарю [cite:17][cite:18].

**Definition of done:**
- Появился единый policy reference doc.
- Основные policy-bearing места кода/конфигов ссылаются на него.
- Нет терминов-двойников с размытым смыслом.

##### PR-03 — Invariant test harness

**Проблема:** критичные доменные истины пока слишком легко дрейфуют [cite:17][cite:18].

**Что делать:**
- Завести инвариантный test-suite для providers и ownership logic.
- Проверить determinism, idempotency, serialization consistency, policy classification [cite:17][cite:18].

**Definition of done:**
- Suite запускается в CI.
- Есть минимальный набор fixtures.
- Падение инварианта даёт читаемую причину, а не случайный stack trace.

##### PR-04 — Hook replay fixtures

**Проблема:** hook/telemetry слой особенно подвержен silent semantic regressions [cite:17].

**Что делать:**
- Собрать исторические и синтетические transcript samples.
- Зафиксировать ожидаемые normalized/derived outputs.
- Добавить replay runner и golden comparison [cite:17][cite:176].

**Definition of done:**
- Любое изменение hook parser можно прогнать на baseline fixtures.
- CI показывает именно semantic diff отчёта, а не просто “test failed”.

##### PR-05 — Telemetry quality flags

**Проблема:** система богата сигналами, но слишком слабо показывает качество самих сигналов [cite:17].

**Что делать:**
- Добавить completeness/quality markers.
- Маркировать heuristic-derived sections.
- Отдельно показывать skipped/invalid/unknown event counts [cite:17].

**Definition of done:**
- Отчёт всегда сообщает, насколько он полный.
- Degraded mode перестаёт маскироваться под normal success [cite:17].

##### PR-06 — CLI diagnostics baseline

**Проблема:** сложность домена уже требует explainable operational interface [cite:18].

**Что делать:**
- Минимально ввести или усилить `status`, `validate`, `doctor`, `explain`, `dry-run` поверх самых важных flows [cite:18].
- Привести ошибки к более явным классам и recovery hints [cite:18].

**Definition of done:**
- Пользователь может понять текущее состояние системы без чтения исходников.
- На базовые failure scenarios есть next-step guidance [cite:18].

##### PR-07 — Architecture docs spine

**Проблема:** knowledge architecture отстаёт от реальной сложности системы [cite:17][cite:18].

**Что делать:**
- Создать скелет architecture docs по ключевым доменам.
- Сослаться на них из README и operational guides [cite:164][cite:166].

**Definition of done:**
- Есть устойчивый entrypoint для понимания архитектуры.
- Основные домены больше не существуют только как реконструкция из кода.

##### PR-08 — Hook pipeline split

**Проблема:** `run-report/_lib.py` уже стал highly coupled aggregation engine [cite:17].

**Что делать:**
- Разнести adapter, normalization, metrics, reporting.
- Сохранить backward-compatible output schema, если это возможно [cite:17].

**Definition of done:**
- Replay suite остаётся зелёным.
- Изменение одной категории сигналов не требует риска для всего пайплайна.

##### PR-09 — Usage sync hardening

**Проблема:** вендорный `_usage.py` создаёт integrity и maintenance risk [cite:17].

**Что делать:**
- Ввести checksum/integrity check либо generation-based sync flow.
- Явно документировать источник истины usage logic [cite:17].

**Definition of done:**
- Drift usage copy обнаруживается автоматически.
- Обновление usage logic не зависит от человеческой памяти.

##### PR-10 — Agent semantic core map

**Проблема:** multi-surface agent model рискует дрейфовать между `.agents`, `.claude`, `.codex`, `.claude-plugin` [cite:18].

**Что делать:**
- Описать canonical semantic core агента.
- Составить matrix соответствия runtime surfaces [cite:18].

**Definition of done:**
- Для каждого агентного surface понятно, canonical он или adapter-derived.
- Дублирование intent становится измеримым.

##### PR-11 — Cross-surface drift checks

**Проблема:** даже после semantic core дрейф между поверхностями может оставаться ручным [cite:18].

**Что делать:**
- Добавить consistency checker или хотя бы structured diff report между runtime variants [cite:18].

**Definition of done:**
- CI или локальная команда показывает, где конкретно расходятся агентные поверхности.

##### PR-12 — Core boundary refactor

**Проблема:** `core/` рискует оставаться coordination-heavy hub [cite:18].

**Что делать:**
- После предыдущих contracts и tests начать пошаговый перенос к domain/application/infra split [cite:18].
- Идти малыми PR внутри этой волны, а не одним гигантским merge.

**Definition of done:**
- Ключевые ответственности становятся локальнее.
- Новые изменения проще размещать по понятным слоям.

#### Что можно делать параллельно

Не все PR обязаны идти строго один за другим. Возможная параллелизация:

- PR-01 и PR-02 можно вести параллельно, потому что это primarily documentation + vocabulary work [cite:18].
- PR-03 и PR-04 можно частично параллелить после фиксации базовых contracts [cite:17][cite:18].
- PR-06 и PR-07 тоже хорошо сочетаются: CLI explainability и documentation усиливают друг друга [cite:18].
- PR-08, PR-10, PR-12 лучше не смешивать друг с другом, потому что это уже тяжёлые structural initiatives [cite:17][cite:18].

#### Правила для PR template

Для такого репозитория полезно стандартизировать сам формат pull requests. GitHub рекомендует использовать PR templates и required checks для стандартизации review-process, а protected branches и rulesets помогают не пропускать risky merges без нужных условий [cite:210]. Для `swissknifeman` template должен включать:

- какой доменный контракт затронут;
- меняется ли policy/ownership semantics;
- есть ли change в machine-readable output;
- какие replay/golden/invariant tests покрывают изменение;
- какие docs нужно обновить;
- есть ли risk of drift for agents/providers/hooks [cite:210].

Это особенно важно, потому что многие опасные изменения здесь выглядят “маленькими” на уровне diff, но большими на уровне semantics [cite:17][cite:18].

#### Критерий хорошей следующей итерации разработки

Хорошая следующая волна изменений для `swissknifeman` — это не та, где больше всего передвинуто кода. Хорошая волна — та, после которой у проекта появляется больше явных контрактов, меньше скрытых смыслов и больше автоматических гарантий against drift [cite:17][cite:18].

Именно поэтому лучшая ближайшая стратегия — начать не с большого рефакторинга, а с PR-01 → PR-05: сначала закрепить модель, словарь, инварианты, replay-базу и quality flags. После этого уже можно безопасно идти в CLI, docs и structural decomposition [cite:17][cite:18].


### 13. ADR pack — набор архитектурных решений для фиксации

#### Итерация 13 — превращение выводов в постоянные архитектурные решения

После roadmap и implementation plan следующий зрелый шаг — не просто выполнять изменения, а зафиксировать ключевые архитектурные развилки как ADR (Architecture Decision Records). ADR предназначены именно для этого: они фиксируют существенное архитектурное решение вместе с контекстом и последствиями, а типовые шаблоны строятся вокруг секций `status`, `context`, `decision` и `consequences` [cite:218][cite:219]. Практика хранения ADR прямо в репозитории и ведения их как append-only decision log считается хорошей нормой, особенно для решений, которые трудно менять, влияют на maintainability/security/performance или имеют несколько разумных альтернатив [cite:220][cite:222][cite:227][cite:232].

Для `swissknifeman` это особенно важно, потому что проект уже перерос стадию, где архитектурные решения можно держать в памяти. Здесь есть как минимум несколько cross-cutting решений, от которых зависят providers, hooks, agents, CLI, telemetry и security semantics одновременно [cite:17][cite:18]. Если такие развилки не зафиксировать как ADR, команда снова вернётся к knowledge trapped in implementation — даже при наличии хорошего аудита [cite:17][cite:18].

#### Где хранить ADR

Наиболее уместная схема для этого репозитория — завести ADR прямо внутри project docs, например `docs/adr/` или `docs/decisions/`. Хранение ADR рядом с кодом и документацией считается предпочтительной практикой, потому что решения остаются versioned вместе с системой, а не теряются во внешних инструментах [cite:220][cite:222][cite:227][cite:231]. Нумерация по порядку и единый шаблон тоже считаются хорошей практикой, потому что позволяют строить понятный decision log вместо набора произвольных заметок [cite:220][cite:222][cite:231].

Для `swissknifeman` хорошо подойдёт такой базовый формат:

- `docs/adr/0001-provider-truth-model.md`
- `docs/adr/0002-ownership-policy-vocabulary.md`
- `docs/adr/0003-hook-pipeline-boundaries.md`
- `docs/adr/0004-telemetry-quality-model.md`
- `docs/adr/0005-agent-semantic-core.md`
- `docs/adr/0006-cli-explainability-contract.md`
- `docs/adr/0007-testing-and-quality-gates.md`

#### Рекомендуемый шаблон ADR

Для этого проекта не нужен тяжёлый enterprise-шаблон. Достаточно короткого и дисциплинированного формата: title, status, context, decision, consequences, alternatives, related decisions [cite:219][cite:222][cite:227]. Критично другое: записи должны быть краткими, однозначными и не редактироваться задним числом после принятия; если решение меняется, нужно создавать superseding ADR, а не переписывать историю [cite:222][cite:227][cite:232].

Минимальный шаблон для `swissknifeman`:

- Title
- Status (`Proposed`, `Accepted`, `Superseded`, `Deprecated`) [cite:222][cite:227]
- Context
- Decision
- Consequences
- Alternatives considered
- Related docs / related ADRs

#### Набор рекомендуемых ADR

Ниже — не просто темы, а уже готовый пакет решений, который логично занести в репозиторий почти без дополнительного переосмысления.

##### ADR-0001 — Provider truth model

**Статус:** Proposed.

**Контекст:** provider subsystem оперирует несколькими близкими представлениями состояния: config, manifest, lock, artifacts, reconcile behaviour [cite:18]. Сейчас риск заключается в смешанной truth model, где разные слои могут по-разному трактовать canonical state [cite:18].

**Решение:** принять формальную state model с уровнями `intent state`, `resolved state`, `materialization plan`, `materialized state`, а manifest либо закрепить как canonical intent document, либо как строго определённый derived artifact, но не как ещё одну равноправную истину [cite:18].

**Последствия:** возрастёт ясность provider lifecycle, улучшатся tests и explainability, но потребуется переосмыслить текущие implicit assumptions в provider-related коде [cite:18].

##### ADR-0002 — Ownership and policy vocabulary

**Статус:** Proposed.

**Контекст:** проект уже использует semantics `managed`, `user_owned`, `protected`, `safe`, `trusted`, в том числе через lock-файлы и hooks [cite:17][cite:18]. Сейчас главный риск — policy split-brain между слоями системы [cite:17][cite:18].

**Решение:** ввести централизованный policy vocabulary и единый resolver semantics для ownership/path classification; все mutation-sensitive решения должны опираться на этот vocabulary, а не на локальные трактовки [cite:17][cite:18].

**Последствия:** security semantics станут стабильнее и понятнее, но часть scattered helper logic придётся мигрировать в центральный policy слой [cite:17].

##### ADR-0003 — Hook pipeline boundaries

**Статус:** Proposed.

**Контекст:** `run-report/_lib.py` уже объединяет adapter behaviour, schema-tolerant parsing, metrics extraction, heuristics и report assembly [cite:17]. Это создаёт hook gravity и повышает риск coupling [cite:17].

**Решение:** разделить hook pipeline на четыре слоя: adapter, normalization, domain metrics, reporting [cite:17]. Observation hooks могут быть fail-open, но должны выставлять quality flags; enforcement hooks требуют отдельной policy taxonomy [cite:17].

**Последствия:** replay-тесты и эволюция схемы станут проще, но потребуется промежуточный refactor и временная поддержка backward-compatible outputs [cite:17].

##### ADR-0004 — Telemetry quality model

**Статус:** Proposed.

**Контекст:** telemetry уже богата derived signals, но слабо маркирует собственное качество: completeness, degraded mode, heuristic derivation, missing parsers [cite:17]. Это создаёт риск ложного доверия к отчётам [cite:17].

**Решение:** любой telemetry/report output должен включать explicit quality model: completeness markers, heuristic fields, skipped/invalid counts, confidence by section [cite:17]. Versioning должен охватывать не только финальный output schema, но и normalized event contract [cite:17].

**Последствия:** observability станет надёжнее как инструмент эксплуатации и security analysis, но downstream consumers должны будут учитывать richer metadata [cite:17].

##### ADR-0005 — Agent semantic core and runtime adapters

**Статус:** Proposed.

**Контекст:** проект содержит несколько agent-related surfaces: `.agents`, `.claude`, `.claude-plugin`, `.codex` [cite:18]. Это создаёт риск intent drift между runtime-представлениями [cite:18].

**Решение:** зафиксировать canonical semantic core для агента и трактовать runtime-specific представления как adapters или delivery variants, а не как равноправные источники истины [cite:18]. Для drift detection должны существовать consistency checks между surface variants [cite:18].

**Последствия:** снизится ручное дублирование intent, но часть существующих каталогов придётся переосмыслить как generated/delivered layers [cite:18].

##### ADR-0006 — CLI explainability contract

**Статус:** Proposed.

**Контекст:** CLI — главный операционный интерфейс сложной системы, но проекту уже явно нужны status/validate/doctor/explain/trace/dry-run сценарии, а не только thin command routing [cite:18].

**Решение:** принять, что CLI обязан не только выполнять операции, но и объяснять state, planned mutations, resolution decisions и recovery paths [cite:18]. Ошибки должны быть разделены как минимум на user/config, environment, resolution, drift и internal classes [cite:18].

**Последствия:** UX станет намного сильнее и снизит support/debug cost, но потребует явного presenter/error-model слоя [cite:18].

##### ADR-0007 — Testing and quality gates as architecture protection

**Статус:** Proposed.

**Контекст:** большинство ключевых рисков проекта — semantic regressions, а не локальные алгоритмические баги [cite:17][cite:18]. Обычные unit tests недостаточны для их контроля [cite:17][cite:18].

**Решение:** сделать invariant tests, hook replay suites, golden outputs, policy checks и schema compatibility обязательными quality gates [cite:17][cite:176]. Quality system должна защищать architectural contracts, а не только функции [cite:17][cite:18].

**Последствия:** скорость изменения кода может немного снизиться, но устойчивость и предсказуемость проекта вырастут существенно [cite:17][cite:18].

#### В каком порядке создавать ADR

Не все ADR одинаково срочны. Логичный порядок принятия:

1. `ADR-0001 Provider truth model` [cite:18].
2. `ADR-0002 Ownership and policy vocabulary` [cite:17][cite:18].
3. `ADR-0004 Telemetry quality model` [cite:17].
4. `ADR-0007 Testing and quality gates` [cite:17][cite:18].
5. `ADR-0006 CLI explainability contract` [cite:18].
6. `ADR-0003 Hook pipeline boundaries` [cite:17].
7. `ADR-0005 Agent semantic core and runtime adapters` [cite:18].

Такой порядок полезен потому, что сначала закрепляются vocabulary, truth и safety model, потом quality protection, а уже потом более глубокие structural decisions [cite:17][cite:18].

#### Как связать ADR с текущим execution plan

ADR не должны жить отдельно от roadmap и PR plan. Хорошая практика — связывать значимые решения с backlog и PR workflow, а также использовать шаблоны и process notes, чтобы команда понимала, когда нужен новый ADR [cite:223][cite:227]. Для `swissknifeman` это можно оформить так:

- PR-01 ссылается на ADR-0001.
- PR-02 ссылается на ADR-0002.
- PR-03/PR-04/PR-05 ссылаются на ADR-0004 и ADR-0007.
- PR-06 ссылается на ADR-0006.
- PR-08 ссылается на ADR-0003.
- PR-10/PR-11 ссылаются на ADR-0005.

Тогда audit -> ADR -> PR образуют одну непрерывную цепочку архитектурного управления, а не три независимых слоя документации [cite:17][cite:18][cite:223].

#### Критерий качества ADR для этого проекта

Хороший ADR в `swissknifeman` должен быть коротким, но не абстрактным. Он должен отвечать не только на вопрос “что решили”, но и на вопрос “какую неоднозначность аудита это решение закрывает” [cite:218][cite:222][cite:227]. Если ADR не уменьшает distributed truth, policy ambiguity, heuristic drift или cross-surface drift, значит он либо слишком поверхностный, либо описывает не самое важное решение [cite:17][cite:18].

Именно поэтому ADR pack здесь — не бюрократия, а способ превратить крупные выводы аудита в долговечную архитектурную память репозитория [cite:225][cite:227].


### 14. Risk register / issue register

#### Итерация 14 — превращение аудита в управляемый реестр рисков

После audit, roadmap, PR-plan и ADR pack логично добавить ещё один слой — risk register. Для software/system projects risk register обычно фиксирует описание риска, вероятность, влияние, приоритет, owner, mitigation и contingency/status; именно такой формат считается удобным для регулярного пересмотра и управления сложными изменениями [cite:237][cite:238]. В случае `swissknifeman` это особенно полезно, потому что часть проблем уже выглядит не как “один баг”, а как долговременные architectural risks: distributed truth, policy split-brain, heuristic drift, cross-surface drift и knowledge trapped in implementation [cite:17][cite:18].

GitHub Issues и GitHub Projects хорошо подходят для того, чтобы превращать такие риски в управляемый backlog: issues можно разбивать на подзадачи, маркировать приоритетами и отслеживать как таблицу, board или roadmap [cite:235][cite:242][cite:245]. Поэтому risk register в этом документе полезно строить так, чтобы его можно было почти механически перенести в issues, labels и project fields [cite:235][cite:242].

#### Модель risk register для этого репозитория

Для `swissknifeman` разумно использовать поля:

- `Risk ID`
- `Title`
- `Category`
- `Likelihood`
- `Impact`
- `Priority`
- `Affected areas`
- `Detection method`
- `Mitigation`
- `Contingency / issue response`
- `Owner type`
- `Status`

Такая структура согласуется с типичными risk register подходами, где риск описывается через вероятность, влияние, ответственного и план обработки [cite:237][cite:238].

#### Severity scale

Чтобы документ оставался практически полезным, ниже используется простая шкала:

- **Likelihood:** Low / Medium / High.
- **Impact:** Medium / High / Critical.
- **Priority:** P0 / P1 / P2 / P3.
- **Status:** Open / Monitoring / Mitigating / Planned / Resolved.

#### Главный принцип

Не каждый риск должен сразу становиться issue, но каждый P0/P1 риск должен иметь:

- способ обнаружения;
- owner type;
- mitigation path;
- понятную связь с ADR и PR roadmap [cite:17][cite:18].

Иначе проект знает о проблеме, но не управляет ей.

#### Сводный реестр рисков

| Risk ID | Title | Category | Likelihood | Impact | Priority | Affected areas | Detection method | Mitigation | Contingency / response | Owner type | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R-01 | Provider truth ambiguity | Architecture | High [cite:18] | Critical [cite:18] | P0 | `provider_*`, config, manifest, lock, artifacts | Invariant tests; design review [cite:18] | ADR-0001 + provider state model + invariant suite [cite:18] | Freeze risky refactors until truth model explicit | Architect / core maintainer | Open |
| R-02 | Split policy semantics | Security / Policy | High [cite:17][cite:18] | Critical [cite:17] | P0 | ownership logic, hooks, locks, configs, writes | Policy tests; doc/code review [cite:17] | ADR-0002 + central policy resolver [cite:17][cite:18] | Block sensitive mutations behind preflight checks [cite:17] | Security-minded maintainer | Open |
| R-03 | Silent telemetry degradation | Observability | High [cite:17] | High [cite:17] | P0 | run-report, usage, reports, operator decisions | Replay suite; quality flags audit [cite:17] | ADR-0004 + completeness/confidence model [cite:17] | Treat degraded reports as operational warnings | Telemetry owner | Open |
| R-04 | Hook gravity | Architecture / Runtime | High [cite:17] | High [cite:17] | P1 | hook libs, report pipeline, event parsing | Complexity review; replay regression failures [cite:17] | ADR-0003 + hook pipeline split [cite:17] | Limit new logic in hooks until boundaries defined | Hook maintainer | Open |
| R-05 | `_usage.py` vendor drift | Observability / Maintainability | Medium [cite:17] | High [cite:17] | P1 | core usage, hook runtime copy | Integrity checks; sync validation [cite:17] | PR-09 usage sync hardening [cite:17] | Manual resync and compare outputs | Core maintainer | Open |
| R-06 | Agent intent drift across surfaces | Architecture / DX | High [cite:18] | High [cite:18] | P1 | `.agents`, `.claude`, `.codex`, `.claude-plugin` | Cross-surface diff checks [cite:18] | ADR-0005 + drift checker [cite:18] | Freeze adapter proliferation until core map exists | Agent-platform maintainer | Open |
| R-07 | Weak CLI explainability | UX / Operations | Medium [cite:18] | High [cite:18] | P1 | CLI, diagnostics, support burden | Manual operator walkthroughs; contract tests [cite:18] | ADR-0006 + diagnostics baseline [cite:18] | Add operator runbook and recovery hints [cite:18] | CLI maintainer | Open |
| R-08 | Knowledge trapped in implementation | Documentation / Governance | High [cite:17][cite:18] | High [cite:18] | P1 | docs, onboarding, architecture memory | Docs audit; onboarding friction review [cite:18] | Architecture docs spine + ADR pack [cite:18][cite:218] | Require docs updates in key PRs | Tech lead / maintainer | Open |
| R-09 | Missing semantic regression safety net | Quality | High [cite:17][cite:18] | Critical [cite:17][cite:18] | P0 | providers, hooks, CLI outputs, policies | CI gates missing; regression escapes [cite:17][cite:176] | ADR-0007 + invariant/replay/golden suites [cite:17][cite:176] | Pause deeper refactors until safety net exists | QA-minded maintainer | Open |
| R-10 | Coordination-heavy core | Maintainability | High [cite:18] | High [cite:18] | P1 | `core/`, orchestration layer | Module dependency review [cite:18] | Boundary refactor after contracts/tests [cite:18] | Contain new logic to explicit submodules | Core maintainer | Monitoring |
| R-11 | Unsafe writes before policy enforcement | Security | Medium [cite:17] | Critical [cite:17] | P0 | managed/protected paths, mutation flows | Mutation scenario tests; incident review [cite:17] | Preflight checks + policy resolver [cite:17] | Restrict high-risk write paths immediately | Security-minded maintainer | Open |
| R-12 | Input schema drift in hook transcripts | Runtime compatibility | Medium [cite:17] | High [cite:17] | P1 | transcript parser, reports | Replay fixtures; unknown event counters [cite:17] | Normalized schema layer + quality flags [cite:17] | Tolerate but loudly mark partial parsing [cite:17] | Hook/telemetry owner | Open |
| R-13 | Drift between docs and actual runtime | Documentation / Operations | Medium [cite:18] | Medium [cite:18] | P2 | README, docs, examples, commands | Docs review; operator confusion [cite:18] | Docs spine + doc ownership + PR checklist [cite:18] | Mark stale docs and constrain entrypoints | Maintainer | Monitoring |
| R-14 | Overly large refactor PRs | Delivery risk | Medium [cite:17][cite:18] | High [cite:17][cite:18] | P1 | all structural initiatives | PR review discipline; branch policy [cite:203][cite:210] | PR-sized execution plan; one-goal-per-PR [cite:203][cite:210] | Split PRs before merge approval | Tech lead | Open |
| R-15 | Recovery paths remain implicit | Operations | Medium [cite:18] | High [cite:18] | P1 | CLI UX, docs, troubleshooting | Manual dry-run/troubleshooting review [cite:18] | Add doctor/validate/explain/runbooks [cite:18] | Maintain fallback manual recovery guide | CLI/docs owner | Open |

#### Top P0 risks

Из всего реестра наиболее опасны именно следующие риски, потому что они бьют по устойчивости всей системы, а не одной подсистемы [cite:17][cite:18]:

- `R-01 Provider truth ambiguity` [cite:18]
- `R-02 Split policy semantics` [cite:17][cite:18]
- `R-03 Silent telemetry degradation` [cite:17]
- `R-09 Missing semantic regression safety net` [cite:17][cite:18]
- `R-11 Unsafe writes before policy enforcement` [cite:17]

Именно они должны первыми превращаться в tracked GitHub issues и required project milestones [cite:235][cite:242].

#### Как переводить это в GitHub Issues

GitHub Issues и Projects позволяют связывать tasks, priorities, custom fields и roadmaps в одном workflow [cite:235][cite:242]. Для `swissknifeman` это можно разложить так:

- Один `risk issue` на каждый P0/P1 риск [cite:235].
- Labels: `risk`, `architecture`, `security`, `telemetry`, `cli`, `docs`, `quality`, `p0`, `p1`, `p2` [cite:245].
- Custom fields в Project: `Likelihood`, `Impact`, `Owner type`, `ADR link`, `Target PR wave` [cite:242].
- Milestones: `Wave A Contracts`, `Wave B Safety Net`, `Wave C Explainability`, `Wave D Decomposition` [cite:242][cite:245].

Так risk register перестаёт быть пассивной таблицей и становится входом в операционное управление архитектурным долгом [cite:235][cite:242].

#### Формат issue для риска

Каждый риск-issue стоит создавать по общей структуре:

- Summary.
- Why this matters.
- Current evidence.
- Detection signals.
- Mitigation plan.
- Related ADR.
- Related PR wave.
- Exit criteria.

Это создаёт bridge между аудитом, ADR и implementation plan, а не разрывает их на отдельные артефакты [cite:17][cite:18].

#### Когда риск становится issue-инцидентом

Хорошая практика risk management — различать риск и уже произошедшую проблему: когда риск материализуется, он должен получить issue/incident response, но связь с исходным риском нужно сохранять [cite:238]. Для `swissknifeman` это особенно важно в случаях silent telemetry regressions, unsafe writes, lock/policy conflicts и broken drift checks [cite:17][cite:18].

Пример:

- Risk: `Silent telemetry degradation`.
- Materialized issue: “после изменения parser-а отчёт перестал учитывать часть retrieval events”.
- Action: заводится отдельный bug issue, но он ссылается на `R-03` как на реализовавшийся риск [cite:238].

#### Owner model

Пока проект, вероятно, сильно зависит от одного основного автора, полезно назначать не конкретных людей, а `owner type` [cite:18]. Это практично, потому что позволяет управлять рисками даже до появления формальной команды.

Рекомендуемые owner types:

- `Core maintainer`
- `Hook/telemetry owner`
- `CLI/docs owner`
- `Security-minded maintainer`
- `Agent-platform maintainer`
- `Tech lead / architect`

Это снижает персональную привязку и одновременно подсказывает, какой тип компетенции нужен для закрытия риска [cite:18].

#### Ритм пересмотра risk register

Для ongoing-проекта risk register полезно пересматривать регулярно; типовые рекомендации по управлению рисками предполагают периодический review и обновление статусов, вероятностей, приоритетов и планов mitigation [cite:238]. Для `swissknifeman` логичен такой ритм:

- перед стартом каждой PR-волны;
- после каждого архитектурно значимого merge;
- после любого security-sensitive или telemetry-sensitive инцидента;
- при пересмотре roadmap или ADR [cite:17][cite:18].

#### Критерий зрелости

Реестр рисков будет полезен только если его использовать не как архив тревог, а как механизм принятия решений. Хороший признак зрелости здесь такой: любой крупный change proposal в `swissknifeman` можно быстро сопоставить с риском, ADR, PR-wave и quality gates [cite:17][cite:18].

Тогда архитектурный аудит перестаёт быть разовой экспертизой и становится частью постоянного цикла управления развитием репозитория [cite:17][cite:18].


### 15. GitHub issue pack

#### Итерация 15 — превращение аудита в готовый набор issue-заготовок

Следующий практический уровень после risk register — подготовить issue pack, то есть набор почти готовых GitHub issues, которые можно создавать без дополнительной аналитической работы. GitHub Issues и Projects поддерживают labels, sub-issues, custom fields и визуализацию в таблицах, boards и roadmaps, что делает их естественной операционной средой для переноса архитектурного аудита в рабочий план [cite:235][cite:242][cite:259]. Репозиторий также может использовать issue templates и forms, чтобы стандартизировать состав информации, а organization-level issue fields позволяют хранить структурированные metadata по приоритету, owner type, ADR и стадии выполнения [cite:248][cite:250].

Для `swissknifeman` это особенно полезно, потому что большая часть уже найденных проблем требует не одного общего epic, а набора управляемых задач: часть из них — architecture decisions, часть — safety gates, часть — refactoring enablers, часть — operational UX improvements [cite:17][cite:18]. Хороший issue pack сокращает friction между анализом и действием: вместо “решим потом” проект получает конкретные трекаемые work items с ясными exit criteria [cite:235][cite:242].

#### Рекомендуемая label taxonomy

GitHub labels используются для категоризации и фильтрации issues и PR, поэтому для `swissknifeman` полезно заранее определить ограниченный, но выразительный набор меток [cite:261]. Рекомендуемая taxonomy:

- Priority: `p0`, `p1`, `p2`, `p3`.
- Domain: `architecture`, `providers`, `policy`, `security`, `hooks`, `telemetry`, `agents`, `cli`, `docs`, `quality`.
- Type: `risk`, `adr`, `refactor`, `test`, `observability`, `governance`, `ux`.
- Execution wave: `wave-a-contracts`, `wave-b-safety-net`, `wave-c-explainability`, `wave-d-decomposition`, `wave-e-scaling` [cite:242][cite:261].

Лучше не делать label taxonomy слишком широкой, иначе она быстро теряет управляемость [cite:261].

#### Рекомендуемые project fields

GitHub organization issue fields позволяют хранить структурированные custom fields для issues [cite:248]. Для этого проекта особенно полезны:

- `Likelihood` — Low / Medium / High [cite:248].
- `Impact` — Medium / High / Critical [cite:248].
- `Owner type` — Core maintainer / Hook-telemetry owner / CLI-docs owner / Security maintainer / Architect [cite:248].
- `ADR` — text or single-select link marker.
- `PR wave` — Wave A / B / C / D / E [cite:248].
- `Exit criteria ready` — Yes / No.
- `Risk ID` — R-01 etc.

Это позволяет поддерживать issue pack как управляемую систему, а не просто как список задач [cite:235][cite:242][cite:248].

#### Рекомендуемая структура issue

Ниже используется общий каркас issue. Он соответствует сильной практике управления задачами через GitHub Issues: достаточно структуры для исполнения, но без лишней бюрократии [cite:235][cite:250].

Шаблон:

- Title
- Labels
- Project fields
- Related risk
- Related ADR
- Problem
- Why this matters
- Proposed work
- Exit criteria
- Possible sub-issues

#### Готовые issue-заготовки

##### ISSUE-01

**Title:** Define and document provider truth model

**Labels:** `p0`, `architecture`, `providers`, `adr`, `wave-a-contracts`

**Project fields:**
- Risk ID: `R-01`
- Likelihood: `High`
- Impact: `Critical`
- Owner type: `Architect / core maintainer`
- ADR: `ADR-0001`
- PR wave: `Wave A`

**Related risk:** `R-01 Provider truth ambiguity` [cite:18]

**Related ADR:** `ADR-0001 Provider truth model` [cite:18]

**Problem:** provider subsystem currently appears to rely on multiple adjacent representations of state across config, manifest, lock and materialized artifacts, without one fully explicit canonical truth model [cite:18].

**Why this matters:** without a clear state model, provider-related behavior can drift across lifecycle stages, making reconcile logic, validation and future refactors less predictable [cite:18].

**Proposed work:**
- Define the lifecycle states: intent, resolved, plan, materialized [cite:18].
- Clarify which layer is canonical and which layers are derived [cite:18].
- Add a concise architecture doc in `docs/architecture/` or `docs/adr/` [cite:218][cite:220].

**Exit criteria:**
- A canonical document exists.
- Provider-related terminology is consistent.
- Follow-up test work can reference this model.

**Possible sub-issues:** state machine diagram, glossary, provider validation mapping.

##### ISSUE-02

**Title:** Centralize ownership and policy vocabulary

**Labels:** `p0`, `security`, `policy`, `architecture`, `adr`, `wave-a-contracts`

**Project fields:**
- Risk ID: `R-02`
- Likelihood: `High`
- Impact: `Critical`
- Owner type: `Security-minded maintainer`
- ADR: `ADR-0002`
- PR wave: `Wave A`

**Related risk:** `R-02 Split policy semantics` [cite:17][cite:18]

**Related ADR:** `ADR-0002 Ownership and policy vocabulary` [cite:17][cite:18]

**Problem:** semantics such as `managed`, `user_owned`, `protected`, `safe` and `trusted` appear too important to remain distributed across code paths and conventions [cite:17][cite:18].

**Why this matters:** inconsistent classification can lead to unsafe writes, confusing operator behavior and long-term policy drift [cite:17].

**Proposed work:**
- Create a policy glossary.
- Define the canonical resolver semantics.
- Map mutation-sensitive flows to the glossary [cite:17][cite:18].

**Exit criteria:**
- One policy vocabulary exists.
- Sensitive paths can be explained using canonical terms.
- Future policy tests have a stable target.

**Possible sub-issues:** protected path matrix, safe mutation scenarios, ownership decision table.

##### ISSUE-03

**Title:** Introduce invariant test suite for provider and policy semantics

**Labels:** `p0`, `quality`, `test`, `providers`, `policy`, `wave-b-safety-net`

**Project fields:**
- Risk ID: `R-09`
- Likelihood: `High`
- Impact: `Critical`
- Owner type: `QA-minded maintainer`
- ADR: `ADR-0007`
- PR wave: `Wave B`

**Related risk:** `R-09 Missing semantic regression safety net` [cite:17][cite:18][cite:176]

**Related ADR:** `ADR-0007 Testing and quality gates as architecture protection` [cite:17][cite:176]

**Problem:** the project currently has too much semantic risk concentrated in provider/ownership behavior to rely on ad hoc testing [cite:17][cite:18].

**Why this matters:** without invariant checks, regressions can preserve syntax while breaking domain guarantees [cite:17][cite:18].

**Proposed work:**
- Add determinism and idempotency tests [cite:18].
- Cover ownership classification invariants [cite:17].
- Make the suite mandatory in CI [cite:177].

**Exit criteria:**
- Core invariants are executable.
- CI blocks regressions in provider/policy semantics.
- Failures are diagnosable.

**Possible sub-issues:** serialization invariants, reconcile idempotency, ownership matrix fixtures.

##### ISSUE-04

**Title:** Add replay fixtures for hook and telemetry parsing

**Labels:** `p0`, `hooks`, `telemetry`, `quality`, `test`, `wave-b-safety-net`

**Project fields:**
- Risk ID: `R-03`
- Likelihood: `High`
- Impact: `High`
- Owner type: `Hook/telemetry owner`
- ADR: `ADR-0004`, `ADR-0007`
- PR wave: `Wave B`

**Related risk:** `R-03 Silent telemetry degradation` [cite:17]

**Related ADR:** `ADR-0004 Telemetry quality model`; `ADR-0007 Testing and quality gates` [cite:17][cite:176]

**Problem:** hook and report logic depends on schema-tolerant and heuristic parsing, which is vulnerable to silent semantic drift [cite:17].

**Why this matters:** parsing can degrade without obvious crashes, while operator trust in reports remains high [cite:17].

**Proposed work:**
- Collect synthetic and historical transcript fixtures [cite:17].
- Add replay runner and expected normalized outputs [cite:17].
- Compare results using golden baselines [cite:176].

**Exit criteria:**
- Parser changes are regression-tested against fixtures.
- Semantic drift becomes visible in CI.
- Unknown and partial parse cases are measurable.

**Possible sub-issues:** malformed event fixtures, missing usage parser fixtures, oversized transcript fixtures.

##### ISSUE-05

**Title:** Add telemetry completeness and confidence markers

**Labels:** `p0`, `telemetry`, `observability`, `quality`, `wave-b-safety-net`

**Project fields:**
- Risk ID: `R-03`
- Likelihood: `High`
- Impact: `High`
- Owner type: `Hook/telemetry owner`
- ADR: `ADR-0004`
- PR wave: `Wave B`

**Related risk:** `R-03 Silent telemetry degradation` [cite:17]

**Related ADR:** `ADR-0004 Telemetry quality model` [cite:17]

**Problem:** current reporting appears to expose derived information without sufficiently exposing signal quality and completeness [cite:17].

**Why this matters:** consumers may interpret partial or heuristic output as complete truth [cite:17].

**Proposed work:**
- Add `complete/partial/degraded/heuristic` markers [cite:17].
- Surface skipped/invalid counters [cite:17].
- Mark sections with missing dependencies such as usage parsing [cite:17].

**Exit criteria:**
- Every report communicates its own quality.
- Degraded outputs are explicit.
- Downstream users can branch on quality metadata.

**Possible sub-issues:** report schema update, CLI rendering, machine-readable contract update.

##### ISSUE-06

**Title:** Introduce CLI diagnostics baseline: status, validate, doctor, explain

**Labels:** `p1`, `cli`, `ux`, `architecture`, `wave-c-explainability`

**Project fields:**
- Risk ID: `R-07`
- Likelihood: `Medium`
- Impact: `High`
- Owner type: `CLI/docs owner`
- ADR: `ADR-0006`
- PR wave: `Wave C`

**Related risk:** `R-07 Weak CLI explainability` [cite:18]

**Related ADR:** `ADR-0006 CLI explainability contract` [cite:18]

**Problem:** the operational interface likely requires richer diagnostics to match the complexity of the domain [cite:18].

**Why this matters:** without explainability, users must inspect repository internals to understand state and failures [cite:18].

**Proposed work:**
- Define minimal command set for status and validation [cite:18].
- Add recovery hints and dry-run style outputs [cite:18].
- Clarify error classes and operator messages [cite:18].

**Exit criteria:**
- Common failure states have operator-facing explanations.
- Safe inspection paths exist before mutation.
- Diagnostics become part of the supported surface.

**Possible sub-issues:** error taxonomy, dry-run output, doctor command MVP.

##### ISSUE-07

**Title:** Create architecture documentation spine

**Labels:** `p1`, `docs`, `architecture`, `governance`, `wave-c-explainability`

**Project fields:**
- Risk ID: `R-08`
- Likelihood: `High`
- Impact: `High`
- Owner type: `Tech lead / maintainer`
- ADR: `ADR-0001`, `ADR-0002`, `ADR-0003`, `ADR-0004`, `ADR-0005`, `ADR-0006`, `ADR-0007`
- PR wave: `Wave C`

**Related risk:** `R-08 Knowledge trapped in implementation` [cite:17][cite:18]

**Problem:** critical architecture knowledge appears to live more in code structure and implicit conventions than in canonical documentation [cite:17][cite:18].

**Why this matters:** this increases onboarding cost, bus factor and the risk of accidental misuse during refactoring [cite:18].

**Proposed work:**
- Add `docs/architecture/README.md` as entrypoint.
- Link providers, hooks, agents, CLI, telemetry, security domains.
- Reference ADRs from the architecture docs [cite:218][cite:220].

**Exit criteria:**
- There is one coherent reading path into the architecture.
- Major domains are documented as domains, not only as files.
- New contributors can orient themselves without reverse-engineering everything.

**Possible sub-issues:** docs map, glossary page, architecture navigation page.

##### ISSUE-08

**Title:** Split hook pipeline into adapter, normalization, metrics and reporting layers

**Labels:** `p1`, `hooks`, `refactor`, `architecture`, `wave-d-decomposition`

**Project fields:**
- Risk ID: `R-04`
- Likelihood: `High`
- Impact: `High`
- Owner type: `Hook/telemetry owner`
- ADR: `ADR-0003`
- PR wave: `Wave D`

**Related risk:** `R-04 Hook gravity` [cite:17]

**Related ADR:** `ADR-0003 Hook pipeline boundaries` [cite:17]

**Problem:** the current hook reporting layer appears to accumulate parsing, heuristics, aggregation and output responsibilities in one place [cite:17].

**Why this matters:** this increases coupling, weakens change isolation and makes testing more fragile [cite:17].

**Proposed work:**
- Separate raw event ingestion from normalized model [cite:17].
- Separate metrics derivation from final report assembly [cite:17].
- Keep compatibility through replay-backed refactor [cite:17].

**Exit criteria:**
- Hook responsibilities are structurally clearer.
- Replay suite stays green through the refactor.
- New telemetry logic can be added with less blast radius.

**Possible sub-issues:** normalized event types, metrics module extraction, report formatter extraction.

##### ISSUE-09

**Title:** Harden usage synchronization and detect `_usage.py` drift

**Labels:** `p1`, `telemetry`, `quality`, `refactor`, `wave-d-decomposition`

**Project fields:**
- Risk ID: `R-05`
- Likelihood: `Medium`
- Impact: `High`
- Owner type: `Core maintainer`
- ADR: `ADR-0004`
- PR wave: `Wave D`

**Related risk:** `R-05 _usage.py vendor drift` [cite:17]

**Problem:** copying or vendoring usage logic introduces maintenance and integrity risk if sync rules are implicit [cite:17].

**Why this matters:** usage metrics are central to report trustworthiness, so drift here can invalidate downstream analysis [cite:17].

**Proposed work:**
- Define canonical source for usage logic [cite:17].
- Add integrity or diff checks [cite:17].
- Reduce manual sync dependence.

**Exit criteria:**
- Usage drift is automatically detectable.
- Sync expectations are documented.
- Report integrity improves.

**Possible sub-issues:** checksum script, sync command, integrity CI check.

##### ISSUE-10

**Title:** Define canonical agent semantic core and runtime mapping

**Labels:** `p1`, `agents`, `architecture`, `adr`, `wave-d-decomposition`

**Project fields:**
- Risk ID: `R-06`
- Likelihood: `High`
- Impact: `High`
- Owner type: `Agent-platform maintainer`
- ADR: `ADR-0005`
- PR wave: `Wave D`

**Related risk:** `R-06 Agent intent drift across surfaces` [cite:18]

**Related ADR:** `ADR-0005 Agent semantic core and runtime adapters` [cite:18]

**Problem:** several runtime-specific agent surfaces appear to coexist without a clearly documented semantic source of truth [cite:18].

**Why this matters:** intent drift becomes likely, especially as the repository evolves across vendors and runtimes [cite:18].

**Proposed work:**
- Define the semantic fields that make an agent canonical [cite:18].
- Map each runtime surface to that core [cite:18].
- Mark which layers are generated, adapted or manually maintained [cite:18].

**Exit criteria:**
- One semantic core exists.
- Runtime mappings are explicit.
- Drift is measurable instead of anecdotal.

**Possible sub-issues:** field matrix, canonical schema, adapter mapping notes.

##### ISSUE-11

**Title:** Add cross-surface drift checks for `.agents`, `.claude`, `.codex` and plugin variants

**Labels:** `p1`, `agents`, `quality`, `test`, `wave-e-scaling`

**Project fields:**
- Risk ID: `R-06`
- Likelihood: `High`
- Impact: `High`
- Owner type: `Agent-platform maintainer`
- ADR: `ADR-0005`
- PR wave: `Wave E`

**Related risk:** `R-06 Agent intent drift across surfaces` [cite:18]

**Problem:** even with a semantic core, surface variants can still drift unless consistency is checked continuously [cite:18].

**Why this matters:** manual comparison does not scale and drift can remain invisible until behavior diverges [cite:18].

**Proposed work:**
- Add a consistency checker.
- Surface structured diffs in CI or local diagnostics [cite:18].
- Decide which differences are allowed and which are violations [cite:18].

**Exit criteria:**
- Drift checks are executable.
- Known acceptable differences are codified.
- Surface divergence becomes observable.

**Possible sub-issues:** diff rule set, baseline fixtures, CI reporting.

##### ISSUE-12

**Title:** Introduce PR template and project workflow for architecture-sensitive changes

**Labels:** `p1`, `governance`, `docs`, `quality`, `wave-a-contracts`

**Project fields:**
- Risk ID: `R-14`
- Likelihood: `Medium`
- Impact: `High`
- Owner type: `Tech lead`
- ADR: `ADR-0007`
- PR wave: `Wave A`

**Related risk:** `R-14 Overly large refactor PRs` [cite:203][cite:210]

**Problem:** architecture-sensitive changes are too risky to merge without a standard review structure [cite:203][cite:210].

**Why this matters:** small diffs can still hide large semantic changes in policy, CLI contracts or telemetry behavior [cite:17][cite:18].

**Proposed work:**
- Add PR template.
- Require mention of affected risks, ADRs and machine-readable contracts [cite:210].
- Encourage one-goal-per-PR discipline [cite:203][cite:210].

**Exit criteria:**
- Architecture-sensitive PRs follow one review structure.
- Reviewers can see semantic risk quickly.
- The repository gains process memory, not just code history.

**Possible sub-issues:** template file, checklist wording, contribution guide update.

#### Epic map

GitHub supports sub-issues, so часть этих задач удобно связать как epic -> sub-issues hierarchy [cite:259]. Рекомендуемый верхний уровень:

- **Epic A — Contracts and governance**: ISSUE-01, ISSUE-02, ISSUE-12 [cite:259].
- **Epic B — Safety net and telemetry trust**: ISSUE-03, ISSUE-04, ISSUE-05 [cite:259].
- **Epic C — Explainability and knowledge architecture**: ISSUE-06, ISSUE-07 [cite:259].
- **Epic D — Structural decomposition**: ISSUE-08, ISSUE-09, ISSUE-10 [cite:259].
- **Epic E — Scaling checks**: ISSUE-11 [cite:259].

#### Ограничения GitHub workflow, которые стоит учитывать

Issue templates и issue forms помогают стандартизировать ввод, но custom project fields не всегда автоматически заполняются напрямую из issue form, поэтому часть структуры всё равно придётся поддерживать через process discipline или automation [cite:250][cite:257][cite:260]. Это не блокер, но важно не переоценить уровень автоматизации на старте [cite:248][cite:250].

#### Критерий готовности

Issue pack можно считать зрелым, когда по каждому P0/P1 риску уже существует минимум один готовый issue draft с labels, ADR-link, mitigation scope и exit criteria [cite:17][cite:18][cite:235]. В таком состоянии аудит уже полностью переводится в execution system: risk -> ADR -> issue -> PR -> merge -> review [cite:17][cite:18][cite:242].


### 16. Execution checklist и 30-60-90 day launch order

#### Итерация 16 — финализация в operational sequence

После issue pack самый полезный следующий шаг — собрать всё в execution checklist: что запускать сначала, что можно делать параллельно, какие результаты нужны через 30, 60 и 90 дней. Формат 30-60-90 обычно используется как трёхфазная дорожная карта, где первые 30 дней посвящены пониманию и фиксации основы, следующие 30 — планированию и первым улучшениям, а финальные 30 — внедрению и оценке результата [cite:262][cite:269][cite:273][cite:275]. В инженерном и project-tracking контексте это особенно хорошо сочетается с milestones, labels, sub-issues и roadmap views в GitHub Projects [cite:242][cite:259][cite:264][cite:274].

Для `swissknifeman` такой формат хорош тем, что он дисциплинирует порядок действий. Этот репозиторий нельзя безопасно улучшать хаотично: сначала нужно закрепить contracts и risk boundaries, затем — safety net, затем — explainability и only after that structural decomposition [cite:17][cite:18]. Иначе каждая попытка “сделать чище” рискует увеличить количество скрытых регрессий вместо уменьшения сложности [cite:17][cite:18].

#### Главный принцип очередности

Улучшения нужно запускать не по принципу “что проще закодить”, а по принципу “что сильнее снижает архитектурную неопределённость”. Поэтому в execution order действуют четыре строгих правила [cite:17][cite:18]:

- Сначала **закрепить смысл**, потом менять код.
- Сначала **закрыть риски silent regressions**, потом рефакторить.
- Сначала **сделать систему объяснимой**, потом масштабировать её.
- Все глубокие structural changes должны опираться на ADR, tests и diagnostics [cite:17][cite:18].

#### Launch checklist — до старта первой волны

Перед тем как открывать первые PR, полезно убедиться, что operational foundation готова [cite:235][cite:242][cite:264].

- Создан GitHub Project для аудита и remediation work [cite:242].
- Созданы milestones по волнам: `Wave A`, `Wave B`, `Wave C`, `Wave D`, `Wave E` [cite:264][cite:268].
- Созданы labels из issue pack taxonomy [cite:261].
- Подготовлен PR template для architecture-sensitive изменений [cite:210].
- Подготовлен базовый docs-entrypoint для архитектуры.
- Определено, какие риски являются blocking для merges в ближайшей фазе.
- Есть agreement, что большие refactor PR запрещены до прохождения Wave A/B [cite:17][cite:18].

#### Первые 30 дней — Contracts and control

Первые 30 дней должны быть сфокусированы не на глубоком переписывании, а на стабилизации архитектурного словаря и карты рисков. В логике 30-60-90 планов первый этап обычно направлен на наблюдение, понимание системы и фиксацию базовых ожиданий [cite:269][cite:273][cite:275]. Для `swissknifeman` это означает:

##### Цели 0-30 дней

- Закрепить provider truth model [cite:18].
- Закрепить ownership/policy vocabulary [cite:17][cite:18].
- Ввести базовую governance-дисциплину для PR и issues [cite:203][cite:210].
- Поднять architecture docs spine [cite:18][cite:218].

##### Обязательные результаты 0-30 дней

- Приняты или как минимум подготовлены `ADR-0001` и `ADR-0002` [cite:17][cite:18].
- Открыты P0/P1 issues по issue pack [cite:235][cite:242].
- Есть начальный `docs/architecture/` и `docs/adr/` каркас [cite:220][cite:232].
- Репозиторий использует PR template и review-checklist для risky changes [cite:210].
- Все новые структурные идеи привязаны к risk register, а не обсуждаются в отрыве [cite:17][cite:18].

##### Что нельзя делать в первые 30 дней

- Нельзя запускать большой refactor hooks или `core/` без зафиксированных ADR [cite:17][cite:18].
- Нельзя менять policy-sensitive semantics “по месту”, без vocabulary consolidation [cite:17].
- Нельзя расширять agent surface, если semantic core ещё не описан [cite:18].

#### Дни 31-60 — Safety net and trust

Второй блок 30-60-90 планов обычно посвящён quick wins, внедрению базовых улучшений и выстраиванию измеримых целей [cite:269][cite:273][cite:275]. Для `swissknifeman` это значит: главная задача второй волны — сделать систему менее хрупкой через test gates и quality visibility [cite:17][cite:18].

##### Цели 31-60 дней

- Ввести invariant suite для providers/policy [cite:17][cite:18].
- Ввести replay fixtures для hooks/telemetry [cite:17].
- Добавить telemetry quality/completeness flags [cite:17].
- Начать измерять unknown/degraded/partial parsing cases [cite:17].

##### Обязательные результаты 31-60 дней

- В CI есть как минимум минимальный invariant gate [cite:177].
- В CI есть replay suite для hook parser/regression checking [cite:17].
- Отчёты явно показывают degraded/heuristic sections [cite:17].
- Любые изменения telemetry-поведения можно сравнить с baseline outputs [cite:176].

##### Quick wins 31-60 дней

- Вынести counters для skipped/unknown events [cite:17].
- Добавить dry-run/validate там, где это можно сделать без глубокого рефакторинга [cite:18].
- Ввести integrity check для `_usage.py` либо хотя бы детектор drift [cite:17].

#### Дни 61-90 — Explainability and decomposition start

Финальный этап 30-60-90 обычно предназначен для выполнения плана и оценки того, какие изменения действительно работают [cite:269][cite:273][cite:275]. Для `swissknifeman` на этом этапе уже можно позволить первые серьёзные структурные изменения — но только потому, что контракты и safety net к этому моменту должны быть созданы [cite:17][cite:18].

##### Цели 61-90 дней

- Усилить CLI diagnostics surface [cite:18].
- Формализовать agent semantic core [cite:18].
- Начать hook decomposition по слоям [cite:17].
- Подготовить boundary refactor plan для `core/` [cite:18].

##### Обязательные результаты 61-90 дней

- Есть минимальный набор `status / validate / doctor / explain` сценариев [cite:18].
- Есть документированная agent semantic core map [cite:18].
- Hook pipeline decomposition начата, но защищена replay suite [cite:17].
- Следующая фаза масштабирования уже опирается на quality gates, а не на intuition [cite:17][cite:18].

##### Что считать успехом к 90 дню

- Проект имеет явный vocabulary and truth model [cite:17][cite:18].
- Основные silent regressions уже ловятся автоматикой [cite:17][cite:176].
- Оператор видит качество telemetry, а не только её содержимое [cite:17].
- Структурные изменения выполняются по плану, а не через ad hoc cleanup [cite:17][cite:18].

#### 90-дневная карта по неделям

| Период | Фокус | Ключевой результат |
|---|---|---|
| Week 1 | Project bootstrap | Issues, labels, milestones, PR template, docs skeleton [cite:242][cite:261] |
| Week 2 | Provider contracts | Draft/provider truth model ADR [cite:18] |
| Week 3 | Policy contracts | Ownership/policy vocabulary baseline [cite:17][cite:18] |
| Week 4 | Governance close | Risk-to-issue-to-ADR linkage working [cite:17][cite:18] |
| Week 5 | Invariants | Initial provider/policy invariant suite [cite:17][cite:18] |
| Week 6 | Replay fixtures | Hook parser replay baseline [cite:17] |
| Week 7 | Telemetry trust | Quality markers and degraded mode visibility [cite:17] |
| Week 8 | Safety-net review | CI gates produce meaningful signals [cite:176][cite:177] |
| Week 9 | CLI diagnostics | Minimal status/validate/explain progress [cite:18] |
| Week 10 | Agent semantic core | Canonical agent mapping draft [cite:18] |
| Week 11 | Hook decomposition start | Safe extraction plan or first split landed [cite:17] |
| Week 12 | 90-day review | Reassess risks, roadmap, next-wave structural work [cite:238][cite:242] |

#### Parallelization map

Часть работы действительно можно вести параллельно, но только в разрешённых комбинациях.

##### Можно параллельно

- ADR-0001 и ADR-0002 [cite:17][cite:18].
- Issue bootstrap и docs skeleton [cite:235][cite:242].
- Invariant suite и replay fixture preparation после фиксации contracts [cite:17][cite:18].
- CLI diagnostics baseline и docs clarification [cite:18].

##### Нежелательно параллельно

- Hook decomposition и `core/` boundary refactor одновременно [cite:17][cite:18].
- Agent semantic core redesign одновременно с расширением новых runtime surfaces [cite:18].
- Policy refactor и risky write-path changes без preflight checks [cite:17].

#### Merge gates по фазам

GitHub Projects best practices рекомендуют связывать larger goals с milestones и smaller units с issues/labels [cite:264]. Для `swissknifeman` это лучше всего выразить через фазовые merge gates:

##### Gate A

До завершения Wave A запрещены:
- большие refactor PR;
- policy-changing merges без ADR reference;
- изменения, которые затрагивают provider semantics без vocabulary alignment [cite:17][cite:18].

##### Gate B

До завершения Wave B запрещены:
- глубокие hook rewrites без replay suite;
- изменения telemetry logic без quality markers;
- изменения provider reconciliation без invariant tests [cite:17][cite:176].

##### Gate C

До завершения Wave C нежелательны:
- CLI surface expansions без diagnostics contract;
- docs-heavy claims о supported behavior без canonical docs;
- новые operator workflows без explainability surface [cite:18].

#### Review checklist для каждой волны

Каждая волна должна заканчиваться не только merge-ами, но и review checkpoint.

##### После 30 дней проверить

- Есть ли уже чёткая canonical vocabulary? [cite:17][cite:18]
- Зафиксированы ли главные ADR? [cite:218][cite:219]
- Привязаны ли P0/P1 risks к issues и owner types? [cite:235][cite:242]

##### После 60 дней проверить

- Ловит ли CI semantic regressions? [cite:17][cite:176]
- Видно ли degraded telemetry? [cite:17]
- Можно ли безопасно делать первые decomposition changes? [cite:17][cite:18]

##### После 90 дней проверить

- Стала ли система объяснимее для внешнего мейнтейнера? [cite:18]
- Уменьшился ли риск policy/telemetry drift? [cite:17][cite:18]
- Достаточно ли foundation для Wave D/E? [cite:17][cite:18]

#### Минимальный стартовый список задач

Если нужен совсем практический short-list, то первые задачи должны быть такими:

1. Создать `docs/adr/` и `docs/architecture/` skeleton [cite:220][cite:232].
2. Открыть issues для `R-01`, `R-02`, `R-03`, `R-09`, `R-11` [cite:17][cite:18].
3. Добавить PR template и labels/milestones [cite:210][cite:261][cite:264].
4. Написать `ADR-0001` и `ADR-0002` в draft [cite:18].
5. Подготовить invariant suite plan и replay fixture plan [cite:17][cite:18].
6. Только после этого — трогать hooks или core structurally [cite:17][cite:18].

#### Критерий готовности к следующему этапу

Следующая фаза проекта считается подготовленной не тогда, когда “сделано много PR”, а тогда, когда архитектурный риск реально уменьшился. Для `swissknifeman` это означает очень конкретные признаки: contracts зафиксированы, риски видимы, CI умеет ловить semantic regressions, telemetry сама сообщает качество своих выводов, а структурные изменения привязаны к ADR и issue system [cite:17][cite:18].

Только после этого можно считать, что проект вышел из режима интуитивного сопровождения и вошёл в режим управляемой архитектурной эволюции [cite:17][cite:18].


### 17. Executive summary и финальная оценка

#### Итерация 17 — итоговый управленческий слой

Этот аудит охватывал репозиторий `swissknifeman` как AI-agent orchestration system с providers, hooks, telemetry, multi-surface agent definitions, policy-bearing file operations и CLI-ориентированным operational surface [cite:17][cite:18]. По своей сути проект уже вышел далеко за рамки набора скриптов: это насыщенная архитектурой developer platform для управления локальными агентными workflow, и именно поэтому его главные риски лежат не в синтаксических дефектах, а в domain ambiguity, policy drift, heuristic fragility и недостатке формализованных contracts [cite:17][cite:18].

Хорошая новость состоит в том, что у проекта есть сильный фундамент. Плохая — в том, что дальнейший рост без stabilizing layer будет увеличивать стоимость сопровождения быстрее, чем ценность новых возможностей [cite:17][cite:18]. Иными словами: `swissknifeman` выглядит как сильный и перспективный инженерный инструмент, но сейчас он находится в точке, где ему уже нужна архитектурная дисциплина уровня платформы, а не уровня personal toolbox [cite:17][cite:18].

#### Что было проверено в документе

Перед финализацией был отдельно перепроверен сам Markdown-документ на целостность критичных поздних секций. В нём сохранены и не потеряны разделы по testing/quality gates, master roadmap, PR-plan, ADR pack, risk register, GitHub issue pack и execution checklist [cite:17][cite:18].

Текущая версия документа поэтому уже представляет собой не просто audit narrative, а полный remediation dossier: анализ, приоритизация, архитектурные решения, реестр рисков, план PR-исполнения, issue-level operationalization и 90-дневный порядок запуска [cite:17][cite:18][cite:235][cite:242].

#### Общая оценка репозитория

С архитектурной точки зрения `swissknifeman` производит впечатление репозитория с высоким уровнем инженерной амбиции и высокой концентрацией доменной логики [cite:17][cite:18]. Особенно сильными выглядят: стремление к unified orchestration around agent workflows, наличие provider-driven мышления, наличие hook/reporting surfaces и попытка строить operational tooling вокруг реальной практики использования AI coding agents [cite:17][cite:18].

Но ровно эти же достоинства создают и главный класс рисков. Когда orchestration-проект растёт вокруг providers, lock/config semantics, hooks, telemetry и multi-runtime delivery, система очень быстро становится чувствительной к implicit assumptions [cite:17][cite:18]. Если эти assumptions не закрепить как explicit contracts, проект начинает зависеть от памяти автора и от локального знания о том, “как оно на самом деле устроено” [cite:17][cite:18].

#### Сильные стороны

- Проект уже обладает **реальной архитектурной глубиной**, а не просто утилитарным CLI-слоем [cite:17][cite:18].
- В репозитории явно присутствует попытка выстроить доменные модели вокруг providers, agents, hooks и reports, а это хорошая база для platformization [cite:17][cite:18].
- Наличие telemetry/reporting surfaces даёт основу для explainability и observability, даже если эта основа пока нуждается в quality model [cite:17].
- Проект подходит для превращения в устойчивую orchestration-platform, потому что у него уже есть свои repeatable concepts, а не только ad hoc automation [cite:18].

#### Главные системные проблемы

- **Distributed truth** между config, manifest, lock, artifacts и runtime layers [cite:18].
- **Split policy semantics** для ownership/protected/safe/trusted concepts [cite:17][cite:18].
- **Heuristic drift** внутри hook/telemetry parsing и aggregation [cite:17].
- **Cross-surface drift** между `.agents`, `.claude`, `.claude-plugin`, `.codex` [cite:18].
- **Knowledge trapped in implementation**, из-за чего сопровождение опирается на реконструкцию, а не на canonical docs [cite:17][cite:18].
- **Insufficient semantic regression protection**, из-за чего самые дорогие ошибки могут долго оставаться невидимыми [cite:17][cite:176].

Эти проблемы не означают, что проект “плохой”. Они означают, что он уже перерос свой прежний режим развития [cite:17][cite:18].

#### Top-5 критических действий

Если свести весь аудит к пяти самым важным действиям, приоритет должен быть таким [cite:17][cite:18]:

1. Зафиксировать provider truth model как canonical architecture contract [cite:18].
2. Централизовать ownership/policy vocabulary и mutation rules [cite:17][cite:18].
3. Ввести invariant tests, hook replay suite и golden/quality gates [cite:17][cite:176][cite:177].
4. Сделать telemetry/report outputs quality-aware, а degraded modes — явными [cite:17].
5. Превратить agent/runtime surface в модель с canonical semantic core и drift checks [cite:18].

Почти всё остальное либо зависит от этих шагов, либо становится намного безопаснее после их выполнения [cite:17][cite:18].

#### Что не стоит делать сейчас

Наиболее опасный следующий шаг для `swissknifeman` — это большой “красивый” рефакторинг без фиксации инвариантов и vocabulary [cite:17][cite:18]. Такой рефакторинг почти наверняка даст локально более чистый код, но одновременно повысит риск сломать доменную правду, policy semantics или telemetry interpretation так, что это проявится только позже [cite:17][cite:18].

Также не стоит преждевременно масштабировать поддержку новых agent surfaces, добавлять новые orchestration patterns или расширять automation вокруг hooks до тех пор, пока не укреплён слой contracts и quality gates [cite:17][cite:18]. Иначе проект будет масштабировать не зрелую архитектуру, а текущую неоднозначность [cite:17][cite:18].

#### Финальный стратегический вердикт

`swissknifeman` выглядит как **перспективная и инженерно сильная** orchestration-система, но в текущем состоянии её стоит считать platform-in-transition, а не fully hardened platform [cite:17][cite:18]. Репозиторий уже достаточно мощный, чтобы приносить высокую ценность, но ещё недостаточно формализован, чтобы безопасно и быстро масштабироваться без растущего архитектурного долга [cite:17][cite:18].

Итоговая рекомендация поэтому однозначна: ближайшая стратегия должна быть **stabilization before expansion** [cite:17][cite:18]. Сначала contracts, policy vocabulary, regression safety net, telemetry quality model и explainability; затем decomposition; и только потом расширение платформенных возможностей [cite:17][cite:18].

#### Readiness verdict

Если формулировать кратко, readiness verdict такой:

- Для **дальнейшего быстрого масштабирования** проект пока не готов без дополнительных stabilizing steps [cite:17][cite:18].
- Для **целенаправленной стабилизации и взросления** проект очень хорошо подготовлен, потому что у него уже есть достаточно сильная доменная основа, чтобы инвестиции в архитектурную дисциплину окупились [cite:17][cite:18].
- Для **следующей фазы развития** лучшая тактика уже определена в документе: Wave A -> Wave B -> Wave C -> Wave D/E, без перепрыгивания через contracts and safety gates [cite:17][cite:18].

Именно в этом и заключается главный вывод всего аудита: `swissknifeman` не нужно изобретать заново. Ему нужно зафиксировать собственную архитектурную правду, защитить её автоматикой и только после этого наращивать масштаб [cite:17][cite:18].

### 18. Completeness check

#### Итерация 18 — контроль полноты документа

Для контроля полноты итоговый документ должен содержать следующие слои, и в текущей версии они присутствуют [cite:17][cite:18]:

- архитектурный аудит по доменам;
- безопасность и policy semantics;
- hooks и telemetry;
- testing и quality gates;
- master roadmap и приоритизация;
- PR-sized implementation plan;
- ADR pack;
- risk register;
- GitHub issue pack;
- execution checklist и 30-60-90 launch order;
- executive summary и final verdict.

Дополнительная проверка показала, что все ожидаемые критичные поздние секции присутствуют, а значит в ходе последних итераций документ не потерял ключевые блоки структуры. [cite:17][cite:18]
