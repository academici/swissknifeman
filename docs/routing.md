# Приоритеты источников и роутинг задач

## Порядок чтения источников

1. **Корневой `CLAUDE.md` / `AGENTS.md` проекта** — хаб: что за проект, куда смотреть дальше.
2. **Проектные `.ai/skills` + `.ai/guidelines`** — наивысший приоритет правил (специфика именно этого проекта).
3. **Laravel Boost** — версионно-специфичные скиллы и гайдлайны (см. [boost-compatibility](/skiller/boost-compatibility)).
4. **Скиллы swissknifeman** — архитектура, практики, процессы.

**Конфликт правил → побеждает более специфичный источник: проект > Boost > реестр.**

## Архитектурные слои: что куда (правило-стоп против разрастания)

swissknifeman — **зонтик из четырёх пакетов**, а не одно «ядро». Прежде чем что-то добавлять, реши, в какой
слой это попадает — это останавливает расползание (цель экосистемы — *лучший policy-driven
оркестратор, а не самый большой набор скиллов*):

| Слой | Что это | Где живёт | Примеры |
|:--|:--|:--|:--|
| **Контент / методики** | скиллы, чеклисты, стандарты, stack-инструкции | пакет **skiller** (`skills/`, `presets/`, `profiles/`) | github-ops, tdd-discipline, mcp-advisor |
| **Оркестрация / политика / память** | провижининг, граф, namespace-память, MCP-хаб | пакет **maind** (`lib/maind/`) | sync, health, fleet, MCP-сервер `maind_*` |
| **Обучение / уроки** | захват уроков из прогонов, cross-project паттерны, человеко-гейт | пакет **analyst** (`lib/analyst/`) | digest, scan, suggest, promote |
| **Окружение** | permissions, хуки, проводка MCP-серверов | пакет **harness** (`configs/claude-code/`) | пресеты permissions, каталог MCP |
| **Внешний движок** | зрелый runtime, который не пишем сами | подключается извне | GitHub CLI, Serena (код-граф), agentmemory, browser |

**Правило:** новая способность — это новая **запись в одном из слоёв**, а не код в maind «на всякий
случай». Стек-инструкции, тест-доктрины, security-чеклисты, GitHub-воркфлоу → **скилл/пресет в skiller**,
а не Python в maind. Выбор MCP-серверов под проект → пресеты `profiles/mcp[]` + скилл `general/mcp-advisor`,
а не вторая секция в конфиге maind. Зрелый рыночный движок → подключаем как внешний MCP/CLI, не реализуем заново.

Канон по слоям — в самих пакетах: [архитектура скиллов](/skiller/guide/skills-architecture) (skiller),
[композиция узла](/maind/architecture) (maind), [continuous learning](/analyst/) (analyst),
[конфиги и MCP](/harness/) (harness).

## Алгоритм поиска скилла

1. **Профиль** — какая роль решает задачу (`profiles/`): разработчик, основатель, оператор, PM.
2. **Бакет** — предметная область: `php`, `frontend`, `devops`, `quality`, `architect`, `pm`, `founder`, `operator`, `oss-dev`, `general`, `python`, `blender`, `roles`, `imported`.
3. **Таблица задач** ниже — прямое сопоставление «делаю X → открой скилл Y».
4. **Теги `skills.json`** — если таблица не покрыла, ищи по тегам.

## Тип задачи → скилл

### PHP / Laravel

