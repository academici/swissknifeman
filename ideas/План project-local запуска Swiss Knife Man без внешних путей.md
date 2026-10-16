# План project-local запуска Swiss Knife Man без внешних путей

## Решение

Swiss Knife Man следует перевести на **project-bound invocation**: любая команда, работающая с конкретным проектом, запускается через файл `.swissknifeman/launcher.py`, находящийся внутри этого проекта. Пользователь, Task, AI-команда и оркестратор больше не передают `--project`, `--plans-root` или путь к `packages/*/scripts/*.py`; корень проекта выводится только из физического расположения launcher.

Имя `launcher.py` точнее, чем `starter.py` или `proxy.py`: файл не устанавливает систему, не содержит бизнес-логику и не является постоянно работающим посредником. Он устанавливает проверенный invocation context и без дополнительного процесса передает управление установленному umbrella CLI.

Ключевое ограничение: в проект копируется **не реализация Swiss Knife Man**, а короткий стабильный transport adapter. Исправления planner, orch, conductor, config, provider integration и других пакетов устанавливаются в hub и сразу применяются ко всем проектам; повторная синхронизация проектов требуется только при изменении launcher protocol или самого минимального шаблона.

## Проверенное состояние

В `aicore.state` уже есть единая модель `ProjectContext` и resolver с приоритетом `explicit --project` → `SKM_PROJECT_ROOT` → ближайший `.git`/`.swissknifeman`. Resolver различает Git-каталог, `.git`-файл worktree и project marker, а некорректный явно названный каталог отклоняет вместо тихого fallback. Набор тестов подтверждает приоритеты, worktree, остановку поиска, относительные explicit paths и отказ при stale path.

`orch.project.require()` уже делегирует определение проекта в `aicore.state.resolve_project()` и не разрешает project-writing operation без контекста. Это хорошая база, но текущий порядок приоритетов недостаточен для строгой project-bound модели: explicit `--project` сейчас побеждает environment context, поэтому команда теоретически может быть запущена через launcher проекта A, но получить `--project B`. В новом контракте launcher context должен быть authoritative, а несовпадающий `--project` — ошибкой, не override.

Конфигурационная система уже связывает project layer с `<project>/.swissknifeman/config.toml` и применяет слои в порядке `defaults → machine → project → extra → env → invocation → flags`. Следовательно, после надежной передачи project root существующая config architecture сможет получать project config без дополнительных путей.

Umbrella CLI уже обнаруживает модули по `unit.json`, запускает module CLI через `exec` и специально не содержит module logic. Установщик создает стабильную команду `swissknifeman` в bin-dir, а текущий shell entrypoint сам вычисляет hub root и затем выполняет `scripts/umbrella.py`. Это означает, что project launcher может обращаться к публичной команде `swissknifeman`, а не знать расположение checkout или внутренних Python-файлов.

Planner уже объявляет `scripts/plan.py` публичным CLI в `unit.json`, но его инструкции требуют `python3 <Planner package root>/scripts/plan.py`. Та же зависимость продублирована в deprecated Task alias. Это именно тот класс внешних путей, который новая архитектура должна полностью запретить.

Planner по умолчанию ищет `plans/` вверх от текущего рабочего каталога, а `--plans-root` остается общим аргументом почти всех verbs. После project-bound запуска default должен стать детерминированным `<project_root>/plans`; иначе launcher знает проект, но planner продолжает независимо выводить location из `cwd`.

У orch обнаружен отдельный structural mismatch: manifest объявляет два публичных CLI — `scripts/orch.py` и `scripts/conduct.py`, тогда как umbrella выбирает только первый элемент `provides.cli`. До миграции orchestration нужно объединить под одной группой `swissknifeman orch ...`, иначе local launcher будет стабилен, но часть функций останется вне публичного router contract.

## Неподлежащие компромиссу правила

Новая архитектура считается завершенной только при выполнении всех инвариантов:

1. **Никаких внешних script paths.** Ни Task, ни command markdown, ни provider artifact, ни пользователь не упоминает checkout Swiss Knife Man, `<Planner package root>`, `packages/*`, `scripts/plan.py`, `scripts/conduct.py` или аналогичный путь.
2. **Никакого `--project` в штатном project mode.** Project root выводится из местоположения `.swissknifeman/launcher.py`.
3. **Launcher root authoritative.** Любой второй источник project root обязан совпасть с launcher root; несовпадение завершает выполнение до чтения конфигурации и до записи.
4. **Один публичный router.** После launcher все вызовы проходят через установленный `swissknifeman`, затем через umbrella и только затем в module CLI.
5. **Никакой бизнес-логики в launcher.** В нем нет planner/orch imports, чтения TOML, unit discovery, маршрутизации verbs, миграций или записи state.
6. **Project root и invocation cwd различаются.** Root определяет config/state/write boundary; cwd хранится отдельно для диагностики и осознанной интерпретации относительных пользовательских аргументов.
7. **Write containment обязателен.** Любая project-writing operation после разрешения symlink должна оставаться внутри canonical project root.
8. **stdout является контрактом команды.** Launcher и router не печатают служебные сообщения в stdout; диагностика идет в stderr или structured JSON.
9. **Обновление атомарно.** `project sync` никогда не оставляет частично записанный launcher или lock.
10. **Поведение проверяется end-to-end.** Unit-тест resolver сам по себе не подтверждает цепочку Task → launcher → umbrella → module → project write.

