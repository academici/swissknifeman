# Changelog — _common

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/); версии — per-PACK (semver).

## [0.2.0] - 2026-07-01

### Added

- **Директива liveness-supervision в `orchestrator.md`** (rate-limit incident
  2026-07-01). Для фонового `dev-loop` оркестратор допиши блок `SUPERVISION` —
  контракт основной сессии: доклад статуса каждые ~30 мин (`Monitor`/`ScheduleWakeup`
  на `git log <base>..HEAD`), `PushNotification` на застой/`<failures>`, `TaskStop`
  при нужде. Затронут install-файл `.claude/agents/{PACK_PREFIX}-orchestrator.md`.
  Мотивация: рантайм `agent()` авто-ретраит rate-limit до высокого капа → затяжной
  hang не виден изнутри скрипта; надёжный предохранитель — только внешний supervisor.

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
