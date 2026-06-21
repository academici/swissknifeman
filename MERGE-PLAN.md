# План: монорепо academici — слияние maind в swissknifeman

> Статус: **черновик-предложение**, код не тронут. Решения зафиксированы с пользователем
> (2026-06-20). Этот файл — источник истины по миграции; правим его по ходу.

## Цель (словами пользователя)

Один репозиторий = настоящий швейцарский нож. Сейчас управление распылено: maind —
оркестратор (рулит brain, swissknifeman и др.), но swissknifeman при этом отдельный нож
со своим установщиком и реестром. Приходится **вспоминать, откуда что управляется**. Хочу
**один репо, в нём и скиллы, и управление памятью/графом**, как **система разных плагинов**
(плагин памяти, плагин скиллов, …) под одной крышей, единая консольная точка входа, единый
хаб управления всеми остальными проектами. «Бесшовно влить в один CLI» не требуется —
требуются **лучшие практики**.

## Зафиксированные решения

| Развилка | Решение |
|:--|:--|
| Корень монорепо | **swissknifeman** (alias `skm`) — нож становится зонтиком |
| Раскладка | **`packages/` для обоих**: `packages/swissknifeman/` + `packages/maind/` (симметрия, масштаб на brain и др.) |
| Общий python-core | **только дословные дубли** на первом этапе (низкий риск) |
| Что делаю сейчас | **детальный план в файл** (этот документ), код не трогаю |
| Единый CLI | обёртка-роутер + **под-бинарники сохраняются** (`maind`, `swissknifeman` остаются рабочими) |
| Реестры `~/.maind` + `~/.swissknifeman` | **остаются раздельными** на этапах 1–4; объединение — опционально позже |

## Что подтверждено разведкой (факты, на которых стоит план)

1. **Один `marketplace.json` уже умеет N плагинов из разных подкаталогов.** swissknifeman
   прямо сейчас держит 17 плагинов с `source: ./skills/php`, `./skm`, `./generate-skill`
   ([.claude-plugin/marketplace.json](.claude-plugin/marketplace.json)). Добавить
   `source: ./packages/maind` — штатный путь.
2. **Дублирование инфраструктуры дословное и измеримое:** `Env`,
   `die/warn/now_iso/confirm/sanitize`, `parse_args`, диспетчер `main()`, `bin/<name>`,
   `install.sh`, `scripts/test.sh`, `__main__.py` — ~120-150 строк Python + ~150 строк bash
   скопированы байт-в-байт. Shared-пакета нет.
3. **Оркестраторский слой maind узкий:** вся координация — два словаря в
   `packages/maind/lib/maind/orchestrate.py` (`CAPABILITIES` + `SIBLINGS`) + subprocess по
   argv, без `shell=True`. Координируемые узлы: brain, swissknifeman, agent-memory, Serena.
4. **Жёсткие завязки на корень репо** (это главные точки риска при переезде):
   - `bin/swissknifeman`: `REPO_ROOT=$(dirname $SELF)/..`, затем проверки
     `-d $REPO_ROOT/skills`, `-f $REPO_ROOT/.claude-plugin/marketplace.json`,
     `-d $REPO_ROOT/lib/swissknifeman` (строки 27-43).
   - `lib/swissknifeman/registry.py`: пишет `root/.claude-plugin/marketplace.json`,
     читает `root/skm/...`, `source` пути считает от корня репо (строки 145-170).
   - `bin/maind`: аналогично `REPO_ROOT=dirname/..`, `python3 -m maind $REPO_ROOT`.
   - `packages/maind/.mcp.json`: `command: ${CLAUDE_PLUGIN_ROOT}/bin/maind` — путь к
     лаунчеру относительно корня установленного плагина.
5. **Marketplace rename меняет идентификаторы** `<plugin>@<marketplace>` для всех уже
   установленных плагинов; кэш `~/.claude/plugins/` это не подхватывает автоматически
   (память: [marketplace-rename-cache]). Поскольку корень = swissknifeman, **имя
   marketplace остаётся `swissknifeman`** → существующие `*@swissknifeman` НЕ ломаются.
   Ломается только `maind@maind` (1 плагин, user-scope) — он станет `maind@swissknifeman`.

## Целевая раскладка

