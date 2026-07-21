# Migration sequence and boundaries

**Основание:** `brief/00-brief.md`, `research/00-user-intent-traceability.md`,
`research/01-target-architecture-options.md`.

## Почему порядок именно такой

Capability contract и provider vocabulary должны появиться раньше renderer'ов: иначе
каждый пакет создаст собственные названия и precedence. Renderer/lock должны появиться
раньше массовой publication: иначе первое dual-provider копирование само создаст drift.
Skills/marketplace предшествуют task-командам, потому что Codex command parity доставляется
через skills. Harness следует после команд, чтобы hooks/agents ссылались на стабильные
entry points. mAInd/analyst мигрируются после provider domain, но до self-hosting pilot,
чтобы пилот оставил neutral telemetry.

## Boundary с FOREMAN

FOREMAN остаётся paused на P1.4. Dual-provider plan не исполняет его items и не строит
unattended multi-provider runner. Он экспортирует provider execution/capability contract
и только после P7.4 передаёт FOREMAN разрешение продолжить. FOREMAN затем должен заменить
Claude-only headless invocation на provider-neutral runner, используя экспортированный
контракт отдельным design/reconcile шагом.

## Boundary с fleet rollout

В миграцию входят schema, resolver, dry-run/doctor и self-hosting проекта
`swissknifeman`. Автоматическое изменение всех 25 project configs и установка artifacts
по флоту не входят: это необратимо расширило бы blast radius до стабилизации FOREMAN.
После FOREMAN создаётся отдельная rollout wave с cohorts, backups/rollback и project-specific
provider selection.

## Design budget

План затрагивает ecosystem core, шесть пакетов и публичные contracts; выбран бюджет 3
design passes. Pass 1 фиксирует evidence/architecture/skeletons. Pass 2 детализирует P0–P3
и reconciliation общей модели. Pass 3 детализирует P4–P7, проводит pre-mortem, finish,
roadmap и design audit preparation.

