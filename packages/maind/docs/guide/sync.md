# Sync — unified provisioning

`maind sync` — one command that parses `config.json` and rolls out **managed
artifacts** for connected projects. Fan-out for projects and resolution paths/scope are included in the general
context (`sync.py`), to avoid duplicating the loop in each module; `maind deploy` — this
`sync --only mcp`.

## Command

```bash
maind sync --all                                   # all enabled-projects, all providers
maind sync --project flexcrm                       # one project
maind sync --namespace axioma                      # fan-out by namespace-group
maind sync --all --only mcp,graph --mode update    # narrow set and mode
maind sync --all --dry-run --json                  # plan without record, machine readable
```

Selecting projects (`select_projects`) — exactly one of `--project` / `--namespace` / `--all`.

## Provisioners (in order of application)

| Provisioner | What it does | Module |
|:--|:--|:--|
| `mcp` | writes MCP-hub servers (agent-memory + maind [+ code graph]) in `.mcp.json` project | `deploy.py` |
| `code-graph` | starting `.serena/project.yml` (when `code:true`, engine Serena) — language + ignores + initial_prompt | `codegraph.py` |
| `graph` | `derive` project graph from sources + rebuild `_index.db` | `derive.py` |
| `memory-hook` | `MODE=manual`: remove digest and leave native off; `MODE=maind`: explicitly enable SessionStart digest | `health.py` |
| `health-hook` | opt-in SessionStart-hook (`observability.session_start_health_hook`; disabled by default) | `health.py` |
| `health-doc` | managed block «priority №1» in `CLAUDE.md` | `health.py` |
| `ecosystem-skill` | controlled skill `ecosystem-mcp` (what the MCP-tools, connections, repairs) in `.claude/skills/` | `skilldoc.py` |
| `setup-skill` | controlled skill `ecosystem-setup` (project tooling decision tree) in `.claude/skills/` | `skilldoc.py` |
| `skills-catalog` | `skiller update` — re-resolve skill catalog (buckets/exclude from disk); new skill for an already selected bucket (e.g. `pao` in `php`) arrives without manual re-run | `orchestrate.py` → `skm:update` |
| `agent-pack` | deterministic rolling/upgrade agent-pack(ov) project profile | `orchestrate.py` → `env:agent-pack` |
| `output-style` | `outputStyle: lean` (terce-agent-voice, token-saving) to all `.claude/settings.local.json`; opt-out — `project.output_style: "off"` | `orchestrate.py` → `env:hooks` |
| `router-config` | directory intent-router (`.claude/agent-router.config.json`), only for projects with the hook enabled | `orchestrate.py` → `env:router` |
| `instructions` | managed instruction blocks for the selected providers | `sync.py` → harness instructions |
| `gitignore` | appends `.gitignore` lines from `packages/aicore/configs/gitignore-policy.json` for service files that already exist (`ignore`, and `portable-or-ignore` when the file holds a machine path). Does not delete lines and does not run `git rm --cached`. Last, so files written earlier in the same sync are visible | `aicore/state/gitignore.py` |

> `memory-hook` reads «intent» memory from the committed `<project>/.swissknifeman/hooks.env` (`MEMORY_MODE`; legacy
> `<project>/.claude/memory.env.ini` while there is no carrier), which `maind onboard --memory` sets through
> `harness hooks --memory` (skipped with `PARTNER_UNAVAILABLE` without harness). So auto-download can be extended to already connected
> projects without full onboard: `maind sync --all --only memory-hook`.
>
> `skills-catalog`/`output-style` — the same principle for skills and terse voice: `skiller
> integrate` (and through it `maind onboard`) puts them only on **new** onboardings;
> `maind sync --all` regularly rolls out the same thing to already connected projects.

`--only mcp,graph,...` limits the set (names are checked against the registry, typo → error).

## Modes (`--mode`)

«Sync method by area»:

| mode | behavior |
|:--|:--|
| `install` | create only if there is no artifact |
| `update` | update an existing one (drift by content-hash) |
| `auto` (default) | both: no → install, deprecated → update, fresh → skip |

`changed` in the report means the applied mutation: graph-provider compares contents
story (serialization is deterministic), a doc/hook — content-hash block. Successful delegated
`--dry-run` proves that the plan is feasible, but is not flagged as a change only by `rc=0`;
after stable live sync this saves JSON idempotence gate verifiable. Dry-run nothing
does not write and shows the plan.

In the root repository SwissKnifeMan `ecosystem-mcp` and `ecosystem-setup` also exist as
thin projections `repository-bootstrap`, belonging to `skiller registry`. If the file is explicitly
indicates this `canonical` and `generator`, `maind sync` returns `foreign-owner` and not
overwrites neither of the two skill projections. `maind doctor --skill-drift` doesn't count them
pattern drift maind; such projections need to be corrected through `skiller registry`.

## How to find out what sync is generally needed (drift-gate)

`sync` deterministic (content-hash), but **does not call itself**. Provider templates
(`templates/skills/ecosystem-mcp/SKILL.md` etc.) and skill registry (`skiller`) over time
are being improved, but already onboarded projects do not receive this until someone manually restarts
sync — «rolls out regularly» from the note above requires a trigger. Read-only checking that
trigger is overdue:

```bash
maind doctor --skill-drift        # ecosystem-mcp/ecosystem-setup: absent/stale by fleet enabled-projects
skiller doctor --vendor-drift     # vendor-skills (buckets/include CORE_SKILLS): add/update/remove by fleet
```

Both - dry run (`plan_sync`/`_apply_managed_skill(..., dry=True)`), do not write anything; in
normal `doctor` (without flags) — one at a time summary-line. Run after ANY point
(`--only`) onboarding/integration - not only after `--all`: `--only` sinks most often and
leave «half of the project» unsynchronized because not the entire set is applied
providers. Real incident (2026-07): project `agelto` worked for two weeks without a code graph
Serena — `ecosystem-mcp` was rolled out BEFORE the rule was added to the template «first graph,
then grep», and no one restarted sync, to pick it up; the agent quietly read the files
entirely instead `find_symbol`, drift was not visible without this command.

## Example output

```
sync (mode=auto, projects 1, providers: mcp, graph, memory, memory-hook, health-hook, health-doc, ecosystem-skill)
  ✓ mcp             flexcrm            .mcp.json
  ✓ graph           flexcrm            12n/9e (code 7, doc 1)
  ○ memory          flexcrm            memory daemon not running The project does not have
  ✓ health-hook     flexcrm            installed
  ✓ health-doc      flexcrm            updated
  ✓ ecosystem-skill flexcrm            .claude/skills/ecosystem-mcp/SKILL.md
```

Next: [Trust (workspace) →](./workspace)

`feature-log-hook` is a retirement-only provisioner: sync removes old managed SessionEnd commit
copying hooks and their scripts, preserving foreign hooks. It never installs a feature-log hook
or writes graph seeds/commit history into memory. The cleanup is idempotent and supports dry-run.
