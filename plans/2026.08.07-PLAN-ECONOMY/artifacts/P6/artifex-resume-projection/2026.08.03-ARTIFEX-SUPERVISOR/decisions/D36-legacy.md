---
id: D36
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P3 keeps Codex/Claude as separate pure argv/event mappers over `worker-envelope-v1`; one shared P3.4 process runner alone owns subprocess, timeout, caps, redaction and orphan handling. RAG:— (repo-grounded: `research/09-p3-provider-adapter-design.md`).

## Почему

Additive adapters preserve the P1 neutral SSOT, while one runner prevents the reliability boundary from drifting by provider.
