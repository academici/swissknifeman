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

P0 — последовательная contract-design цепочка, а не параллельный research fan-out:

1. P0.1 пересчитывает repository inventory и классифицирует coupling.
2. P0.2 потребляет baseline и фиксирует единый язык, support-level semantics и scenarios.
3. P0.3 потребляет утверждённый язык и запечатывает capability/artifact contracts + ADR.
4. P0.4 потребляет frozen contracts и запечатывает migration/FOREMAN/fleet gates.

Каждый следующий item зависит от deliverables предыдущего. Критерий обязательной оркестрации
`plan-protocol` не срабатывает: четыре scope не независимы, поэтому workflow-скрипт создал бы
ложный параллелизм и гонку при freeze contracts.

## Несущие решения детализации

- Inventory — воспроизводимый артефакт с tree/worktree anchor, а не вручную переписанные числа.
- Ubiquitous language хранится отдельно от implementation schema; термины проверяются scenarios.
- Contract получает `frozen`/`v1.0.0` только после явной записи Approval Owner в D-log.
- P0 не замораживает несуществующий «provider execution contract». FOREMAN после P7.4 получает
  bundle: P0 capability/artifact/migration-gate contracts + P4 command/routing contract + P7
  release evidence. Это устраняет прежнюю неоднозначность D7 без преждевременного дизайна P4.
- P0.4 утверждает структуру гейтов, но не снимает паузу FOREMAN и не запускает fleet rollout.

## Pre-mortem: план провалился через 6–12 месяцев

| Кластер отказа | Ранний сигнал | Mitigation | Owner/item |
|:--|:--|:--|:--|
| Два provider tree стали двумя канонами | ручная правка generated adapter без source change | source/rendered hashes, managed boundary, drift+repair contract | P0.3 → P2 |
| Пакеты используют разные значения одного capability | одинаковое слово даёт разные diagnostics | glossary + scenario matrix + enum compatibility rules до P1 | P0.2/P0.3 |
| Временный bootstrap объявлен финальной доставкой | `.agents/`/global MCP не воспроизводятся install/update | inventory class `bootstrap-only`; cleanup и self-host E2E gate | P0.1/P0.4 → P7.2/P7.3 |
| Автономность Codex ошибочно приравнена к безопасности | `approval_policy=never` принят как расширение sandbox | раздельные approval/sandbox/trust capabilities; explicit full-access profile | P0.2/P0.4 → P5.2 |
| Claude Code регрессирует во время Codex migration | existing commands/settings больше не проходят current validate/E2E | Claude compatibility hard gate и двухсторонние fixtures | P0.4 → P3–P7 |
| FOREMAN возобновлён по факту «код вроде готов» | P7.4 не имеет точной precondition table и evidence refs | frozen migration-gate contract + adversarial P7.4 verdict | P0.4/P7.4 |
| Fleet изменён до стабилизации self-hosting | diff в project configs вне swissknifeman | explicit no-write fleet gate; отдельный rollout plan после FOREMAN | P0.4/P7.4 |
| Документация capability matrix расходится с runtime | README редактируется отдельно от manifest | генерировать matrix из manifest и проверять drift | P0.3 → P7.1 |

## Verification

- RAG: fresh Codex manual helper ×1 OK; `perplexity-web` official-Anthropic query ×1 OK;
  mAInd memory recall ×1 OK.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: exact schema полей будущих P1/P2 manifests — намеренно не
  фиксируется P0-design сессией; определяется P0.2/P0.3 через owner gate и затем реализуется P1/P2.
- Обходки/[POSSIBLE-DEFECT]: временные `.agents/skills` и global MCP остаются bootstrap-only;
  P0.4 обязан удержать их вне frozen distribution contract.
