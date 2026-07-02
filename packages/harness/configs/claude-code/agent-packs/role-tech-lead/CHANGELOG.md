# Changelog — role-tech-lead pack

Версии per-PACK (Keep a Changelog). Каждая запись помечает затронутый install-файл,
чтобы апгрейдящий агент сопоставил изменение с конкретным файлом проекта.

## [0.2.1] - 2026-07-02

### Changed

- Технический бамп: раскатка provenance-headers движка agent-packs (harness) — при
  ре-рендере/upgrade агенты получают header `swissknifeman:generated` с Edit-policy.
  Содержимое агентов пака не менялось. Контекст: SKM-MASTER-002 фаза E.

## [0.1.0] - 2026-06-25

### Added

- Персона-пак `role-tech-lead` (`shape: role`, кросс-стек): субагенты — sprint-planner (opus), delegation-triage (sonnet), review-gatekeeper (sonnet).
  Доставка по `project.roles` → `role_packs`-карта хаба (вариант A+C). Интервью —
  только `PACK_PREFIX`; модельные тиры литералами в `model:` (standalone-доставка не
  получает `profile.model_tiers`). Файлы: `agents/*.md` → `.claude/agents/{PACK_PREFIX}-*.md`.
