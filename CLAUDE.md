# CLAUDE.md — swissknifeman

Гид по кодовой базе для агентов. Это **реестр-хаб AI-скиллов** экосистемы academici: единый source
of truth портируемых скиллов, раздаёт их в проекты (Claude Code / Cursor / Gemini). Документация —
`docs/` (VitePress); операционный раннбук — скилл `project-tooling-runbook` в maind.

## Что это

Скиллы живут в `skills/<bucket>/<name>/SKILL.md`. swissknifeman раздаёт их **двумя независимыми
каналами** (спрашивай канал у пользователя):

- **connect** — plugin marketplace Claude Code (бакет = плагин). Скиллы НЕ копируются в репо,
  автообновляются из реестра. Пишет `.claude/settings.local.json` (`enabledPlugins`).
- **vendor** — физический перенос конкретных скиллов в репо (`.ai/skills/` / `.claude/skills/`),
  управляется `.swissknife.json` (или `.swissknifeman/config.json`) + `swissknifeman sync`.

Плюс: `integrate` — визард по всему функционалу; `registry` — регенерация выходных артефактов.

### CORE-политика (раздача по умолчанию)

Токен-экономный CORE раздаётся в КАЖДЫЙ проект по умолчанию (`--no-core` отключает):
connect → бакеты `general`+`oss-dev`; vendor → skill-level `context-economy`, `anti-drift`,
`compact-responses`, `session-handoff`, `gh-review`. `permissions.deny`-пресеты применяются в
`connect`/`vendor` (`--no-permissions` отключает). Дубли хаба maind (`shared-memory`,
`cross-project-coordinator`) — default-exclude.

## Раскладка

- `bin/swissknifeman` — тонкий bash-лаунчер → `python3 -m swissknifeman`.
- `lib/swissknifeman/*.py` — вся логика, **stdlib-only** (без сторонних зависимостей в рантайме).
- `skills/<bucket>/<name>/SKILL.md` — скиллы; `buckets.json` — метаданные бакетов (description/category/tags).
- `profiles/*.json` — профили по типу проекта (project-type → buckets).
- `configs/claude-code/` — пресеты `permissions` (settings.*.json) + хуки (auto-approve/memory/notify).
- `generate-skill/` — meta-скилл создания скиллов; `skm/` — management-плагин (slash-команды CLI).
- `tests/` — `unittest` против синтетического реестра (`tests/fixtures.py`), tmpdir.
- **Генерёжка (не править руками):** `skills.json`, `skills/_index.md`, `.claude-plugin/marketplace.json`,
  `skills/*/.claude-plugin/plugin.json`, `docs/guide/graph.md` — всё из `swissknifeman registry`.

### Ключевые модули

| Модуль | Ответственность |
|:--|:--|
| `cli.py` | диспетчер команд (`COMMANDS` → `cmd_*`) |
| `common.py` | `Env` (frozen), `parse_flags`, frontmatter-парсинг, `apply_permissions` |
| `config.py` | `.swissknife.json`, профили, `resolve_selection`, **CORE-политика** (`CORE_SKILLS`/`CORE_BUCKETS`/`DEFAULT_EXCLUDE`) |
| `connect.py` | канал marketplace (плагины-бакеты) |
| `vendor.py` | канал физ. переноса (сбор скиллов, `requires`, flat/bucket-раскладка, boost.json) |
| `integrate.py` | визард: скиллы + permissions + auto-approve + memory + hub + brain |
| `registry.py` | `skills.json` + `skills/_index.md` (tag matrix) + marketplace/plugin-манифесты + граф |
| `update.py` / `sync.py`* | обновление подключения; vendor-синк из конфига |
| `lock.py` | `skills-lock.json` (карта внешних скиллов: skm + boost) |
| `status.py` / `listing.py` / `state.py` | отчёт по проекту; реестр проектов (`~/.swissknifeman/projects.json`) |
| `hub.py` | генерация хаба скиллов (CLAUDE.md/.ai) в потребляющем проекте |
| `boost.py` | синк `boost.json::skills` для Laravel Boost проектов |
| `topology.py` | `~/.swissknifeman/topology.json` (расположение узлов) |
| `doctor.py` | диагностика окружения |

\* `sync` реализован в `update.py`/`vendor.py` (отдельного `sync.py` нет — команда роутится в cli.py).

## Конвенции (соблюдай при правках)

- **stdlib-only** в `lib/`. Никаких pip-зависимостей в рантайме.
- **`Env` передаётся явно** (frozen dataclass), без модульных глобалей — всё тестируемо в tmpdir.
- **Сообщения — на русском** (`die(...)`, `warn(...)`), как в maind/brain.
- **Запись в проекты — merge-only**, существующее не затирается, бэкап `*.bak`.
- **Два канала раздачи** (connect/vendor) — не дублируй логику; общий выбор — `config.resolve_selection`.
- **Скилл** = каталог с `SKILL.md`; frontmatter: `name·bucket·version·description·risk·persona·tags·requires·produces_for·outputs`.
- **После правок скиллов/бакетов** — `swissknifeman registry` (перегенерит реестр/индекс/манифесты).
- connect — **bucket-granular** (skill-level exclude игнорируется); vendor — **skill-granular**.

## Разработка

```bash
bash scripts/test.sh          # unittest (синтетический реестр, без сети/php)
bash scripts/validate.sh      # py_compile + bash -n + JSON + тесты
swissknifeman registry        # регенерация skills.json / _index.md / marketplace.json / graph
```

Коммиты — Conventional Commits, на русском. Перед PR: `scripts/validate.sh` зелёный, `registry` прогнан.
