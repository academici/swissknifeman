# Changelog — _common

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/); версии — per-PACK (semver).

## [0.5.0] - 2026-07-30

### Added

- **Delegation contract в грамматике PLAN**: новое
  поле формата возврата `; output: <формат возврата>` в строке `Task N -> @<role> : <цель>` и
  секция «Контракт задания» с пятью обязательными элементами задания субагенту
  (`objective`/`output`/`tools`/`sources`/`boundaries`, first-party Anthropic) и правилом
  «задание без формата возврата не выдаётся». Аддитивно — существующие поля грамматики
  (`deps:`/`files:`/`risk:`/`skills:`/`gate:`) не переименованы и не удалены. Затронут
  install-файл `.claude/agents/{PACK_PREFIX}-orchestrator.md` и провайдер-нейтральный канон
  `configs/common/agent-packs/roles.json::_common.orchestrator.content`.

## [0.4.1] - 2026-07-12

### Changed

- **Диета `description` всех агентов пака** (P4.1, план CONTEXT-ECONOMY): frontmatter
  `description:` каждого `agents/*.md` сокращён до cap 600B — 1 показательный `<example>`
  вместо 2-3, анти-триггер сведён к одной фразе прозой. Затронуты install-файлы
  `.claude/agents/{PACK_PREFIX}-*.md` (все агенты пака).

## [0.4.0] - 2026-07-02

### Added

- **`rules/generated-assets.md` — edit-policy generated-ассетов** (install-файл
  `.claude/rules/generated-assets.md`, paths: `.claude/{agents,workflows,hooks}/**`).
  Файл с блоком `swissknifeman:generated` — собственность пака: не редактировать,
  расширять только через Extension-points/`.claude/rules/*-overrides.md`; нужна правка
  core — остановиться и отчитаться (человек делает upgrade пака или правит шаблон).
  Контекст: SKM-MASTER-002 фаза E (provenance-headers + drift-детект в движке harness).

## [0.3.0] - 2026-07-01

### Added

- **Footer `VERIFICATION` + RAG-правило плана в `orchestrator.md`** (field-feedback: агенты
  неохотно жмут RAG при формировании плана). Оркестратор теперь: (1) верифицирует внешние факты
  плана ДО финализации — сначала `perplexity-web` (flat-rate, токен-дёшево), `context7` для API;
  (2) правок ради правок не плодит; (3) допиши в конец плана блок `VERIFICATION` (RAG-движки ·
  **непроверенное → ПОВТОРНЫЙ ПРОХОД** при отказе движка · обходки-`[POSSIBLE-DEFECT]`). Затронут
  install-файл `.claude/agents/{PACK_PREFIX}-orchestrator.md`. Формат — канон-скилл `verify-claims`.

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
