# Карта кодовой базы для разработчика и агента

Начните с [правил](../../AGENTS.md), модуля-владельца, его схем и тестов.
При параллельной работе используйте отдельный worktree и сохраняйте чужие изменения.

При наличии `.codegraph/` запросите нужный символ/файл через `codegraph_explore`
с `projectPath` своего worktree или `codegraph explore "имя символа"` из его корня.
Затем читайте только недостающие срезы. Без CodeGraph назначение пакета, его входные файлы и тесты,
которые его импортируют, даёт сгенерированный [индекс исходников](../reference/source-index.md);
на уровень ниже — `uv run --frozen python tools/source_index.py --files <путь>` (строка docstring
на каждый файл), `--outline <файл>` (публичные сигнатуры и реэкспорты: фасад `public.py` в паре
десятков строк вместо сотен) и `--tests <путь>` (все импортирующие тесты). См. [слои и модули](layers-and-modules.md) и [каталог контрактов](contracts.md).

## Модули и прямые зависимости

У каждого `src/skm/modules/<module>/` одинаковые входы:

| Путь внутри модуля | Назначение |
|---|---|
| `public.py` | Фасад для других модулей и реэкспорт DTO/ID; одна UoW вызывающей команды |
| `ports.py` | Protocol: репозитории и типизированные gateways; реализация через DI |
| `module.py` | `MODULE`: прямые `depends_on`, порты, события, реализованные handlers |
| `domain/` | Чистые сущности и правила; без IO, часов, окружения |
| `application/` | Команды/запросы/подписчики и `registry.py`; работа в UoW |
| `host/` | Операции хоста, если нужны модулю; control plane через `ctx.client` |
| `generated/` | DTO из схем; обновляются только генератором |

Таблица отражает **фактический `MODULE.depends_on`**, проверяемый архитектурными тестами.
Вторая колонка — JSON-массив, пригодный для машинного чтения; её сверяет
[тест карты](../../tests/unit/tools/test_codebase_map.py).

| Модуль | depends_on (JSON) | Ответственность |
|---|---|---|
| [access](../../src/skm/modules/access/) | `[]` | Субъекты, токены, членство и авторизация |
| [settings](../../src/skm/modules/settings/) | `[]` | Администрирование конфигурации |
| [workspace](../../src/skm/modules/workspace/) | `["access"]` | Проекты, репозитории, checkout, хосты и workers |
| [artifacts](../../src/skm/modules/artifacts/) | `["access", "workspace"]` | Blobs, файлы, immutable версии и grants |
| [policy](../../src/skm/modules/policy/) | `["access", "workspace"]` | Полномочия, tool intents и approvals |
| [extensions](../../src/skm/modules/extensions/) | `["access", "workspace", "policy"]` | Пакеты, ресурсы, quarantine и trust |
| [runtimes](../../src/skm/modules/runtimes/) | `["access", "workspace", "extensions"]` | Каталог runtime, capabilities и admission |
| [planning](../../src/skm/modules/planning/) | `["access", "workspace", "artifacts", "extensions", "runtimes"]` | Планы, drafts и immutable revisions |
| [context](../../src/skm/modules/context/) | `["access", "workspace", "planning", "extensions", "artifacts"]` | Сборка контекста и research |
| [execution](../../src/skm/modules/execution/) | `["access", "workspace", "artifacts", "extensions", "policy", "runtimes", "planning", "context"]` | Runs, stages, leases, checks и acceptance |
| [integrations](../../src/skm/modules/integrations/) | `["workspace", "artifacts", "extensions", "policy", "runtimes"]` | Проекции в клиенты и hooks |
| [knowledge](../../src/skm/modules/knowledge/) | `["access", "workspace"]` | Optional: память, уроки и граф |
| [learning](../../src/skm/modules/learning/) | `["access", "workspace", "runtimes", "execution", "knowledge"]` | Optional: кандидаты уроков и promotion |
| [exports](../../src/skm/modules/exports/) | `["access", "workspace", "planning", "execution"]` | Optional: представления и vault |

Наличие файла не означает готовность сценария: часть контрактов ещё декларативна.
Для межмодульного вызова импортируйте `from skm.modules.planning import public as planning`
и передавайте текущую `uow`, например `planning.get_revision_specification(uow, revision_id)`.
Транзитивной зависимости недостаточно; прямой импорт чужих `domain/`, `application/`, `ports.py`
или `generated/` из модуля запрещён, кроме точных объявленных архитектурных исключений.

## Общие слои и точки регистрации

| Где | Что искать или обновлять |
|---|---|
| [kernel](../../src/skm/kernel/) | Общие типы, ошибки, IDs, UoW/port contracts; нет зависимости от platform |
| [platform](../../src/skm/platform/) | IO-примитивы, config engine, схемы, процесс/FS; нет зависимости от модулей |
| [application_bus](../../src/skm/application_bus/) | Dispatch/ask, транзакции, idempotency и outbox |
| [bootstrap](../../src/skm/bootstrap/) | Composition root, `build_app`, bindings, `MODULE_CATALOG` |
| [adapters](../../src/skm/adapters/) | Реализации портов по технологии; memory/PostgreSQL parity |
| [CLI](../../src/skm/entrypoints/cli/) / [API](../../src/skm/entrypoints/api/) | Тонкие поверхности; вызовы bus/public, без domain/application imports |
| [schemas](../../src/skm/schemas/) | Единственный source JSON Schema; копий в корневом `schemas/` нет |
| [gen.py](../../tools/gen.py) / [codegen](../../tools/codegen/) | `make gen`: Python/TypeScript DTO, каталоги и CLI reference |
| [adapter_inventory.py](../../tests/architecture/adapter_inventory.py) | Зарегистрировать новый concrete adapter |
| [contract_registrations.py](../../tests/architecture/contract_registrations.py) | Зарегистрировать реализованный bus handler/host operation |
| [contracts-*.md](contracts-01.md) | Указать owner нового product-файла в подходящей части инвентаря |
| [test_contract_imports.py](../../tests/architecture/test_contract_imports.py), [test_cli_thin.py](../../tests/architecture/test_cli_thin.py), [test_rules.py](../../tests/architecture/test_rules.py) | Импорты, граф, инвентари, DI, размеры и generated provenance |

