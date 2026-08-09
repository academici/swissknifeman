---
id: D145
date: 2026-08-09
status: accepted
item: P5.4
items: [P5.4]
supersedes: []
superseded_by: null
---

## Решение

**`action` остаётся construction input детерминированного writer и не становится полем durable
`DecisionRequest` v1.** Writer строит `canonical_action` из входного `action`, сверяет с ним все
tool-computed fields и удаляет construction input до closed-shape validation и append. Повторная
проверка application восстанавливает `action` только из `canonical_action.action`, уже покрытого
`action_digest`.

## Почему

Frozen schema прямо задаёт `request.additional_properties: false` и не объявляет `action`, но
объявляет `canonical_action` как tool projection. `plan_authority.canonical_action()` и P4 producer
нуждаются в action data только для создания этой проекции. Хранение raw `action` в очереди расширило
бы closed shape; изменение frozen v1 для исправления writer boundary не требуется. RAG:—
(repo-grounded: `root/contracts/decision-request-v1.schema.json` → request/canonical_action;
`packages/task/lib/task/plan_authority.py` → `canonical_action`; D144).

## Consequences

P5.4 реализует boundary внутри `plan_requests.py`, покрывает его negative tests и сохраняет frozen
contract files/authority frame byte-identical. Предыдущая escalation P5.4 снимается как неверное
смешение transient construction input и durable contract payload; D144 остаётся в силе.
