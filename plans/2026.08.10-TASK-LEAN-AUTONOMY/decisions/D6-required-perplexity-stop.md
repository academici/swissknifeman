---
id: D6
date: 2026-08-10
status: accepted
item: P0.1
items: [P0.1, P0.2]
supersedes: []
superseded_by: null
actor: repository-owner (accepted via brief/00-brief.md and brief/01-refinements.md)
model: gpt-5.6-sol/high (authored; actual effort not independently attested)
evidence: RAG:— brief/00-brief.md + brief/01-refinements.md + findings/02-external-rag.md
---

## Решение

Если задача явно требует Perplexity Web, проверяется базовый search. Его недоступность или
функциональный отказ после одной узкой повторной попытки является owner-visible stop; другой
web-инструмент не подменяет обязательный retrieval молча.

## Почему

Advanced-режим может деградировать отдельно от MCP; источник, требуемый владельцем, является
частью acceptance. RAG:— (repo-grounded: `brief/00-brief.md`, `brief/01-refinements.md`,
`findings/02-external-rag.md`).
