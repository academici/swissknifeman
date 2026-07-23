# 2026.07.23-FLEET-DUAL-PROVIDER — Fleet rollout двух провайдеров

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.07.23-FLEET-DUAL-PROVIDER |
| Title | Последовательная двухпровайдерная настройка проектов |
| Version | 0.4.0 |
| Status | 🟡 In progress |
| Document Type | Executable Master Plan |
| Authoring Model | frontier |
| Design Passes | 3/3 — ecosystem-core fleet change: initial design, RED remediation, final cross-phase reconciliation |
| Last Updated | 2026-07-23 |
| Repository | swissknifeman |
| Related Packages | skiller · harness · maind |
| Execution Mode | phase-first |
| Target Operator Classes | implementation (exec) · frontier (design/audit) |
| Approval Owner | Dmitry Vostrikov — пользовательский запрос от 2026-07-23 |
| Home | repo:plans/2026.07.23-FLEET-DUAL-PROVIDER |

## 1. Context

Реализация dual-provider завершена, но первый fleet dry-run выявил, что connect
канал не может доставить Codex в consumer-репозитории. Требуется устранить этот
разрыв без неявной глобальной установки и без перезаписи user/managed drift.
После механизма раскатка идёт строго по одному зарегистрированному проекту,
фиксируя каждый сбой в плане и возвращаясь к owning source. Пропавшие временные
записи не являются целью автоматического удаления. RAG:— (repo-grounded:
findings/00-fleet-dry-run-2026-07-23.md).

## 2. Execution Rules

- Каждый проект применяется только после его dry-run и проверяется health/managed locks.
- `--repair` применяется лишь к подтверждённому managed-drift; чужие конфликты не перезаписывать.
- Любой новый fleet-отказ сначала воспроизводится тестом и исправляется в owning package.
- Временные отсутствующие реестровые пути пропускать с явной находкой, не удалять автоматически.
- Один item за раз; после terminal item обновлять status, journal и handoff.

## 3. Routing

