---
id: D7
date: 2026-08-12
status: accepted
item: P1.1
items: [P1.1, P1.2, P1.3]
supersedes: []
superseded_by: null
---
## Решение

Все неархивные Layout v1 планы детерминированно мигрируются в v2 до удаления v1 execution
reader/schema/branches. После cutover активный план без `Layout | v2` fail-closed; архивный v1 остаётся
историческими байтами, но не исполняется Task runtime. RAG:✅ 2026-08-12
`Microsoft Durable Functions versioning` + `Kubernetes deprecated API migration`;
выжимка и URLs — `findings/02-rag-resilience-and-schema-cutover-2026-08-12.md`.

## Почему

Удаление execution compatibility до миграции live plans может оставить их невозобновляемыми; после
доказанного zero-active-v1 второй executable schema лишь сохраняет divergence и regression surface.