## Целевая цепочка

```text
User / Task / provider command
        |
        | project-local invocation only
        v
.swissknifeman/launcher.py
        |
        | SKM_LAUNCHER_* context; no --project
        v
installed `swissknifeman`
        |
        | validates launcher protocol and root
        v
umbrella router
        |
        | one public CLI per unit
        v
planner / orch / harness / maind / other module
        |
        | shared InvocationContext
        v
project config, plans, state and bounded writes
```

Штатные формы вызова:

```bash
python3 -I .swissknifeman/launcher.py planner next PLAN7
python3 -I .swissknifeman/launcher.py planner context PLAN7 P2.1 --stdout
python3 -I .swissknifeman/launcher.py orch conduct run --plan PLAN7 --items P2.1
python3 -I .swissknifeman/launcher.py project context --json
```

Для Task путь скрывается один раз в project-local task definition:

```yaml
version: '3'

tasks:
  skm:
    desc: Run Swiss Knife Man bound to this project
    cmds:
      - python3 -I .swissknifeman/launcher.py {{.CLI_ARGS}}

  plan:next:
    cmds:
      - task: skm
        vars:
          CLI_ARGS: planner next {{.PLAN}}
```

Повседневный вызов тогда выглядит так:

```bash
task skm -- planner next PLAN7
task skm -- orch conduct status RUN42
```

`-I` нужен для изолированного запуска минимального Python launcher: обычный запуск script добавляет каталог script в Python import path, тогда как isolated/safe-path execution снижает риск подмены импортов содержимым проекта. Launcher обязан использовать только standard library.[^1][^2]

## Launcher contract

### Расположение

Канонический файл:

```text
<project>/.swissknifeman/launcher.py
```

Он должен быть обычным tracked file, а не symlink. Если launcher является symlink, вычисление root через resolved target может привязать команду к template внутри hub, а не к проекту; поэтому symlink launcher отклоняется до запуска.

Canonical root вычисляется так:

```python
raw_launcher = Path(__file__).absolute()
project_root = raw_launcher.parent.parent.resolve(strict=True)
```

`Path.resolve()` делает путь абсолютным, убирает `..` и разрешает symlink components. После этого launcher проверяет, что его parent называется `.swissknifeman`, а canonical launcher действительно находится непосредственно в `<root>/.swissknifeman/launcher.py`.[^3]

### Обязанности

Launcher выполняет только следующие действия:

- Проверяет собственное расположение и тип файла.
- Вычисляет canonical project root из `__file__`.
- Сохраняет canonical invocation cwd.
- Находит публичный executable `swissknifeman` через `shutil.which()`.
- Формирует `SKM_LAUNCHER_*` environment contract.
- Удаляет внешний `PYTHONPATH`, чтобы project environment не подменял hub modules.
- Заменяет текущий процесс установленным CLI.

`shutil.which()` возвращает executable, который был бы выбран для команды в текущем `PATH`, либо `None`; это стандартный способ разрешить публичную команду без hard-coded path. `os.execvpe()` заменяет текущий процесс, не возвращается при успехе и использует `PATH` из переданного environment. Благодаря process replacement launcher не создает ожидающий parent process, не перехватывает stdin/stdout/stderr и сохраняет естественную signal/exit semantics.[^4][^5]

### Reference implementation