```
swissknifeman/                       ← корень репо (имя marketplace = swissknifeman, без ренейма)
├── .claude-plugin/
│   └── marketplace.json             ← генерируемый; +1 запись { name: maind, source: ./packages/maind }
├── packages/
│   ├── swissknifeman/               ← ПЕРЕЕХАЛО из корня: lib/, bin/, skm/, generate-skill/,
│   │   │                              skills/, profiles/, buckets.json, scripts/, tests/, configs/
│   │   └── ...
│   └── maind/                       ← ПЕРЕЕХАЛО из ../maind: lib/, bin/, commands/, .mcp.json,
│       │                              templates/, tests/, scripts/, config/
│       └── ...
├── core/                            ← НОВОЕ (этап 3): academici_core/ — дословные дубли
│   └── academici_core/{env,term,args,cli}.py + templates/{bin,install,test}
├── bin/
│   ├── academici                    ← НОВОЕ: роутер-фасад (academici memory…/skills…/onboard…)
│   ├── swissknifeman → packages/swissknifeman/bin/swissknifeman   (или тонкий shim)
│   └── maind         → packages/maind/bin/maind                    (или тонкий shim)
├── install.sh                       ← один установщик: academici + под-команды + state-каталоги
└── docs/                            ← единый VitePress, одна философия (конец дублю ecosystem.md)
```

> ВАЖНО: «корень = swissknifeman», но физически содержимое swissknifeman тоже спускается в
> `packages/swissknifeman/`. В корне остаются только зонтичные артефакты: `.claude-plugin/`,
> `bin/`, `core/`, `install.sh`, `docs/`, `MERGE-PLAN.md`. Это и есть симметрия из решения
> «packages/ для обоих».

---

## Этапы (каждый — отдельный PR, зелёный `validate.sh`, откатываемый)

### Этап 0 — подготовка и сетка безопасности (нельзя пропускать)

Цель: зафиксировать «как было», чтобы любой шаг можно было сверить и откатить.

- [ ] Снять снимок установленных плагинов: скопировать `~/.claude/plugins/installed_plugins.json`
      и `known_marketplaces.json` в `MERGE-PLAN.snapshots/` (вне git, или в gitignore).
- [ ] Зафиксировать список проектов с установленными `*@swissknifeman` (из installed_plugins):
      edufy, memster, vintera, … — это «потребители», которых нельзя сломать.
- [ ] Прогнать оба `scripts/validate.sh` и `scripts/test.sh` на текущем состоянии — записать
      «зелёный baseline» (число тестов в каждом).
- [ ] Найти ВСЕ места, где зашит путь `bin/maind` или `bin/swissknifeman`:
      - `grep -rn 'bin/maind' ~/.claude ~/projects` — особенно `.mcp.json` всех онбордженных
        проектов (deploy.py пишет `bin/maind mcp --scope ...`).
      - `~/.maind/projects.json`, `~/.swissknifeman/projects.json` — абсолютные пути к репо.
      - `~/.local/bin/maind`, `~/.local/bin/swissknifeman` — симлинки.
      - **`<repo>/.maind.json`** — конфиг узла (реестр проектов экосистемы, приватный, `0600`).
        Содержит `local_path`/`vault_path` к проектам — проверить, нет ли там абсолютного пути
        к самому репо maind (на себя). Лежит в корне maind, переезжает в этап 2.
- [ ] **Инвентаризировать запущенные сервисы** (`systemctl --user`):
      - `maind-memory.service` — демон общей памяти (agent-memory), запускается через `bin/maind`
        (ExecStart содержит путь к лаунчеру) → после переезда путь меняется → unit-файл сломан.
      - `docs-watcher.service` — brain docs-watcher (pidfile `~/.brain/docs-watcher.pid`).
        Brain репо НЕ переезжает, но сервис трогаем, если переезд затронет память (порты 4111/4112).
      - Записать текущее состояние: `systemctl --user is-active maind-memory docs-watcher` +
        сохранить копии unit-файлов `~/.config/systemd/user/maind-memory.service` (etc.) в snapshots.
- [ ] **Решение по git-истории:** сохранять ли историю maind при переезде. Варианты:
      - (A) `git subtree add --prefix=packages/maind <maind-repo> main` — сохраняет историю.
      - (B) Просто `git mv` после копирования — история maind остаётся в старом репо, в новом
        один коммит «import maind». Проще, но история maind не доступна в монорепо.
      - Рекомендация: **(A) subtree** — один раз, ценно для blame/archeology.

### Этап 1 — физический переезд swissknifeman в packages/ (внутри своего же репо)

