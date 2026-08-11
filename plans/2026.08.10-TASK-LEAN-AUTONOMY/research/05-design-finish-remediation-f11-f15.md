# Design-finish reconciliation — F11–F15

Дата: 2026-08-10.

## Источники

- `findings/03-design-audit-2026-08-10.md` — audit round 2 и repair contracts F11–F15.
- `findings/02-external-rag.md` — exact PRINCE2/PeopleCert и GitHub Spec Kit evidence.
- `research/03-task-transition-map.md` — P1.1 runtime/context/docs ownership map.
- `research/04-field-canary-protocol.md` — P1.2 bounded precondition и canary.
- worktree root/package instructions — generated-doc, package-cwd, provenance и foreign-diff
  boundaries. RAG:— (repo-grounded: root `AGENTS.md`, `packages/task/AGENTS.md`).

## Reconciliation

| Finding | Закрытие в ТЗ | Acceptance carrier |
|:--|:--|:--|
| F11 layout-v2 context | P1.1 владеет `task_contract.py`/`command_render.py`, red-first v2 fixture и отдельным v1 compatibility fixture | v2 exact `continue-root`; четыре live payload проверяются по `next.context`, не по build count |
| F12 Task docs | P1.1 переносит overview/methodology source в `packages/task/docs`, добавляет standalone config и `scripts/docs-sync.sh --check` ownership для aggregate | package build + aggregate build + byte-current projection |
| F13 dirty root ledger | D9 назначает repository owner/foreign-diff owner; P1.2 проверяет только committed `HEAD` и не включает `docs/reference.md` в Files | два exact `git grep ... HEAD` до journal start/canary writes; red → waiting |
| F14 external evidence | findings/02 получает exact official URLs; tolerance claim ограничен публично подтверждённой escalation boundary; Spec Kit claim сужен до “most overhead” | source URL + verification date + high/medium confidence boundary |
| F15 dangling start | original session получает terminal `closed-deviations` через canonical append writer; текущий finish-run получает собственную start/terminal пару | append-only journal + regenerated status |

## Invariants preserved

D1–D8 не отменены и не ослаблены. D9 только назначает authority/precondition для внешнего ledger.
Owner-driven отказ от нового supervisor/control plane остаётся самостоятельным repo-grounded
решением: сужение Spec Kit evidence не превращает decomposition в новый default. P0/P1 не
исполняются; generated views не редактируются вручную; foreign ARTIFEX, `docs/reference.md`,
корневой `roadmap/` и `plans/ACTIVE.md` остаются вне write scope.

## Проверка (verification status)

- RAG: `perplexity-web search_advanced` ×2 OK 2026-08-10; exact official PRINCE2/PeopleCert и
  GitHub Spec Kit pages открыты и сверены напрямую.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: ничего.
- Обходки/[POSSIBLE-DEFECT]: отсутствуют; hook-derived telemetry непригодна из-за отсутствующих
  global hooks/stale run-report и не используется как acceptance evidence.