```python
#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path

PROTOCOL = "1"
NAME = "launcher.py"
DIRNAME = ".swissknifeman"


def fail(code: str, message: str, exit_code: int = 1) -> "NoReturn":
    print(f"{code}: {message}", file=sys.stderr)
    raise SystemExit(exit_code)


raw = Path(__file__).absolute()
try:
    mode = raw.lstat().st_mode
except OSError as exc:
    fail("LAUNCHER_UNREADABLE", str(exc))

if stat.S_ISLNK(mode):
    fail("LAUNCHER_SYMLINK_FORBIDDEN", str(raw))
if not stat.S_ISREG(mode):
    fail("LAUNCHER_NOT_REGULAR", str(raw))
if raw.name != NAME or raw.parent.name != DIRNAME:
    fail("LAUNCHER_LOCATION_INVALID", str(raw))

try:
    root = raw.parent.parent.resolve(strict=True)
    cwd = Path.cwd().resolve(strict=True)
except OSError as exc:
    fail("PROJECT_PATH_INVALID", str(exc))

expected = root / DIRNAME / NAME
if raw.resolve(strict=True) != expected:
    fail("LAUNCHER_LOCATION_INVALID", f"expected {expected}")

command = shutil.which("swissknifeman")
if command is None:
    fail(
        "HUB_NOT_INSTALLED",
        "install Swiss Knife Man or add its bin directory to PATH",
        127,
    )

hub = Path(command).resolve(strict=True)
if hub == raw.resolve(strict=True):
    fail("LAUNCHER_RECURSION", str(hub))

env = os.environ.copy()
env.pop("PYTHONPATH", None)
env["PYTHONSAFEPATH"] = "1"
env["SKM_LAUNCHER_ACTIVE"] = "1"
env["SKM_LAUNCHER_PROTOCOL"] = PROTOCOL
env["SKM_LAUNCHER_PATH"] = str(raw.resolve(strict=True))
env["SKM_LAUNCHER_PROJECT_ROOT"] = str(root)
env["SKM_INVOCATION_CWD"] = str(cwd)
env["SKM_PROJECT_ROOT"] = str(root)

sys.stdout.flush()
sys.stderr.flush()
os.execvpe(str(hub), [str(hub), *sys.argv[1:]], env)
```

Это reference shape, а не место для дальнейшего роста. Если файл становится длиннее примерно 60–80 строк или начинает импортировать Swiss Knife Man packages, архитектурная граница нарушена.

### Platform scope

Текущий установленный entrypoint `bin/swissknifeman` является Bash-script и использует `readlink`, `dirname`, `exec python3`. Поэтому первая версия project launcher должна честно заявлять POSIX support. Windows support следует выпускать только после появления native Python console entrypoint и отдельных tests для process replacement, PATH/PATHEXT, interrupt propagation и executable discovery; нельзя объявлять cross-platform только потому, что `pathlib` работает на Windows.

## Authoritative context

### Новая модель

В `aicore.state` нужен расширенный immutable object:

```python
@dataclass(frozen=True)
class InvocationContext:
    project_root: Path | None
    invocation_cwd: Path
    resolution: str
    marker: str | None
    launcher_path: Path | None
    launcher_protocol: int | None
```

Допустимые `resolution`:

```text
launcher | flag | environment | git | marker | none
```

Правило выбора меняется:

```text
valid launcher context
    > explicit --project only if equal to launcher root
    > SKM_PROJECT_ROOT only if equal to launcher root

without launcher:
    explicit --project
    > SKM_PROJECT_ROOT
    > nearest .git/.swissknifeman
    > none
```

Таким образом существующий non-launcher workflow остается совместимым, но launcher mode становится закрытым от retargeting.

### Валидация в umbrella

Umbrella должен вызывать `read_invocation_context()` **до** выбора builtin, alias или module. При `SKM_LAUNCHER_ACTIVE=1` выполняются проверки:

1. `SKM_LAUNCHER_PROTOCOL` — целое число из поддерживаемого диапазона.
2. `SKM_LAUNCHER_PROJECT_ROOT` — существующий absolute directory после `resolve(strict=True)`.
3. `SKM_LAUNCHER_PATH` — существующий regular file без symlink.
4. Launcher path равен `anonical root>/.swissknifeman/launcher.py`.
5. `SKM_PROJECT_ROOT`, если присутствует, равен canonical launcher root.
6. `SKM_INVOCATION_CWD` — absolute existing directory.
7. Project lock существует и его protocol совместим с hub.

Только после этого umbrella нормализует environment и продолжает маршрутизацию. Module process получает уже проверенные canonical values.

### Защита от другого проекта

Следующие вызовы обязаны завершиться до module import и до config read:

```bash
SKM_PROJECT_ROOT=/work/B \
python3 -I /work/A/.swissknifeman/launcher.py planner next PLAN1
```

Launcher перезаписывает stale environment root значением A. Если ниже по цепочке передан несовпадающий explicit flag:

```bash
python3 -I /work/A/.swissknifeman/launcher.py orch conduct run --project /work/B
```

общий resolver возвращает:

```text
PROJECT_CONTEXT_CONFLICT: launcher project is /work/A, but --project names /work/B
```

Совпадающий legacy flag временно допускается с deprecation warning, затем удаляется из project-mode documentation. Молча выбирать один из двух путей нельзя.

## Project metadata

Рядом с launcher нужен tracked lock:

```text
.swissknifeman/launcher.lock.json
```

Предлагаемый документ:

```json
{
  "$schema": "urn:swissknifeman:project-launcher-lock:v1",
  "protocol": 1,
  "template_sha256": "<sha256>",
  "minimum_hub_version": "0.1.0",
  "managed_files": [
    ".swissknifeman/launcher.py"
  ]
}
```

Lock не содержит machine-specific absolute path, username, HOME или hub checkout. Это позволяет коммитить его и переносить проект между машинами. В репозитории уже применяется аналогичный lock-artifact pattern: `.swissknifeman/provider-artifacts.lock.json` находится рядом с project config.

Сам launcher не является trust anchor и не должен считать собственный hash доказательством целостности: измененный script может изменить и свою проверку. Digest проверяет установленная команда `swissknifeman project verify`, которая сравнивает project artifact с каноническим template в hub.

## Project commands

В umbrella добавляется builtin command group `project`:

```text
swissknifeman project init
swissknifeman project sync
swissknifeman project verify
swissknifeman project context [--json]
swissknifeman project doctor [--json]
swissknifeman project exec -- <group> <args...>
```

### `project init`

Запускается из корня потребляющего проекта:

```bash
cd /work/product
swissknifeman project init
```

Команда:

- Требует Git root либо явное подтверждение создания marker-only project.
- Создает `.swissknifeman/`, если каталога нет.
- Не перезаписывает foreign launcher без `--adopt` или интерактивного подтверждения.
- Создает launcher и lock атомарно.
- При необходимости создает минимальный `config.toml` с `schema_version`.
- Обновляет project `.gitignore` только через существующую централизованную policy, не строковыми append.
- После записи запускает `project verify`.

В штатной команде нет target path. Initial binding идет к текущему проекту, поэтому даже первичная установка не требует внешнего Python path и не требует `--project`.

### `project sync`

Внутри уже инициализированного проекта:

```bash
python3 -I .swissknifeman/launcher.py project sync
```

Команда сравнивает protocol, digest и managed file set. При отсутствии изменений она является no-op; при различии показывает exact plan, затем атомарно заменяет только managed artifacts. Пользовательские `config.toml`, state, plans и неизвестные файлы не затрагиваются.

### `project verify`

Read-only проверки:

- Launcher существует.
- Это regular file, не symlink.
- Location соответствует contract.
- SHA-256 совпадает с lock и текущим template либо находится в явно поддерживаемом compatibility set.
- Protocol поддерживается hub.
- Project context round-trip возвращает этот же root.
- `swissknifeman` executable обнаруживается.
- Umbrella handshake проходит.
- Project config читается и schema version поддерживается.
- State/write directories не выходят за root через symlink.

### `project context --json`

Пример стабильного результата:

```json
{
  "$schema": "urn:swissknifeman:invocation-context:v1",
  "project_root": "/work/product",
  "invocation_cwd": "/work/product/services/api",
  "resolution": "launcher",
  "launcher": {
    "path": "/work/product/.swissknifeman/launcher.py",
    "protocol": 1,
    "verified": true
  },
  "config": "/work/product/.swissknifeman/config.toml",
  "plans_root": "/work/product/plans"
}
```

Эта команда становится единственным диагностическим источником правды для Task, support, provider commands и CI.

## CWD semantics

Launcher не должен безусловно выполнять `chdir(project_root)`. Текущий cwd может быть важен для переданного пользователем относительного input path. Вместо скрытого изменения директории должны существовать два явных значения:

- `project_root`: security/config/state boundary.
- `invocation_cwd`: место пользовательского вызова.

Для каждого unit в `unit.json` добавляется execution declaration:

```json
{
  "execution": {
    "project": "required",
    "cwd": "project",
    "writes": "project"
  }
}
```

Допустимые значения:

| Поле | Значения | Назначение |
|---|---|---|
| `project` | `required`, `optional`, `none` | Нужен ли project context |
| `cwd` | `project`, `preserve`, `unit` | Рабочий каталог module process |
| `writes` | `none`, `project`, `machine`, `project-and-machine` | Разрешенная зона записи |

Для planner и orch/conductor рекомендуются `project=required`, `cwd=project`, `writes=project`. Для machine doctor/install — `project=none`. Для команд, обрабатывающих явно названный файл относительно cwd, применяется `cwd=preserve`, но project boundary все равно передается отдельно.

## Planner migration

Planner manifest уже корректно предоставляет один CLI. Требуется изменить location defaults и всю документацию.

### Новый default

В launcher mode:

```text
plans_root = project_root / "plans"
```

`store.find_plans_root()` больше не используется как primary default для project-bound command. `--plans-root`:

- Удаляется из user/provider instructions.
- В launcher mode допускается только при canonical equality с `<project>/plans` в переходный период.
- Несовпадающее значение возвращает `PROJECT_PATH_OVERRIDE_FORBIDDEN`.
- Для административного non-project workflow может остаться отдельный explicit mode, но не использоваться Task или AI-командами.