Цель: корень репо чистый, содержимое в `packages/swissknifeman/`. Самый «механический», но
ломает завязки на корень — поэтому идёт первым и отдельно.

- [ ] `git mv` содержимого корня → `packages/swissknifeman/`: `lib/`, `bin/`, `skm/`,
      `generate-skill/`, `skills/`, `profiles/`, `references/`, `adapters/`, `configs/`,
      `scripts/`, `tests/`, `buckets.json`, `skills.json`, `skills-lock.json`(если есть),
      `.skills-scanner.json`, `install.sh`(пока), `package.json`(docs).
- [ ] Оставить в корне: `.claude-plugin/`, `docs/`, `.git*`, `README.md`, `LICENSE`,
      `CHANGELOG.md`, `MERGE-PLAN.md`. (`.claude-plugin/marketplace.json` правим на этапе 4.)
- [ ] **Починить `bin/swissknifeman`** (строки 27-43): `REPO_ROOT` теперь должен указывать на
      `packages/swissknifeman`, а не на `dirname/..`. Простейший вариант — лаунчер остаётся в
      `packages/swissknifeman/bin/`, его `REPO_ROOT=$(dirname $SELF)/..` корректно даёт
      `packages/swissknifeman`. Проверки `skills/`, `lib/swissknifeman` тогда сходятся сами.
      НО: проверка `.claude-plugin/marketplace.json` смотрит в корень репо, а он теперь на
      уровень выше пакета → надо либо ослабить проверку (искать marketplace.json вверх по
      дереву до `.git`), либо убрать её из лаунчера.
- [ ] **Починить `registry.py`** генератор: `root` в нём = текущий рабочий каталог реестра.
      Развести два понятия: `pkg_root` (= `packages/swissknifeman`, где `skills/`, `buckets.json`,
      `skm/`) и `repo_root` (где `.claude-plugin/marketplace.json`). `source`-пути плагинов
      станут `./packages/swissknifeman/skills/<bucket>` (относительно корня репо/marketplace).
- [ ] Прогнать `validate.sh` + `test.sh` — должны остаться зелёными (числа из baseline).
- [ ] **Перезапустить `install.sh`** (симлинк теперь на новый путь лаунчера) и проверить
      `swissknifeman status` из любого проекта-потребителя.

> Эффект на потребителей: `source` в marketplace меняется → при следующем
> `swissknifeman connect/update` плагины переустановятся с нового пути. Имя marketplace то же,
> идентификаторы `*@swissknifeman` те же. Нужен прогон `update --all` после этапа 4.

### Этап 2 — внос maind в packages/maind

> Порядок критичен: **стоп сервисов → переезд → перенос конфига → правка путей → старт сервисов**.
> Демон памяти и его unit-файл держат путь к `bin/maind`, который меняется.

- [ ] **Застопить сервисы узла ПЕРЕД переездом** (иначе демон держит старый путь/порты):
      - `maind service stop` (или `systemctl --user stop maind-memory.service`).
      - `systemctl --user stop docs-watcher.service` — если переезд затрагивает память/порты.
      - Проверить, что порты памяти (4111/4112) свободны и pidfile снят.
- [ ] Внести maind (subtree, см. этап 0-A) в `packages/maind/`.
- [ ] **Перенести `.maind.json`** из старого корня maind в `packages/maind/.maind.json`
      (вместе с `.maind.example.json`). Это приватный конфиг узла (`0600`) — НЕ коммитить,
      сохранить права. Лаунчер `bin/maind` ищет его относительно своего `REPO_ROOT`, который
      после переезда = `packages/maind` → конфиг должен лежать там же. Если внутри `.maind.json`
      есть запись-на-себя с абсолютным путём к старому репо maind — обновить на новый путь.
- [ ] **Починить `packages/maind/bin/maind`**: `REPO_ROOT=$(dirname $SELF)/..` теперь даёт
      `packages/maind` — это правильно (там `lib/maind` и `.maind.json`). Проверки сходятся.
- [ ] **Починить `packages/maind/.mcp.json`**: `command: ${CLAUDE_PLUGIN_ROOT}/bin/maind`.
      Если плагин maind будет иметь `source: ./packages/maind`, то `CLAUDE_PLUGIN_ROOT`
      укажет на `packages/maind` → путь `${CLAUDE_PLUGIN_ROOT}/bin/maind` корректен. Проверить.
