# Skills Repository: Полный план и аудит источников

> Документ для агента Fable. Версия 2.0 — полная редакция с аудитом источников и расширенным топ репозиториев.
> Репозиторий: `academici/brain` · Цель: создание `academici/skills`

---

## Часть I. Аудит текущего состояния `academici/brain`

### Структура репозитория (подтверждено живым сканом)

Репозиторий `academici/brain` — это не просто Obsidian vault, а полноценная мультиагентная рабочая среда. Ключевые находки:

| Папка / Файл | Размер | Назначение |
|---|---|---|
| `skills-lock.json` | 25 778 байт | Lock-файл системы скиллов — аналог `package-lock.json` |
| `package.json` + `package-lock.json` | 615 + 212 345 байт | NPM-экосистема уже встроена |
| `CLAUDE.md` | 18 599 байт | Основной системный промпт для Claude Code |
| `AGENTS.md` | 2 436 байт | Мультиагентная конфигурация |
| `GEMINI.md` | 1 719 байт | Конфигурация для Gemini |
| `.claude/settings.json` | 1 033 байт | Локальные настройки Claude Code |
| `.cursor/` | dir | Настройки Cursor |
| `.ai/` | dir | Общие AI-настройки |
| `.antigravity/` | dir | Кастомная интеграция |
| `.claude-plugin/` | dir | Плагины Claude |
| `.mcp.json` | 759 байт | MCP-серверы конфигурация |
| `commands/` | dir | Кастомные команды агентов |
| `scripts/` | dir | Автоматизационные скрипты |
| `02 - Knowledge/` | dir | Obsidian Knowledge Base |
| `40 - AI/` | dir | AI-специфичные знания |
| `90 - Templates/` | dir | Шаблоны |

**Критическое наблюдение:** `skills-lock.json` (25KB) означает, что система управления скиллами уже функционирует как package manager. Новый репозиторий `academici/skills` должен быть совместим с этим lock-форматом, а не заменять его.

**Важные файлы для миграции:**
- `.pre-commit-config.yaml` — уже настроены pre-commit хуки (качество кода)
- `.env.example` — переменные окружения для агентов
- `logs/` — логи работы агентов
- `Без названия.base` + `.canvas` — Obsidian Canvas файлы

---

## Часть II. Топ-20 репозиториев со скиллами (расширенный аудит)

### Категория A: Прямые источники скиллов (импортировать as-is)

#### 1. get-zeked/perplexity-super-skills
**URL:** https://github.com/get-zeked/perplexity-super-skills  
**⭐ 205 stars | 25 forks | Обновлён: апрель 2026**

Самый ценный источник для задачи. 12 production-ready SKILL.md файлов с YAML frontmatter. Каждый файл содержит: gap-analysis матрицу, структурированные workflows, шаблоны, decision trees, quality checklists. Полностью cross-agent: работает с Perplexity Computer, Claude Code, Cursor/Windsurf.

**Скиллы для импорта:**
- `ai-agent-super-skill` — ReAct/Plan-Execute архитектура, MCP серверы, RAG, subagent coordination
- `dev-engineering-super-skill` — Architecture, frontend, backend, QA/testing, DevOps, CI/CD
- `agent-security-super-skill` — Prompt injection defense, OWASP/NIST frameworks
- `research-knowledge-super-skill` — Knowledge graphs, data exploration, statistical analysis
- `pm-super-skill` — PRD/feature specs, RICE/MoSCoW, sprint ops, OKRs
- `token-efficient` — Адаптировано из drona23/claude-token-efficient

**Установка:**
```bash
git clone https://github.com/get-zeked/perplexity-super-skills.git
```

---

#### 2. mwguerra/claude-code-plugins
**URL:** https://github.com/mwguerra/claude-code-plugins  
**Фокус: Obsidian Vault + Claude Code integration**

