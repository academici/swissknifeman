# P2.1 case — agentools field audit

**Case ID:** `agentools`
**Audit date:** 2026-09-21
**Executor route:** Cursor `cursor-grok-4.6-high` / frontier/high (owner-attested). Catalog Cursor frontier pin remains `claude-opus-5-thinking-high` and is not this session's model. `gpt-5.6-sol` / `gpt-6-astra` are for final review only.
**Rubric source:** `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/research/02-p1-measurement-contract.md` · `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/findings/p2-design-method.md` · `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/decisions/D4-p2-multiple-case-method-and-budget.md`
**P1 predecessor:** GREEN `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/findings/01-p1-verified-baseline.md`. Frozen corpus T1–T6 has no project-matched agentools members.

Consumer bytes: `git show <HEAD>:<path>` only. No dirty reads. No consumer write/fix/sync/deploy/onboard.

## Snapshot

| Field | Pre | Post |
|:--|:--|:--|
| Project ID | `agentools` | `agentools` |
| Resolved path | `/home/vostrikov/projects/packages/agentools` | same |
| Unique nonempty `.git` path | 1 of 1 | 1 of 1 |
| Branch | `main` | `main` |
| HEAD | `6658ba89108c3bca2234938d79ef3db80429cb53` | `6658ba89108c3bca2234938d79ef3db80429cb53` |
| `git status --porcelain=v1` hash | `2d35ad9702e6e810b115b286380afdd8ad5ec884a7e9547ebc647413017124fe` | `2d35ad9702e6e810b115b286380afdd8ad5ec884a7e9547ebc647413017124fe` |
| Dirty status entries | 443 | 443 |
| Tracked files | 2098 | 2098 |
| Concurrent drift | — | none (`stable`) |

Design-time HEAD `a39a5cc` is not this execution snapshot; paths were re-resolved from `maind projects status --json`.

**Provider/configuration snapshot:**

- Status `connected`; `trusted=true`; daemon reachable; scope `project:agentools`.
- Declared MCP files `.mcp.json`, `.cursor/mcp.json` — not in `git ls-files` (live MCP `coverage-gap`). Tracked example: `.mcp.json.example`.
- `agentmemory_mcp=false`, `maind_mcp=true`, `code_mcp=false`.
- `skills_lock=false`, `skills_count=0`.
- Agent packs: installed `[]`, `lock=false`.
- `.swissknife.json` enables `claude-code` and `codex` only — **cursor is absent** from `providers.selection` while Cursor hooks and Cursor run-reports exist.
- Stack: protocol-first PHP+Dart MCP layer (`README.md`); root `composer.json` missing at HEAD; `php/composer.json` exists (not content-read; README used for identity).

## Sample ledger

Parsers: `maind.codegraph_usage._load_reports` + `core.codegraph_telemetry.scan_run_report`. 7 recent reports, all Cursor, all `outcome=ok`. Sampled 6 (limit). Codex 0. Claude-code 0. `analyst sessions --project agentools`: no jsonl for encoded cwd.

P1 corpus match: **0 / 6**. Observable classes in sample: ordinary-implementation and ordinary-implementation+memory (5/6 have memory MCP names).

| Pair | Session | Provider | Occurred | Observable class | Memory tool calls | Symbol-like tool calls |
|:--|:--|:--|:--|:--|--:|--:|
| AO-P1 | `ae796d1b-20f8-4c6a-8f24-e240c4f98dbb` | cursor | 2026-09-20T18:31:41Z | ordinary-implementation + memory | 16 | 24 |
| AO-P2 | `cc4b3936-badc-4de8-9ef9-dee2ab8a0346` | cursor | 2026-09-20T13:37:12Z | ordinary-implementation + memory | 10 | 67 |
| AO-P3 | `6da8118f-da4e-4c10-a5b2-45587b035450` | cursor | 2026-09-20T06:45:51Z | ordinary-implementation | 0 | 0 |
| AO-P4 | `2386c9a7-0fd6-43df-9f87-7f7c60090b81` | cursor | 2026-09-19T18:42:24Z | ordinary-implementation + memory | 8 | 14 |
| AO-P5 | `97016ca1-6b55-41db-b81d-36ebc05a9759` | cursor | 2026-09-19T13:44:04Z | ordinary-implementation + memory | 7 | 0 |
| AO-P6 | `1017c71d-683d-4042-84ff-81e1c7cf362a` | cursor | 2026-09-19T03:28:43Z | ordinary-implementation + memory | 2 | 0 |

