# P2.1 cross-project synthesis

**Date:** 2026-09-21
**Scope:** evidence-ID-only comparison of `findings/p2-corex-field.md`, `findings/p2-agentools-field.md`, `findings/p2-edufy-field.md`.
**Method:** `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/findings/p2-design-method.md` · D4. Labels are `replicated` | `context-dependent` | `conflicting` | `unassessable`.
**Sentence bound:** claims below are about these three cases at the recorded commits and Cursor-completed report samples, not the whole academici fleet.
**Reducer:** no `go|keep|defer|reject`. Activity is not productivity. Association is not causality.
**Route note:** this execution used Cursor Grok 4.6 frontier/high (owner). Composer 2.5 is the implementation class. Codex sol/astra are for final review, not this synthesis.

No raw observation was added here. Every row cites case evidence IDs.

## Case identity matrix

| Case | Evidence | Branch / HEAD | Tracked / dirty | Packs | Root files |
|:--|:--|:--|:--|:--|:--|
| corex | snapshot in `p2-corex-field.md` | `main` `65441b16` | 4500 / 553 | 3 | AGENTS+CLAUDE umbrella |
| agentools | snapshot in `p2-agentools-field.md` | `main` `6658ba89` | 2098 / 443 | 0 | CLAUDE health+hub only |
| edufy | snapshot in `p2-edufy-field.md` | `feat/edufy-core` `8f2ac44c` | 4251 / 142 | 2 (lock modified) | AGENTS+CLAUDE umbrella, largest CLAUDE |

Pre/post HEAD and porcelain hashes matched in all three cases (`stable`). Design-time HEADs were not reused.

## Sample coverage matrix

| Denominator | corex | agentools | edufy |
|:--|:--|:--|:--|
| Content-reads | 7 paths CX ledger | 7 paths AO ledger (`composer.json` missing) | 14 paths ED ledger |
| Trusted completed pairs | 6/26 reports (CX-P1–P6) | 6/7 (AO-P1–P6) | 6/37 (ED-P1–P6) |
| P1 corpus T1–T6 match | 0/6 | 0/6 | 0/6 |
| Cursor `outcome=ok` | 6 | 7 | 7 |
| Claude reports with outcome | 0 of 19 | 0 of 0 | 0 of 30 |
| Codex reports | 0 | 0 | 0 |
| `analyst sessions` jsonl | none | none | none |
| Tracked live `.mcp.json` | none | none | none |

## Mechanisms