| Items | Model class/effort | Exec | Почему |
|:--|:--|:--|:--|
| P0.1 | frontier/high | manual | открытый fleet-contract carrier для внешнего Codex connect consumer |
| P0.2 | implementation/high | manual | меняет eligibility/failure semantics fleet sync |
| P1.1–P2.1 | implementation/high | manual | внешнее состояние/конфликты требуют проверки по каждому проекту |

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P0 | Устранить блокер connect-проекции | 1/2 | 🟠 Done with deviations |
| P1 | Пилот и стабилизация | 0/2 | 🟡 In progress |
| P2 | Последовательный fleet rollout | 0/1 | ⬜ Not started |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-07-23 | P1/P2 полностью детализированы до первого exec; carrier implementation остаётся P0 input. | Исполнимый fleet порядок и retry boundary должны быть проверяемы до provider writes. RAG:— (repo-grounded: findings/00-fleet-dry-run-2026-07-23.md) |
| D2 | 2026-07-23 | Drift остаётся fail-closed, repair — только явный. | Иначе автоматизация может стереть локальную работу. RAG:— (repo-grounded: packages/skiller/lib/skiller/skillset.py:857) |
| D3 | 2026-07-23 | Внешний Codex connect consumer получает repo-contained marketplace и self-contained selected plugin bundles под существующим artifact lock; self-host остаётся thin, install/cache/enable — отдельное user-level действие. | Официальный Codex manual подтверждает repo marketplace и contained local sources, frozen publication contract запрещает внешний thin path и implicit native install. RAG:✅ 2026-07-23 (`findings/P0.1-codex-connect-carrier-verification.md`, Build plugins). |
| D4 | 2026-07-23 | P0.1 включает owning generated Codex bundle, его conformance test, существующую CLI-документацию и `[Unreleased]`; внешняя копия обязана получать runtime tree уже из self-contained generated source. | Attempt 2 audit доказал, что downstream carrier не может восстановить runtime files, отсутствующие в generated `core`; repo `docs-maintenance`/`release-discipline` требуют синхронных user-facing docs и changelog. Spec синхронизирован до attempt 3; поздняя синхронизация docs/CHANGELOG в attempt 2 остаётся process deviation. RAG:— (`findings/P0.1-attempt2-independent-audit.md`). |
| D5 | 2026-07-23 | Owner directed P1.1 to skip `sibintek-insiders`: the actively worked consumer must not be mutated; redesign the pilot selection before retry. | P1.1 dry-run found unmanaged root instruction ownership and package-target absence; `--repair`/`--force` are outside scope. RAG:— (`findings/P1.1-pilot.md`). |
| D6 | 2026-07-23 | Consumer instruction scope is topology-derived: `root` always; each package scope only for its exact real package directory, preserving frozen order. Ordinary consumers do not receive synthetic swissknifeman package targets. | Existing mAInd broadens every request to all scopes while harness already accepts an ordered subset; this resolves the topology conflict without relaxing ownership or changing the harness contract. RAG:— (`research/01-pilot-selection-contract.md`). |
| D7 | 2026-07-23 | Replacement pilot is the first registry-order external candidate passing the complete no-write eligibility/provider/worktree/instruction preflight; D5 target and self-host are excluded. No match blocks without writes; repair/force stay forbidden. | Committed evidence does not prove a named next candidate, so deterministic selection is the only non-guessing carrier. RAG:— (`research/01-pilot-selection-contract.md`). |
| D8 | 2026-07-23 | Owner directed rollout to continue: P1.1 reopens as a fresh manual execution beginning with a new live registry-order D7 scan, not a pre-named candidate or a deferral. Exactly one normal apply remains conditional on one candidate passing the complete preflight. | Eligibility is live external state; the owner authorizes a new evidence pass but does not relax D5–D7, permit repair/force, or authorize overwriting dirty/unmanaged bytes. RAG:— (repo-grounded: `brief/01-refinements.md`). |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-07-23 | issue-planner/frontier | Design pass 1/3: initial fleet dry-run converted into P0 carrier/eligibility design. |
| 2026-07-23 | issue-planner/frontier | Design pass 2/3: RED audit-1 разобран; добавлены parity acceptance, retry и полная карта rollout. |
| 2026-07-23 | issue-planner/frontier | Design pass 3/3: cross-phase reconciliation audit-2 — JIT removed, routing/files/budget reconciled. |
| 2026-07-23 | task-plan-run / gpt-5.6-sol/high | P0.1 закрыт: project-scoped Codex connect carrier публикует contained selected bundles с Claude parity — детали см. phases/P0.md P0.1 Completion Notes. |
| 2026-07-23 | root-review / gpt-5.6-sol/high | P0.1 переоткрыт, attempt 2: внешний bundle терял runtime support files (`snippets/`, `references/`, scripts/assets), поэтому claim self-contained не подтверждён. |
| 2026-07-23 | task-plan-run / gpt-5.6-sol/high | P0.1 закрыт attempt 2: runtime support tree доставляется с consumer exclusions и symlink-containment preflight — детали см. phases/P0.md P0.1 Completion Notes. |
| 2026-07-23 | independent-audit / gpt-5.6-sol/high | P0.1 attempt 2 RED: generated `core` остаётся thin; item переоткрыт attempt 3, spec синхронизирован D4. |
| 2026-07-23 | task-plan-run / gpt-5.6-sol/high | P0.1 закрыт attempt 3: owning generator публикует canonical runtime tree в generated `core` и внешний carrier — детали см. phases/P0.md P0.1 Completion Notes. |
| 2026-07-23 | independent-audit / gpt-5.6-sol/high | P0.1 attempt 3 GREEN: canonical → generated → external runtime transfer, exclusions, containment и commit topology подтверждены без findings. |
| 2026-07-23 | task-plan-run / gpt-5.6-terra/high | P0.2 закрыт с deviations: unavailable registry paths стали provider-qualified skips; no-write fleet rerun классифицировал consumer blockers — детали см. phases/P0.md P0.2 Completion Notes. |
| 2026-07-23 | task-plan-run / gpt-5.6-terra/high | P1.1 skipped by owner decision: `sibintek-insiders` не изменялся после fail-closed instruction dry-run — детали см. phases/P1.md P1.1 Completion Notes. |
| 2026-07-23 | task-plan-design / gpt-5.6-sol/xhigh | P1.1 redesigned and reopened by D6/D7: topology-derived instruction scopes plus deterministic replacement selection; item spec commit `7df01cbc`. |
| 2026-07-23 | task-plan-run / gpt-5.6-terra/high | P1.1 blocked: D6 repair is validated, but D7 selected no compatible external candidate — details in `phases/P1.md` P1.1 Completion Notes. |
| 2026-07-23 | task-plan-design / gpt-5.6-terra/high | P1.1 reopened by D8: rollout continues with a fresh non-named registry-order D7 scan and one conditional normal apply. |
