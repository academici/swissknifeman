---
name: harness-operations
bucket: repository-bootstrap
version: 0.1.0
description: "Operational map of the harness package (Claude Code environment setup): permissions/mcp/hooks/agent-packs/doctor commands, preset catalog, agent-packs subsystem. Activate for any task touching packages/harness/ or when deciding which preset/MCP/mode to connect to a project."
risk: read
persona: oss-dev
tags: [harness, permissions, mcp, hooks, root-bootstrap]
requires: []
produces_for: []
outputs: [chat]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# harness operations (Claude Code environment)

Internal skill (not exported). Facts only — the `harness` package's capability map. skiller's map
(skill distribution) is [package-architecture]; hub onboarding is [ecosystem-integration]. harness
configures the Claude Code ENVIRONMENT in a project (permissions, MCP, hooks, agent-packs);
skiller delegates to it via subprocess.

[package-architecture]: ../package-architecture/SKILL.md
[ecosystem-integration]: ../ecosystem-integration/SKILL.md
[project-tooling-runbook]: ../project-tooling-runbook/SKILL.md

## When to activate

- A task touches `packages/harness/` (lib, configs/claude-code/, scripts, hooks).
- Need to decide which **permissions preset / MCP server / auto-approve mode** to connect to a
  project for its stack.
- Question "how does harness distribute the environment", "what are agent-packs", "why isn't the
  prompt auto-approved".

## CLI (source of truth — `configs/claude-code/`)

```bash
harness permissions --target . [--preset a,b] [--file F] [--global] [--dry-run] [--list]
harness mcp         --target . --mcp context7,playwright [--list] [--dry-run]
harness hooks       --global                         # hook files in ~/.claude/hooks (once per machine)
harness hooks       --target . --auto-approve strict --memory core:federation
harness agent-packs <list|render|upgrade|doctor> [--pack P] [--target DIR]
                    [--auto] [--answer K=V] [--install-only] [--allow-shell off|safe|full] [--dry-run]
harness doctor
```

Writes to projects are **merge-only**, existing content is not overwritten, backup `*.bak`. All
writers are atomic (tmp+`mv`/`os.replace`).

## Preset catalog (`configs/claude-code/`)

| What | Files | Purpose |
|:--|:--|:--|
| **settings (permissions)** | `settings.{base,laravel,php-package,node,python,docker,global,yolo,product-boundary,agent-teams,observer}.json` | allow/ask/deny per stack; merge-only into `.claude/settings*.json` |
| **MCP servers** | `mcp/{context7,fetch,filesystem,github,memory,perplexity,playwright,sequential-thinking}.json` | bare config objects → `.mcp.json` |
| **auto-approve** | `hooks/auto-approve/` (modes `strict`/`permissive`/`bypass`/off) | PreToolUse hook; order `deny_hard`→`deny_block`→`allow`; lists in `config.json` |
| **memory** | `hooks/memory/` (`file`/`federation`/`agentmemory`) | unified memory; shares state with skiller (`~/.swissknifeman/`) |
| **notify / review-gate / log** | `hooks/{notify,review-gate}/`, `hooks/log-bash-command.sh` | OS notifications; deterministic architecture gate on SubagentStop; Bash log |

**auto-approve modes:** `strict` (allowlist-first, safe default — read-only auto-allow, mutations
→ prompt, catastrophic → deny) · `permissive` (denylist-first, trusted project only) · `bypass`
(everything except `deny_hard` — container/VM only) · `off`. ⚠️ Interpreters (`python -c`,
`awk`/`sed`) are NOT auto-approved (quoted body invisible to the analyzer) —
`trust_inline_interpreters` off by default. ⚠️ `review-gate` executes `check_command` only from a
machine-owned config (not project-local — RCE), unless `ALLOW_PROJECT_CONFIG=1` is set.

