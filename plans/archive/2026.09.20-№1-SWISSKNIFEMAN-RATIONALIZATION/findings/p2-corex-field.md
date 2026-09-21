# P2.1 case — corex field audit

**Case ID:** `corex`
**Audit date:** 2026-09-21
**Executor route:** Cursor `cursor-grok-4.6-high` / frontier/high (owner-attested). Frozen `command-routing.json` Cursor `class_selectors.frontier` still lists `claude-opus-5-thinking-high`; this case does not treat that pin as the live model. Codex `gpt-5.6-sol` / `gpt-6-astra` are reserved for final review, not this observational pass.
**Rubric source:** `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/research/02-p1-measurement-contract.md` · `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/findings/p2-design-method.md` · `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/decisions/D4-p2-multiple-case-method-and-budget.md`
**P1 predecessor:** GREEN `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/findings/01-p1-verified-baseline.md`. Frozen corpus T1–T6 has no project-matched corex members; sampling used recent managed run-reports only.

Consumer bytes were read only as `git show <HEAD>:<path>`. Dirty worktree bytes were not read. No consumer command with write/fix/sync/deploy/onboard semantics was run.

## Snapshot

| Field | Pre | Post |
|:--|:--|:--|
| Project ID | `corex` | `corex` |
| Resolved path | `/home/vostrikov/projects/packages/corex` | same |
| Unique nonempty `.git` path | 1 of 1 | 1 of 1 |
| Branch | `main` | `main` |
| HEAD | `65441b16218ebfc04889385b8b9a1aeff066d217` | `65441b16218ebfc04889385b8b9a1aeff066d217` |
| `git status --porcelain=v1` hash | `4a3bdbb082ccbb2b237ea5513adfd03beafa01b8a3a19c15eab55381399c6fc0` | `4a3bdbb082ccbb2b237ea5513adfd03beafa01b8a3a19c15eab55381399c6fc0` |
| Dirty status entries | 553 | 553 |
| Tracked files | 4500 | 4500 |
| Concurrent drift | — | none (`stable`) |

**Provider/configuration snapshot** (read-only `maind projects status --json`, project `corex`):

- Hub status `connected`; `trusted=true`; memory daemon reachable; scope `project:corex`.
- MCP files declared: `.mcp.json`, `.cursor/mcp.json`. Neither path is git-tracked → live MCP bytes are `coverage-gap` (untracked/dirty forbidden).
- `agentmemory_mcp=false`, `maind_mcp=true`, `code_mcp=false`.
- `skills_lock=false`, `skills_count=0` (swissknifeman/laravel_boost/local all 0).
- Agent packs installed: `_common`, `laravel-package`, `role-maintainer` (`lock=true`, `modified=false`).
- Stack identity from tracked `README.md` / `composer.json`: PHP 8.3–8.5, Laravel 12–13, monorepo `corex/monorepo`.

## Sample ledger

Trusted completed task/run-report pairs: managed Cursor `run_summary` schema 2 via `maind.codegraph_usage._load_reports` + `core.codegraph_telemetry.scan_run_report`. Identity kept as `project=corex` / `cwd` / `session_id` / `provider_id=cursor`. Raw JSON was not substituted for lost identity.

Frozen P1 corpus match: **0 / 6** task classes. Denominator for pairs: 6 Cursor `outcome=ok` of 26 recent reports (19 Claude-code reports had no `outcome` field → not trusted-complete). Codex reports: 0/26.

| Pair | Session | Provider | Occurred | Observable class | Memory tool calls | Symbol-like tool calls | Notes |
|:--|:--|:--|:--|:--|--:|--:|:--|
| CX-P1 | `0eb5daae-2848-4ab3-bb74-776d6a8ed29f` | cursor | 2026-09-20T15:55:19Z | ordinary-implementation + memory | 2 | 0 | Write+Shell plus `MCP:maind_memory_*` |
| CX-P2 | `f33d74ab-865e-456f-b8ad-d3505819f3a2` | cursor | 2026-09-20T15:45:48Z | ordinary-implementation | 0 | 0 | Write+Shell, no hub MCP |
| CX-P3 | `aea46952-7f53-4e8f-b143-39c78e1ace0c` | cursor | 2026-09-20T12:29:44Z | other-read | 0 | 0 | Grep+Read only |
| CX-P4 | `b1aa28ca-90c7-4398-93da-bc7d4e29c80f` | cursor | 2026-09-19T19:08:02Z | ordinary-implementation + memory | 16 | 4 | also `MCP:get_symbols_overview`, `MCP:search` |
| CX-P5 | `7abf2acd-6212-4ed3-9018-32705db05034` | cursor | 2026-09-19T14:21:32Z | ordinary-implementation | 0 | 0 | Write+Task+`MCP:search` |
| CX-P6 | `99be0426-087b-47dd-b3db-c01615b28036` | cursor | 2026-09-19T07:30:37Z | empty-tools | 0 | 0 | `outcome=ok` with empty `tools.by_name` |

