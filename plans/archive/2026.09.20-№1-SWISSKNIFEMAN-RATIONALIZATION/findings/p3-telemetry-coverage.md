# P3 telemetry coverage — 2026-09-21

Exact execution provider for this item: Cursor `cursor-grok-4.6-high` / frontier / high.
Durable run `690aa4985d3ba14e4531e6eb2ff2af17bf1297cbac25dfbc1a00043704691638`.
Owner-attested route; catalog `class_selectors.frontier` still pins `claude-opus-5-thinking-high`.
`cursor-agent` argv had `--force --sandbox disabled --trust --approve-mcps` and no `--model`, `--workspace`, or `task:` prompt.
`task.session_context` has Codex and Claude adapters only.

RAG:— 2026-09-21 from tracked source/tests plus one live Cursor probe. No product, telemetry, or consumer writes.

## Field ownership

| Field | Automatic capture owner | Pilot worksheet owner | If unobservable |
|:--|:--|:--|:--|
| Run identity | Provider hook `session_id`/`conversation_id` written at `sessionEnd` | Live `CURSOR_CONVERSATION_ID` and Task `run_id` | `n/a\|coverage-gap` |
| Mechanism exposure | Typed `maind` / `codegraph` blocks, else classified `tools.by_name` | Exact MCP tool name and tool-call timestamp | `n/a\|coverage-gap` |
| Calls | Sidecar counts / transcript counts | Worksheet call list | `n/a\|coverage-gap`, never `0` |
| Result / evidence quality | Claude transcript `results`/`found_*`; Cursor sidecar has none | Returned memory id/score or symbol path | `n/a\|coverage-gap` |
| Acceptance | Frozen P1 oracle on an A/B arm | Probe known-nonempty result | `n/a\|coverage-gap` |
| Tokens / time | Provider `metrics` / `usage`; Cursor reports `metrics: {}` | Wall clock of the probe call if recorded | `n/a` |
| Ordinary reads / searches | `Read`/`Grep`/`Glob`/`rg` counts | Same names on the worksheet | `n/a\|coverage-gap` |
| Unrelated writes | Run-report files-changed / git status | Scoped `git status` of declared Files | `n/a\|coverage-gap` |

Automatic report and worksheet are never merged into one number.

## Provider matrix

Sources: `packages/harness/configs/claude-code/hooks/run-report/_lib.py` (`parse_events`, `_maind_tool`, `_codegraph_tool`); `core/codegraph_telemetry.py`; `packages/harness/lib/harness/hooks.py` Cursor `_tool_telemetry` / `_run_report`; `.cursor/hooks/lifecycle.py`; `packages/analyst/lib/analyst/readers/__init__.py`; `packages/maind/lib/maind/codegraph_usage.py`; tests in `core/tests/test_codegraph_telemetry.py`, `packages/harness/tests/test_run_report.py`, `packages/harness/tests/test_cursor_hook_render.py`.

| Axis | Claude Code | Codex | Cursor (exact provider) |
|:--|:--|:--|:--|
| Identity | Transcript session + `.claude/runs` schema 2 | Sidecar/transcript session; `.codex/runs` | Hook `conversation_id` → `.cursor/runs/<id>.json` schema 2 at `sessionEnd`. Live env `CURSOR_CONVERSATION_ID=9c5317fe-29c7-4d9c-aa34-0e80a0d1c877` ≠ hook id `6a029f10-06e7-42fa-a428-cfef0a22014b` (P2.1 run). **coverage-gap** |
| Mechanism exposure | `mcp__maind__maind_memory_*` and `mcp__codegraph__*` / `mcp__plugin_core_codegraph__*` classified in transcript | Same parser when a transcript exists; otherwise calls-only sidecar | Live preToolUse names are `MCP:<tool>` (2-part). Tests and `codegraph_tool_op` only classify 3-part `MCP:plugin-core-codegraph:<op>`. `MCP:find_symbol` and `MCP:maind_memory_*` stay opaque `by_name` keys. **coverage-gap** |
| Calls | Counted per tool and per typed op | Counted when transcript/sidecar present | Sidecar counts the 2-part name. Typed `codegraph` block is written only when `_codegraph_tool` matches. Live 2-part names do not match. **n/a for typed ops** |
| Result / evidence quality | `maind.*.results`, `found_total`, `found_max` from tool_result JSON (`test_maind_mcp_metrics`) | Reuses Claude parser if transcript exists; else none | Sidecar stores `{tool, ts}` only. No result text, score, found-count, or usefulness. **n/a** |
| Acceptance | Not in the report; needs the P1 oracle | Same | Same. Analyst has `("cursor", 1)` only; live files are schema 2 → `ANALYTICS_UNKNOWN_SCHEMA`. **coverage-gap** |
| Tokens / time | Transcript usage accumulator | Sidecar/metrics when present | `metrics: {}` in committed-shape `.cursor/runs/*.json`; `cursor.duration_ms` is whole-session, not per tool. **n/a for tokens** |
| Ordinary reads / searches | `Read`/`Grep`/`Glob` in `tools.by_name` | Same when captured | Same sidecar names (`Read`, `Grep`, `Shell`) |
| Unrelated writes | Transcript Edit/Write file list | Sidecar/files when present | Not in the Cursor schema 2 summary used here; worksheet uses git status |

