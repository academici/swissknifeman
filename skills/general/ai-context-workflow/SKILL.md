---
name: ai-context-workflow
bucket: general
version: 0.1.0
description: "Редактирование AI-контекста проекта: .ai/guidelines, .ai/skills, boost.json; запрет правки сгенерированных CLAUDE.md/AGENTS.md; обязательный php artisan boost:update; объяснение цикла для Cursor и Claude Code."
risk: write
persona: oss-dev
tags: [ai, workflow, conventions]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# AI Context Workflow

## Когда активировать

- Нужно добавить, переименовать или изменить skill/guideline в `.ai/`.
- Нужно добавить пакет или skill в `boost.json`.
- Пользователь правит контекст агентов или спрашивает, почему дублируются файлы в `.cursor/skills/` vs `.ai/skills/`.
- Задача — описать другому разработчику, как безопасно обновлять правила для ИИ.

Смена архитектурных договорённостей в коде должна сопровождаться правками в **`docs/dev/*`** (и workflow-доках при необходимости) и здесь, в **`.ai/`**, иначе агенты разъедутся с репозиторием. См. **`.ai/guidelines/architecture.md`**.

## Единый источник правды

| Что правим руками | Что не правим |
|---|---|
| `.ai/guidelines/*.md` | `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` в корне |
| `.ai/skills/*/SKILL.md` | `/.claude/skills/` (в `.gitignore`, генерируется) |
| `boost.json` (список skills) | Сгенерированные куски в корне после Boost |

После любого изменения в таблице слева выполнить **`php artisan boost:update`** или **`composer ai:sync`**.

## Обязательный порядок

1. Правка только в `.ai/` или `boost.json`.
2. `composer ai:sync` (или `php artisan boost:update`).
3. Убедиться, что новый skill добавлен в `boost.json` → `"skills": [...]`, иначе генерация его не подхватит.
4. Коммит: исходники `.ai/*`, `boost.json`; не коммитить игнорируемые сгенерированные файлы.

## Дублирование

- Кастомные скиллы проекта живут в **`.ai/skills/`**.
- Vendor- и Boost-скиллы подмешиваются через `boost.json`; их не копировать вручную в `.ai/`, если не нужна переопределяющая версия.
- Каталог `.cursor/skills/` в репозитории может содержать копии из экосистемы агента; **правило редактирования доменных скиллов проекта** — всё равно через `.ai/skills/` и повторная генерация.

## Ссылка для людей

Полный разбор для людей: каталог `docs/ai/` (`index.md`, `source-layout.md`, `scenarios.md`, `environment.md`); в собранной документации портал `/ai`.
