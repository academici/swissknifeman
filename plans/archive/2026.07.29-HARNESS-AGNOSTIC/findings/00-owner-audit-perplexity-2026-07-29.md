## 0. Как читать этот документ

Это консолидированная версия двух предыдущих аудитов репозитория `academici/swissknifeman` — ничего из первого (структурный аудит трёх пакетов) и второго (токен-бюджет и лучшие практики 2026) не удалено, всё сведено в единую логику и порядок. Документ рассчитан на прямую передачу в Claude Code для дальнейшей проработки: каждый раздел заканчивается конкретными файлами/структурами, которые нужно создать или изменить. В конце — отдельный блок референсов со всеми источниками, на которых основаны выводы.

## 1. Резюме и вердикт

Текущая монорепа `academici/swissknifeman` (пакеты `skiller`, `harness`, `maind`, `task`) уже прошла два внутренних аудита и содержит зрелый decisions-ledger, который явно фиксирует отклонённые идеи (наследование агентов через `extends:`, движок Mustache-рендера, file-lock, нумерация файлов приоритета). Любой новый аудит обязан подаваться **вместе** с `decisions-ledger.md` и `framework-overview.md`, иначе он будет заново предлагать то, что уже отклонено с доказательствами.

Главный вывод обеих итераций аудита сходится в одной точке: harness-агностик и role-based агенты — это не новая архитектура с нуля, а (а) завершение уже начатого плана (Фаза 3 "Универсальные роли" из `framework-overview.md`), и (б) смена базовой единицы упаковки знаний с широких bucket-ов на атомарные plugin/pack по образцу `wshobson/agents`. Второй пункт — это то, что не было очевидно на первом проходе аудита и стало ключевым после более глубокого разбора токен-экономики.[^1]

Итоговая рекомендация: не создавать пятый пакет-надстройку, а (1) сменить единицу дистрибуции знаний с bucket на plugin/pack, (2) достроить Фазу 3 ролей в `harness`+`skiller`/`knowledge` по decisions-ledger, (3) добавить тонкий cross-harness adapter layer только при реальной необходимости работы вне Claude Code/Cursor, и (4) формализовать foreman в `packages/task` как автономный, context-budget-driven оркестратор, а не workflow с фиксированными узлами.[^2]

## 2. Текущее состояние репозитория

Монорепа уже разделила ответственность на независимые пакеты, что структурно соответствует запросу на harness-агностик разделение:

| Пакет | Роль | Статус |
|---|---|---|
| `skiller` | Скиллы (provider-neutral `SKILL.md` + snippets), профили проектов, upstream-sync | Зрелый, есть CLI, marketplace-плагин |
| `harness` | Настройка Claude Code: permissions-пресеты, MCP-серверы, хуки | Выделен из skiller осознанно, назван так же, как термин из индустрии |
| `maind` | Долгосрочная память агентов, граф связей, реестр агентов/проектов, MCP-сервер | Отдельный "мозг" экосистемы, топология hub+namespace |
| `task` | Slash-команды постановки задач (`/task:design`, `/task:dev`, `/task:fix`, `/task:review`) + plan-протокол (`/task:plan-*`) | Plugin-only, пинит модель/effort под тип задачи |

Пакет `task` уже содержит зачаток "foreman"-логики — plan-протокол с исполнительным слоем (`plan-design` → `plan-exec` → `plan-close` → `plan-audit`), детерминированным линтером схемы плана (`plan_lint.py`) и режимом `plan-run`, который наследует модель/effort сессии владельца, а не пинит их. Это ближе к workflow, чем к автономному foreman.

## 3. Диагноз проблемы №1: "скиллы не видны / избыточны"

Проблема не в структуре бакетов (`architect`, `devops`, `php`, `quality` — уже разумная категоризация), а в том, что скиллы в Claude Code **preload через поле `skills:` на субагенте**, которое молча no-op'ится при опечатке в имени — это зафиксировано в decisions-ledger как источник регрессии "скиллы не видны", и Фаза 1 плана прямо адресует это фиксом видимости (сверка имён `skills:` со `skills.json`, freshness-штамп). Избыточность скиллов — это проблема **обнаружения и гарантированной загрузки**, а не моделирования.