- [ ] **Самое опасное — `.mcp.json` уже онбордженных проектов.** deploy.py пишет туда
      абсолютный `bin/maind`. После переезда абсолютный путь к `bin/maind` изменился
      (`packages/maind/bin/maind`). Варианты:
      - Прогнать `maind deploy --all` (или `sync --all --only mcp`) — перепишет MCP-конфиги
        на новый путь. **Это обязательный шаг после переезда**, иначе MCP-хаб у проектов сломан.
      - До прогона — оставить symlink `~/.local/bin/maind` рабочим (через install.sh), тогда
        проекты, использующие `node_modules/.bin`/PATH, не падают; но прямые абсолютные пути в
        `.mcp.json` всё равно надо переписать deploy-ем.
- [ ] Прогнать `packages/maind` тесты (`scripts/test.sh` внутри пакета) — зелёные.
- [ ] **Обновить systemd unit-файл памяти** под новый путь лаунчера:
      - `maind service install` (перегенерит `ExecStart` с новым `bin/maind`) ИЛИ вручную
        поправить `~/.config/systemd/user/maind-memory.service`, затем `systemctl --user daemon-reload`.
- [ ] **Поднять сервисы ПОСЛЕ переезда и правки путей** (зеркало стопа в начале этапа):
      - `maind service start` (или `systemctl --user start maind-memory.service`) →
        `maind memory status` / `maind status` подтверждают, что демон жив на новом пути.
      - `systemctl --user start docs-watcher.service` (если стопили).
- [ ] `maind doctor` — окружение узла в порядке (видит `.maind.json` на новом месте, демон жив).

### Этап 3 — общий core (только дословные дубли)

Цель: убрать копипасту, не трогая доменную логику. Выносим ТОЛЬКО байт-в-байт идентичное.

- [ ] Создать `core/academici_core/` (stdlib-only, как и всё):
      - `env.py` — базовый `Env` (frozen dataclass, `root/cmd/home`, `__post_init__`).
        Проектные path-property (`state_dir`, `db_file`, `vault_path`…) — через подкласс в
        каждом пакете.
      - `term.py` — `die`, `warn`, `now_iso`, `confirm` (4 функции, идентичны байт-в-байт).
      - `text.py` — `sanitize` (slug).
      - `args.py` — `parse_args(args, spec, max_pos=0)` (maind-вариант — надмножество,
        покрывает swissknifeman `parse_flags`).
      - `cli.py` — `run_dispatch(commands, prog, argv)` (тело `main()` идентично).
      - `templates/` — шаблоны `bin/<name>`, фрагменты `install.sh`, `scripts/test.sh`,
        `__main__.py` (для генерации/справки, не рантайм).
- [ ] Подключить core к обоим пакетам через `PYTHONPATH` (лаунчеры уже ставят
      `PYTHONPATH=$REPO_ROOT/lib`; добавить `:$REPO_ROOT/../../core` или абсолютный путь к
      `core/`). Без pip, без установки — просто ещё один путь в PYTHONPATH.
- [ ] В `lib/maind/common.py` и `lib/swissknifeman/common.py`: заменить дубли на
      `from academici_core import env, term, args, cli`. Оставить в локальных `common.py`
      ТОЛЬКО уникальное (maind: atomic JSON, http, managed-block; swissknifeman: frontmatter,
      apply_permissions). **НЕ выносим** atomic JSON / http / frontmatter на этом этапе
      (решение «только дословные дубли»).
- [ ] Обновить `scripts/test.sh` обоих, чтобы тесты видели `core/` в PYTHONPATH.
- [ ] Прогнать оба test.sh — числа тестов = baseline, всё зелёное.

> Граница «только дословные дубли»: выносим Env+term+text+args+cli.run_dispatch. НЕ выносим:
> atomic_write_json/http (только в maind), frontmatter/apply_permissions (только в
> swissknifeman), managed_block, config-валидатор, doctor-каркас. Их вынос — отдельный
> будущий этап, если захочется.

### Этап 4 — единый marketplace + плагин maind под зонтиком

- [ ] Расширить `registry.py`: «ручные» (не-бакетные) плагины вынести из хардкода в данные
      (напр. секция в `buckets.json` или новый `plugins.extra.json`): сейчас skm хардкодится
      (строки 156-164); добавить туда же запись для **maind** —
      `{ name: maind, source: ./packages/maind, category: ecosystem, tags: [hub, memory, graph] }`.