**safe-dirs (rm inside trusted folders):** `rm`/`rmdir` targeting strictly inside allowlist roots
bypass `deny_hard` — MACHINE-OWNED allowlist `<monorepo>/safe-dirs.json` (repo ROOT, gitignored,
template `safe-dirs.example.json` — same pattern as maind's config.json; hook resolution ladder:
`$SKM_SAFE_DIRS_CONFIG` → monorepo root via the PATH launcher's realpath → legacy
`~/.swissknifeman/safe-dirs.json`, `init` migrates it into the repo). Commands: `harness
safe-dirs init|list|add|remove|prune-ask`; default includes onboarded projects from
`projects.json`. Verdict — `hooks/auto-approve/lib/safedirs.py`, fail-closed (shlex-argv,
realpath, containment, `.git`/root protection; globs by static prefix; `$VAR`/`$( )`/`xargs rm`
→ deny). A project-level hook-config override does not affect the allowlist. `Bash(rm -r*)` ask
rules were removed from presets (a hook-allow doesn't beat a static ask) — on older projects, run
`harness safe-dirs prune-ask --global --all-projects`.

## agent-packs (persona/stack packs)

`configs/claude-code/agent-packs/` — parameterized bundles of agents+hooks+settings, rolled out
into a project by ROLE or STACK (layered on top of skiller's skills):

- **Stack packs:** `backend-laravel`, `node-frontend`, `python-backend`, `dart-flutter` (detected
  by project type).
- **Role packs:** `role-cto`, `role-founder`, `role-maintainer`, `role-tech-lead` (chosen
  explicitly, layer on top of any stack) + `_common` (shared base).
- `pack.json`: `{pack, version, description, stack.shape, requires.{skills, harness_presets},
  interview[]}`.
- Body templating: `<!-- pack:if KEY -->…<!-- pack:endif -->` blocks; answers from
  `interview[]` deterministically (profile/`--answer K=V`). `--allow-shell off|safe|full` — the
  pack's hook shell policy.
- Lock: `.claude/agent-pack.lock.json` (idempotent render).
- A project profile (`skiller profiles/*.json`) declares `agent_pack: [...]` —
  `integrate`/`onboard` roll them out via harness.

## Key modules (`lib/harness/`)

`cli.py` (dispatcher) · `common.py` (`Env(BaseEnv)`, core re-export) · `settings.py` (merge-only
writers) · `permissions.py` (wraps `scripts/apply-permissions.sh`) · `mcp.py`
(`block_mcp`/`available_mcp`) · `hooks.py` (`block_autoapprove`/`block_memory`/`install_global`) ·
`agentpacks.py` (pack renderer) · `doctor.py`.

## Cross-dependencies

- **skiller delegates here** via subprocess (`skiller connect`/`vendor`/`integrate` call `harness
  permissions|mcp|hooks`; resolution `SKM_HARNESS_BIN` →
  `<monorepo>/packages/harness/bin/harness`; missing harness → graceful skip).
- **Memory shares state with skiller** (`~/.swissknifeman/topology.json`/`projects.json`); paths
  in installed hooks must NOT change (back-compat).
- `.swissknife.json:memory_brain` is written by harness (`hooks --memory`), validated by skiller
  (`CONFIG_KEYS`).

## Checklist (harness edits)

- [ ] stdlib-only in `lib/harness/`; `Env` explicit (frozen); Russian messages.
- [ ] Project writes merge-only + `*.bak` + atomic.
- [ ] New preset/MCP/hook → in `configs/claude-code/`; bash hooks pass `bash -n` (validate.sh).
- [ ] Hook executes untrusted input? → machine-owned/opt-in only (see review-gate).
- [ ] After plugin/command edits — `skiller registry` (the shared marketplace picks up harness).
- [ ] `bash packages/harness/scripts/validate.sh` green.

## Related

[package-architecture] (skiller/distribution), [ecosystem-integration] (hub/onboarding),
[project-tooling-runbook] (multi-source skills + Boost-as-MCP).

## Provenance (root-bootstrap, P1.2)

Class-A private/source-only root-bootstrap identity (D31/D38, `plans/2026.07.24-AGENT-RELIABILITY`):
canonical source is this file's `SKILL.ru.md`; thin projections —
`.claude/skills/harness-operations/SKILL.md` and `.agents/skills/harness-operations/SKILL.md`
(generated by `skiller registry`, never hand-edited). Bucket `repository-bootstrap` is
private/source-only: never published as an ordinary unit/core/marketplace entry, never
vendored/connected into a consumer project.

<!-- ru-source-sha256: 47cc88032230bdcd06d1cc90d71ebba8601fed82498b5acac4972639b43aa4ef -->
