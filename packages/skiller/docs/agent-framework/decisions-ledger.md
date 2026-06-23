# Decisions Ledger — что принято / отклонено

Реестр решений по каркасу агентов. **Вход для аудита**
([framework-audit](../workflows/framework-audit)): подаёшь Perplexity, чтобы он НЕ
перепредлагал уже отклонённое/принятое. Отклонять решение можно — но только с НОВЫМ
доказательством.

Колонки: дата · решение · вердикт · обоснование · где приземлилось.

## Архитектурные принципы

| Дата | Решение | Вердикт | Обоснование |
|---|---|---|---|
| 2026-06-23 | Дом базы шаблонов — **harness**; playbook — **skiller** | ✅ accept | harness уже владеет `.claude/`-окружением; skiller — скиллами |
| 2026-06-23 | **Per-pack** версионность (1 пак = 1 semver + 1 CHANGELOG) | ✅ accept | проще, чем per-template; проект пинит одну версию |
| 2026-06-23 | **Агент-driven**, не Python/Mustache движок | ✅ accept | требование владельца; шаблоны = реальные файлы + lock |
| 2026-06-23 | Универсальность: **паки по концерну + общие роли** | ✅ accept | back/front/fullstack = композиция паков; роли едины |
| 2026-06-23 | lock = `.claude/agent-pack.lock.json` (не `.swissknife.json`) | ✅ accept | разные владельцы; нужна вложенная per-file структура + sha |

## Из аудита #1 (universal-framework)

| Дата | Идея | Вердикт | Обоснование / куда |
|---|---|---|---|
| 2026-06-23 | AI Skills Index в CLAUDE.md | ✅ absorb | уже hub; расширяем (Фаза 1), boost-aware (`.ai/guidelines`) |
| 2026-06-23 | Движок генерации агентов (Mustache `.tpl`, `generate-agents`) | ❌ reject | против агент-driven; шаблоны = реальные `.md` в паке |
| 2026-06-23 | Профили-наследование `laravel→php-backend→base` (рендер) | ⏸ defer | как данные (`extends`), не рендер-движок |
| 2026-06-23 | `.swissknife.json` схема (`shape`/`stacks`/`skills_map`) | ✅ absorb | только данные (Фаза 3) |
| 2026-06-23 | path-scoped rules `.claude/rules/` | ✅ absorb | **нативно** (офиц. docs/en/memory); Фаза 3 |
| 2026-06-23 | spec-first гейт (spec-writer) | ✅ absorb (опц.) | как опц. role-agent на крупные фичи, не глоб. гейт; артефакт `tech-spec.md` |
| 2026-06-23 | task-graph `tasks.json` (Task Master) | ⏸ defer | не плодить слой; если надо — на maind/agentmemory |
| 2026-06-23 | `skiller init` | ⏸ defer | свернуть в существующий `integrate` |
| 2026-06-23 | file-lock протокол (`touch {file}.lock`) | ❌ reject | хрупко; заменено one-branch/worktree |
| 2026-06-23 | <500-char system prompts | ✅ absorb (гайдлайн) | конвенция, не жёсткий лимит |
| 2026-06-23 | Нумерация файлов агентов `01_`,`02_` для приоритета | ❌ reject | **проверено**: на `/agents` НЕ влияет |
| 2026-06-23 | `skiller validate-agents` | ✅ absorb | валидатор (данные, не движок): имена `skills:`, дубли, scope tools (Фаза 3) |
| 2026-06-23 | explore-субагент | ✅ absorb | есть (`Explore`); добавим seed в роли |
| 2026-06-23 | complexity scoring 1–10 | ❌ reject | церемония; порог делегирования качественный |

## Из аудита #2 (agent-teams + ponytail)

| Дата | Идея | Вердикт | Обоснование / куда |
|---|---|---|---|
| 2026-06-23 | `extends:`/`@include` наследование агентов; frontmatter `triggers/role/version/project_type` | ❌ reject | **REFUTED** офиц. доками — не нативно/выдумано; наследование = build-time пака |
| 2026-06-23 | `.claude/rules/` (path-scoped) нативно | ✅ confirmed | офиц. docs/en/memory → берём |
| 2026-06-23 | skill-enforcement хук (TeammateIdle, exit 2, греп транскрипта) | ❌ reject (как хук) | хрупкая эвристика; «гейт на скиллы» закрывает детерминированная сверка имён `skills:` в hub |
| 2026-06-23 | ponytail (YAGNI-лесенка + over-engineering ревью) | ✅ absorb (дисциплину) | без внешнего плагина; в reviewer-роль + опц. `quality/lean-code` |
| 2026-06-23 | Agent Teams (Mesh, teammates) | ✅ accept v1 | эксперимент; CC ≥2.1.178; Фаза 6; роли = teammates |

## Проверенные факты Claude Code (офиц. доки, 2026-06-23)

| Факт | Вердикт |
|---|---|
| `.claude/rules/` с `paths:` — авто-загрузка по путям | ✅ нативно (docs/en/memory) |
| Субагент `extends:`/`@include` наследование | ❌ не существует |
| Frontmatter `triggers/role/version/project_type` у агента | ❌ не существует |
| Agent Teams + `teammateMode` + хуки TeammateIdle/TaskCompleted | ✅ реально, экспериментально, CC ≥2.1.178 |
| Нумерация файлов агентов → приоритет `/agents` | ❌ не влияет |
| `${CLAUDE_PROJECT_DIR}` / `${CLAUDE_PLUGIN_ROOT}` в командах хуков | ✅ нативно |
| Конкурентность субагентов | ~16 одновременно / 1000 на прогон |