Two observable task classes used for the P1 contract mapping: ordinary-implementation and hub-memory-on-implementation. Review/audit, research/design, durable-plan, and environment/provider-fix classes were not evidenced in this sample.

`analyst sessions --project corex --weeks 4 --json`: no Claude jsonl transcripts for encoded cwd `-home-vostrikov-projects-packages-corex` (`n/a`, not zero).

## Source-read ledger (≤24)

All `git show 65441b16218ebfc04889385b8b9a1aeff066d217:<path>`.

| # | Path | Bytes | SHA-256 |
|--:|:--|--:|:--|
| 1 | `AGENTS.md` | 16546 | `f004834e7f38532ad794d9a300556661338ca13affad5625379c02fd1e009001` |
| 2 | `CLAUDE.md` | 22265 | `45fcd4b8ba1892babe338911988cd6881757c8a205d9bfb617e7fa136d3173a9` |
| 3 | `.swissknife.json` | 366 | `8f759645419a303fc2ee5e026e1daa2e68271ea900c9b9627d39ae5709413b42` |
| 4 | `plans/ACTIVE.md` | 352 | `96e435e2b5cb2f1d1b483a27e15ec17e40436a7160f471fb5a2dbc631696f7a4` |
| 5 | `.claude/auto-approve.env.ini` | 12 | `3b760a42375525c8f7e9d5386bab83e0253e1cf2ccbaef5ca1bc21b1e3edc13b` |
| 6 | `README.md` | 1755 | `11fac0e8ecfebfa5a65fa945c8efb756df83efd790e447c2c1e073703955935d` |
| 7 | `composer.json` | 3848 | `fe3206d2eb2e12c3a2ca84caf2097d5ad462af3a40797534706417cb38645779` |

Tracked swissknifeman-adjacent index (not all shown): root instructions 2; `.swissknife.json` 1; `plans/ACTIVE.md` 1; `.claude/auto-approve.env.ini` 1. No tracked `.mcp.json` / `.cursor/mcp.json` / Cursor rules.

## Swissknifeman surface / activation matrix

| Surface | Tracked presence | Activation in sample | Coverage |
|:--|:--|:--|:--|
| Root instructions | `AGENTS.md` 22 semantic markers, umbrella `root.ecosystem-identity` text; `CLAUDE.md` 21 markers + managed `maind:healthcheck` | Always-on for Codex/Claude-shaped sessions; Cursor not attested from these files | observed footprint; Cursor first-turn cost `n/a` |
| Skills | `skills_count=0`; plugins listed in `.swissknife.json`: core, laravel-testing, oss-dev, php, php-packages, quality, task | No skill-body reads in report tool names | coverage-gap for per-skill value |
| Agent packs | 3 installed (maind status) | No pack-role tool names in the 6 pairs | consistent-with install, activation unmeasured |
| Hooks | `.claude/auto-approve.env.ini` `MODE=bypass` | Bypass is a tracked policy, not a run outcome | observed |
| MCP | Untracked `.mcp.json` / `.cursor/mcp.json`; `code_mcp=false` | Cursor tools include `MCP:maind_memory_*` and once `MCP:get_symbols_overview` | live config coverage-gap; tool names observed |
| Task | `plans/ACTIVE.md` points at COREX-PLATFORM-HARDENING | No plan-protocol tool names in sample | inventory only |
| Providers in `.swissknife.json` | claude-code, codex, cursor all enabled | Sample is Cursor-only | Codex/Claude run-report completion coverage-gap |

## Evidence rows

