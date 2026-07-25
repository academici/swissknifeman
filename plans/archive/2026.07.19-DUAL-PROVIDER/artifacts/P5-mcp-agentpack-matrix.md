# P5 MCP and agent-pack projection matrix

**Item:** P5.4
**Contract:** `provider-harness-contract` v1.0.0 (D85)
**Scope:** temp-root/cache-contained render, check and repair evidence only. No MCP server,
hook, workflow, subagent, user-global, self-host, fleet or FOREMAN operation was started.

## Independent inventory and common source

| Inventory | Independent source | Common result |
|:--|:--|:--|
| MCP servers | `configs/claude-code/mcp/*.json` | 8 IDs; missing=0, extra=0, duplicates=0 |
| Agent packs | declared `pack.json` entries | 10 packs |
| Agent roles | declared `role=agent` entries | 44 roles; missing=0, extra=0, duplicates=0 |

`configs/common/agent-packs/roles.json` is the semantic role/content source: identity,
complete multiline description/examples, tokenized semantic content, skill IDs, semantic tool
and command requirements, P4 model class, and activation requirements. It contains no provider
path, selector, frontmatter, slash command, hook or workflow spelling. Named semantic tokens
cover roster, managed-role override, orchestration-carrier, tool and model requirements; they are
resolved only by named adapters.

`configs/claude-code/agent-packs/role-bindings.json` is a Claude-only binding with exactly 44
unique `(pack_id, role_id)` records and only `model_selector` and `color`. Model trace resolves a
selector placeholder through the declared current pack interview default, then applies frozen P4:
`haiku → economy`, `sonnet|inherit → implementation`, `opus → frontier`. Result: economy=8,
implementation=22, frontier=14; missing=extra=duplicates=unknown_selector=model_class_mismatch=0.

## Named projections

| Surface | Claude Code | Codex | Safety / evidence |
|:--|:--|:--|:--|
| MCP | Claude-only `configs/claude-code/mcp/bindings.json` → existing project `.mcp.json` merge-only consumer | Codex-only `configs/codex/mcp/bindings.json` → P2 whole-file `.codex/config.toml`, native `mcp_servers` TOML | Each binding envelope declares exactly one provider, scope, target and serialization; cross-provider binding is rejected. Claude foreign entries are preserved. Codex render/check/managed-drift repair uses P2 lock plan. Secret references stay `${…}` placeholders. |
| Agent role | Common source + Claude selector/color binding synthesizes the full legacy consumer | Common source + P4 class map synthesizes `.codex/agents/<prefix>-<role>.toml` | Generated Claude bytes equal every one of 44 legacy consumer sources before the established installation provenance wrapper. |
| Managed role override | Claude token maps to its named rule declaration | Codex token maps to `.codex/agents/<prefix>-reviewer-overrides.toml` | This is a provider path mapping, not a hidden pack-guard hook or blocker. |
| Orchestration carrier | Claude token maps to the established carrier | No Codex wrapper | `_common/orchestrator` blocks with `HARNESS_ACTIVATION_UNSUPPORTED:codex:command.workflow-carrier:P4`, because the frozen P4 mapping lacks that native carrier. |

Codex accounting is exact: **43 actual native consumer files rendered and inspected; 1 qualified
block; total 44.** Every actual TOML was parsed and scanned for Claude path/selector/slash/workflow
tokens. Each consumer carries its semantic skills, command IDs and P4-selected model.

## Focused evidence

`tests.test_provider_agentpacks` proves the independent 44-role exact set, binding/default/P4
model trace with missing/extra/unknown-selector negatives, byte-identical full Claude consumers,
43 render + 1 qualified block, actual TOML inspection, Codex P2 create→check-noop→managed-drift-repair,
and the default Claude P2 plan path's full-binding validation plus exact legacy bytes.
`tests.test_provider_mcp` proves 8-server exact coverage, trust/unknown/duplicate/resolved-secret
refusal, parsed actual Codex TOML, P2 create→check-noop→repair, and current Claude merge-only
foreign-server preservation. Immediate legacy MCP/agentpack/provenance consumers remain green.

No artifact, lock, report or fixture contains a resolved secret value.
