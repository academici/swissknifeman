---
description: Summary hub status mAInd (memory/graph/demons) and ecosystem projects.
allowed-tools: Bash(maind:*)
---
## Node status
!`maind status --json`

## Ecosystem Projects
!`maind projects list --json`

Summarize for the user from the output above: what is raised (memory daemon, graph - nodes/ribs, docs-watcher), how many projects are connected and in which namespace, are there any problems with communication. If the memory demon does not respond, tell me `maind start --only memory`. To check a specific project - `/maind:health`.

> If the blocks above are empty/with error - `maind` not in PATH: install CLI (hub repository → `./install.sh`).
