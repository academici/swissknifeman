# CLAUDE.md — skiller

Гид по кодовой базе для агентов. Это **реестр-хаб AI-скиллов** экосистемы academici: единый source
of truth портируемых скиллов, раздаёт их в проекты (Claude Code / Cursor / Gemini). Документация —
`docs/` (VitePress); операционный раннбук — скилл `project-tooling-runbook` в maind.

## Что это

Скиллы живут в `skills/<bucket>/<name>/SKILL.md`. skiller раздаёт их **двумя независимыми
каналами** (спрашивай канал у пользователя):

- **connect** — plugin marketplace Claude Code (бакет = плагин). Скиллы НЕ копируются в репо,
  автообновляются из реестра. Пишет `.claude/settings.local.json` (`enabledPlugins`).
- **vendor** — физический перенос скиллов в репо. Для Claude — `skiller sync` (конфиг
  `.swissknifeman/config.json` `mode:vendor`) → копии в `.claude/skills/` + `skills-lock.json`
  (`managed`). **Файлы коммитятся** — канал для проектов, отдаваемых сторонним разработчикам без
  доступа к реестру (у `connect` marketplace указывает на локальный путь к реестру). Legacy
  `skiller vendor --agent cursor|generic` — для `.ai/.cursor` (для claude deprecated).

Плюс: `init` — создать `.swissknifeman/config.json` (vendor) из автодетекта без копирования;
`integrate` — визард по всему функционалу (`--skills-channel connect|vendor|skip`; `vendor`
для Claude роутится в `sync`); `registry` — регенерация выходных артефактов.

**Два конфига проекта** (не путать): `.swissknife.json` (connect + legacy vendor, bucket-granular,
ключи `CONFIG_KEYS`/`common.py`) и `.swissknifeman/config.json` (vendor `sync`, skill-granular,
ключи `SKILLSET_KEYS`/`skillset.py`). JSON-схемы — `schema/*.json` (DX; рантайм-валидация ручная,
stdlib-only; синхрон держат `tests/test_schema.py` + `skiller doctor`). Тела скиллов в рантайме
читает **сам Claude Code**, не Python (нет `load_skill`) → кэш «загрузки» внутри skiller не нужен.
Канон — `docs/guide/skills-architecture.md`.

### CORE-политика (раздача по умолчанию)

Токен-экономный CORE раздаётся в КАЖДЫЙ проект по умолчанию (`--no-core` отключает):
connect → бакеты `general`+`oss-dev`; vendor → skill-level `context-economy`, `anti-drift`,
`compact-responses`, `session-handoff`, `gh-review`. `permissions.deny`-пресеты применяются в
`connect`/`vendor` (`--no-permissions` отключает). Дубли хаба maind (`shared-memory`,
`cross-project-coordinator`) — default-exclude.

## Раскладка

- `bin/skiller` — тонкий bash-лаунчер → `python3 -m skiller`.
- `lib/skiller/*.py` — вся логика, **stdlib-only** (без сторонних зависимостей в рантайме).
- `skills/<bucket>/<name>/SKILL.md` — скиллы; `buckets.json` — метаданные бакетов (description/category/tags).
  PHP разбит на тонкие бакеты: ядро `php` + `laravel-{testing,filament,livewire,data-layer,auth,architecture,extras}`
  + `php-packages` (разработка пакетов) + одиночные `azguard`/`botkit` (под перенос внутрь пакетов).
  Frontend так же: ядро `frontend` + `frontend-{vue,nuxt,tailwind,naive-ui,reka,vite,linting,animations,figma,wayfinder,backend}`.
- `profiles/*.json` — профили по типу проекта (project-type → buckets).
- `presets/*.json` — **именованные кластеры скиллов** (vendor): `{name, description, extends?, buckets?, include?}`;
  раскрываются в `resolve_skillset` ДО формулы `(presets ∪ buckets ∪ include) − exclude`. Сквозные стеки
  поверх бакетов (часто php+frontend). Валидируются в validate.sh (refs + ацикл `extends`).
- Настройка окружения Claude Code (пресеты permissions, MCP, хуки) **вынесена в пакет
  [`harness`](../harness/CLAUDE.md)** — skiller делегирует туда через subprocess (`apply_permissions`,
  env-блоки `integrate`). Источник истины пресетов больше не здесь.