Структурно идентичен `academici/brain` — тот же подход хранения плагинов внутри Obsidian vault. Содержит `obsidian-vault/` поддиректорию с готовыми CLAUDE.md шаблонами.

**Что брать:**
- Паттерн структуры `.claude-plugin/` директории
- CLAUDE.md шаблоны для project-level контекста
- Механику vault ↔ agent context sync

---

#### 3. PatrickJS/awesome-cursorrules
**URL:** https://github.com/PatrickJS/awesome-cursorrules  
**⭐ ~50k stars — крупнейшая коллекция правил для AI-агентов**

500+ `.cursorrules` файлов по всем технологиям.

**Файлы для импорта в `snippets/php/`:**
- `laravel/`, `php/`, `php-laravel/` директории
- `docker/`, `docker-compose/` для DevOps скиллов
- `filament/` — прямое пересечение со стеком

---

#### 4. anthropics/claude-code (официальный)
**URL:** https://github.com/anthropics/claude-code  

Содержит официальные примеры CLAUDE.md, паттерны subagent orchestration, спецификацию MCP.

---

#### 5. anthropics/knowledge-work-plugins
**URL:** https://github.com/anthropics/knowledge-work-plugins  

Официальные паттерны для работы с документами, кодом, исследованиями.

---

### Категория B: Снипеты и code examples (для `snippets/`)

#### 6. alexeymezenin/laravel-best-practices
**URL:** https://github.com/alexeymezenin/laravel-best-practices  
**⭐ ~25k stars | На русском языке**

Структурированные best practices по Laravel с code examples на PHP.

---

#### 7. LaravelDaily/laravel-tips
**URL:** https://github.com/LaravelDaily/laravel-tips  
**⭐ ~15k stars**

2000+ Laravel tips в формате markdown со сниппетами.

---

#### 8. spatie/laravel-permission (source code)
**URL:** https://github.com/spatie/laravel-permission  
**⭐ ~12k stars — референсная реализация RBAC**

---

#### 9. docker/awesome-compose
**URL:** https://github.com/docker/awesome-compose  
**⭐ ~35k stars — официальный репозиторий Docker**

---

#### 10. lorisleiva/laravel-actions
**URL:** https://github.com/lorisleiva/laravel-actions  
**⭐ ~2.5k stars — Action pattern для Laravel**

---

### Категория C: Cross-agent и инструментарий

#### 11. DenisSergeevitch/agents-best-practices
**URL:** https://github.com/DenisSergeevitch/agents-best-practices  

---

#### 12. drona23/claude-token-efficient
**URL:** https://github.com/drona23/claude-token-efficient  

---

#### 13. vercel-labs/skills
**URL:** https://github.com/vercel-labs/skills  

---

#### 14. awesome-windsurf/awesome-windsurf-rules
**URL:** https://github.com/awesome-windsurf/awesome-windsurf-rules  

---

#### 15. continuedev/continue
**URL:** https://github.com/continuedev/continue  
**⭐ ~20k stars**

---

### Категория D: Архитектурные паттерны

#### 16. kamranahmedse/developer-roadmap
**URL:** https://github.com/kamranahmedse/developer-roadmap  
**⭐ ~300k stars**

---

#### 17. ziadoz/awesome-php
**URL:** https://github.com/ziadoz/awesome-php  
**⭐ ~30k stars**

---

#### 18. public-apis/public-apis
**URL:** https://github.com/public-apis/public-apis  
**⭐ ~330k stars**

---

#### 19. awesome-selfhosted/awesome-selfhosted
**URL:** https://github.com/awesome-selfhosted/awesome-selfhosted  
**⭐ ~230k stars**

---

#### 20. filipdutescu/modern-cpp-template
**URL:** https://github.com/filipdutescu/modern-cpp-template  

---

## Часть III. Идеальная структура `academici/skills`