AO-P1/AO-P2 also list `MCP:replace_content` / `MCP:onboarding` / `MCP:get_symbols_overview`. AO-P4 lists `MCP:maind_graph_project` and `MCP:list_memories`. `scan_run_report` still reports `codegraph.calls=0` on the scan of 7 sessions.

## Source-read ledger (≤24)

HEAD `6658ba89108c3bca2234938d79ef3db80429cb53`. Attempted `composer.json` — missing at HEAD (not a read).

| # | Path | Bytes | SHA-256 |
|--:|:--|--:|:--|
| 1 | `CLAUDE.md` | 3752 | `99dd3110d4c70ff6cc87ad308dd83c062290e05b277086eb63629df0a5551c14` |
| 2 | `.swissknife.json` | 253 | `808d89ca9d724d01a16c760263e25c76340876ba92ca355490835e14010905ca` |
| 3 | `.swissknifeman/provider-artifacts.lock.json` | 59499 | `7244c2c01afcfedb9e9ac8761eec419785d21bcefd6008364ba9a8426cf10df6` |
| 4 | `.cursor/hooks.json` | 716 | `67ab8ea01230e442a1823d6366bbdfddb85c101d474ab91c7c061ea9b8d3ef61` |
| 5 | `.cursor/hooks/lifecycle.py` | 30148 | `a680d9bb820b4f12772d8d2d77aa19b3b60758a73d11cde03f3ba3b1d1be018b` |
| 6 | `README.md` | 2435 | `cedc4bfa3632b268ec1e5f95a37ada13175873d83b20d8fe5e2b66779f4c89` |
| 7 | `plans/AGENTOOLS/00_MASTER_PLAN.md` | 34886 | `f3d758c9c46cb64e2e15ba75b82419c5bd3bcf9721a65b0e2c2fdfe3938118e2` |

Tracked index not fully shown: no `AGENTS.md`; 644 paths under `plans/AGENTOOLS/`; 69 `.agents/plugins/bundles/core/...` files treated as vendored/generated-style delivery and **not** content-read (exclude vendor/generated). Cursor hook surfaces are tracked.

## Swissknifeman surface / activation matrix

| Surface | Tracked presence | Activation in sample | Coverage |
|:--|:--|:--|:--|
| Root instructions | `CLAUDE.md` only: managed healthcheck + swissknifeman hub index (`skills=232` in comment). No `AGENTS.md`. 0 `semantic:` markers | Health `--fix` is always-on prose for Claude-shaped reads | observed |
| Skills | 0 in maind skills_count; 69 vendored `.agents/plugins/bundles/core` paths indexed, not read | No SKILL.md reads in tool names | inventory; body cost unmeasured |
| Agent packs | none installed | n/a | observed empty pack set |
| Hooks | `.cursor/hooks.json` sessionStart memory, command-log, tool-telemetry, run-report; lifecycle.py present; lock records Codex+Cursor harness adapters | 7/7 sampled reports are Cursor `run_summary` schema 2 — consistent-with sessionEnd run-report hook | Cursor activation observed; Codex hook files locked but 0 Codex reports |
| MCP | example tracked; live json untracked; `code_mcp=false` | Heavy `MCP:find_symbol` / `get_symbols_overview` / `replace_content` in AO-P1/P2/P4 | telemetry name mismatch coverage-gap |
| Task | 644 tracked plan files; master plan still points at `/task:dev` | Not swissknifeman plan-protocol Task surfaces in the 6 pairs | large local plan corpus is agentools-owned, not P2 product |
| Provider selection | `.swissknife.json` omits cursor | Sample is 7/7 Cursor | config vs observed provider conflict |

## Evidence rows

