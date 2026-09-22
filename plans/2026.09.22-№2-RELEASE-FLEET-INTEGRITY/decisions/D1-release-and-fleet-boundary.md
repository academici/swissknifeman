---
id: D1
date: 2026-09-22
status: accepted
item: P1.1
items: [P1.1]
supersedes: []
superseded_by: null
---
# D1 — Исправлять owning source и выпускать новый candidate

**Actor:** repository-owner + owner-agent/gpt-6-high
**Evidence:** RAG:— `brief/00-owner-brief.md`, current tag/release state

## Решение

`v0.24.0` остаётся неизменным историческим tag. Исправление version
truth, attestation, provider publication и fleet delivery входит в новый patch/minor
release candidate, выбранный штатным SemVer tooling. Все downstream writes проходят
ownership/preimage/readback gates; внешний publish остаётся owner gate.

## Почему

Изменение опубликованного tag разрушило бы воспроизводимость, а ручная
правка generated files повторила бы исходную ошибку.

## Consequences

Generators, release workflow и fleet sync обязаны доказать
coherence и idempotence до выдачи команды на отдельное publish approval.