Второй источник: универсальные роли (`reviewer`, `implementer`, `test-writer`) существуют только как конкретные Laravel-агенты (`laravel-reviewer`, `laravel-test-writer`), а не как параметризуемые по стеку шаблоны — это прямо помечено как незавершённая Фаза 3. Решение уже спроектировано: **роль = константа, стек = переменная через профиль** (`skills_map`, path-scoped rules), рендерится build-time в `.claude/agents/<prefix>-*.md` под конкретный профиль — не рантайм-наследование, потому что Claude Code официально не поддерживает `extends:`/`@include` на агентах (проверено против официальной документации и отклонено дважды).

## 4. Диагноз проблемы №2: переполнение токен-бюджета

Это диагноз, который добавляет глубину первому проходу аудита. `wshobson/agents` сознательно ушёл от крупных бакетов к **мелким изолированным плагинам** с одной ответственностью, со средним размером 5.5 компонентов на плагин, нулём "раздутых" плагинов и строгим правилом "плагин должен описываться в 5–10 словах". Это напрямую связано с токен-бюджетом: меньшие плагины, более узкие агенты и skill progressive disclosure лучше помещаются в контекстные окна и меньше загрязняют сессию.[^1]

Anthropic в официальном best-practices guide прямо пишет, что контекст заполняется быстро и производительность деградирует по мере заполнения окна; в контекст попадает всё: история диалога, прочитанные файлы, вывод команд и промежуточные результаты. Отсюда практические правила:[^3]

- `CLAUDE.md` должен быть коротким, только про broad, always-on правила; всё ситуативное выносится в skills, потому что skills грузятся on demand, не раздувая каждую сессию.
- Исследовательские или "шумные" задачи должны уходить в subagents, потому что они работают в отдельном контексте и возвращают только summary — официальный паттерн Anthropic и база multi-agent research.[^2]
- Сессии нужно агрессивно очищать между несвязанными задачами (`/clear`, `/compact`, checkpoints), потому что долгий разношёрстный чат создаёт context rot и повторно биллит всё, что было прочитано в начале.[^4]
- Широкие чтения кода должны заменяться узкими grep/find/targeted reads; ранний `read` больших файлов — не разовая цена, а "подписка", переоцениваемая на каждом следующем ходе.[^5][^4]

Вывод: **единица упаковки должна оптимизироваться под вероятность одновременного совместного использования в одной сессии**, а не под человеческую рубрикацию. Bucket `php` — плохая верхняя единица, если Laravel packages, patterns, testing, queues, billing, Eloquent performance и API resources редко нужны одновременно. Progressive disclosure в 2026 должен работать не только внутри `SKILL.md`, но и **на уровне каталога/дистрибуции**.[^6][^1]

## 5. Модель role-based агентов: PHP / Frontend / Docker и др.

Правильная структура — не "агент = язык", а двухосевая матрица **роль × стек**:

| Ось | Значение |
|---|---|
| Роль (константа) | `implementer`, `test-writer`, `reviewer`, `explore`, `plan`, `spec-writer` — набор tools и ответственность не меняются |
| Стек (переменная) | Профиль (`laravel-project` → PHP/Laravel-скиллы; `node-frontend` → Vue/Nuxt-скиллы; `platform-service`/`docker` → инфраструктурные скиллы) |

"PHP-агент", "Frontend-агент", "Docker-агент" реализуются как рендер одной и той же роли под разный профиль — то есть `implementer` для laravel-профиля и `implementer` для node-frontend-профиля — это два разных файла `.claude/agents/php-implementer.md` и `.claude/agents/frontend-implementer.md`, сгенерированных из одного шаблона с разными `skills:` preload-списками. Это устраняет дублирование логики ролей и обеспечивает специализацию по стеку без runtime-магии, которая не поддерживается платформой.