| ID | Rubric | Claim | Label | Source type | Commit / session | Provider | Denominator | Limitations |
|:--|:--|:--|:--|:--|:--|:--|:--|:--|
| AO-E01 | footprint/activation | No tracked `AGENTS.md`; `CLAUDE.md` is healthcheck + hub index (3752 bytes), not the umbrella root dump seen in corex. | observed | git show | `6658ba89` | claude-shaped file | 1 root instruction file | Cursor always-on cost not measured |
| AO-E02 | footprint/activation | `CLAUDE.md` still requires `maind health --cwd --fix` before ordinary work. | observed | git show | `6658ba89` | claude-code | 1 file | Same P1 C09 hypothesis locally; no session-failure link |
| AO-E03 | footprint/activation | Cursor lifecycle hooks and `provider-artifacts.lock.json` records for `harness.cursor.lifecycle` exist; `.swissknife.json` does not enable cursor. | observed | git show | `6658ba89` | cursor vs json selection | 1 lock + 1 swissknife + 1 hooks.json | Does not prove connect-channel intent |
| AO-E04 | observed outcome | 6/6 sampled reports `outcome=ok`, cwd-matched. 5/6 include `MCP:maind_memory_*`. | observed | run-report parser | AO-P1–P6 | cursor | 6/7 recent; 5/6 memory names | Usefulness ordinal not scored |
| AO-E05 | observed outcome | AO-P1/P2/P4 show symbol/replace MCP names (24, 67, 14 calls) while `scan_run_report` fleet scan is `calls=0`. | coverage-gap | parser vs `codegraph_tool_op` | AO-P1, P2, P4 | cursor | 3/6 pairs with symbol-like names | `MCP:` prefix not mapped in telemetry helper |
| AO-E06 | observed outcome | AO-P4 tool names include `MCP:maind_graph_project` and `MCP:list_memories`. | observed | run-report | AO-P4 | cursor | 1/6 pairs | Graph *tool name*, not federation usefulness |
| AO-E07 | flow/friction | 443 dirty entries; 644 tracked plan files; 69 vendored plugin bundle files. | observed | git ls-files + status | `6658ba89` | n/a | 644 plans / 2098 tracked | File count is not prompt cost |
| AO-E08 | flow/friction | Master plan resume protocol still says implementation via `/task:dev`. | observed | git show | `6658ba89` `plans/AGENTOOLS/00_MASTER_PLAN.md` | n/a | 1 file | Document age vs current Task catalog uncompared beyond this citation |
| AO-E09 | collaboration | No `Task` tool in the 6 pairs. | observed | run-report | AO-P1–P6 | cursor | 0/6 | Not a collaboration-quality measure |
| AO-E10 | collaboration | satisfaction/well-being | n/a | — | — | — | — | SPACE: no direct data |
| AO-E11 | coverage/provenance | Codex reports 0; Claude transcripts 0; live MCP untracked; cursor missing from swissknife selection. | coverage-gap | parsers + ls-files | HEAD | mixed | 0 Codex / 7 Cursor | Provider-parity of telemetry is incomplete |

## Value / friction observations

- **Value (bounded):** This case is the densest of the three for Cursor hub-tool *names*: memory in 5/6 pairs, symbol/replace MCP in 3/6, plus one `maind_graph_project` (AO-E04–E06). That is activation evidence for P3, not a keep/go on memory or codegraph.
- **Friction (bounded):** Health `--fix` always-on (AO-E02); Cursor used while `.swissknife.json` omits cursor (AO-E03); large tracked plan+plugin trees (AO-E07).
- Not productivity.

## Coverage / validity threats

- HEAD moved since P2 design (`a39a5cc` → `6658ba89`); execution uses the live commit only.
- Same telemetry naming gap as corex.
- Vendored `.agents/plugins` not read; their first-turn cost is unmeasured.
- No pack, no AGENTS.md: context-dependent vs corex/edufy.
- satisfaction/well-being n/a.

## Case-local summary

agentools at `6658ba89` is a smaller, PHP+Dart protocol package with Cursor hooks and Cursor-only completed reports, frequent memory/symbol MCP names, no agent-pack, no AGENTS.md, and a provider-selection file that does not list Cursor. Telemetry zeros remain coverage gaps. P3 should treat this case as the richest Cursor activation sample of the three, still without usefulness scores. P4 may note provider-selection drift and health `--fix` as friction candidates only.
