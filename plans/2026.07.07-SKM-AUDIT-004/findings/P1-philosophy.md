# P1.3 — Вердикт философии корневого CLAUDE.md и docs drift

Диапазон: `ea8e4d3..HEAD` (17 коммитов, 37 файлов, ~1120 строк). Read-only, дополняет
findings/P1-gates.md (F1/F2) и findings/P1-review.md (N1-N5) — не дублирует их находки.

## Тезисы «Философия и рамки» — вердикт по каждому

| Тезис | Вердикт | Обоснование |
|:--|:--|:--|
| Зонтик ≠ инструмент, имена ≠ роли | не затронут | дифф не трогает `bin/swissknifeman`, `install.sh`-роутинг алиасов, именование marketplace |
| Единый источник истины > копий (дедуп в core/) | **соблюдён** | grep новых функций диффа против `core/`: `run-report.py::_analyst_bin/_run_digest` (резолв бинаря/subprocess), `digest.py::_is_real_check` (regex-классификатор), `doctor.py::_skill_drift*` (fleet-обход), `onboard.py::_ensure_project` (доп. матч по `local_path`) — ни один не дублирует `core.io.atomic_write_*`, `core.repo.find_repo_root/find_monorepo_root`, `core.term.die/warn`. Обратное — `packages/skiller/lib/skiller/topology.py:119-123` (00b2a22) ПОЧИНЕН в сторону дедупа: было `str(env.root)` напрямую, стало `find_monorepo_root(env.root) or env.root` через реэкспорт `skiller.common` → `core.repo`. Единственное отступление — F2 (P1-gates.md, major): `skiller registry` не идемпотентен на чистом дереве (закоммиченный `skills.json`/`docs/guide/budget.md` разошлись с генератором) — это разовый дрейф артефакта, не новый дубль-примитив; уже заведено как находка, здесь не дублируется |
| stdlib-only, без рантайма | **соблюдён** | весь новый/изменённый код диффа — `os`/`sys`/`re`/`json`/`shutil`/`subprocess`/`pathlib`; подтверждено независимо гейтом P1.1 (stdlib grep чистый, единственный сигнал — внутрипроектный `import core`, не нарушение) |
| RAG-делегирование (токен-экономия) | не затронут | дифф не содержит новых внешних RAG-вызовов; существующая практика (perplexity-web в docs/коммит-message) не тронута |
| Детерминированная доставка (манифесты генерируются, не правятся руками) | **нарушен** (см. F2) | `skiller registry` — единственный генератор `skills.json`/`docs/guide/budget.md`; F2 (P1-gates.md) фиксирует расхождение чистого дерева с повторной генерацией — не переисследуется здесь повторно, но формально это прямое нарушение тезиса, попадает в P2.1 как приоритет |
| Faithful-first + провенанс (upstream.json, docs/reference.md) | не затронут | дифф не вендорит внешний код/скиллы; новые `.claude/skills/ecosystem-mcp`, `ecosystem-setup` — не вендоринг стороннего источника, а сгенерированные maind-шаблоны, применённые к себе (dogfooding, см. врезку в файлах «управляется из maind — правь там»), `upstream.json` для них не требуется (это внутренний managed-артефакт, не skill из внешнего репо) |
| Изоляция по namespace | не затронут | дифф не меняет память/граф/namespace-логику |
| Спекулятивное — в roadmap/, не на упреждение | **соблюдён** | `roadmap/skill-description-quality.md` (новый) — статус явно «отложено», внедрён ТОЛЬКО opt-in измеритель (`SKM_DESC_QUALITY=1` в validate.sh, не в CI по умолчанию), никакого гейта/массовой правки описаний. Ровно по букве тезиса — «фичу внедряем по факту измеренной проблемы» |

## Рамки — проверка нарушений

| Рамка | Вердикт | Комментарий |
|:--|:--|:--|
| Не добавляем pip/npm-рантайм в python-пакеты | соблюдена | см. stdlib-only выше |
| Не дублируем примитивы между пакетами | соблюдена | см. дедуп выше; topology.py — пример улучшения, не регресса |
| Не переименовываем зонтик/marketplace/state, не префиксуем плагины | соблюдена | не затронуто диффом |
| Не ломаем зашитые пути maind в `.mcp.json` онбордженных | соблюдена | `onboard.py`-фикс (7402046) только расширяет матчинг существующего проекта по `local_path`, не трогает запись `.mcp.json` |
| Не вендорим Proprietary / без upstream.json | соблюдена | вендоринга в диффе нет |
| Не утверждаем внешние факты по памяти — верифицируем | соблюдена | новые доки (`code-graph.md`, `sync.md`, `roadmap/skill-description-quality.md`) ссылаются на verified-RAG источники там, где нужно (Perplexity+офиц. доки Claude Code hooks в шапке `run-report.py`, verified 2026-07 в roadmap-файле) |

