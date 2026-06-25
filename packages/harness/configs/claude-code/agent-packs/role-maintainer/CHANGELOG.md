# Changelog — role-maintainer pack

Версии per-PACK (Keep a Changelog). Каждая запись помечает затронутый install-файл,
чтобы апгрейдящий агент сопоставил изменение с конкретным файлом проекта.

## [0.1.0] - 2026-06-25

### Added

- Персона-пак `role-maintainer` (`shape: role`, кросс-стек): субагенты — issue-triager (sonnet), contribution-reviewer (sonnet), release-conductor (opus).
  Доставка по `project.roles` → `role_packs`-карта хаба (вариант A+C). Интервью —
  только `PACK_PREFIX`; модельные тиры литералами в `model:` (standalone-доставка не
  получает `profile.model_tiers`). Файлы: `agents/*.md` → `.claude/agents/{PACK_PREFIX}-*.md`.
