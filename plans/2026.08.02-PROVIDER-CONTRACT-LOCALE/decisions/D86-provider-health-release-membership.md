---
id: D86
date: 2026-08-16
status: accepted
item: P6.3
items: [P6.3]
supersedes: []
superseded_by: null
---
## Решение

Владелец выбрал `define_optional_project_membership` для DecisionRequest
`DR-P6-BRAIN-OPTIONALITY-1` с
`action_digest=abae8218d0bbc27dd17dd97f85c555866a9e669f2726d68d8fb5faf31ee8d1a9`.

D32 продолжает владеть exact-set health evidence по всем sealed P0 project IDs. Release admission
становится отдельным результатом: P6.3 производит frozen
`provider-health-release-membership/v1` carrier с одной явной строкой `required|optional` на
каждый sealed ID. Текущий optional ID выводится только из `P6.1-results.json:sealed_project_id` и
привязывается к exact owner response; все остальные sealed IDs явно `required`. Runtime/schema/code
не содержат ветки по имени `brain` и не хардкодят текущий stable ID.

Optional non-green/unavailable project остаётся в exact health evidence и отдельном
`optional_non_green`, но не создаёт project-scoped release blocker. Required project failures и
global blockers — P5 authorization, membership/source drift, malformed evidence, privacy/cleanup
failure на required project и two-run semantic mismatch — остаются release-gating. Frozen P6.2
runtime, `provider-health-v1` aggregate и public mAInd evidence-set schema не меняются.

RAG:— (repo-grounded: owner response in `decisions/queue.jsonl`,
`findings/P6.3-brain-optionality-authority-boundary.md`,
`research/18-p6-optional-membership-design.md`, D32, P6.1 result and current P6.3 evidence).

## Почему

Exact health coverage and release admission answer different questions. Removing an optional
integration from evidence would hide its health, while making every observed integration a release
gate makes optionality impossible. An explicit sealed membership layer preserves both facts and
keeps the repair at the proven P6.3 boundary.

## Consequences

P6.3 must regenerate its spec bundle and two-run evidence after adding the membership schema and
instance. Missing or unproven membership fails closed; there is no implicit default. Any solution
that requires a public mAInd/runtime shape change, suppresses exact health rows or special-cases a
project identity returns to plan-design instead of widening this owner-approved action.
