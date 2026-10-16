# CLI

Launcher `bin/maind` — thin bash-wrapper: checks the environment and calls
`python3 -m maind <repo_root> <cmd> [args]`. Node root - installation directory maind.

## Commands

```bash
maind start [--only memory|graph]      # raise node workers
maind status [--json]                  # summary: memory, graph, agents, projects

maind memory start                     # start memory daemon (Node)
maind memory run                       # foreground (exec node) — for systemd
maind memory stop                      # stop (only his own, does not touch anyone else's)
maind memory status [--json]

maind service install                  # systemd --user: memory daemon autostart
maind service {start|stop|restart|status|logs|uninstall}   # unit control

maind graph query --from project:brain --depth 2 [--edge-types depends_on,uses] [--json]
maind graph neighbors --node project:maind --direction in
maind graph stats [--json]
maind graph --project flexcrm          # graph of one project (federation)
maind graph --cross [--namespace NS]   # cross-project layer (_index.db), opt. one group
maind graph derive [--project ID | --all]   # collect graphs from composer/Brain/override/skills
maind graph rebuild                    # rebuild _index.db
maind graph export --project flexcrm   # project graph → Mermaid (copy-paste in .md)
maind graph export --cross [--raw]     # entire cross-project layer → Mermaid (--raw: without ```-wrappers)

maind agents register <id> [--project P --pid N --kind K]
maind agents heartbeat <id>
maind agents list [--all --json]
maind agents kill <id> [--force]

maind projects list [--namespace NS] [--json]
maind projects health [--project ID | --namespace NS | --all] --evidence-set FILE --json
maind projects sync --from brain [--path DIR]
maind namespaces [--json]              # namespace-ecosystem groups and their member projects

maind deploy [--project ID | --all] [--with-code] [--dry-run]   # MCP-hub servers (= sync --only mcp)
maind sync [--project ID | --namespace NS | --all] [--only mcp,graph,memory,memory-hook,health-hook,health-doc,ecosystem-skill] \
           [--mode install|update|auto] [--dry-run] [--json]        # roll out controlled artifacts
maind health [--cwd | --project ID] [--plan-repair | --apply-repair] [--strict] [--json]     # healthcheck project connection with the hub
maind workspace sync [--dry-run] [--no-allow] [--no-mode]           # trust Claude to ecosystem projects
maind workspace status [--json]
maind run <project> <capability> [-- args]   # pull command brain / swissknifeman

maind fleet manifest                                      # projects + groups by common packages (JSON)
maind fleet duplicates [--group PKG | --projects a,b] [--min-tokens N] [--json]  # cross-project duplicates (jscpd)
maind fleet similar [--group PKG | --projects a,b] [--threshold T] [--json]  # semantically similar code (embeddings)

maind onboard <project> [--with-code] [--with-brain]            # unified onboarding

maind migrate from-brain <.projects.json> [--force]
maind migrate from-agentmemory <dir> [--force]

maind mcp                              # run as MCP-server (stdio)
maind mcp tools [--json]               # tool list and tools_digest (contract mcp-tools/v1)
maind topology show|init [--json]      # machine map of hub nodes (<state>/maind/topology.json)
maind doctor [--quiet] [--json]        # environment diagnostics; --json prints a list of check-result/v1
maind doctor --audit mcp|claude|deny|core|pao|settings|all [--json]  # fleet-project audit
maind doctor --context [--json]        # fleet-aggregation always-on footprint of the first move
                                        #   (skiller budget --first-turn for each project)
maind doctor --skill-drift             # drift ecosystem-mcp/ecosystem-setup from template, by project
maind doctor --channel-drift           # duplicate channel skiller (connect+vendor for one bucket)
maind doctor --gitignore-drift [--project ID] [--block] [--json]
                                        # .gitignore/tracking of each project vs service file map
                                        #   (packages/aicore/configs/gitignore-policy.json); --block — ready lines .gitignore
                                        #   maind sync provisioner gitignore appends those lines
maind verify [--json]                  # proof of work of 3 planes: write real or empty
maind analyze [--cwd | --project ID] [--session ID] [--no-health] [--json]
                                        # post-run verdict with check provenance run-report
maind version                          # git SHA + path to node
```

`analyze` trusts legacy run-report only after verification project/session/provider identity.
Absolute `files_changed` outside the selected project are also considered a conflict provenance. Like this
report is excluded from RED-reasons and returns as `ATTENTION` with
`RUN_REPORT_PROJECT_MISMATCH`; lack of trusted report lowers confidence, but does not prove
product error.

## Machine topology

`maind topology show [--json]` prints the three hub nodes (`brain`, `swissknifeman`, `projects_base`) of the machine map
`<state>/maind/topology.json`; `maind topology init [--brain PATH] [--swissknifeman PATH] [--projects-base PATH] [--yes]` writes it (the previous file
is kept through `aicore.state.backup`). The legacy `~/.swissknifeman/topology.json` is read, with one warning, while the new
file does not exist. `skiller topology` is an alias that prints `SKILLER_TOPOLOGY_MOVED` and calls `maind topology`. The
connected-project registry is `skiller list --json`.

## Doctor

`maind doctor --json` prints a list of `check-result/v1` documents: `maind.environment` (the Python floor is
`aicore.MIN_PYTHON`, 3.9), `maind.config`, `maind.registry`, `maind.memory`, `maind.mcp` (with `tools_digest` and
`protocol_versions`) and `maind.health`; the text form prints `<status> <check_id>: <observed>` and exits 1 when a check
fails. The probe writes nothing and prints no secret. Repair is separate: `maind health --plan-repair` (read-only) and
`maind health --apply-repair`.

## How it works

- Parsing arguments - `common.parse_args` (flags `--x` + positional), not argparse.
- Every command is a function `cmd_X(env, argv)` from the dictionary `COMMANDS` in `cli.py`.
- Launch context - frozen-dataclass `Env` (node root, command, HOME) — is transmitted
  explicitly, without modular globals. Therefore, everything is easy to test.

Next: [MCP-server →](./mcp)
