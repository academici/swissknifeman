# P2.1 case — edufy field audit

**Case ID:** `edufy`
**Audit date:** 2026-09-21
**Executor route:** Cursor `cursor-grok-4.6-high` / frontier/high (owner-attested). Catalog Cursor frontier pin `claude-opus-5-thinking-high` is not this session. `gpt-5.6-sol` / `gpt-6-astra` reserved for final review.
**Rubric source:** `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/research/02-p1-measurement-contract.md` · `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/findings/p2-design-method.md` · `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/decisions/D4-p2-multiple-case-method-and-budget.md`
**P1 predecessor:** GREEN `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/findings/01-p1-verified-baseline.md`. Frozen corpus T1–T6 has no project-matched edufy members.

Consumer bytes: `git show <HEAD>:<path>` only. No dirty reads. No consumer write/fix/sync/deploy/onboard.

## Snapshot

| Field | Pre | Post |
|:--|:--|:--|
| Project ID | `edufy` | `edufy` |
| Resolved path | `/home/vostrikov/projects/edufy` | same |
| Unique nonempty `.git` path | 1 of 1 | 1 of 1 |
| Branch | `feat/edufy-core` | `feat/edufy-core` |
| HEAD | `8f2ac44c698fda429e30b03eabecdfc3164f9f31` | `8f2ac44c698fda429e30b03eabecdfc3164f9f31` |
| `git status --porcelain=v1` hash | `4475ba42475bb39a02c810db5c00e3691f5906a0c08795a90a8fcd896011e051` | `4475ba42475bb39a02c810db5c00e3691f5906a0c08795a90a8fcd896011e051` |
| Dirty status entries | 142 | 142 |
| Tracked files | 4251 | 4251 |
| Concurrent drift | — | none (`stable`) |

Branch is a case property, not a shared baseline with corex/agentools `main`. Design-time HEAD `463ab0a` / 2992 tracked files is not this snapshot.

**Provider/configuration snapshot:**

- Status `connected`; `trusted=true`; daemon reachable; scope `project:edufy`.
- MCP files declared `.mcp.json`, `.cursor/mcp.json` — not git-tracked. Tracked `.mcp.json.example` only.
- `agentmemory_mcp=false`, `maind_mcp=true`, `code_mcp=false`.
- `skills_lock=false`, `skills_count=0` despite tracked `.claude/skills/ecosystem-mcp` and `ecosystem-setup`.
- Agent packs: `_common`, `backend-laravel`; `lock=true`; **`modified=true`** (maind status, not worktree bytes).
- `.swissknife.json`: plugins core, laravel-auth, laravel-data-layer, laravel-testing, php, quality, task; claude-code, codex, cursor enabled; comment that `codex.enabled` still allows native Codex plugins while skiller projections may be off.
- Stack: Laravel app (`composer.json`); README is only `# edufy`.

## Sample ledger

37 recent reports: 7 Cursor (`outcome=ok`), 30 Claude-code (`outcome` missing → not trusted-complete). Sampled 6 Cursor. Codex 0. `analyst sessions --project edufy`: no jsonl.

P1 corpus match: **0 / 6**. Classes: ordinary-implementation+memory, ordinary-implementation, empty-tools.

| Pair | Session | Provider | Occurred | Observable class | Memory tool calls | Symbol-like tool calls |
|:--|:--|:--|:--|:--|--:|--:|
| ED-P1 | `6a718318-387d-4139-93e5-e6775ebc3609` | cursor | 2026-09-21T07:17:10Z | ordinary-implementation + memory | 30 | 27 |
| ED-P2 | `aea1d8de-6d02-4caf-bd83-3c0edd8891c1` | cursor | 2026-09-19T14:23:13Z | empty-tools | 0 | 0 |
| ED-P3 | `9ecf7fc4-03c0-4d70-9f5f-08ad4c78073b` | cursor | 2026-09-19T14:22:34Z | empty-tools | 0 | 0 |
| ED-P4 | `74ab9b6f-53da-49f8-8f8b-b640290253b4` | cursor | 2026-09-19T12:16:44Z | ordinary-implementation + memory | 1 | 0 |
| ED-P5 | `46ff61e7-4aab-4285-8ed4-627fe6eaf076` | cursor | 2026-09-19T07:06:25Z | ordinary-implementation + memory | 1 | 0 |
| ED-P6 | `387f54bd-f086-40a2-b377-d653078148ed` | cursor | 2026-09-18T18:00:10Z | ordinary-implementation | 0 | 0 |

ED-P1 also has `Task` and `MCP:maind_projects_status`. `scan_run_report` on 37 reports: `code_sessions=0`, `calls=0`.

## Source-read ledger (≤24)