Для module-boundaries (кто пишет в какие пути, чтобы параллельные агенты не конфликтовали) есть готовая конвенция из agent-teams.md: backend-роль владеет `app/Http/`, `app/Actions/`, `app/Repositories/`; frontend-роль — `resources/js/`, `pages/`; test-writer — `tests/`; для пересекающихся файлов — последовательное исполнение или worktree-изоляция, а не file-lock (последнее явно отклонено как хрупкое).

## 6. Что переносить из `wshobson/agents`

`wshobson/agents` полезен не объёмом, а тем, что системно решил три задачи: (1) native source-of-truth, (2) дробление marketplace без токен-мусора, (3) обслуживание нескольких харнесов одновременно.[^1]

### 6.1 Канонический короткий индекс вместо толстого root-гайда

Корневой `AGENTS.md` — только table of contents, никогда не растёт больше ~150 строк. Для swissknifeman: корневой хаб — короткий индекс; role routing, plugin map, capability matrix, quality gates — в отдельных docs; auto-loaded root-context рассчитан на то, что его читают в каждой сессии.[^1]

### 6.2 Плагин как атомарная единица

`plugins/<name>/` — self-contained юнит: `agents/`, `commands/`, `skills/`; ставится плагин — подтягиваются только его компоненты. Рекомендуемое дробление текущих bucket-ов:[^7][^1]

| Текущий bucket | Рекомендуемое дробление |
|---|---|
| `php` | `laravel-feature-dev`, `laravel-review`, `laravel-testing`, `laravel-packages`, `eloquent-performance`, `laravel-api-design` |
| `devops` | `docker-runtime`, `docker-builds`, `github-actions`, `deploy-pipelines`, `incident-runbooks`, `observability` |
| `architect` | `api-contracts`, `data-modeling`, `security-architecture`, `adr-writing`, `integration-design` |

### 6.3 Native single-source + generated harness outputs

Source-of-truth живёт только в `plugins/`, артефакты для Codex/Cursor/OpenCode/Gemini генерируются адаптерами как derived outputs. Для swissknifeman — с оговоркой из decisions-ledger: **никакого Mustache-движка как центра архитектуры**. Переносить нужно инвариант, не рендерер: канонический контент в одном месте, харнес-специфичный синтаксис — thin adapter layer, generated outputs — build artifacts, валидируемые на drift.[^1]

### 6.4 Четырёхуровневая модель назначения моделей

Tiered models: Opus для архитектуры/ревью/безопасности, Sonnet для сложной реализации и поддержки, Haiku для быстрых детерминированных задач, Inherit — когда модель выбирает пользователь/родительская сессия. Модель назначается роли и режиму работы, а не только slash-команде:[^8][^6]

- `reviewer`, `security-reviewer`, `architect` → Opus,
- `implementer`, `explore`, `spec-writer` → Inherit или Sonnet,
- `test-writer`, `docs-maintainer`, `formatter` → Haiku/Sonnet,
- `foreman` → Inherit, для наследования модели владельца.

## 7. Что переносить из Anthropic multi-agent research

Anthropic описывает multi-agent system как lead-agent, который планирует исследование и создаёт параллельных subagents, работающих в своих tool loops. Это подтверждает целевую модель foreman: не workflow-граф из фиксированных узлов, а автономный координатор, который сам решает, сколько подагентов создать и как декомпозировать задачу.[^2]

- **Subagents нужны для compression, а не ради параллелизма самого по себе** — там, где exploration-token volume большой, а нужен маленький summary назад.[^9][^2]
- **Lead agent должен сохранять план во внешнюю memory**, потому что большой контекст рано или поздно компактуется/теряется — усиливает роль `maind` как внешней памяти.[^2]
- **Каждый subagent должен получать objective, output format, tool guidance, source guidance и task boundaries** — role-agent'ам нужен жёсткий delegation contract, а не просто "ты PHP-эксперт".[^2]
- **Нужны caps на fan-out.** Обычный старт — 3–5 subagents для breadth-first задач.[^9][^2]
- **Evals обязательны с первого дня**, даже маленькие, реальные, плюс человеческая проверка, потому что LLM judge не видит всё.[^2]

