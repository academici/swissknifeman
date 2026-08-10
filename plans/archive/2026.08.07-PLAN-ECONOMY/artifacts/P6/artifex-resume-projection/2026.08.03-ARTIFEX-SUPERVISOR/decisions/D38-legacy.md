---
id: D38
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P3 permissions are explicit and narrowing-only: Codex uses the verified sandbox plus non-interactive approval config, Claude uses `dontAsk` plus exact available/allowed tools; bypass/yolo, ambient fallback and `--bare` are forbidden. RAG:✅ 2026-08-03 official permission/CLI facts in `findings/07-p3-provider-runtime-recon-2026-08-03.md`; mapping is contract-driven.

## Почему

A headless worker must refuse rather than wait for approval, widen authority or discard repository instructions/hooks.
