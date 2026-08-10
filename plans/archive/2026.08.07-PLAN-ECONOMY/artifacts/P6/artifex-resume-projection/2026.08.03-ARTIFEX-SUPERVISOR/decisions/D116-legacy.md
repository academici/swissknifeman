---
id: D116
date: 2026-08-06
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

[OWNER-DIRECTION:P5.2-IMMUTABLE-G2B-BRIDGE] `brief/31-p5.2-immutable-g2b-bridge-owner-direction-2026-08-06.md` supersedes D114/D115 package mutation only: the sole bridge lives in P5.2 `run-pilot.py`, invokes unchanged G2B business mappers through `worker.run` under the exact admission root/caps, and returns minimized observations. **Consequences:** G2B manifests remain immutable and P5.2 may not modify Artifex package files; all D105/no-retry/no-raw-output/provider restrictions remain unchanged. RAG:— (owner-grounded: `brief/31-p5.2-immutable-g2b-bridge-owner-direction-2026-08-06.md`).

## Почему

Preserves the terminal G2B digest while authorizing the missing execution adapter only for the three P5.2 rows.