- [ ] Скопировать `commands/` maind в его плагин-каталог (он уже в `packages/maind/commands/`;
      убедиться, что `packages/maind/.claude-plugin/plugin.json` объявляет `commands: commands/`
      и `mcpServers: .mcp.json`).
- [ ] Перегенерировать marketplace: `swissknifeman registry`. Проверить, что в
      `.claude-plugin/marketplace.json` появилась запись maind с `source: ./packages/maind`, а
      у бакетов `source` стал `./packages/swissknifeman/skills/<bucket>`.
- [ ] **Удалить старый marketplace maind** (`packages/maind/.claude-plugin/marketplace.json` —
      он больше не нужен, его роль берёт корневой). Оставить только
      `packages/maind/.claude-plugin/plugin.json`.
- [ ] **Миграция установки `maind@maind` → `maind@swissknifeman`:** это единственный плагин,
      чей идентификатор меняется (user-scope). По памяти [marketplace-rename-cache] кэш не
      подхватит сам:
      - снять `maind@maind` в панели плагинов Claude Code,
      - убедиться, что marketplace `swissknifeman` указывает на корень монорепо,
      - поставить `maind@swissknifeman`.
- [ ] Прогнать `swissknifeman update --all` на проектах-потребителях, чтобы их
      `*@swissknifeman` подтянули новые `source`-пути.

### Этап 5 — единая консоль `academici` (фасад-роутер)

Цель: одна точка входа в голове, под-бинарники живут.

- [ ] `bin/academici` — тонкий bash-роутер: первый аргумент = домен, делегирует под-бинарнику.
      Маппинг (примерно):
      - `academici memory|service|graph|deploy|sync|onboard|fleet|run|health|status|doctor|...`
        → `packages/maind/bin/maind <cmd> ...`
      - `academici skills|connect|vendor|integrate|registry|topology|...`
        → `packages/swissknifeman/bin/swissknifeman <cmd> ...`
      - конфликты имён (`status`, `doctor` есть в обоих): развести префиксом домена —
        `academici mem doctor` vs `academici skm doctor`, или явный неймспейс
        `academici maind:doctor` / `academici skm:doctor`.
- [ ] Под-бинарники `maind` и `swissknifeman` ОСТАЮТСЯ (симлинки в `~/.local/bin` живут) —
      не ломаем `.mcp.json` (там зашит `bin/maind mcp`) и мышечную память.
- [ ] Обновить `install.sh` (зонтичный, в корне): ставит симлинки `academici`, `maind`,
      `swissknifeman`; сидит state-каталоги (`~/.maind`, `~/.swissknifeman` — пока раздельные).
- [ ] `academici doctor` (или `academici status`) — сводка по обоим пакетам из одной команды.

### Этап 6 — документация и философия (конец дублю)

- [ ] Объединить `docs/` в один VitePress в корне. `docs/ecosystem.md` — ОДИН канонический
      («швейцарский нож academici: пакет skills + пакет maind(память/граф/координация) +
      внешние узлы brain/agent-memory/Serena»). Убрать дублирующую философию из второго репо.
- [ ] Обновить оба `CLAUDE.md` → один корневой `CLAUDE.md` монорепо + тонкие
      `packages/*/CLAUDE.md` со спецификой пакета.
- [ ] Обновить скиллы `system`/`project-tooling-runbook`/`ecosystem-integration`/`maind-overview`
      — теперь «всё из одного репо academici», убрать формулировки «соседний пакет».
- [ ] README корня: «academici — швейцарский нож: установка, под-команды, плагины».

### Этап 7 — финальная верификация совместимости и массовое обновление потребителей

Цель: убедиться, что для уже подключённых проектов ничего не сломалось; **если совместимость
не сохранилась — обновить все проекты из конфига одной командой**.

- [ ] **Проверка совместимости** на репрезентативных потребителях (edufy, memster, vintera):
      - открыть проект, проверить что MCP-хаб поднимается (`maind-hub`, `agentmemory` в `.mcp.json`
        указывают на актуальный `bin/maind`);
      - `swissknifeman status` / `maind health --cwd .` — связь с хабом зелёная;
      - плагины `*@swissknifeman` видны и активны.