Текущий planner CLI применяет `args.plans_root or store.find_plans_root()` при создании plan и аналогичный resolver для остальных verbs. Эти места должны получать `InvocationContext`, чтобы одна и та же команда не выводила проект одним алгоритмом, а plans root — другим.

### Новые инструкции

В `packages/planner/commands/*.md` и `packages/planner/aliases/task/commands/*.md` вводится одно определение:

```text
Project CLI: `task skm --`.
Never locate or invoke a Swiss Knife Man package script directly.
```

Вызовы:

```bash
task skm -- planner overlays planner:plan-run
task skm -- planner next PLAN7
task skm -- planner start PLAN7 P2.1 --actor provider/model/high --session auto
task skm -- planner context PLAN7 P2.1 --stdout
task skm -- planner finish PLAN7 P2.1 --status done --check V1=0
task skm -- planner commit PLAN7 P2.1 --role executor
```

Фразы `<Planner package root>` и `plan.py is python3 ...` удаляются полностью. Текущие две копии `plan-run` обе содержат внешний path contract, поэтому migration должна обновить primary command и deprecated alias одновременно или, предпочтительно, генерировать alias из одного source template.

## Orch migration

`packages/orch/unit.json` должен объявлять один public CLI:

```json
"cli": ["scripts/orch.py"]
```

В `orch.cli` добавляется command group:

```text
swissknifeman orch conduct run ...
swissknifeman orch conduct resume ...
swissknifeman orch conduct status ...
swissknifeman orch conduct cancel ...
```

`scripts/conduct.py` может сохраниться как private development entrypoint, но удаляется из `provides.cli`, пользовательских инструкций и Task. Это устраняет расхождение, при котором manifest заявляет несколько CLI, а umbrella маршрутизирует только первый.

`orch.project.find/require()` остается adapter над общим resolver, но должен принимать готовый `InvocationContext`; повторное вычисление project root из `Path.cwd()` после umbrella validation не требуется. Текущая реализация каждый раз начинает с `Path.cwd()`, поэтому без изменения module может потерять authoritative source и снова перейти к marker search.

## Write safety

Каждый module, объявивший `writes=project`, использует общий helper:

```python
def require_project_path(context: InvocationContext, candidate: Path) -> Path:
    root = context.project_root.resolve(strict=True)
    target = candidate.resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError:
        raise ProjectWriteError("PROJECT_WRITE_OUTSIDE_ROOT", target, root)
    return target
```

Проверка применяется к final target, parent temporary file, artifacts, plans, worktrees и любым paths из config. Простого string prefix недостаточно: `/work/app2` начинается с `/work/app`, а symlink внутри проекта может вести наружу. Canonical resolution нужна именно перед write; `Path.resolve()` разрешает symlink и устраняет `..`.[^3]

Дополнительные правила:

- Launcher, lock и project config обновляются temp-file в том же каталоге → flush → `fsync` → `os.replace` → directory `fsync`.
- Temp и target должны находиться на одном filesystem; это условие необходимо для atomic replacement pattern.[^6]
- Одновременный `project sync` защищается `.swissknifeman/state/locks/project-sync.lock`.
- Lock создается атомарным `mkdir`/exclusive create и содержит PID, hostname, start time и operation ID.
- Stale lock не удаляется только по возрасту: проверяются process liveness и ownership.
- Каждая массовая mutation имеет `--dry-run --json` с точным списком create/update/unchanged/refused.
- Повторный sync с тем же template digest является no-op.
- Backup создается только для managed file, который ранее принадлежал Swiss Knife Man; foreign file не перезаписывается автоматически.

## Version protocol

Launcher protocol и hub package version — разные величины:

- Package version меняется при обычных feature/bugfix releases.
- Launcher protocol меняется только при изменении environment contract, validation semantics или managed artifact format.

Compatibility rules:

| Ситуация | Поведение |
|---|---|
| Launcher protocol поддерживается | Запуск |
| Launcher старее, но поддерживается | Запуск + structured warning `LAUNCHER_UPDATE_AVAILABLE` |
| Launcher ниже minimum supported | Отказ `LAUNCHER_PROTOCOL_TOO_OLD` |
| Launcher новее hub | Отказ `LAUNCHER_PROTOCOL_NEWER` |
| Digest отличается при том же protocol | `verify` fail; run policy зависит от release mode |
| Lock отсутствует | Отказ в strict mode; migration hint в compatibility mode |

Во время controlled rollout допускается compatibility mode с предупреждением. После миграции всех registered projects CI и production invocation должны использовать strict mode.

## Batch update

Для обновления нескольких проектов не следует сканировать весь home или filesystem. Maind уже позиционируется как project memory/code graph hub и предоставляет contract `projects-list`. Поэтому fleet operation должна брать targets из его registry:

