---
description: Reroll managed artifacts mAInd (MCP, graph, memory, hooks, skill) for connected projects.
argument-hint: "[<project-id> | --all | --namespace NS]"
allowed-tools: Bash(maind:*)
---
Synchronizing hub managed artifacts **mAInd**. Input: «$ARGUMENTS».
Launcher - `maind` (fallback: `${CLAUDE_PLUGIN_ROOT}/bin/maind`).

## Steps
1. **Purpose** from «$ARGUMENTS»: specific `<project-id>` · `--all` (all enabled) · `--namespace <NS>`. If empty, ask (default offer `--all`).
2. **Preview**: `maind sync <target> --dry-run --json` — show what will change.
3. **Application** by confirmation: `maind sync <target> --json`.
4. **Report**: for each project/to the provider - ok / skip / unchanged. The set can be narrowed down by a flag `--only`: `mcp,code-graph,graph,memory,memory-hook,health-hook,health-doc,feature-log-hook,ecosystem-skill,gitignore`. `gitignore` appends `.gitignore` lines for service files that already match `configs/gitignore-policy.json`. It does not run `git rm --cached`.