Новые файлы в `adapters/`, `bootstrap/`, `entrypoints/`, `background/` экспортируют явный `__all__`
(точные исключения задаёт архтест). Не регистрируйте незавершённый handler. CLI reference генерируется,
а не редактируется вручную. Цель для рукописного файла — менее 600 строк; архитектурное правило
для product-кода предупреждает при >600 и ошибается при >900, исключая generated и SQL.

Новая часть инвентаря называется `contracts-<число>.md` и включается ссылкой в `contracts.md`:
проверка читает только перечисленные числовые части. В `adapter_inventory.py` регистрируются concrete
классы из `__all__` каждого модуля, включая совместимый фасад с реэкспортами. При разделении SQL-адаптера
держите SQL-литералы рядом с использующим их классом: импорт константы не доказывает безопасность SQL.
При регистрации операции запускайте и соответствующий contract suite: например,
[execution group contracts](../../tests/contracts/execution/test_group_contracts.py) отдельно сверяет
список реализованных операций, поэтому одной правки `contract_registrations.py` недостаточно.

## Тесты и быстрые проверки

| Где | Переиспользовать |
|---|---|
| [tests/support](../../tests/support/README.md) | Core memory/PG backend, UoW/seed, golden, fault injection, git repo и runner policy |
| [tests/fakes](../../tests/fakes/README.md) | `FrozenClock`, `SequentialIds`, deterministic entropy, реальный bus с test doubles |
| [tests/fixtures](../../tests/fixtures/README.md) | Документы, runtime streams, plugin distributions и execution harness |
| `tests/contracts/<owner>/harness.py` | Композицию конкретного домена и общие memory/PG сценарии |
| [tests/conftest.py](../../tests/conftest.py) | Очистка `SKM_*`, isolated HOME, запрет внешней сети, runner controls |

Регрессии должны быть в корневом `tests/`; `src/skm/modules/**/tests` не входит в default collection.
Маркеры: `pg` (PostgreSQL), `integration` (локальный IO и isolated HOME), `slow` (>2 s),
`e2e` (реальные процессы), `evals` (платные opt-in runtimes), `perf` (замеры).
`make test` исключает `pg/e2e/evals/perf` и архитектуру; `make arch` запускает архитектуру отдельно.

```sh
uv sync --frozen
make check-touched
uv run --frozen python tools/check_touched.py --base new --dry-run
uv run --frozen python tools/check_touched.py --base new
uv run --frozen pytest -q -n 0 tests/unit/tools/test_check_touched.py
make arch
make check
SKM_TEST_DATABASE_URL=postgresql://skm:skm_dev@127.0.0.1:54329/skm_test SKM_REQUIRE_PG=1 make test-pg
```

Число workers ограничено для общей машины: `TEST_WORKERS=4`, `ARCH_WORKERS=2`,
`PG_WORKERS=8`, `E2E_WORKERS=4`. Переопределение на один запуск: `make arch ARCH_WORKERS=0`
или `make test TEST_WORKERS=2`. Каждый worker повторно импортирует набор и держит свои кэши;
`auto` на машине с множеством CPU может исчерпать память при параллельных worktree.
Цели `test`, `test-pg` и `e2e` используют `--dist worksteal` против одиночных длинных «хвостов» xdist;
`tests/architecture` всегда запускайте отдельно с `--dist loadfile`, не смешивая с `--dist load`.
При параллельной работе нескольких worktree ограничивайте суммарное число одновременных PG-workers
на машину (не более 8 суммарно), а при точечной отладке одного сценария запускайте узкий `-k` с `-n 0`.

`check-touched` учитывает branch diff от merge-base, index, рабочие изменения и untracked.
По умолчанию база — `HEAD`. Он проверяет Ruff/format/Pyright изменённых Python-файлов (включая tests),
при изменении настроек проверок расширяет их до всех `src/tests/tools`, при затрагивании product-кода
запускает архитектуру, для schema/codegen/CLI — schema freshness, всегда проверяет ссылки.
Он также сверяет индекс исходников (`make source-index` при расхождении) и печатает команду
со списком тестов, импортирующих изменённые product-модули.
Это preflight: отдельно запускайте затронутые unit/contracts и обязательные PG/e2e сценарии.
`--dry-run` ничего не проверяет; отсутствие файла/инструмента и ненулевой exit не превращаются в PASS.

Главные ловушки: тест не читает `SKM_TEST_DATABASE_URL` напрямую после очистки окружения — использует
`pg_dsn`/`clean_test_database`; переменные задаются до запуска pytest. Не ослабляйте network guard,
в том числе для module/session fixture setup и finalizers. Memory core harness не заменяет production
composition или доменный contract harness. Фасад не открывает собственную транзакцию; host работает
через gateways/`ctx.client`. `make check` включает format, lint, оба Pyright, test, arch, docs и schemas;
PG/e2e запускаются отдельно. Любой `skip:` — недоступная проверка, не доказательство готовности.