```bash
swissknifeman projects verify --all
swissknifeman projects sync --all --dry-run
swissknifeman projects sync --all
```

Алгоритм:

1. Получить snapshot зарегистрированных проектов.
2. Canonicalize и дедуплицировать roots.
3. Для каждого проекта проверить marker и launcher lock.
4. Сформировать immutable plan.
5. Показать plan или JSON.
6. Обновлять проекты по одному с per-project lock.
7. Продолжать после локального отказа, но завершаться non-zero с aggregated result.
8. Никогда не изменять unregistered directory.

Схема результата:

```json
{
  "$schema": "urn:swissknifeman:projects-sync:v1",
  "template_sha256": "...",
  "results": [
    {"root": "/work/a", "status": "updated"},
    {"root": "/work/b", "status": "unchanged"},
    {"root": "/work/c", "status": "refused", "code": "FOREIGN_LAUNCHER"}
  ]
}
```

## Error contract

Ошибки получают стабильный machine-readable code:

| Code | Значение |
|---|---|
| `HUB_NOT_INSTALLED` | `swissknifeman` не найден |
| `LAUNCHER_LOCATION_INVALID` | Файл не находится в каноническом месте |
| `LAUNCHER_SYMLINK_FORBIDDEN` | Launcher является symlink |
| `LAUNCHER_PROTOCOL_TOO_OLD` | Hub больше не поддерживает protocol |
| `LAUNCHER_PROTOCOL_NEWER` | Hub старее launcher |
| `LAUNCHER_DIGEST_MISMATCH` | Managed artifact отличается от lock/template |
| `PROJECT_CONTEXT_CONFLICT` | Второй project source указывает на другой root |
| `PROJECT_CONTEXT_REQUIRED` | Project-bound command запущена без project |
| `PROJECT_PATH_OVERRIDE_FORBIDDEN` | `--plans-root` или аналог меняет project binding |
| `PROJECT_WRITE_OUTSIDE_ROOT` | Final write target вышел за project root |
| `PROJECT_WRITE_SYMLINK_ESCAPE` | Symlink внутри проекта ведет наружу |
| `PROJECT_SYNC_LOCKED` | Идет другая sync operation |
| `FOREIGN_LAUNCHER` | Existing file не принадлежит managed template |

Text mode печатает `CODE: message` в stderr. JSON mode возвращает envelope:

```json
{
  "ok": false,
  "error": {
    "code": "PROJECT_CONTEXT_CONFLICT",
    "message": "launcher project and explicit project differ",
    "details": {
      "launcher_root": "/work/A",
      "explicit_root": "/work/B"
    }
  }
}
```

## Observability

Каждому запуску umbrella присваивается `invocation_id`, но он не обязан печататься. При `--trace-context` или config-enabled tracing записывается event:

```json
{
  "type": "skm.invocation.started",
  "invocation_id": "...",
  "project_root": "/work/product",
  "invocation_cwd": "/work/product/src",
  "resolution": "launcher",
  "launcher_protocol": 1,
  "unit": "planner",
  "argv_redacted": ["next", "PLAN7"]
}
```

Secrets и raw environment не логируются. `project context --json` показывает location и protocol, но не secret configuration values.

## Security boundary

Project-local launcher является исполняемым кодом из репозитория. Это неизбежное trust decision: запускать launcher из непроверенного clone не безопаснее, чем запускать его Taskfile, build script или tests. Архитектура должна не маскировать этот факт.

Защиты:

- Launcher короткий, reviewable и generated from canonical template.
- Запуск документирован через `python3 -I`.
- Launcher не импортирует project modules.
- `PYTHONPATH` удаляется перед hub exec.
- Hub повторно проверяет location, protocol и lock.
- CI проверяет template digest.
- `project verify` запускается до privileged/mass operations.
- Launcher не читает arbitrary project config до передачи управления trusted hub.

Эти меры защищают от случайного drift и path confusion. Они не превращают измененный malicious launcher в trusted code; для этого потребовался бы внешний подписанный native bootstrap, что выходит за нужный threat model.

## Изменения по файлам