Это меняет проектирование `task/foreman`: нужен explicit policy layer — `max_parallel_agents`, `spawn_threshold`, `allowed_agent_roles`, `handoff_contract`, `verification_strategy`, `memory_checkpoint_policy`.

## 8. Что переносить из `learn-claude-code`

Автор разделяет **agent = model** и **harness = tools + knowledge + observation + action + permissions**. 20-stage progression даёт чек-лист зрелости:

Tool Use → TodoWrite → Subagent → Skill Loading → Context Compact → Memory → Task System → Agent Teams → Team Protocols → Autonomous Agents → Worktree Isolation → MCP Plugin.

Статус swissknifeman относительно этой прогрессии:

| Механизм | Статус в swissknifeman |
|---|---|
| Task System (персистентный граф между сессиями) | ⏸ Отложено — "не плодить слой; если надо — на maind/agentmemory" |
| Agent Teams (mesh, независимые сессии) | ✅ Принято как experimental v1, CC ≥2.1.178, роли каркаса годятся как teammates без изменений |
| Team Protocols (фиксированный формат) | Частично — module-boundaries описаны, формального протокола сообщений нет |
| Autonomous Agents (self-claim с борда) | Не реализовано — лид явно spawn'ит teammates по шаблону |
| Worktree Isolation | Упомянуто как альтернатива file-lock, не формализовано как механизм |
| Skill Loading, Hooks, Permissions, Memory hub | ✅ Закрыто в `harness`/`skiller`/`maind` |

Уже закрыты skill loading, hooks, permissions, memory hub, частично agent teams и task protocol. Не закрыты два самых дорогих для качества узла: (1) autonomous claim loop и (2) worktree isolation как first-class primitive. Именно поэтому система ощущается "неидеальной": не потому что бакеты плохи сами по себе, а потому что coarse-grained knowledge packaging сочетается с недостаточно зрелым execution layer.

Внешняя гарантия живости (liveness) уже спроектирована и принята в предыдущем аудите: внешний supervisor (доклад оркестратора ~30 минут + push-нотификация, опционально GHA cron-watchdog) — вместо in-script wall-clock таймеров, которые отклонены как ненадёжные в песочнице. Foreman не может сам гарантировать себе таймаут изнутри одного вызова модели — нужен внешний watchdog-слой.

## 9. Что явно НЕ делать (уже отклонено с доказательствами)

- **Frontmatter-наследование агентов** (`extends:`/`@include`, поля `triggers/role/version/project_type`) — official docs не поддерживают, проверено эмпирически.
- **Python/Mustache-движок генерации агентов** — противоречит требованию "агент-driven"; шаблоны должны оставаться реальными markdown-файлами.
- **File-lock протокол** (`touch {file}.lock`) — хрупко, заменён one-branch/worktree-изоляцией и module-boundaries.
- **Нумерация файлов агентов** (`01_`, `02_`) — эмпирически не влияет на поведение `/agents`.
- **Complexity scoring 1–10** для делегирования — признано церемонией; порог остаётся качественным.
- **In-script wall-clock таймауты** — ненадёжны в песочнице, заменены внешним supervisor'ом.
- **`skiller init`** как отдельная команда — свёрнута в существующий `integrate`.

## 10. Целевая структура репозитория

### 10.1 Верхний уровень монорепы

```text
packages/
  harness/          # runtime integration, permissions, hooks, MCP, harness adapters
  knowledge/        # бывший skiller; source-of-truth for plugins/packs/skills
  maind/            # memory, graph, agent registry, project registry
  task/             # foreman, role orchestration, plan/task protocols, eval hooks
  analyst/          # optional research/reporting package
```