| Задача | Скилл |
|:---|:---|
| Пишу миграцию, модель, схему БД | `php/database` |
| Новый домен / новый Laravel-проект (структура папок) | `php/laravel-structure` |
| Проект вырос: десятки доменов, несколько команд | `laravel-architecture/modular-architecture` |
| Use-case / бизнес-операция | `php/laravel` (actions.md) + `php/dependency-injection` |
| Выборки данных, query-слой | `php/repositories` |
| Права, роли, RBAC | `azguard/azguard` (универсальный) / `laravel-auth/laravel-permissions` (policies, gates) |
| Метаданные enum (label, color) | `laravel-architecture/enum-attributes` |
| Value Object, DTO, pipeline | `php/php-patterns` |
| Ревью/рефакторинг Laravel-кода (без Boost) | `php/laravel-best-practices` |
| Код-стайл PHP | `php/code-style-spatie` |
| Pint / PHPStan / Rector, конвейер качества | `php/static-analysis` |
| Feature/Unit-тесты приложения, изоляция БД, coverage gate | `laravel-testing/laravel-testing` |
| Браузерные E2E-тесты | `laravel-testing/laravel-dusk` |
| WebSocket / Echo / Reverb | `laravel-data-layer/laravel-broadcasting` |
| Admin-панель Filament | `laravel-filament/filament` |
| Загрузка файлов, медиа, конверсии | `laravel-extras/medialibrary` |
| Telegram/чат-бот | `botkit/botkit` |
| Новый Laravel-пакет (scaffold) | `php-packages/laravel-packages`, `php-packages/laravel-package-scaffold` |
| Service provider пакета | `php-packages/laravel-package-service-provider` |
| Тесты пакета (Pest + Testbench) | `php-packages/laravel-package-testing` |
| Документация пакета | `php-packages/laravel-package-docs` |
| Релиз пакета | `php-packages/laravel-package-release` |
| Матрица совместимости пакета (PHP/Laravel/Testbench) | `php-packages/laravel-package-compatibility` |
| Boost-скилл внутри пакета | `php-packages/laravel-package-generate-skill` |
| Правки самого starter kit laravel-expressive | `php-packages/laravel-package-expressive` |

### Frontend

| Задача | Скилл |
|:---|:---|
| Страница/форма Inertia, куда положить файл в `resources/js/` | `frontend-backend/inertia-vue` |
| Vue-компонент, Composition API | `frontend-vue/vue-composition-api` |
| Типобезопасные роуты на фронте | `frontend-wayfinder/wayfinder` |
| Базовая конфигурация Vite | `frontend-vite/vite-module-loader` |
| Две Vite-сборки (приложение + Filament) | `frontend-vite/vite-multi-build` |
| Тесты фронтенда | `frontend-vue/vitest` |
| Код-стайл JS/TS | `frontend-linting/js-code-style` |

### DevOps

| Задача | Скилл |
|:---|:---|
| Docker dev vs prod (compose-разнесение) | `devops/docker-dev-prod` |
| PHP-образ для прода | `devops/docker-php` |
| PostgreSQL в Docker (+ тестовая БД) | `devops/docker-postgres` |
| Полный сервисный стек (queue, scheduler, reverb) | `devops/docker-services` |
| Vite dev server в Docker | `devops/docker-vite` |
| Общая контейнеризация, оптимизация образов | `devops/docker` |
| CI/CD pipeline (GitHub Actions) | `devops/ci-cd` |
| Стратегия веток, PR-workflow, защита веток | `devops/gitops` |
| Makefile как точка входа | `devops/makefile` |
| Node/pnpm на хосте перед hooks | `devops/node-pnpm-preflight` |

### Quality / Architect

| Задача | Скилл |
|:---|:---|
| Стратегия тестирования, пирамида, coverage policy | `quality/test-strategy` |
| Code review (процесс, чек-лист) | `quality/code-review` |
| План рефакторинга | `quality/refactoring-plan` |
| Аудит техдолга | `quality/tech-debt-audit` |
| Архитектура системы, ADR, C4 | `architect/architecture` |
| Выбор стека | `architect/tech-stack-selection` |
| Проектирование API | `architect/api-design` |
| Схема данных (агностично к СУБД) | `architect/data-schema` |
| Безопасность: auth, OWASP, threat modeling | `architect/security-design` |
| Observability: логи, метрики, SLO | `architect/observability-design` |
| Проектирование AI-агента | `architect/agent-design` |
| Eval LLM-выводов | `architect/eval-design` |
| Регуляторика (GDPR, AI Act) до запуска | `architect/legal-compliance` |