HEAD `8f2ac44c698fda429e30b03eabecdfc3164f9f31`.

| # | Path | Bytes | SHA-256 |
|--:|:--|--:|:--|
| 1 | `AGENTS.md` | 12487 | `67247662fb781d82bb8687d9fc458010f62bd3b6d2526fcecb7af2495e2538d3` |
| 2 | `CLAUDE.md` | 32592 | `fad49d393186d4e11189bb515416e97a39f392fea0d302220090f9d78fdf1543` |
| 3 | `.swissknife.json` | 1002 | `189204cc15c1e0f77a6b0c1af905d98d7b635c5bd1ce37cffa1b3e06fd56fe98` |
| 4 | `.claude/settings.json` | 1504 | `5c18382c8d6009e5a848ff56828df0bfa7876c0e5b92b6431cfb2b696143a0d0` |
| 5 | `.claude/agent-pack.lock.json` | 7475 | `128eb8a41a7e2e8ebc6c2ed74d701ca9256ddfa28ad6372694c5ca50ed522160` |
| 6 | `.claude/hooks/review-gate.sh` | 1863 | `c0d78e9502efafa8071dc239f945bbc9654dd7776bc30f85f5ada2002a79f787` |
| 7 | `.claude/skills/ecosystem-mcp/SKILL.md` | 7421 | `73e5a1fa90b6f3377843e79db71757418456757bea7168c9f135fae52032b707` |
| 8 | `.claude/skills/ecosystem-setup/SKILL.md` | 4308 | `3be2b0b324605eb675a148f90dd58dd64bd40557f06e91f03d9ba646fbbd1f0d` |
| 9 | `.claude/commands/code-review.md` | 1211 | `c8f0386571bb8b0e00424587ea387169bb8987b88af18c100bce7c3f8be376b7` |
| 10 | `.claude/agents/edufy-orchestrator.md` | 9934 | `d5c3fb4904208e31a7cfc862e4e86804ae98f46f727e652b28dd67b70ab08d17` |
| 11 | `.agents/skills/ecosystem-mcp/SKILL.md` | 7421 | `73e5a1fa90b6f3377843e79db71757418456757bea7168c9f135fae52032b707` |
| 12 | `README.md` | 8 | `7b6532be84e0e10829750f56c06c670a9c981e42abdb5d523635bbdaeda3df03` |
| 13 | `composer.json` | 8144 | `04209e89d60dd48b3c52f9bfad942764db58dfbdc9985c24799225c1873c97de` |
| 14 | `plans/2026.08.06-EDUFY-BUILD/plan.md` | 94267 | `68c72c34e99772364e54915f5cd64667bcb88c10d41529036aaa032fff2769ee` |

`.agents/skills/ecosystem-mcp/SKILL.md` SHA matches `.claude/skills/ecosystem-mcp/SKILL.md` (duplicate projection). 1795 tracked paths under `plans/` indexed, not all read. Pack lock: `backend-laravel` 0.12.2 while `code-review.md` header says pack `0.13.0` — tracked version skew.

## Swissknifeman surface / activation matrix

| Surface | Tracked presence | Activation in sample | Coverage |
|:--|:--|:--|:--|
| Root instructions | `AGENTS.md` 22 semantic markers, umbrella root text; `CLAUDE.md` 21 markers + healthcheck `--fix` + extra local body (32592 bytes) | Always-on for those providers | observed largest instruction pair of the three cases |
| Skills | ecosystem-mcp/setup vendored into `.claude/skills` and `.agents/skills`; maind `skills_count=0` | Skill files exist; report tool names do not show SKILL.md reads | inventory vs activation gap |
| Agent packs | `_common` + `backend-laravel`; orchestrator/reviewer/commands generated; lock `modified=true` | ED-P1 uses `Task`; orchestrator model pin `opus` | pack present; Cursor sample does not prove pack-role dispatch |
| Hooks | `settings.json`: auto-approve, review-gate, SessionStart `maind-memory.sh`/`maind-health.sh` with **absolute** `/home/vostrikov/projects/edufy/...` paths, SessionEnd run-report + feature-log; `autoMemoryEnabled: false` | Cursor reports exist; Claude reports lack outcome | host-absolute paths are a portability friction |
| MCP | untracked live json; skills document agentmemory + serena + maind; `code_mcp=false` | ED-P1 has find_symbol / get_symbols_overview | config vs tool-name vs telemetry mismatch |
| Task | 1795 tracked plan files including executable `plans/2026.08.06-EDUFY-BUILD/plan.md` | Not evidenced as Task-command activation in the 6 pairs | large in-repo plan corpus |
| Providers | all three enabled in `.swissknife.json` | Sample Cursor-only for completed reports | Claude 30 reports un-scored |