`skiller` логически переименовать в `knowledge` или хотя бы во внутренней документации перейти на термин "knowledge marketplace", потому что текущий нейминг исторический и маскирует, что это уже не просто installer, а ядро content distribution.

### 10.2 Внутри knowledge: не bucket-ы, а packs/plugins

```text
packages/knowledge/plugins/
  laravel-feature-dev/
    agents/
    skills/
    commands/
    docs/
    plugin.json
  laravel-review/
  laravel-testing/
  vue-nuxt-feature-dev/
  docker-runtime/
  docker-builds/
  github-actions/
  adr-writing/
  api-contracts/
  postgres-design/
  incident-response/
  observability/
```

Принцип: один plugin = одна рабочая область, которую реально ставят вместе. Если плагин нельзя описать в 5–10 словах, он слишком широкий.[^1]

### 10.3 Отдельно profiles/packs

```text
packages/knowledge/packs/
  backend-laravel/
    pack.json
    interview.md
    roles/
    workflows/
    settings/
    docs/
  frontend-vue-nuxt/
  platform-docker/
  fullstack-laravel-vue/
```

`pack` — installable composition unit, не knowledge atom. Сюда логично складывать `agent-packs` с `pack.json`, semver, lockfile и interview-driven rendering.

### 10.4 Роли отдельно от домена

```text
packages/task/roles/
  implementer.md
  reviewer.md
  test-writer.md
  explore.md
  planner.md
  spec-writer.md
  foreman.md
```

Это role templates, не конкретные агенты проекта. Конкретные `.claude/agents/*.md` рендерятся pack-установкой: `backend-laravel` создаёт `php-implementer`, `php-reviewer`, `php-test-writer`; `frontend-vue-nuxt` создаёт `frontend-implementer` и т.д..

### 10.5 Role routing matrix

```text
packages/task/configs/role-routing.yaml
```

```yaml
roles:
  implementer:
    default_model: inherit
    allowed_tools: [Read, Grep, Glob, Edit, Write, Bash]
    spawn_when:
      expected_exploration_tokens: low
      shared_context_required: high
  reviewer:
    default_model: opus
    allowed_tools: [Read, Grep, Glob, Bash]
    spawn_when:
      expected_exploration_tokens: medium
      independent: true
  explore:
    default_model: sonnet
    allowed_tools: [Read, Grep, Glob, Bash]
    spawn_when:
      expected_exploration_tokens: high
      result_shape: summary
```

Это превращает неявную логику `task`-команд в policy-driven execution layer.

## 11. Практические правила разбиения для токен-экономики

- **Правило 1: CLAUDE.md ≤ короткий индекс.** Корневой auto-loaded контекст — table-of-contents + safety invariants + verification rules. Всё остальное — docs/skills/hooks. Если правило не применимо ко всем сессиям, оно не должно жить в always-loaded файле.[^1]
- **Правило 2: один skill = один decision surface.** Не "Laravel patterns", а `eloquent-query-optimization`, `queue-job-idempotency`, `form-request-validation`, `api-resource-serialization`.[^6]
- **Правило 3: skill body трёхслойный.** Frontmatter → core instructions → resources/examples on demand. Секции внутри `SKILL.md`: `## Use when`, `## Decision rules`, `## Workflow`, `## References`, `## Examples`.[^6]
- **Правило 4: spawn по бюджету, не по размеру задачи.** Subagent спавнится, когда exploration создаст много мусора, который не нужен lead-context later — обычно если exploration даст 10k+ токенов логов, а обратно нужен 1–2k summary.[^9]
- **Правило 5: role-agent никогда не носит с собой всё знание стека.** Preload минимальный набор invariants; остальное — self-load skills по ходу дела.
- **Правило 6: verification-first.** Каждый pack поставляет verification recipes — тест, билд, screenshot, hook-gate, `/goal`, second-opinion subagent.

## 12. Что дописать в существующие документы репозитория

