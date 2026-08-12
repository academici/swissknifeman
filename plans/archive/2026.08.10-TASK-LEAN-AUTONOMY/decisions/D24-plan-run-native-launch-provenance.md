---
id: D24
date: 2026-08-11
status: accepted
item: P3.3
items: [P3.2, P3.3]
supersedes: []
superseded_by: null
actor: repository-owner (explicit instruction to fix and complete the plan without repeating an unavailable check)
model: gpt-5.6-terra/high (current execution session)
evidence: RAG:✅ official OpenAI Codex CLI/config/app-server documentation + local app-server probe
---

## Решение

Для manual `task:plan-run` заменить недостижимый precondition «provider API текущего thread
аттестует обе оси» на fresh native Codex launch provenance: exact `-m` и
`-c 'model_reasoning_effort="…"'` из handoff выбирают маршрут до начала item. В обоих Task
Contract write-sites manual item записывает `source="cli-flag"`; это не является заявлением о
независимо наблюдаемом runtime telemetry.

## Consequences

P3.3 исправляет canonical command, regression test и generated projections; после его green
terminal state P3.2 немедленно выполняется через тот же fresh launch contract. `plan-exec`,
private rollout files, static config fallback и generic route-evidence semantics остаются вне
изменения. Если официальный API позже даст programmatic runtime route, это отдельная работа.

## Почему

Официальная CLI documentation показывает `/status` для отображения session configuration и
`/model` для выбора model/reasoning; configuration reference документирует model и reasoning
overrides для нового thread. Документированный app-server `thread/read` в проверенной установленной
версии не вернул model/effort. Следовательно, private rollout parsing был бы хрупкой недокументированной
зависимостью, а прежний gate создавал повторяющийся невыполнимый цикл. RAG:✅
(`https://learn.chatgpt.com/docs/codex/cli`,
`https://learn.chatgpt.com/docs/config-file/config-reference`,
`https://learn.chatgpt.com/docs/app-server`).