```
academici/skills/
│
├── README.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── skills.json
├── install.sh
├── .github/
│   ├── workflows/
│   │   ├── validate-skills.yml
│   │   ├── sync-to-brain.yml
│   │   └── generate-index.yml
│   └── PULL_REQUEST_TEMPLATE.md
│
├── skills/
│   ├── _template/
│   │   └── SKILL_TEMPLATE.md
│   ├── php/
│   │   ├── laravel-architecture.md
│   │   ├── laravel-eloquent.md
│   │   ├── laravel-security.md
│   │   ├── laravel-testing.md
│   │   ├── laravel-filament.md
│   │   ├── laravel-permissions.md
│   │   └── php-patterns.md
│   ├── devops/
│   │   ├── docker-compose.md
│   │   ├── docker-laravel.md
│   │   ├── ci-cd-github-actions.md
│   │   └── deployment-vps.md
│   ├── ai-agents/
│   │   ├── claude-code.md
│   │   ├── multi-agent.md
│   │   ├── mcp-servers.md
│   │   ├── token-efficiency.md
│   │   └── agent-security.md
│   ├── architecture/
│   │   ├── system-design.md
│   │   ├── api-design.md
│   │   ├── database-patterns.md
│   │   └── package-design.md
│   ├── business/
│   │   ├── product-management.md
│   │   ├── technical-writing.md
│   │   └── project-planning.md
│   └── cross-domain/
│       ├── code-review.md
│       ├── git-workflow.md
│       └── documentation.md
│
├── snippets/
│   ├── php/
│   │   ├── laravel/
│   │   ├── patterns/
│   │   └── security/
│   ├── docker/
│   ├── git/
│   └── shell/
│
└── adapters/
    ├── claude-code/
    ├── cursor/
    ├── perplexity/
    └── obsidian/
```

---

## Часть IV. SKILL_TEMPLATE.md

```markdown
---
name: skill-name
version: 1.0.0
description: Краткое описание
domain: php|devops|ai-agents|architecture|business|cross-domain
agents:
  - claude-code
  - cursor
  - perplexity
tags: []
sources: []
updated: YYYY-MM-DD
---

# [Skill Name]

## Контекст и назначение
## Ключевые принципы
## Workflows
## Паттерны и антипаттерны
## Примеры
## Чеклист качества
## Связанные скиллы
```

---

## Часть V. skills.json — формат манифеста

```json
{
  "version": "1.0.0",
  "name": "academici-skills",
  "repository": "https://github.com/academici/skills",
  "skills": [],
  "snippets": []
}
```

---

## Часть VI. Алгоритм агента Fable

### Алгоритм SCAN → ANALYZE → EXTRACT → COMMIT

```
SCAN: Рекурсивно обходить scan_paths, фильтровать по языку
ANALYZE: quality_score по метрикам (docblocks, type hints, длина функций)
EXTRACT: Анонимизировать, добавить source comment
COMMIT: PR с описанием найденных паттернов
```

---

## Часть VII. Спринт-план

### Sprint 1 (Неделя 1-2): Foundation
- [ ] Создать `academici/skills`
- [ ] SKILL_TEMPLATE.md и skills.json
- [ ] GitHub Actions: validate + sync
- [ ] Импорт 12 скиллов из get-zeked/perplexity-super-skills

### Sprint 2 (Неделя 3-4): PHP/Laravel Skills
- [ ] 7 скиллов из skills/php/
- [ ] snippets/php/laravel/ (минимум 10)
- [ ] snippets/docker/

### Sprint 3 (Неделя 5-6): Scanner Agent
- [ ] .skills-scanner.json
- [ ] Сканер скрипт
- [ ] Автоматический PR pipeline

### Sprint 4 (Неделя 7-8): Polish & Expand
- [ ] AI-агент скиллы
- [ ] Архитектурные скиллы
- [ ] Obsidian интеграция

---

## Часть VIII. Полный аудит источников

### Прямо проверенные источники

