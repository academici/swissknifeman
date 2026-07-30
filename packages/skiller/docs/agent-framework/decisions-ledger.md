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

## Из аудита #3 (workflow resilience / rate-limit, 2026-07-01)

| Дата | Идея | Вердикт | Обоснование / куда |
|---|---|---|---|
| 2026-07-01 | Честные статусы `green/deferred/infra-failed` (не маскировать инфра под дефект) | ✅ accept | dev-loop.js ×4 + доки; P4 — первый сплит CI-таксономии «infra-flake vs code-deterministic» |
| 2026-07-01 | Fail-fast на терминальный `agent()===null` + меньший батч (дефолт 2) | ✅ accept | dev-loop.js; throttling сам не пройдёт от перехода к следующему срезу; большой батч множит retry-поверхность |
| 2026-07-01 | Liveness через **внешний supervisor** (доклад оркестратора ~30 мин + `PushNotification`; опц. GHA cron-watchdog) | ✅ accept | orchestrator.md + background-agents.md; главный предохранитель, вне песочницы |
| 2026-07-01 | In-script wall-clock / agent-timeout (`withDeadline`/`setTimeout`) | ❌ reject (костыль) | `Date.now()`/`setTimeout` в песочнице недоступны/ненадёжны, `agent()` не отменяем (нет `AbortController`) → не даёт гарантии; hang → эскалация человеку |
| 2026-07-01 | Текст-маркер возврата вместо строгой схемы на длинных возвратах | ✅ accept | dev-loop.js; StructuredOutput retry-cap (5) рантайма обрывал прогон — обходим, не переживаем |
| 2026-07-01 | `perplexity-web` — bounded concurrency (не «sequential only») | ✅ accept | background-agents.md таблица; репо-доки `query-craft` уже описывают daemon v1.3.0 pools; инцидентный 13-way fan-out просто превысил лимит |

## Из аудита #4 (harness-agnostic, 2026-07-29)

| Дата | Идея | Вердикт | Обоснование / куда |
|---|---|---|---|
| 2026-07-29 | Канонический установочный юнит — плагин/пак, бакет — человеческая рубрикация | ✅ accept | описание уже сложившегося (48 бакетов, 10 паков, marketplace ~50 плагинов), не изменение — `2026.07.29-HARNESS-AGNOSTIC` D3/§13 |
| 2026-07-29 | Корневой always-on контекст остаётся коротким индексом | ✅ accept | число для корневой цены: `CLAUDE.md` 88 строк / 7 520 байт (на `4647ad4b`, `wc -l -c CLAUDE.md`) против прежних 194/20 705 — `2026.07.29-HARNESS-AGNOSTIC P1.5` Completion Notes |
| 2026-07-29 | Шаблоны ролей тонкие по знанию, глубину дают скиллы по требованию | ✅ DONE | фиксируется каноном; `roles.md` (self-load fallback скиллов в теле промта роли) |
| 2026-07-29 | Политика спавна/делегирования — от контекст-бюджета | ✅ accept | принято, содержание и носитель — `2026.07.29-HARNESS-AGNOSTIC P4` (декларативная схема политики), здесь только ссылка |
| 2026-07-29 | Каждый пак поставляет verification-контракты и eval-фикстуры | ⚠ частично DONE | SubagentStop review-gate (`hooks/review-gate.sh` + `REVIEW_GATE_CMD`) есть в 4/10 паков (`backend-laravel`, `dart-flutter`, `node-frontend`, `python-backend`); честностной агент `test-verifier` — только у `backend-laravel` (1/10); 6/10 паков (`laravel-package`, `_common`, `role-cto`, `role-founder`, `role-maintainer`, `role-tech-lead`) не несут ни того ни другого — разрыв реален, не закрывается этой записью |

## Проверенные факты Claude Code (офиц. доки, версия факта — своя дата)

| Факт | Вердикт |
|---|---|
| `.claude/rules/` с `paths:` — авто-загрузка по путям | ✅ нативно (docs/en/memory, 2026-06-23) |
| Субагент `extends:`/`@include` наследование | ❌ не существует (2026-06-23) |
| Frontmatter `triggers/role/version/project_type` у агента | ❌ не существует (2026-06-23) |
| Нумерация файлов агентов → приоритет `/agents` | ❌ не влияет (2026-06-23) |
| `${CLAUDE_PROJECT_DIR}` / `${CLAUDE_PLUGIN_ROOT}` в командах хуков | ✅ нативно (2026-06-23) |
| Agent Teams — экспериментально (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`), `teammateMode` дефолт `in-process` с v2.1.179 (было `auto`), `iterm2`-режим с v2.1.186; хук-события команды: `TeammateIdle`/`TaskCreated`/`TaskCompleted`; teammates не наследуют `/model` лида, effort лида наследуют с v2.1.186 в split-pane | ✅ подтверждено `code.claude.com/docs/en/agent-teams` (2026-07-29) |
| Поля `skills`/`mcpServers` определения субагента НЕ применяются, когда оно запущено как teammate (загружает скиллы/MCP из настроек проекта/пользователя как обычная сессия) | ⚠ ограничивает модель ролей каркаса — оговорка внесена в `roles.md`/`agent-teams.md`, `code.claude.com/docs/en/agent-teams` (2026-07-29) |
| Лимиты Agent-тула: 200 субагентов за сессию (`CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION`, v2.1.212+), 20 одновременно (`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`, v2.1.217+), глубина вложенности 3 (v2.1.219) | ✅ `code.claude.com/docs/en/sub-agents` (2026-07-29) — отдельный потолок от workflow-рантайма ниже, не смешивать |
| Workflow-рантайм (`agent()` из `Workflow`): ~16 конкуррентно, до 1000 на прогон — в лимит Agent-тула НЕ засчитывается | ✅ repo-grounded (workflow tool description), проверено против Ф17 (2026-07-29) |
| `skills:` преднагрузка субагента: полное тело скилла инжектится в контекст; неизвестное/выключенное имя — молчаливый пропуск + запись в debug-лог (видимой ошибки нет) | ✅ `code.claude.com/docs/en/sub-agents` (2026-07-29) |