`packages/maind/lib/maind/codegraph_usage.py` `scan_project` feeds `.cursor/runs` through `scan_run_report`. A Cursor report whose `by_name` has only `MCP:find_symbol` yields `calls=0`, which must be recorded as a parser miss, not zero value.

Claude is the only provider with automatic memory result quality. Codex without a transcript is calls-only. Cursor automatic capture cannot bind this item's identity, typed exposure, result quality, tokens, or analyst acceptance.

## Controlled probes on the exact provider

Both probes used this Cursor session's MCP servers (`maind`, `plugin-core-codegraph`). They are worksheet evidence. They do not repair automatic capture.

### Memory — known nonempty result

| Step | ID / evidence | Result |
|:--|:--|:--|
| store | MCP `maind_memory_store` key `p3-probe-9c5317fe` scope `project:swissknifeman` | `success: true`, id `mem_mub0hgx0_c76c9db132ce`, `createdAt` `2026-09-21T08:57:03.181Z` |
| recall | MCP `maind_memory_recall` query `p3-probe-9c5317fe scan_run_report` | Top hit id `mem_mub0hgx0_c76c9db132ce`, score `24.64`; additional lower-score unrelated facts |
| forget | MCP `maind_memory_forget` key `mem_mub0hgx0_c76c9db132ce` | `deleted: 1`, `success: true` |
| post-forget recall | same query | `mem_mub0hgx0_c76c9db132ce` absent |

Committed source named in the seed: `core/codegraph_telemetry.py` `scan_run_report`. The seed is deleted; leftover `mem_ms2xc809_2220776884ad` (`probe`) is a pre-existing foreign fact and was not touched.

Sidecar (wrong conversation `6a029f10-06e7-42fa-a428-cfef0a22014b`): `MCP:maind_memory_store` `2026-09-21T08:57:03.156Z`; `MCP:maind_memory_recall` `2026-09-21T08:57:09.481Z`. No result payload.

### Codegraph — known nonempty result

| Step | ID / evidence | Result |
|:--|:--|:--|
| find_symbol | `plugin-core-codegraph` `find_symbol` name_path `scan_run_report` path `core/codegraph_telemetry.py` | Function at lines 83–92 |

Sidecar: `MCP:find_symbol` `2026-09-21T08:57:03.686Z`, no `codegraph_op`. `codegraph_tool_op("MCP:find_symbol")` is `None`; `codegraph_tool_op("MCP:plugin-core-codegraph:find_symbol")` is `find_symbol` (`core/tests/test_codegraph_telemetry.py`).

## Binding verdict

The exact provider can invoke both mechanisms and return a known nonempty result on the worksheet.

It does not bind, in one automatic report, run identity, typed mechanism exposure, result quality, tokens, and downstream analyst acceptance.

Paired A/B runs are not expanded. Both mechanism verdicts are `defer` with this gap. That is a GREEN P3 outcome under D5.

## Environment notes (non-gating)

- Managed Cursor observer rule is active; this item wrote only declared plan Files.
- Live MCP configs remain untracked (P2 remainder).
- `maind health --cwd` was `connected` before the probes.