| Файл/область | Изменение |
|---|---|
| `bootstrap/project/launcher.py` | Канонический stdlib-only template |
| `bootstrap/project/launcher.lock.schema.json` | Contract managed lock |
| `scripts/umbrella.py` | Early launcher validation; `project` builtins; execution policy |
| `bin/swissknifeman` | Сохранить stable public entrypoint; позже заменить native Python console script |
| `packages/aicore/lib/aicore/state/locations.py` | `InvocationContext`; authoritative launcher resolution; conflict checks |
| `packages/aicore/lib/aicore/state/__init__.py` | Export нового API |
| `packages/aicore/tests/state/test_locations.py` | Launcher precedence/conflict tests |
| `packages/aicore/lib/aicore/util/io.py` | Использовать/расширить atomic write helpers для project sync |
| `packages/planner/lib/planner/plan/cli.py` | Project-bound default plans root; override refusal |
| `packages/planner/lib/planner/plan/store.py` | Принимать resolved plans root, не искать независимо в launcher mode |
| `packages/planner/commands/*.md` | Только project-local invocation |
| `packages/planner/aliases/task/commands/*.md` | То же; устранить duplicated external path language |
| `packages/orch/unit.json` | Один public CLI |
| `packages/orch/lib/orch/cli.py` | `conduct` subgroup |
| `packages/orch/lib/orch/project.py` | Consume validated InvocationContext |
| `packages/orch/scripts/conduct.py` | Private/dev compatibility shim либо удаление после migration |
| `packages/*/unit.json` | `execution.project/cwd/writes` declarations |
| `configs/umbrella.json` | Только temporary legacy aliases, без script paths в user contract |
| `docs/control-surface.md` | Launcher как transport, не отдельная capability |
| CI workflows | Forbidden-path scan, template drift, e2e project-bound tests |

## Тестовая матрица

### Launcher unit tests

1. Запуск из project root.
2. Запуск из вложенного каталога.
3. Project path с пробелами.
4. Unicode project path.
5. Launcher missing executable.
6. Launcher как symlink.
7. `.swissknifeman` как symlink.
8. Broken cwd.
9. Stale `SKM_PROJECT_ROOT` перезаписывается launcher root.
10. Empty/malformed protocol.
11. Newer/older protocol.
12. stdout остается пустым до module output.
13. Exit code module сохраняется.
14. SIGINT/SIGTERM propagation на POSIX.
15. `PYTHONPATH` не переносится в hub.

### Context tests

1. Launcher A + `--project A` — временно allowed.
2. Launcher A + `--project B` — `PROJECT_CONTEXT_CONFLICT`.
3. Launcher A + env B — launcher overwrites/normalizes to A.
4. Без launcher flag продолжает побеждать env/marker по legacy contract.
5. Git worktree с `.git`-файлом.
6. Nested repository.
7. Marker-only project.
8. Home `.swissknifeman` не принимается как project marker — существующий resolver уже тестирует этот случай.

### Write tests

1. Normal file внутри root.
2. `../outside` refusal.
3. Absolute outside path refusal.
4. Symlink file наружу.
5. Symlink parent directory наружу.
6. Non-existing child под symlink parent.
7. Atomic failure before replace leaves old file intact.
8. Concurrent sync.
9. Repeated sync is no-op.
10. Foreign launcher не перезаписывается.
11. Permission failure дает stable error.
12. Crash после temp write не повреждает target.

### End-to-end tests

1. Temp project → `project init` → launcher → `project context --json`.
2. Launcher → planner `new` создает plan только в `<root>/plans`.
3. Launcher from nested cwd → тот же plans root.
4. Launcher → orch conduct использует тот же root для config и state.
5. Project A и B имеют одинаковый plan ID; launcher A никогда не читает B.
6. Task alias вызывает launcher, не package script.
7. JSON planner output остается валидным envelope.
8. Hub bugfix применяется без project sync.
9. Protocol/template change требует sync и корректно диагностируется.
10. Fleet dry-run не изменяет проекты.

## CI enforcement

После migration добавляется запрещающий scan. Build падает, если provider commands, Task aliases или docs содержат:

```text
<Planner package root>
packages/*/scripts/*.py
scripts/plan.py
scripts/conduct.py
--project
--plans-root
```

Исключения разрешаются только в migration docs, internal tests и source manifests. Проверка должна анализировать целевые каталоги allowlist-подходом, а не весь repository без контекста.

Дополнительные gates:

- Canonical launcher digest совпадает с fixture.
- Generated aliases не расходятся с primary commands.
- Каждый `kind=capability` unit имеет не более одного public `provides.cli`.
- Каждый project-writing unit объявляет execution policy.
- E2E test доказывает одинаковый project root на каждом layer.
- Test запускается из nested cwd и Git worktree.

## Порядок внедрения

### Этап 1 — contracts

1. Зафиксировать architecture decision record: project-local launcher является authoritative context source.
2. Добавить `InvocationContext` и launcher environment schema.
3. Расширить resolver conflict semantics, сохранив legacy mode.
4. Реализовать `project context --json`.
5. Добавить unit tests до изменения planner/orch.

**Acceptance:** synthetic launcher context проходит validation; mismatched explicit root отклоняется до module import.

### Этап 2 — project artifacts

1. Добавить canonical launcher template.
2. Добавить lock schema и digest generation.
3. Реализовать `project init/sync/verify`.
4. Реализовать atomic write и sync lock.
5. Добавить project doctor checks.

