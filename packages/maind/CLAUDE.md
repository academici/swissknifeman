<!-- swissknifeman:instructions:maind:claude-code:common:begin -->
<!-- semantic:maind.identity -->
<!-- semantic:maind.three-planes -->
<!-- semantic:maind.layout -->
<!-- semantic:maind.module-boundaries -->
<!-- semantic:maind.orchestration -->
<!-- semantic:maind.engineering-invariants -->
<!-- semantic:maind.validation-release -->
<!-- instruction:maind.identity -->
## maind.identity
`maind` is the ecosystem control-plane hub for shared memory, cross-project graph data, project and agent registries, and its MCP server.
<!-- instruction:maind.three-planes -->
## maind.three-planes
Keep agent-memory, the maind federation graph, and the Serena code graph as independent planes; they meet only in orchestration and remain namespace-isolated.
<!-- instruction:maind.layout -->
## maind.layout
Keep `bin/maind` as the launcher, `lib/maind/` as stdlib-only logic, `provision/` and `analysis/` as named subpackages, and tests independent of a live daemon.
<!-- instruction:maind.module-boundaries -->
## maind.module-boundaries
Read graph data through `federation.graph_reader`, derive graph facts from sources of truth, and retain canonical adapters `federation` or `disabled` with legacy aliases normalized. Also, never treat `graphify` as a live tool name — manual graph links live only in `<repo>/.maind.graph.json`.
<!-- instruction:maind.orchestration -->
## maind.orchestration
Keep memory, graph, and code-graph modules decoupled; combine them only through onboarding, sync, and orchestration entry points.
<!-- instruction:maind.engineering-invariants -->
## maind.engineering-invariants
Keep `lib/maind/` stdlib-only, pass frozen `Env` explicitly, write JSON atomically, emit English diagnostics, and preserve `project:`, `ns:`, and `global` memory isolation.
<!-- instruction:maind.validation-release -->
## maind.validation-release
Before release run `bash scripts/test.sh` and `bash scripts/validate.sh`, then use Russian Conventional Commit messages.
<!-- swissknifeman:instructions:maind:claude-code:common:end -->
<!-- swissknifeman:instructions:maind:claude-code:extension:begin -->
<!-- semantic:maind.claude-code.plugin-and-mcp -->
<!-- semantic:maind.claude-code.workspace-trust -->
<!-- instruction:maind.claude-code.plugin-and-mcp -->
## maind.claude-code.plugin-and-mcp
The Claude Code plugin exposes only `/maind:*` command wrappers; maind MCP tools arrive through the per-project `maind` server in `.mcp.json`.
<!-- instruction:maind.claude-code.workspace-trust -->
## maind.claude-code.workspace-trust
Claude Code workspace trust is managed by `workspace.py` in `.claude/settings.local.json` and remains separate from provider-agnostic hub state.
<!-- swissknifeman:instructions:maind:claude-code:extension:end -->