### General / Roles

| Задача | Скилл |
|:---|:---|
| Коммит, PR, формат сообщения | `general/git-commit-rules` |
| Правка `.ai/guidelines`, `boost.json` | `general/ai-context-workflow` |
| SSOT скиллов для нескольких агентов | `general/skills-ssot` |
| Декомпозиция сложной задачи | `general/complex-task-orchestrator` |
| Постановка задачи агенту | `general/task-brief-template` |
| Сквозное изменение через несколько слоёв | `general/cross-layer-change-checklist` |
| Карта проекта, зоны ответственности | `general/project-map` |
| Реестр используемых пакетов | `general/packages-stack` |
| Тикетная доменная логика (проектный) | `general/ticket-workflow` |
| UserRole/Priority (проектный; новый RBAC → `azguard/azguard`) | `general/user-roles` |
| Персона: CTO / tech lead / maintainer / solo founder | `roles/*` |

### PM / Founder / Operator

| Задача | Скилл |
|:---|:---|
| BRD | `pm/brd` |
| PRD из BRD | `pm/prd-from-brd` |
| Аудит требований | `pm/requirement-critic` |
| Бизнес-процесс, FSM, диаграммы | `pm/business-process` |
| Roadmap, MVP-фазы | `pm/product-roadmap` |
| Монетизация | `pm/monetization-design` |
| GTM-стратегия | `pm/go-to-market` |
| Unit economics | `pm/unit-economics` |
| Сырая идея → гипотеза | `founder/idea-discovery` |
| Анализ конкурентов | `founder/competitive-analysis` |
| Новый стартап-проект (полный цикл) | `founder/new-project` |
| Риски (RAID, pre-mortem) | `founder/risk-assessment` |
| Pitch deck | `founder/pitch-deck` |
| Инцидент в проде | `operator/incident-response` |
| Postmortem после SEV-1/2 | `operator/postmortem` |
| Runbook на алерт | `operator/runbook` |
| On-call ротация | `operator/oncall-rotation` |
| Capacity planning | `operator/capacity-planning` |

### OSS / Python / Blender / Imported

| Задача | Скилл |
|:---|:---|
| OSS-репозиторий: структура, README, ADR | `oss-dev/oss-development` |
| LICENSE, CoC, CONTRIBUTING | `oss-dev/oss-governance` |
| SemVer, CHANGELOG, релизный pipeline | `oss-dev/release-engineering` |
| DX: quick-start, ergonomics, CLI UX | `oss-dev/dx-design` |
| Аудит зависимостей, SBOM | `oss-dev/dependency-audit` |
| Структура ML/DS-проекта | `python/ml-project-structure` |
| venv и зависимости Python | `python/venv-dependencies` |
| 3D-модель через MCP Blender | `blender/mcp-blender-workflow` |
| Правила конкретной модели | `blender/model-rules` |
| Резьба для 3D-печати | `blender/threading` |
| Ловушки Blender 5.0 API | `blender/version-gotchas` |
| Широкие доменные задачи (маркетинг, продажи, финансы, legal, research…) | `imported/*` (по названию бакета) |

## Model-routing пинов task-команд

Каждая `/task:*`-команда пинит `model`/`effort` во frontmatter `packages/task/commands/*.md`,
перебивая настройки сессии (SSOT-матрица тиров — скилл `general/plan-protocol` §9, здесь **не
дублируется**, а обосновывается per-command). Секция фиксирует **рационал каждого пина + вердикт
аудита P3.1** (`plans/2026.07.15-TELEMETRY-OPT/findings/P3-routing-audit.md`) — провенанс, чтобы
не second-guess'ить пины повторно. Ось оптимизации — **токен-экономия** (Opus доминирует по out:
8.1M vs Sonnet 5.4M — самый дорогой рычаг). Ось downgrade — **только Opus → Sonnet 5**: Fable 5
дороже Opus (out $50 = 2× Opus, up-tier для frontier-сложности) → как цель-даунгрейда исключён.

