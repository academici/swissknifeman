---
id: D15
date: 2026-08-02
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

`provider-control-plane-v1` composes existing SSOTs additively: provider config owns desired selection, capability manifest owns support, artifact locks own managed provenance, and adapters own only their provider projection/observation/status. It must not introduce a monolithic rival schema or read provider output as canonical intent. RAG:— (repo-grounded: archived provider contracts, `core/provider/{config,manifest,registry,artifact,lock}.py`, `findings/05-p1-contract-verification-2026-08-02.md`).

## Почему

This is the only option that preserves predecessor identities and independent adapters; replacement/output-derived alternatives create a second source of truth.