- [ ] **Если совместимость НЕ сохранилась — обновить проекты из конфига** (реестры — источник
      истины по списку проектов):
      - **MCP/артефакты maind:** `maind sync --all` (или `maind deploy --all` для только MCP) —
        перечитывает `.maind.json`/`~/.maind/projects.json` и перепровиженивает все проекты на
        новые пути. Идемпотентно, делает `.bak`. Это «обновить проекты из конфига» для maind-слоя.
      - **Скиллы/marketplace swissknifeman:** `swissknifeman update --all` — проходит по
        `~/.swissknifeman/projects.json` и подтягивает новые `source`-пути плагинов.
      - **brain (если задействован):** `maind run --list` → при необходимости `brain:status`/`sync`
        по проектам.
- [ ] Зафиксировать «зелёный финал»: оба `validate.sh`+`test.sh` зелёные, демоны живы,
      выборка проектов-потребителей подтверждена.
- [ ] Сверить с baseline-снимком из этапа 0: число тестов, список `*@swissknifeman`, статусы
      сервисов — расхождений нет (или объяснены).

---

## Карта рисков (по убыванию остроты)

| Риск | Где | Митигировать |
|:--|:--|:--|
| `.mcp.json` онбордженных проектов держат абсолютный `bin/maind` — переезд ломает MCP-хаб | этап 2 | обязательный `maind deploy --all` после переезда; держать `~/.local/bin/maind` симлинк рабочим |
| `bin/swissknifeman` и `registry.py` завязаны на корень репо | этап 1 | развести `pkg_root` vs `repo_root`; ослабить/убрать проверку marketplace.json из лаунчера |
| `maind@maind` → `maind@swissknifeman` рег. меняется, кэш не подхватит | этап 4 | ручная переустановка в панели (память marketplace-rename-cache); только 1 плагин, user-scope |
| `source`-пути всех бакетов меняются (`./skills/x` → `./packages/swissknifeman/skills/x`) | этап 1+4 | `swissknifeman update --all` по потребителям; имя marketplace не меняется → ID те же |
| core в PYTHONPATH вместо pip — хрупкость путей | этап 3 | абсолютный путь к `core/` в лаунчерах; тесты гоняют с тем же PYTHONPATH |
| git-история maind теряется | этап 0 | `git subtree add` (вариант A) |
| Конфликт имён команд (`status`,`doctor`) в фасаде | этап 5 | неймспейс-префикс домена в `academici` |
| Демон памяти `maind-memory.service` держит старый путь в `ExecStart` | этап 2 | стоп до переезда → `maind service install` (regen unit) → daemon-reload → старт после |
| `.maind.json` (конфиг узла) остаётся в старом корне, лаунчер его не находит | этап 2 | перенести в `packages/maind/`, сохранить `0600`, поправить путь-на-себя если есть |
| Совместимость для онбордженных проектов не сохранилась после всех правок | этап 7 | `maind sync --all` + `swissknifeman update --all` — обновить ВСЕ проекты из конфига |

## Принципы (соблюдать на всех этапах)

- **stdlib-only** в python (как было в обоих). core тоже stdlib-only.
- **Под-бинарники не умирают** — `maind`/`swissknifeman` остаются рабочими все этапы.
- **Имя marketplace = swissknifeman** (без ренейма) → минимум поломок установок.
- **Каждый этап — отдельный PR, зелёный validate+test, откатываемый.** Не сливать этапы.
- **Conventional Commits на русском** (конвенция обоих репо).
- После переезда любого `bin/*` — **обязательный re-deploy MCP** на проекты (этап 2).
- **Сервисы: стоп до переезда, старт после** (`maind-memory`, при необходимости `docs-watcher`) —
  unit-файлы держат путь к лаунчеру, который меняется. Никогда не переезжать на живом демоне.
- **Реестры — источник истины по проектам:** массовое обновление потребителей делается из
  конфига (`maind sync --all` / `swissknifeman update --all`), а не руками по проекту (этап 7).

## Открытые вопросы (решить до старта соответствующего этапа)

1. git-история maind: subtree (A) или squash-import (B)? → этап 0.
2. core подключать через PYTHONPATH или всё же завести `pyproject.toml` с editable-install?
   (решение «только дубли» склоняет к PYTHONPATH — без pip). → этап 3.
3. Объединять ли `~/.maind` + `~/.swissknifeman` в `~/.academici`? (отложено за рамки этого
   плана — отдельная миграция реестров). → после этапа 5.
4. Нужен ли brain тоже в `packages/`? Сейчас он внешний узел (vault). План его НЕ трогает,
   но `packages/` готов его принять позже.