**Acceptance:** новый temp project инициализируется из cwd без target path; повторный sync — no-op; foreign file сохраняется.

### Этап 3 — router

1. Добавить early context validation в umbrella.
2. Добавить execution declarations в unit schema.
3. Передавать validated context module processes.
4. Устранить multiple public CLI ambiguity.

**Acceptance:** umbrella не маршрутизирует project-required unit без valid context; `orch` имеет один public entrypoint.

### Этап 4 — planner

1. Перевести default plans root на `<project>/plans`.
2. Запретить external override в launcher mode.
3. Обновить primary planner commands.
4. Обновить/сгенерировать Task aliases.
5. Добавить planner e2e test.

**Acceptance:** `task skm -- planner next PLAN1` работает из любой вложенности; ни одна инструкция не содержит package root.

### Этап 5 — orch

1. Добавить `orch conduct` subgroup.
2. Передавать `InvocationContext` вместо повторного cwd resolution.
3. Перевести config/state/write paths.
4. Оставить временный internal compatibility shim с warning.

**Acceptance:** conductor читает config и пишет state только в project launcher root; direct `conduct.py` отсутствует в public docs/manifests.

### Этап 6 — fleet

1. Подключить maind project registry.
2. Реализовать verify/sync all.
3. Сначала dry-run на всех registered projects.
4. Обновить pilot projects.
5. После успешной telemetry включить strict lock mode.

**Acceptance:** aggregated result перечисляет каждый проект; не зарегистрированные каталоги не изменяются.

### Этап 7 — удаление legacy

1. Удалить `--project` из project-mode docs и Tasks.
2. Удалить `<package root>` placeholders.
3. Удалить public direct script aliases.
4. Включить forbidden-path CI gate.
5. После одного deprecation window запретить даже совпадающий `--project` в launcher mode.

**Acceptance:** repository scan не находит запрещенные patterns в user-facing surfaces.

## Definition of done

Архитектура считается готовой, когда одновременно доказаны следующие свойства:

- Любая project operation начинается с `.swissknifeman/launcher.py` или project-local Task alias.
- Ни пользователь, ни AI-команда не передает путь к файлу за пределами проекта.
- Ни одна штатная команда не требует `--project` или `--plans-root`.
- Launcher root нельзя изменить downstream flag или environment variable.
- Planner, orch и config видят один и тот же canonical root.
- Все writes проходят containment/symlink checks.
- Launcher не содержит package logic.
- Обычный hub bugfix не изменяет project artifacts.
- Protocol change диагностируется и обновляется атомарно.
- `project context --json` объясняет каждый запуск.
- E2E и CI gates предотвращают возврат direct script paths.

## Итоговая оценка

Предложенная project-local точка входа является правильным направлением, но надежной она становится только после изменения **контракта приоритетов**: launcher должен не просто устанавливать `SKM_PROJECT_ROOT`, а быть authoritative source, с которым обязаны совпадать все downstream paths. Текущий resolver, config layer и umbrella дают хорошую основу, однако existing `flag > environment` semantics, independent planner root search и multiple orch CLI должны быть исправлены до объявления гарантии.

Итоговая модель исключает внешний path argument на уровне UX, документации, runtime validation и CI. Проект знает только свой `.swissknifeman/launcher.py` и публичные группы `planner`, `orch`, `project`; установленный hub остается единственным владельцем реализации и исправлений.

---

## References

1. [sys — System-specific parameters and functions — Python 3.12. ...](https://docs.python.org/3.12/library/sys.html) - A string giving the absolute path of the executable binary for the Python interpreter, on systems wh...

2. [1 Command Line and Environment](https://docs.python.org/3/using/cmdline.html) - The format is the same as the shell’s `PATH`: one or more directory pathnames separated by `os.paths...

3. [docs.python.org · 3 · librarypathlib — Object-oriented filesystem paths — Python 3.13.15 ...](https://docs.python.org/3.13/library/pathlib.html) - **Path.resolve(*strict=False*)¶**
Make the path absolute, resolving any symlinks.

4. [docs.python.org › 3 › libraryos — Miscellaneous operating system interfaces — Python 3.15. ...](https://docs.python.org/3/library/os.html) - The variants which include a “p” near the end (`execlp()`, `execlpe()`, `execvp()`, and `execvpe()`)...

5. [shutil — High-level file operations](https://docs.python.org/3/library/shutil.html) - Return the path to an executable which would be run if the given *cmd* was called.

6. [python-atomicwrites.readthedocs.io › en › latestatomicwrites — atomicwrites 1.4.0 documentation - Read the Docs](https://python-atomicwrites.readthedocs.io/en/latest/_modules/atomicwrites.html) - If ``dst`` exists, it will be silently
...
Both paths must reside on the same filesystem for the ope...