| # | Источник | Тип | Статус | Что взять |
|---|---|---|---|---|
| 1 | [academici/brain](https://github.com/academici/brain) | Репозиторий | ✅ Отсканирован | skills-lock.json формат, .claude/, структура vault |
| 2 | [get-zeked/perplexity-super-skills](https://github.com/get-zeked/perplexity-super-skills) | Skills collection | ✅ Отсканирован | 12 SKILL.md файлов, YAML frontmatter, gap-analysis |
| 3 | [mwguerra/claude-code-plugins](https://github.com/mwguerra/claude-code-plugins) | Plugin framework | ✅ Референс | Obsidian vault интеграция, CLAUDE.md паттерны |

### Референсные источники (предоставлены)

| # | Источник | Ключевые паттерны |
|---|---|---|
| 4 | [anthropics/claude-code](https://github.com/anthropics/claude-code) | Официальный CLAUDE.md формат, MCP spec |
| 5 | [anthropics/knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins) | Knowledge work паттерны |
| 6 | [PatrickJS/awesome-cursorrules](https://github.com/PatrickJS/awesome-cursorrules) | 500+ rules PHP/Laravel/Docker |
| 7 | [vercel-labs/skills](https://github.com/vercel-labs/skills) | Vercel deployment patterns |
| 8 | [DenisSergeevitch/agents-best-practices](https://github.com/DenisSergeevitch/agents-best-practices) | Multi-agent coordination |

### Рекомендованные дополнительные источники

| # | Источник | ⭐ Stars | Домен | Приоритет |
|---|---|---|---|---|
| 9 | [alexeymezenin/laravel-best-practices](https://github.com/alexeymezenin/laravel-best-practices) | ~25k | PHP/Laravel | 🔴 Высокий |
| 10 | [LaravelDaily/laravel-tips](https://github.com/LaravelDaily/laravel-tips) | ~15k | PHP/Laravel | 🔴 Высокий |
| 11 | [spatie/laravel-permission](https://github.com/spatie/laravel-permission) | ~12k | PHP/Permissions | 🔴 Высокий |
| 12 | [docker/awesome-compose](https://github.com/docker/awesome-compose) | ~35k | Docker | 🟡 Средний |
| 13 | [lorisleiva/laravel-actions](https://github.com/lorisleiva/laravel-actions) | ~2.5k | PHP/Patterns | 🟡 Средний |
| 14 | [drona23/claude-token-efficient](https://github.com/drona23/claude-token-efficient) | — | AI Agents | 🟡 Средний |
| 15 | [awesome-windsurf/awesome-windsurf-rules](https://github.com/awesome-windsurf/awesome-windsurf-rules) | — | AI/IDE Rules | 🟡 Средний |
| 16 | [continuedev/continue](https://github.com/continuedev/continue) | ~20k | AI/IDE | 🟢 Низкий |
| 17 | [kamranahmedse/developer-roadmap](https://github.com/kamranahmedse/developer-roadmap) | ~300k | Taxonomy | 🟢 Низкий |
| 18 | [ziadoz/awesome-php](https://github.com/ziadoz/awesome-php) | ~30k | PHP Ecosystem | 🟢 Низкий |
| 19 | [public-apis/public-apis](https://github.com/public-apis/public-apis) | ~330k | API integrations | 🟢 Низкий |
| 20 | [awesome-selfhosted/awesome-selfhosted](https://github.com/awesome-selfhosted/awesome-selfhosted) | ~230k | DevOps/Infra | 🟢 Низкий |

### Личный опыт (уникальные снипеты)

| Источник | Домен | Снипеты |
|---|---|---|
| AzGuard (academici) | PHP/Security | Injection detection, threat scoring, middleware |
| botkit-dev (academici) | PHP/Bots | Bot framework patterns, webhook handling |
| Filament projects | PHP/UI | Filament v3 resource patterns |
| Permission management | PHP/RBAC | Entity-scoped roles, context systems |

---

*Документ версии 2.0. Подготовлен для агента Fable. Обновлён: 10 июня 2026.*
