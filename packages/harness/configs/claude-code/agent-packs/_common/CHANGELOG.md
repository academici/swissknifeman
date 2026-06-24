# Changelog — _common

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/); версии — per-PACK (semver).

## [0.1.0] - 2026-06-24

### Added

- Стек-агностичный субагент `orchestrator` (`agents/orchestrator.md`): delegate-only
  tech-lead, разведка ролей через `.claude/agents/{PACK_PREFIX}-*.md`, машиночитаемый
  план `Task N → @<prefix>-<role>` с режимами Sequential / Parallel-max2 / Gated.
- Интервью: `PACK_PREFIX`, `MODEL_ORCHESTRATOR` (default `inherit`).

### Migration notes (agent-facing)

- Первая версия — апгрейда нет.
- Устанавливать вместе со стек-паком; `PACK_PREFIX` должен совпадать с его префиксом,
  иначе `@<prefix>-<role>` не резолвятся в роли стек-пака.
- Рекомендованный тир: `MODEL_ORCHESTRATOR=opus` (планирование выигрывает от сильной модели).
