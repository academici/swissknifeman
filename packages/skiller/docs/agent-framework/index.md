# Agent Framework

Опинионированный каркас агент-практик Claude Code экосистемы academici: субагенты,
скиллы, воркфлоу, хуки — версионируемые и переносимые между проектами.

> **Стойка: данные + скилл, НЕ движок-генератор.** Шаблоны — реальные `.md`/`.js`
> файлы в версионируемых паках; установку, адаптацию и upgrade выполняет агент по
> понятным метаданным (manifest + CHANGELOG + lock), а не Python/Mustache-компилятор.
> Это сознательное решение (см. [decisions-ledger](./decisions-ledger)).

## Карта

| Документ | О чём |
|---|---|
| [framework-overview](./framework-overview) | Текущее состояние каркаса — что уже есть (вход для аудита) |
| [decisions-ledger](./decisions-ledger) | Что принято / отклонено и почему (вход для аудита) |
| [roles](./roles) | Универсальные роли-агенты (reviewer/implementer/…); общие, стек — из профиля |
| [skills-index-and-hub](./skills-index-and-hub) | Hub как AI Skills Index; фикс регрессии «скиллы не видны» |
| [post-integration-checklist](./post-integration-checklist) | Проверка целостности после внедрения/upgrade пака |
| `agent-packs` (скилл) | Установка/upgrade версионируемых паков — `skills/system/agent-packs/SKILL.md` |

## Непрерывный аудит

Каркас развивается через периодические аудиты Perplexity. Промт и петля:

- Промт: [workflows/framework-audit](../workflows/framework-audit) — вставляешь в
  Perplexity, на вход даёшь `framework-overview` + `decisions-ledger`.
- Архив прогонов: [audits/](../audits/) (raw + триаж по каждому).
- Ledger источников: `packages/skiller/references/framework-audits.md`.

Петля самоякорящаяся: каждый аудит стартует от пост-предыдущего состояния, поэтому
не перепредлагает уже готовое или отклонённое.

## Компоненты (пакеты)

- **harness** — версионируемые паки (`configs/claude-code/agent-packs/`), хуки,
  settings, MCP. Раздаёт файлы в `.claude/` проекта (merge-only).
- **skiller** — скиллы + hub (AI Skills Index) + playbook-скилл `agent-packs`.
- **maind** — память и граф (опц. персистентный task-граф — отложено).
