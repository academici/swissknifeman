---
description: Healthcheck connection between the CURRENT project and the hub mAInd; upon confirmation (or --fix) — auto-repair.
argument-hint: "[--fix]"
allowed-tools: Bash(maind:*)
---
## Communication health (current directory)
!`maind health --cwd --json`

Parse the result: `status` (connected / partial / standalone), `memory_daemon`, availability `agentmemory_mcp` / `maind_mcp` in the project, list `hints`.

If the status is not `connected`:
- when `--fix` in «$ARGUMENTS» OR explicit user confirmation - run `maind health --cwd --fix` (will raise the memory daemon if necessary and add MCP-hub servers into the project), then show updated status;
- otherwise - just list the tips `hints` and suggest running with `--fix`.
