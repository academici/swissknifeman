# Changelog — role-founder pack

Версии per-PACK (Keep a Changelog). Каждая запись помечает затронутый install-файл,
чтобы апгрейдящий агент сопоставил изменение с конкретным файлом проекта.

## [0.1.2] - 2026-07-12

### Changed

- **Диета `description` всех агентов пака** (P4.1, план CONTEXT-ECONOMY): frontmatter
  `description:` каждого `agents/*.md` сокращён до cap 600B — 1 показательный `<example>`
  вместо 2-3, анти-триггер сведён к одной фразе прозой. Затронуты install-файлы
  `.claude/agents/{PACK_PREFIX}-*.md` (все агенты пака).

## [0.1.1] - 2026-07-02

### Changed

- Технический бамп: раскатка provenance-headers движка agent-packs (harness) — при
  ре-рендере/upgrade агенты получают header `swissknifeman:generated` с Edit-policy.
  Содержимое агентов пака не менялось. Контекст: SKM-MASTER-002 фаза E.

## [0.1.0] - 2026-06-25

### Added

- Персона-пак `role-founder` (`shape: role`, кросс-стек): субагенты — idea-validator (opus), mvp-scoper (sonnet), founder-cadence (sonnet).
  Доставка по `project.roles` → `role_packs`-карта хаба (вариант A+C). Интервью —
  только `PACK_PREFIX`; модельные тиры литералами в `model:` (standalone-доставка не
  получает `profile.model_tiers`). Файлы: `agents/*.md` → `.claude/agents/{PACK_PREFIX}-*.md`.