### В `framework-overview.md`
Новый раздел `## Packaging model`: bucket-ы = legacy taxonomy for humans; canonical install unit = plugin/pack; skill granularity measured by decision-surface; root context ≤ 150 lines; role templates separate from stack packs; spawn policy based on context budget.

### В `roles.md`
Model tier matrix; allowed tools by role; handoff contract format; when role should self-load skills; when role must ask foreman for parallel delegation.

### В `agent-teams.md`
`max_parallel_agents` defaults; module-boundary ownership table; conflict resolution protocol; external watchdog/supervisor rules; review loop after each implementer batch.

### В `skills-index-and-hub.md`
Hub is index, not encyclopedia; freshness/version markers; plugin/pack installation state; role→plugin routing hints; warnings for oversize context components.

### В `decisions-ledger.md`
Новые решения: D19 — canonical install unit = plugin/pack, not broad bucket; D20 — root context files must remain ultra-short; D21 — role templates are knowledge-thin, skills provide depth on demand; D22 — foreman spawn policy is context-budget-driven; D23 — each pack ships verification contracts and eval fixtures.

## 13. Итоговый вывод

Если упростить до одного решения: нужно менять не только runtime orchestration, но и единицу упаковки знаний. Сегодня buckets хороши для каталога, но плохи как runtime distribution primitive. Лучшие практики 2026 показывают другой pattern: короткий root context, атомарные плагины, progressive disclosure, role-thin agents, external memory, context-budget-based spawning и mandatory verification.[^4][^2][^1]

Целевая архитектура swissknifeman:

- `knowledge` хранит атомарные plugins/skills,
- `packs` собирают их в installable stack compositions,
- `task` рендерит universal roles в stack-specific agents,
- `foreman` управляет decomposition/spawn/review на основе token economics,
- `maind` хранит память/план/реестр,
- `harness` адаптирует это под Claude/Cursor/дальше при необходимости.

Это смена базового packaging primitive с bucket-centric на plugin/pack-centric — структурная разница между "рабочей системой" и действительно "идеальной системой" для 2026 года.

## 14. Референсы (для проверки и передачи в Claude Code)

Ниже — полный список источников, использованных при подготовке обоих аудитов, с кратким описанием того, что именно из них взято. Это позволяет Claude Code самостоятельно перепроверить выводы и углубиться в первоисточники при реализации.

**Внутренние документы репозитория `academici/swissknifeman` (первоисточник, GitHub):**
- `README.md` (корень репозитория) — обзор монорепы, назначение пакетов.
- `packages/skiller/README.md` — назначение skiller, структура skills/, профили, upstream-sync, CLI.
- `packages/harness/README.md` — назначение harness, permissions-пресеты, MCP, хуки.
- `packages/maind/README.md` — назначение maind, топология hub+namespace, память, граф, MCP-сервер.
- `packages/task/CLAUDE.md` — назначение task, plan-протокол, интент-команды, model/effort pinning.
- `packages/skiller/docs/agent-framework/framework-overview.md` — канонический срез текущего состояния каркаса, статусы ✅/🔜/⏸.
- `packages/skiller/docs/agent-framework/roles.md` — модель универсальных ролей, build-time рендеринг, анти-паттерны.
- `packages/skiller/docs/agent-framework/decisions-ledger.md` — реестр принятых и отклонённых архитектурных решений.
- `packages/skiller/docs/agent-framework/agent-teams.md` — Agent Teams эксперимент, module-boundaries.
- `packages/skiller/docs/workflows/*` — каталог существующих межсистемных workflow (framework-audit, background-agents, claude/cursor/perplexity адаптеры).

**Внешние репозитории, предоставленные пользователем:**
- `github.com/wshobson/agents` — multi-harness plugin marketplace для Claude Code/Codex/Cursor/OpenCode/Gemini: атомарные плагины, tiered model strategy, native single-source + generated adapters, короткий root `AGENTS.md`.
  - `AGENTS.md`, `README.md`, `docs/plugins.md`, `docs/architecture.md`, `docs/agent-skills.md` — использованы для практик дробления плагинов, модели назначения моделей, progressive disclosure.
  - DeepWiki-обзор `deepwiki.com/wshobson/agents/9-repository-configuration` — каталог агентов/скиллов/плагинов, tiered model matrix.