- `generate-skill/` — meta-скилл создания скиллов; `skm/` — management-плагин (slash-команды CLI).
- `tests/` — `unittest` против синтетического реестра (`tests/fixtures.py`), tmpdir.
- **Генерёжка (не править руками):** `skills.json`, `skills/_index.md`, `.claude-plugin/marketplace.json`,
  `skills/*/.claude-plugin/plugin.json`, `docs/guide/graph.md`, `docs/guide/budget.md` — всё из `skiller registry`.

### Ключевые модули

| Модуль | Ответственность |
|:--|:--|
| `cli.py` | диспетчер команд (`COMMANDS` → `cmd_*`) |
| `common.py` | `Env` (frozen), `parse_flags`, frontmatter-парсинг, `harness_bin`/`apply_permissions` (делегируют окружение пакету harness) |
| `config.py` | `.swissknife.json`, профили, `resolve_selection`, **CORE-политика** (`CORE_SKILLS`/`CORE_BUCKETS`/`DEFAULT_EXCLUDE`) |
| `connect.py` | канал marketplace (плагины-бакеты) |
| `vendor.py` | канал физ. переноса (сбор скиллов, `requires`, flat/bucket-раскладка, boost.json) |
| `integrate.py` | визард: скиллы + hub (свои) + permissions/MCP/auto-approve/memory (делегируются в `harness`) + brain |
| `registry.py` | `skills.json` + `skills/_index.md` (tag matrix) + marketplace/plugin-манифесты + граф + карта бюджета |
| `budget.py` | трёхъярусный токеновый бюджет (⊕ always / ↻ on-trigger / ⌥ on-demand): команда `skiller budget`, генератор `docs/guide/budget.md`, строка в `status`. ЕДИНЫЙ источник токен-математики |
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
- **Скилл** = каталог с `SKILL.md`; frontmatter: `name·bucket·version·description·risk·persona·tags·requires·produces_for·outputs` (+ опц. `level`: core|foundation|extension).
- **Двуязычная модель скиллов.** `SKILL.ru.md` — ПОЛНЫЙ русский ИСТОЧНИК (его правит человек, коммитится, SSOT). `SKILL.md` — КОМПАКТНЫЙ английский канон, **генерируется из RU**, передаёт все условия минимумом текста — его и только его грузит агент (русский в контекст не попадает). Поток правок локального скилла: **правишь `SKILL.ru.md` → регенеришь `SKILL.md`** (промт `prompts/generate/claude-canon-from-ru.md`) → `check-translations.sh --stamp`. Свежесть EN метит `<!-- ru-source-sha256: … -->`; когерентность — `scripts/check-translations.sh`. `*.ru.md` НЕ вендорится в проекты (vendor их игнорит). Внешние (upstream) скиллы — канон EN от upstream (не трогаем), `SKILL.ru.md` для них лишь справка.
- **Бюджет токенов** — единственный источник математики `budget.py` (не дублируй `len/N` по месту). `description` резидентно в каждом запросе (ярус-0) — держи его конкретным и компактным.
- **После правок скиллов/бакетов** — `skiller registry` (перегенерит реестр/индекс/манифесты).
- connect — **bucket-granular** (skill-level exclude игнорируется); vendor — **skill-granular**.
- **Анти-bloat при создании скиллов** — новый скилл только без пересечений (иначе расширяй существующий), без имён конкретных проектов/пакетов в теле. Гейты: `anti-drift` («спроси перед расширением»), `code-simplifier` (YAGNI-чеклист), `architecture` (ADR), `package-contribution-protocol` (граница «проект↔пакет»). Полная методология — `docs/guide/methodology.md`.

## Разработка

```bash
bash scripts/test.sh          # unittest (синтетический реестр, без сети/php)
bash scripts/validate.sh      # py_compile + bash -n + JSON + тесты
skiller registry        # регенерация skills.json / _index.md / marketplace.json / graph
npm run docs:standalone:build # standalone-сайт доков (своя docs/.vitepress, base /skiller/)
npm run docs:build            # зонтичный агрегат (docs-sync → ../../docs)
```

Доки пакета (`docs/`) собираются и **standalone** (своя `docs/.vitepress/config.mts`),
и в зонтичном агрегате. Внутренние ссылки — **относительные** (`./`, `../`), без
`/skiller/`-префикса; кросс-пакетные ссылки (на `harness`/зонтичный `/routing`)
резолвятся только в агрегате — в standalone они в `ignoreDeadLinks`.

Коммиты — Conventional Commits, на русском. Перед PR: `scripts/validate.sh` зелёный, `registry` прогнан.
