> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: dev-engineering-super-skill
bucket: architect
version: 0.1.0
description: Comprehensive full-stack development and engineering skill merging Perplexity Computer's built-in dev tools with Claude Code's engineering team skills. Covers architecture, frontend, backend, fullstack, QA/testing, DevOps/CI-CD, security, debugging, TDD, code review, and more. Use when writing code, debugging, architecting systems, reviewing code, writing tests, deploying, or doing any software engineering work.
license: MIT
metadata:
  author: get-zeked
  version: '1.0'
adapters: [claude, cursor, fable]
sha256: ""
---

# Супер-скилл разработки и инженерии — навигатор

Тонкий навигатор над внешним монолитом **get-zeked/dev-engineering-super-skill**
(`strategy: notify`, ~80KB операционное руководство по SDLC). Полное тело —
в [`references/full.md`](references/full.md). **Открывай точечно нужный раздел
под конкретный вопрос, не целиком** (экономия контекста).

**Сначала — гранулярный нативный скилл:** `architect/architecture` ·
`api-design` · `data-schema` · `domain-modeling` · `agent-design` ·
`eval-design` · `security-design` · `observability-design` ·
`tech-stack-selection` · `codebase-design`. Справочник — только для сквозного
обзора SDLC, который не покрывает ни один отдельный скилл.

## Карта разделов ([`references/full.md`](references/full.md))

| Задача | Раздел |
|:--|:--|
| Сравнение возможностей Perplexity vs Claude Code | §1 Gap Analysis |
| Диаграммы, C4, ADR, выбор паттернов | §2 Architecture & System Design |
| Скаффолдинг, React/Next.js, бандлы, a11y, SEO | §3 Frontend Engineering |
| API-дизайн, оптимизация БД, аутентификация, нагрузочное тестирование | §4 Backend Engineering |
| Шаблоны, анализ качества, матрица стеков | §5 Fullstack Development |
| TDD, пирамида тестирования, покрытие, Playwright E2E | §6 Testing & QA |
| Систематическая отладка, автоматизация ревью | §7 Debugging & Code Review |
| Пайплайны, GitHub Actions, Terraform, k8s, мониторинг | §8 DevOps & CI/CD |
| Сканирование, OWASP, STRIDE, крипто, комплаенс, IR | §9 Security Engineering |
| Профилирование, диалекты SQL, визуализация, статистика | §10 Data Engineering & Analysis |
| Changelog из git, README, API-доки | §11 Changelog & Documentation |
| Нативные инструменты Perplexity Computer | §12 Unique Perplexity Computer Capabilities |
| Быстрый выбор раздела · сценарии комбинирования скиллов | Quick Reference · Skill Combination Workflows |

## Сопровождение (для мейнтейнеров реестра)

Апстрим `strategy: notify`; отслеживаемое тело — `references/full.md` (`body_path`
в `upstream.json`). SKILL.md написан вручную — `scripts/update-upstreams.sh` его
не перезаписывает. Полный русский перевод тела удалён при переносе на
thin-navigator (P2.3 SKM-MASTER-003) — доступен в git-истории этого файла.
