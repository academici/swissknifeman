---
id: D37
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Every attempt starts a new non-persistent provider process with no resume/continue/session reuse; native child-agent surfaces are disabled, and any non-disabled child policy is capability-unsupported/OWNER in v1. RAG:✅ current non-persistence/tool/feature controls in `findings/07-p3-provider-runtime-recon-2026-08-03.md`; child refusal is internal policy.

## Почему

Current CLIs do not expose one proven common hard cap for child count, scope and budget; a prompt-only limit is not authority.