| Mechanism | Label | Evidence IDs | Preserved denominators | Bound statement |
|:--|:--|:--|:--|:--|
| Cursor completed run-reports exist and are cwd-matched | replicated | CX-E04, AO-E04, ED-E04 | 6/26, 6/7, 6/37 | In these three cases, trusted completion is Cursor schema-2 `run_summary` only. |
| `MCP:maind_memory_recall`/`store` names appear in some `outcome=ok` Cursor pairs | replicated | CX-E06, AO-E04, ED-E04 | 2/6, 5/6, 3/6 pairs with memory names | Activation of memory *tool names* is visible in all three samples; P1 usefulness ≥2 is unassessable here. |
| `scan_run_report` codegraph calls = 0 while some pairs list `MCP:find_symbol` / `get_symbols_overview` / replace | replicated | CX-E05, AO-E05, ED-E06 | 26, 7, 37 reports scanned; symbol-like names in a subset of pairs | Telemetry helper does not treat Cursor `MCP:` names as codegraph ops; zeros are coverage-gap, not unused-graph proof. |
| Codex run-report coverage | replicated | CX-E11, AO-E11, ED-E11 | 0 Codex reports / case | Cannot compare Codex vs Cursor outcomes in these cases. |
| Claude transcript (`analyst sessions`) coverage | replicated | CX-E11, AO-E11, ED-E11 | 0 jsonl / encoded cwd | Claude first-turn overhead is n/a here. |
| Live MCP config untracked | replicated | CX snapshot MCP files vs ls-files; AO-E11; ED-E11 | 0 tracked `.mcp.json` | Hub status lists mcp files that this audit must not read. |
| `CLAUDE.md` healthcheck commands `maind health --cwd --fix` before ordinary work | replicated | CX-E02, AO-E02, ED-E02 | 1 CLAUDE.md / case | Same always-on `--fix` prose in all three tracked Claude roots. |
| Dirty worktree as read boundary | replicated | CX-E07, AO-E07, ED snapshot dirty 142 | 553, 443, 142 porcelain entries | All three cases were dirty; only HEAD bytes used; no cleanup. |
| satisfaction / well-being | replicated | CX-E10, AO-E10, ED-E10 | n/a | SPACE: no direct data in any case. |
| Umbrella swissknifeman root instructions in consumer `AGENTS.md`/`CLAUDE.md` | context-dependent | CX-E01, ED-E01 vs AO-E01 | 2/2 files corex; 2/2 edufy; 0 AGENTS.md agentools | Present in corex and edufy; agentools CLAUDE is health+hub index only. |
| Agent-pack install | context-dependent | corex snapshot 3 packs; AO empty packs; ED-E03/ED-E09 packs | 3 vs 0 vs 2 | Packs are not a shared surface across the three. |
| Cursor listed in `.swissknife.json` `providers.selection` | conflicting | AO-E03 vs corex/edufy swissknife excerpts | agentools omits cursor yet 7/7 reports are Cursor; corex and edufy enable cursor | Config and observed provider disagree in agentools; the other two files list cursor. |
| `Task` tool in sample | context-dependent | CX-E09, AO-E09, ED-E09 | 1/6, 0/6, ≥1/6 | Not a shared collaboration pattern. |
| Absolute host paths in tracked Claude settings | context-dependent | ED-E07 | 2 command strings in one file | Only edufy in this set. |
| Tracked auto-approve `MODE=bypass` | context-dependent | CX-E03 | 1 file | Only corex in this set. |
| Duplicate ecosystem-mcp skill SHA across `.claude/skills` and `.agents/skills` | context-dependent | ED-E03 | 2 copies same SHA | Only edufy content-read this pair. |
| Feature-branch vs `main` | context-dependent | ED-E11 vs corex/agentools snapshots | edufy `feat/edufy-core` | Cross-case totals must not pool branches as one baseline. |
| Memory/codegraph *usefulness* (P1 ordinal ≥2, provenance-correct) | unassessable | CX-E06, AO-E04, ED-E04 plus P1 contract | no usefulness field in reports | Tool names ≠ capability-value threshold. |
| Population-wide swissknifeman value or deletion verdict | unassessable | all coverage rows | three cases, Cursor-only completion | Explicitly out of P2 (D2, D4). |

## Inputs for P3

- Treat `core.codegraph_telemetry.scan_run_report` zeros as **instrumentation coverage-gap** (CX-E05, AO-E05, ED-E06), not as unused codegraph.
- Prefer identity-preserving `tools.by_name` with `MCP:maind_memory_*` and symbol-like names, still as activation not usefulness.
- Denominator is Cursor-completed schema-2 reports; Codex and Claude-completion fields are missing.
- Richest Cursor activation sample: agentools (AO-E04–E06) then edufy ED-P1; corex is sparser (2/6 memory pairs).
- Do not run P3 as a fleet-wide statistical test.

## Inputs for P4

Candidate *friction* rows (still not `go`):

- Health `--fix` always-on prose: CX-E02, AO-E02, ED-E02 (`replicated` in these cases).
- Umbrella root projection into consumers: CX-E01, ED-E01 (`context-dependent`; absent as umbrella dump in AO-E01).
- Provider-selection vs observed Cursor: AO-E03 (`conflicting` in agentools).
- Absolute hook paths: ED-E07 (`context-dependent`).
- Auto-approve bypass: CX-E03 (`context-dependent`).
- Pack/skill duplicate and version skew: ED-E03 (`context-dependent`).

P1 reducer and D2 still require a matched experiment before `go`. Ambiguous coverage stays `defer`.

## What this synthesis does not say

- It does not say swissknifeman is unused or must be deleted.
- It does not say memory or codegraph have proven capability value.
- It does not average the three cases into one productivity number.
- It does not authorize P5.