**Правило пина (при правке `model`/`effort`):** синхронно обнови строку «Пинит X/Y» в `description`
того же файла (рассинхрон = дефект) и прогони `skiller registry` (description едет в
`marketplace.json`, руками его не правь). Downgrade correctness-critical команды = ставка на
качество во ВСЕХ проектах экосистемы → **только с Owner-одобрением**, не по цене.

| Команда | Пин (акт.) | Рационал | Вердикт P3.1 |
|:--|:--|:--|:--|
| **design** | `opus/high` | Синтез research-fanout → durable план/ADR; кросс-источниковое reasoning, SSOT архитектуры (propagates во все проекты). Плохой дизайн тиражируется ecosystem-wide. Fanout уже Sonnet. | **keep-Opus** — correctness-critical, downgrade-risk HIGH, quality-телеметрии нет; Sonnet 5 (~93% Opus) — лишь *плаузибельный* Owner-A/B, не слепой downgrade |
| **dev** | `sonnet/high` | Opus-пин был тонким планировочным слоем (нарезка вертикальных срезов + risk/blast-radius); impl-субагенты уже Lean-tiered (Sonnet impl / Opus xhigh на HIGH-review / Haiku тривиал). Планирование = coding-agentic домен. | **downgrade-candidate → применён P3.2** (Owner-делегировано): Sonnet 5 par/обгоняет Opus на agentic (80.4 vs 74.6); плохая нарезка recoverable per-slice через review-gate → risk MODERATE |
| **make-workflow** | `sonnet/high` | Процедурный контур: матчинг 1/4 шаблонов → slot-fill → статический выходной ревьюер (RED блокирует). Низкий open-ended синтез; гейт ловит выпиленные обязательные стадии. | **downgrade-candidate → применён P3.2** (Owner-делегировано): «копия шаблона + слоты + чеклист-гейт», статический ревьюер — safety-net → risk LOW-MODERATE |
| **plan-design** | `opus/high` | Авторинг мастер-плана; тяжёлая схема/RAG-маркеры/DoR/pre-mortem; SSOT, дешёвая модель исполнит БЕЗ чата. Плохой план → cheap-исполнители падают без чата. | **keep-Opus** — наивысший рычаг, Owner-blessed (D1); downgrade-risk HIGH. Не трогать |
| **research** | `opus/high` | Многоисточниковый retrieval + верификация + синтез с цитатами; fanout Sonnet, Opus reduce/синтезирует. | **needs-Owner** — Sonnet 5 near-par, но fidelity цитат + кросс-источниковое reasoning — зона, где Opus чуть впереди. Возможный A/B `sonnet/high` → **OQ-4** (Decision pending), низкий приоритет |
| **plan-audit** | `opus/xhigh` | Adversarial-аудит закрытой фазы; ~15 finding-типов, no-op-детект, scope-drift, re-run Validation. | **keep-Opus/xhigh** — bug-finding = сильнейшая зона Opus 4.8 («stronger real-bug finding»); недо-аудит пропускает дефекты тихо; xhigh оправдан. Не трогать |
| **review** | `opus/xhigh` | Read-only adversarial code/doc-ревью; Stage A стек→скиллы, B классика+conformance, C adversarial verify; coverage-first. | **keep-Opus/xhigh** — тот же класс adversarial bug-finding, Opus 4.8 best-in-class; xhigh оправдан. Не трогать |

Аудит-факты (RAG:✅ 2026-07, canonical `claude-api` reference + `perplexity-web`): Sonnet 5 ≈93%
способностей Opus 4.8 при ~60% цены, обгоняет на autonomous-agentic (80.4/74.6); Opus 4.8 лидер
SWE-bench Pro (69.2/63.2) + SOTA bug-finding. **Ограничение:** `analyst token-report --by phase`
не реализован (`token_report.py:38-41`) → ROI конкретного downgrade не квантифицируется, приоритет
trial'ов **качественный** (по downgrade-risk), не по измеренной экономии.