## Docs drift — чек-лист (ТЗ для P2.2)

Известный drift подтверждён + дополнительные пункты:

1. **Корневой `CLAUDE.md` — таблица «Пакеты»** (строки ~68-73): `packages/task` отсутствует.
   Добавить строку: `task` · «интент-команды постановки задач + plan-протокол
   (/task:design|dev|review|research|fix, /task:plan-design|plan-exec|plan-close|plan-audit)» ·
   CLI: **нет** (только slash-команды/plugin, без бинаря) · деталь: пинит модель/effort/workflow
   per-команда, перебивая настройки сессии.
2. **Корневой `CLAUDE.md` — раздел «Раскладка»** (дерево каталогов, строки ~14-19): добавить
   `packages/task/` в перечень наравне с skiller/harness/maind/analyst.
3. **Корневой `CLAUDE.md` — блок CLI** (строки ~104-113): `task` не входит в `swissknifeman
   <group>` роутинг (и не должен — у него нет `bin/`, только slash-команды через plugin) —
   ЯВНО отметить это как осознанное отличие («task — plugin-only пакет, без CLI-роутинга через
   корневой `swissknifeman`»), иначе читатель решит, что пропуск — недосмотр.
4. **`install.sh`** (корень, `for pkg in skiller harness maind analyst`): `task` сознательно не
   ставится — у него нет `install.sh`/бинаря (плагин доставляется через marketplace/vendor
   skiller-канал, не через `~/.local/bin`). Не находка сама по себе, но пункт 1 должен явно
   зафиксировать эту причину, иначе выглядит как пропущенный пакет.
5. **`packages/task/CLAUDE.md` отсутствует** — у всех остальных пакетов (skiller/harness/
   maind/analyst) свой CLAUDE.md с конвенциями; `task` тестируется (`validate.sh` зелёный,
   см. P1-gates.md) и имеет нетривиальную структуру (`commands/`, `lib/task/`, `tests/`,
   `.claude-plugin/`) — минимум minor gap для консистентности пакетной документации.
6. **`docs/reference.md`** — сверка не выявила новых пропусков: дифф не адаптирует внешние
   паттерны, требующие записи (диагностика fleet-drift/regex-классификатор сигнала A/symlink-
   дедуп — внутренняя инженерия, не заимствование). Ничего добавлять не требуется.
7. **`.claude-plugin/marketplace.json`** — `task` уже объявлен корректно (запись с `"package":
   "task"`, найдена по grep) — drift здесь отсутствует, для полноты чек-листа зафиксировано
   как «проверено, ОК».

## Severity-сводка для P2.2

- **minor**: пункты 1-3 (корневой CLAUDE.md — таблица/раскладка/CLI-блок), пункт 5
  (packages/task/CLAUDE.md отсутствует).
- **nit**: пункт 4 (install.sh — уточнить комментарием, почему task пропущен явно).
- пункт 6, 7 — не находки, зафиксированы как «проверено».

## Исходы (P2.2)

1. **fixed** — строка `task` добавлена в таблицу «Пакеты» корневого `CLAUDE.md` (роль,
   CLI: «нет (plugin-only, без `bin/`)», деталь — команды + model-routing per-команда).
2. **fixed** — `packages/task/` добавлен в дерево «Раскладка» корневого `CLAUDE.md`
   (после analyst, с пометкой «без CLI, только plugin»).
3. **fixed** — в CLI-блок добавлен явный комментарий: `task` сознательно без строки в
   `swissknifeman <group>`-роутинге (нет bin/CLI, только slash-команды плагина).
4. **fixed** — в `install.sh` перед `for pkg in skiller harness maind analyst` добавлен
   комментарий: `task` в списке нет сознательно (нет bin/install.sh, plugin-only,
   доставка через marketplace/vendor).
5. **fixed** — создан `packages/task/CLAUDE.md` (по образцу `packages/harness/CLAUDE.md`):
   «Что это» / «Раскладка» / «Конвенции» / «Разработка», зафиксирован осознанный факт
   «нет bin/CLI/install.sh».
6. **проверено, без изменений** — `docs/reference.md`, drift не найден (см. исходный вердикт).
7. **проверено, без изменений** — `.claude-plugin/marketplace.json` уже корректен;
   `skiller registry` прогнан после правок — diff пуст (идемпотентно).

Валидация: `bash -n install.sh` OK; `grep packages/task CLAUDE.md` непустой;
`skiller registry` не оставил неожиданный diff; `bash packages/task/scripts/validate.sh` —
59 тестов OK, `plan-lint: OK (3 план(ов), 0 ошибок, 0 предупреждений)`.