| ID | Rubric | Claim | Label | Source type | Commit / session | Provider | Denominator | Limitations |
|:--|:--|:--|:--|:--|:--|:--|:--|:--|
| CX-E01 | footprint/activation | Tracked `AGENTS.md`/`CLAUDE.md` carry swissknifeman umbrella root instructions (`root.ecosystem-identity`, package-boundary text about `packages/<name>/`). | observed | git show HEAD | `65441b16` | n/a (file) | 2/2 root instruction files | Does not prove token cost or false activation rate |
| CX-E02 | footprint/activation | `CLAUDE.md` managed healthcheck instructs `maind health --cwd --fix` before ordinary work; `AGENTS.md` has no healthcheck. | observed | git show HEAD | `65441b16` | claude-shaped vs codex-shaped files | 1 of 2 root files | Matches P1 C09 as a local instance, not a causal harm count |
| CX-E03 | footprint/activation | Auto-approve policy is tracked `MODE=bypass`. | observed | git show HEAD | `65441b16` | claude-code hook env | 1 file | Effect on instruction violations unmeasured |
| CX-E04 | observed outcome | 6/6 sampled Cursor reports have `outcome=ok` with project-matched cwd. | observed | run-report parser | CX-P1–P6 | cursor | 6 ok / 26 recent reports | 19 Claude reports un-scored; empty-tools CX-P6 is weak outcome evidence |
| CX-E05 | observed outcome | `scan_run_report` returns `codegraph.calls=0` on all 26 reports, while CX-P4 tool names include `MCP:get_symbols_overview`. | coverage-gap | run-report parser vs `codegraph_tool_op` | CX-P4 | cursor | 4 symbol-like calls in one session; 0 telemetry calls | Cursor `MCP:` names are not counted by `core.codegraph_telemetry` |
| CX-E06 | observed outcome | Memory MCP tool names appear in 2/6 pairs (CX-P1, CX-P4); report `memory_calls` field absent. | observed | run-report `tools.by_name` | CX-P1, CX-P4 | cursor | 2/6 pairs | Activity of recall/store, not usefulness ordinal from P1 contract |
| CX-E07 | flow/friction | Dirty tree 553 entries at a clean-HEAD read boundary; worktree bytes were not used. | observed | git status hash | pre=post `4a3bdbb0` | n/a | 553 / 4500 tracked | Dirt is a validity bound, not a product defect of swissknifeman |
| CX-E08 | flow/friction | Always-on health `--fix` text in `CLAUDE.md` coexists with P1 policy that health is for setup/symptoms. | consistent-with | git show + P1 C09 | `65441b16` | claude-code | 1 file | Frequency of `--fix` in live sessions not in this sample |
| CX-E09 | collaboration | `Task` tool appears in CX-P5 only. | observed | run-report | CX-P5 | cursor | 1/6 pairs | No multi-agent quality or handoff success metric |
| CX-E10 | collaboration | satisfaction/well-being | n/a | — | — | — | — | No interview/direct well-being data (SPACE) |
| CX-E11 | coverage/provenance | Codex run-reports 0/26; Claude transcripts 0 for this cwd; live MCP files untracked. | coverage-gap | parsers + `git ls-files` | HEAD `65441b16` | codex, claude-code | 0 Codex; 0 analyst sessions; 0 tracked mcp.json | Zeros are missing coverage, not absence of value |

## Value / friction observations

- **Value (bounded):** Cursor sessions in this sample do call `MCP:maind_memory_recall`/`store` and sometimes symbol/search MCP while completing `outcome=ok` writes (CX-E04, CX-E06). That is hub-tool *activation*, not a P1 usefulness ordinal ≥2.
- **Friction (bounded):** Consumer root instructions copy the swissknifeman umbrella contract (CX-E01). Claude-shaped `CLAUDE.md` still commands `maind health --cwd --fix` as priority-1 (CX-E02, CX-E08). Tracked auto-approve is `bypass` (CX-E03).
- Activity counts are not productivity.

## Coverage / validity threats

- Construct: run-report `tools.by_name` vs `codegraph`/`memory_calls` fields disagree (CX-E05).
- External: dirty 553-entry worktree; only HEAD bytes used.
- Internal: 6 Cursor pairs, two classes, no Codex, no Claude completion field, no P1 corpus match.
- Reliability: CX-P6 empty tools with `ok` may be a truncated report.
- `satisfaction/well-being`: n/a.

## Case-local summary

corex at `65441b16` on `main` is a connected Laravel-package monorepo with a large dirty worktree, umbrella-root instruction projection, Claude health `--fix` text, and Cursor-only completed run-reports. Memory MCP names are visible in a minority of the sample; codegraph telemetry remains a coverage gap even when symbol MCP names appear. No deletion or `go` verdict is licensed. Inputs for P3: do not treat `scan_run_report` zeros as unused memory/codegraph. Inputs for P4: instruction-projection mismatch and health `--fix` are candidate *friction* rows, still `defer` until a matched experiment (D2).
