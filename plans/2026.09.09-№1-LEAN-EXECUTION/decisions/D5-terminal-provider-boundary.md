---
id: D5
date: 2026-09-09
status: accepted
item: P4.1
items: [P4.1, P4.2]
supersedes: []
superseded_by: null
---
# D5 — Own a repository transcript seam, not the external provider final write-site

**Actor:** design-author/gpt-5.6-sol/high
**Evidence:** RAG:— P10.6 source artifact and current Task/Harness/Artifex code boundaries

## Решение

P4 implements the terminal-admission verifier, lease/resume state and `final_allowed` transcript
event in repository-owned code and adapters. It must not claim to prevent a conversational final
emitted wholly outside those call sites; that boundary is reported as an explicit capability gap
with an integration contract and proof fixture.

## Почему

Testing a local result normalizer is not proof that an external chat transport obeys the guard.

**Consequences:** P4 acceptance distinguishes local deterministic proof from external-provider
integration evidence; no external deployment/write is authorized by this plan.