- `github.com/shareAI-lab/learn-claude-code` — 20-стадийный учебный курс по harness engineering: модель "agent = model, harness = среда", прогрессия механизмов (Tool Use → MCP Plugin), явное разделение agency (обучена) и harness (написан).

**Внешние материалы по best practices Claude Code 2026 (веб-источники):**
- `code.claude.com/docs/en/best-practices` — официальный гайд Anthropic: деградация качества по мере заполнения контекста, короткий CLAUDE.md, verification-first, использование subagents для шумных задач.
- `simonwillison.net/2025/Jun/14/multi-agent-research-system` — разбор статьи Anthropic "How we built our multi-agent research system": lead-agent + parallel subagents, delegation contract, caps на fan-out, важность evals.
- `amitkoth.com/claude-code-token-budgeting` — модель четырёх "форм" стоимости токенов (контекст, subagents, skills, caching).
- `academy.kspl.tech/blog/2026-06-05-claude-code-subagent-context-window-strategy` — матрица сигналов "spawn vs inline" для субагентов, привязка к контекстному бюджету, а не размеру задачи.
- `anhtu.dev` (Claude Code Skills 2026 — Progressive Disclosure) — трёхуровневая модель progressive disclosure в SKILL.md, governance, анти-паттерны.

Эти источники использовались комплементарно: внутренние документы репозитория дали текущий статус и уже принятые/отклонённые решения, внешние репозитории — конкретные архитектурные паттерны для переноса, а материалы по best practices 2026 — обоснование того, почему выбор единицы упаковки знаний напрямую влияет на токен-бюджет и качество ответов агентов.

---

## References

1. [agents/AGENTS.md at main · wshobson/agents - GitHub](https://github.com/wshobson/agents/blob/main/AGENTS.md) - Multi-harness agentic plugin marketplace for Claude Code, Codex CLI, Cursor, OpenCode, and Gemini CL...

2. [Anthropic: How we built our multi-agent research system](https://simonwillison.net/2025/Jun/14/multi-agent-research-system/) - A multi-agent system consists of multiple agents (LLMs autonomously using tools in a loop) working t...

3. [Best practices for Claude Code](https://code.claude.com/docs/en/best-practices) - Most best practices are based on one constraint: Claude's context window fills up fast, and performa...

4. [How to budget tokens in Claude Code - Amit Kothari](https://amitkoth.com/claude-code-token-budgeting/) - A surprising Claude Code bill is almost never one big expense. It is four different cost shapes stac...

5. [Claude Code memory: how to survive a 200k context window filling up](https://dev.to/subprime2010/claude-code-memory-how-to-survive-a-200k-context-window-filling-up-idk) - Claude Code memory: how to survive a 200k context window filling up If you've used Claude...

6. [agents/README.md at main · wshobson/agents - GitHub](https://github.com/wshobson/agents/blob/main/README.md) - Intelligent automation and multi-agent orchestration for Claude Code - wshobson/agents

7. [Multi-harness agentic plugin marketplace for Claude Code ...](https://github.com/wshobson/agents) - Each plugin is isolated and composable: agents, commands, and skills are auto-discovered from direct...

8. [Repository Configuration | wshobson/agents | DeepWiki](https://deepwiki.com/wshobson/agents/9-repository-configuration) - This page provides comprehensive catalogs of all components in the Claude Code Plugins repository. U...

9. [Claude Code Subagent: When to Spawn vs Inline in 2026 — Koenig ...](https://academy.kspl.tech/blog/2026-06-05-claude-code-subagent-context-window-strategy) - The spawn vs inline decision comes down to context budget, not task size. Use this 7-signal matrix t...

