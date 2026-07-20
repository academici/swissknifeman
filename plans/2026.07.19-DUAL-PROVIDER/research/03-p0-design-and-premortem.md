# P0 design synthesis и pre-mortem

**Дата:** 2026-07-19  
**Основание:**
`brief/00-brief.md`,
`findings/repository-baseline-2026-07-19.md`,
`findings/provider-capabilities-2026-07-19.md`,
`findings/upstream-patterns-2026-07-19.md`,
`research/01-target-architecture-options.md`,
`research/02-sequence-and-boundaries.md`,
project memory `project:swissknifeman` (checkpoint и interim dual-provider audit).

## Декомпозиция P0

P0 — последовательная contract-design цепочка, а не параллельный research fan-out.
После D52 терминальная P0.1 не переписывалась; correction получила отдельный carrier P0.5:

1. P0.1 пересчитывает repository inventory и классифицирует coupling.
2. P0.5 отдельно корректирует umbrella Command Surface observation.
3. P0.2 потребляет оба baseline carrier и фиксирует единый язык, support-level semantics и scenarios.
4. P0.3 потребляет утверждённый язык и запечатывает capability/artifact contracts + ADR.
5. P0.4 потребляет frozen contracts и запечатывает migration/FOREMAN/fleet gates.

Каждый следующий item зависит от deliverables предыдущего. Критерий обязательной оркестрации
`plan-protocol` не срабатывает: пять scope не независимы, поэтому workflow-скрипт создал бы
ложный параллелизм и гонку при freeze contracts.

## Несущие решения детализации

- Inventory — воспроизводимый артефакт с tree/worktree anchor, а не вручную переписанные числа.
- Ubiquitous language хранится отдельно от implementation schema; термины проверяются scenarios.
- Contract получает `frozen`/`v1.0.0` только после явной записи Approval Owner в D-log.
- D59 заморозил migration gates G01–G11 единым decision set: security axes,
  no-write/rollback, reconcile-only FOREMAN bundle, fleet no-op и трассировку рисков.
- P0 не замораживает несуществующий «provider execution contract». FOREMAN после P7.4 получает
  bundle: P0 capability/artifact/migration-gate contracts + P4 command/routing contract + P7
  release evidence. Это устраняет прежнюю неоднозначность D7 без преждевременного дизайна P4.
- P0.4 утверждает структуру гейтов, но не снимает паузу FOREMAN и не запускает fleet rollout.

## Pre-mortem: план провалился через 6–12 месяцев

| Кластер отказа | Ранний сигнал | Mitigation | Gate/evidence | Owner/item |
|:--|:--|:--|:--|:--|
| Два provider tree стали двумя канонами | ручная правка generated adapter без source change | source/rendered hashes, managed boundary, drift+repair contract | G02–G06, G08; P2/P3/P4/P5/P6 conformance + `P7-self-host-e2e.md` | P0.3 → P2.4/P3.5/P4.5/P5.5/P5.7/P6.5/P7.2 |
| Пакеты используют разные значения одного capability | одинаковое слово даёт разные diagnostics | glossary + full provider matrix + compatibility cases before artifact work | G01/G02; frozen P0 contracts + `P1-provider-compatibility-matrix.md` | P0.2/P0.3/P1.1–P1.4 |
| Временный bootstrap объявлен финальной доставкой | `.agents/`/global MCP не воспроизводятся install/update | inventory class `bootstrap-only`; isolated/live E2E; provenance-only cleanup | G08–G10; `P7-self-host-e2e.md`, `P7-bootstrap-cleanup.md`, release audit | P0.1/P0.4 → P7.2/P7.3/P7.4 |
| Автономность Codex ошибочно приравнена к безопасности | `approval_policy=never` принят как расширение sandbox | independent trust/approval/sandbox; explicit-only full access; negative cases | G05/G08/G10; `P5-harness-conformance.md` + P7 security probes | P0.2/P0.4 → P5.2/P5.5/P7.2/P7.4 |
| Claude Code регрессирует во время Codex migration | existing commands/settings больше не проходят current validate/E2E | Claude compatibility hard gates at publication, commands, harness, docs and release | G03–G05, G07–G10; P3/P4/P5/P7 conformance artifacts | P3.2/P3.5/P4.3/P4.5/P5.5/P5.7/P7.1–P7.4 |
| FOREMAN возобновлён по факту «код вроде готов» | нет literal P7.4 GREEN, Owner D# или exact bundle | frozen gate + cold adversarial audit + reconcile-only handoff | G10; `P7-release-audit.md`, manifest, donor row `P1`/handoff delta 0 | P0.4/P7.4 + Approval Owner |
| Fleet изменён до стабилизации self-hosting | diff в project configs вне swissknifeman | protected delta 0; separate post-FOREMAN plan with cohorts/backups/rollback | G11; P7.4 audit now, future fleet-plan evidence later | P0.4/P7.4 + future rollout owner |
| Документация capability matrix расходится с runtime | README редактируется отдельно от manifest | generated matrix with catalog/version hash and exact-set drift check | G07/G10; `P7-provider-docs-conformance.md` + release audit | P0.3 → P7.1/P7.4 |
| Environment defect даёт ложный GREEN | model/effort, hook, MCP, sandbox или lint не подтверждён | D56 immediate disclosure/repair; cold preflight; failed/skipped check remains red | Все G01–G10 reject non-reproducible evidence | Root agent + owner item/phase |
| Audit regression выявлен после close | next phase стартует на stale GREEN | D58 formal reopen/fix-forward, separate repair commit and independent re-audit | Gate reverts to fail until repeated GREEN | Owning item/phase + independent auditor |

### Phase coverage

- P0 обслуживает G01; P1 — G02; P2 artifact conformance входит в G02/G08.
- P3 publication обслуживает G03; P4 command/routing — G04; P5 security/instructions — G05.
- P6 deploy+cold restart обслуживает G06; P7 docs/self-host/cleanup/audit — G07–G10.
- FOREMAN получает только G10 reconcile authority; future fleet wave отделена G11.

## Verification

- Approval Owner: D59, 2026-07-20 — exact seven-point decision set утверждён без
  semantic changes к candidate.1.
- RAG: fresh Codex manual helper ×1 OK; `perplexity-web` official-Anthropic query ×1 OK;
  mAInd memory recall ×1 OK.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: exact schema полей будущих P1/P2 manifests — намеренно не
  фиксируется P0-design сессией; определяется P0.2/P0.3 через owner gate и затем реализуется P1/P2.
- Обходки/[POSSIBLE-DEFECT]: временные `.agents/skills` и global MCP остаются bootstrap-only;
  G08–G10 удерживают их вне frozen distribution contract до provenance-backed replacement,
  rollback proof и Owner-approved cleanup inventory.
