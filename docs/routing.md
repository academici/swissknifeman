# Приоритеты источников и роутинг задач

## Порядок чтения источников

1. **Корневой `CLAUDE.md` / `AGENTS.md` проекта** — хаб: что за проект, куда смотреть дальше.
2. **Проектные `.ai/skills` + `.ai/guidelines`** — наивысший приоритет правил (специфика именно этого проекта).
3. **Laravel Boost** — версионно-специфичные скиллы и гайдлайны (см. [boost-compatibility.md](boost-compatibility.md)).
4. **Скиллы swissknifeman** — архитектура, практики, процессы.

**Конфликт правил → побеждает более специфичный источник: проект > Boost > реестр.**

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
| Проект вырос: десятки доменов, несколько команд | `php/modular-architecture` |
| Use-case / бизнес-операция | `php/laravel` (actions.md) + `php/dependency-injection` |
| Выборки данных, query-слой | `php/repositories` |
| Права, роли, RBAC | `php/azguard` (универсальный) / `php/laravel-permissions` (policies, gates) |
| Метаданные enum (label, color) | `php/enum-attributes` |
| Value Object, DTO, pipeline | `php/php-patterns` |
| Ревью/рефакторинг Laravel-кода (без Boost) | `php/laravel-best-practices` |
| Код-стайл PHP | `php/code-style-spatie` |
| Pint / PHPStan / Rector, конвейер качества | `php/static-analysis` |
| Feature/Unit-тесты приложения, изоляция БД, coverage gate | `php/laravel-testing` |
| Браузерные E2E-тесты | `php/laravel-dusk` |
| WebSocket / Echo / Reverb | `php/laravel-broadcasting` |
| Admin-панель Filament | `php/filament` |
| Загрузка файлов, медиа, конверсии | `php/medialibrary` |
| Telegram/чат-бот | `php/botkit` |
| Новый Laravel-пакет (scaffold) | `php/laravel-packages`, `php/laravel-package-scaffold` |
| Service provider пакета | `php/laravel-package-service-provider` |
| Тесты пакета (Pest + Testbench) | `php/laravel-package-testing` |
| Документация пакета | `php/laravel-package-docs` |
| Релиз пакета | `php/laravel-package-release` |
| Матрица совместимости пакета (PHP/Laravel/Testbench) | `php/laravel-package-compatibility` |
| Boost-скилл внутри пакета | `php/laravel-package-generate-skill` |
| Правки самого starter kit laravel-expressive | `php/laravel-package-expressive` |

### Frontend

| Задача | Скилл |
|:---|:---|
| Страница/форма Inertia, куда положить файл в `resources/js/` | `frontend/inertia-vue` |
| Vue-компонент, Composition API | `frontend/vue-composition-api` |
| Типобезопасные роуты на фронте | `frontend/wayfinder` |
| Базовая конфигурация Vite | `frontend/vite-module-loader` |
| Две Vite-сборки (приложение + Filament) | `frontend/vite-multi-build` |
| Тесты фронтенда | `frontend/vitest` |
| Код-стайл JS/TS | `frontend/js-code-style` |

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
| UserRole/Priority (проектный; новый RBAC → `php/azguard`) | `general/user-roles` |
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