## Evidence rows

| ID | Rubric | Claim | Label | Source type | Commit / session | Provider | Denominator | Limitations |
|:--|:--|:--|:--|:--|:--|:--|:--|:--|
| ED-E01 | footprint/activation | `AGENTS.md`/`CLAUDE.md` include swissknifeman umbrella root instructions (same semantic family as corex). `CLAUDE.md` is 32592 bytes. | observed | git show | `8f2ac44c` | n/a | 2 root files | Token cost unmeasured |
| ED-E02 | footprint/activation | Healthcheck in `CLAUDE.md` still commands `maind health --cwd --fix`. SessionStart hooks call project-local `maind-health.sh` via absolute host path. | observed | git show | `8f2ac44c` `.claude/settings.json` | claude-code | 1 settings + 1 CLAUDE.md | Hook script bodies not read (would add paths) |
| ED-E03 | footprint/activation | Duplicate ecosystem-mcp skill SHA in `.claude/skills` and `.agents/skills`. Pack lock 0.12.2 vs command header 0.13.0. | observed | git show | `8f2ac44c` | claude + agents projection | 2 skill copies + lock + command | Drift is tracked; runtime effect unmeasured |
| ED-E04 | observed outcome | ED-P1 `outcome=ok` with 30 memory-named tool calls and 27 symbol-like calls plus `Task`. | observed | run-report | ED-P1 | cursor | 1/6 pairs | Strongest single-session activation in this case; not a usefulness score |
| ED-E05 | observed outcome | 2/6 sampled reports are empty-tools `ok` (ED-P2, ED-P3). | coverage-gap | run-report | ED-P2, P3 | cursor | 2/6 | Truncation vs true empty session unknown |
| ED-E06 | observed outcome | `scan_run_report` 0 calls / 0 code_sessions on 37 reports including ED-P1 symbol MCP names. | coverage-gap | parser | fleet 37 | cursor+claude | 37 reports | Same `MCP:` naming gap |
| ED-E07 | flow/friction | Hardcoded `/home/vostrikov/projects/edufy` in tracked `settings.json` SessionStart commands. | observed | git show | `8f2ac44c` | claude-code | 2 hook command strings | Breaks other checkouts; not observed failing in this sample |
| ED-E08 | flow/friction | `code_mcp=false` while ecosystem-mcp skill tells agents to use Serena `find_symbol`. | consistent-with | maind status + git show skill | `8f2ac44c` + ED-P1 | mixed | skill vs status vs tool names | Tool names appeared anyway; which server served them is unproven |
| ED-E09 | collaboration | `Task` in ED-P1; orchestrator agent forbids Write/Bash and pins `model: opus`. | observed | run-report + git show | ED-P1 + orchestrator.md | cursor vs pack pin | 1/6 pairs | Pack pin vs this Cursor/Grok session is a routing mismatch, not a quality score |
| ED-E10 | collaboration | satisfaction/well-being | n/a | — | — | — | — | No direct data |
| ED-E11 | coverage/provenance | Feature branch `feat/edufy-core`; 30 Claude reports without outcome; 0 Codex; 0 analyst transcripts; live MCP untracked. | coverage-gap | snapshot + parsers | `8f2ac44c` | mixed | 7 Cursor ok / 37 reports | Branch is not comparable to `main` cases |

## Value / friction observations

- **Value (bounded):** ED-P1 is a single dense Cursor session with memory, symbol MCP, projects_status, Task, and Write (ED-E04). Duplicate skill files prove delivery, not that agents opened them.
- **Friction (bounded):** Umbrella-root dump (ED-E01), health `--fix` plus absolute paths (ED-E02, ED-E07), pack version skew and skill duplication (ED-E03), `code_mcp=false` vs skill text (ED-E08), orchestrator `opus` pin (ED-E09).
- Empty-tools ok reports (ED-E05) reduce trust in the 6-pair denominator.
- Not productivity.

## Coverage / validity threats

- Feature branch vs other cases' `main`.
- `agent_packs.modified=true` is live maind status, not a git-show of dirty pack files.
- 1795 plan files not sampled beyond one plan.md.
- Same telemetry gap.
- satisfaction/well-being n/a.

## Case-local summary

edufy at `8f2ac44c` on `feat/edufy-core` is the richest *installed* swissknifeman surface (umbrella roots, packs, generated agents/commands, dual skill projections, SessionStart health/memory hooks) and has one very active Cursor report plus several weak/empty ones. Configuration tells agents to use codegraph while `code_mcp=false`. P3 should not treat report-field zeros as non-use. P4 friction candidates: absolute hook paths, health `--fix`, instruction duplication, pack-version skew — all `defer` without a matched experiment (D2).
