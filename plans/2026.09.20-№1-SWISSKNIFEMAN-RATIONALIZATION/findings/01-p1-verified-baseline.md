# P1 verified baseline — 2026-09-20

## Boundary and retrieval record

- Repository snapshot: `f116cb9d62c54fd0d5114930dff5cb88b6d02551`; the worktree was already dirty before P1.1. P1.1 writes only its two declared plan evidence files and Task-owned plan bookkeeping.
- Execution route: Codex `gpt-5.6-sol/high`, provider-thread-state, cwd `/home/vostrikov/projects/packages/swissknifeman`, approval `never`, sandbox `danger-full-access`.
- Tool versions: `codex-cli 0.155.1`, Claude Code `2.1.266`, Cursor Agent `2026.09.18-9a7762b`.
- Perplexity `search_advanced(web, academic)`: `n/a` in this run because the configured server was not exposed as a callable tool. Earlier design evidence is retained as a lead, not treated as independent P1 verification.
- Ordinary web retrieval had intermittent connection failures. Primary vendor pages were opened directly after the search adapter failed; repository and GitHub evidence was obtained read-only. Missing observations below remain `n/a`, never zero.

## Independently verified external premises

- RAG:✅ OpenAI Codex Skills, accessed 2026-09-20: <https://developers.openai.com/codex/skills>. Codex first exposes skill metadata and loads the full `SKILL.md` when selected; referenced resources may be loaded later. This supports progressive disclosure, not the deletion of any local skill.
- RAG:✅ OpenAI Codex `AGENTS.md`, accessed 2026-09-20: <https://developers.openai.com/codex/agent-configuration/agents-md>. Codex builds an instruction chain from root toward the working directory before work. This verifies that persistent instructions have a context cost, not that a particular local rule is dispensable.
- RAG:✅ Anthropic Agent Skills overview and authoring guidance, accessed 2026-09-20: <https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview> and <https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices>. Metadata is always available while instructions and resources are progressively disclosed. This verifies the mechanism only.
- RAG:✅ GitHub PR #156 checks, accessed with `gh pr view` on 2026-09-20: <https://github.com/academici/swissknifeman/pull/156>. The merged PR had failed `hygiene`, Python 3.9, `validate`, and `lint` checks, with Python 3.10–3.13 green. Root cause and current branch health are not implied by that historical check record.

## Repository measurement snapshot

| Surface | Observation | Coverage / denominator | Interpretation |
|:--|:--|:--|:--|
| First-turn budget | `skiller budget --first-turn --provider codex --target . --json`: skills 1,719 tokens, agents 567, root instructions 2,653, hooks 1,156, MCP 424; total 6,519, verdict `OK` | Codex projection; 31 listed of 35 skills, 4 excluded; deferred MCP accounting is a lower bound | RAG:— measured footprint; no quality or deletion verdict |
| Root carriers | `AGENTS.md`: 9,004 bytes/92 lines/22 semantic markers; `CLAUDE.md`: 9,390 bytes/104 lines/21 markers | Current dirty worktree; generated provider projections | RAG:— substantial common surface plus provider additions; semantic duplication cost is still unmeasured |
| Health policy | `AGENTS.md` limits health/doctor checks to setup, environment change, or symptoms; `CLAUDE.md:97-98` still prescribes `maind health --cwd` and `--fix` | Two provider projections at the same snapshot | RAG:— real semantic drift; effect frequency and harm remain hypotheses |
| Task surface | 11 command files under `packages/task/commands`; plan protocol, adapters, validators and generated carriers are present | Repository inventory, not runtime activation | RAG:— complexity exists; cost/value ratio is unmeasured |
| Skill surface | 1,354 files under `packages/skiller/skills`; first-turn listing is 31 skills/1,719 tokens | Files include canonical content and resources; file count is not prompt count | RAG:— heterogeneous inventory; no bulk-disable verdict |
| CI surface | Seven workflows; `.github/workflows/validate.yml` invokes repository validation | Current tree plus historical PR #156 checks | RAG:— trust concern is verified historically; current root cause is outside P1 |
| MCP parity | `maind doctor --audit mcp --json` reports no declared-surface drift for swissknifeman and the connected fleet entries inspected | Structural configuration only; not semantic usefulness | RAG:— parity is observable, but cheaper semantic parity is an untested candidate |
| Codegraph reports | Fleet scan: 319 recent reports, 2 codegraph sessions, 3 calls; selected projects: swissknifeman 0/33, corex 0/26, agentools 0/6, edufy 0/36 | Claude/Cursor reports only; zero Codex reports; bounded to latest 40/project | RAG:— low observed activation with incomplete provider/result coverage, therefore a coverage gap |
| Memory/graph reports | The same selected 101 reports contain 0 recorded `memory_calls` and 0 `graph_calls` | 79 Claude and 22 Cursor reports; schemas without `maind` fields count as absent coverage, not successful zero-use measurement | RAG:— coverage gap; not proof of no value |
| Analyst sessions | `analyst sessions --weeks 4 --json`: two Claude sessions, one turn each, usage/overhead counters absent or zero | No Codex/Cursor denominator | RAG:— insufficient for cross-provider productivity claims |
| Generated provider docs | `render-provider-commands.py --root . --check` reports drift in `packages/task/docs/reference/provider-model-roles.md` | Owning Task sources were already dirty before P1.1 | RAG:— pre-existing projection defect; P1 neither repairs nor claims it |

## Claim ledger

| ID | Audit recommendation / hypothesis | Evidence and source | Provider / coverage / denominator | Verdict for P1 |
|:--|:--|:--|:--|:--|
| C01 | Shrink root instructions to 1–2 KB | RAG:✅ vendor instruction-loading premise above; RAG:— 2,653-token local first-turn component | Codex budget only; no paired outcomes | `[UNVERIFIED]` H1 practical benefit; retain for matched experiment |
| C02 | Remove common `CLAUDE.md`/`AGENTS.md` duplication | RAG:— carrier sizes and current health-policy divergence above | Claude/Codex projections; Cursor not sampled | Drift is verified; H2 quality/token effect is `[UNVERIFIED]` |
| C03 | Make Task actions explicit-only and simplify ordinary work | RAG:— Task command/protocol inventory and routing config | Activation telemetry unavailable | H3, H8, H9 and H15 remain hypotheses; no removal verdict |
| C04 | Split generic review into dispatcher/profiles | RAG:— `packages/task/commands/review.md` and command routing | No false-activation denominator | `[UNVERIFIED]` H4 |
| C05 | Replace fixed model/effort pins with capability routing | RAG:— current routing config and plan route | One current Codex route; no matched model runs | `[UNVERIFIED]` H5/H12; no mapping change authorized |
| C06 | Disable most generic skills; retain conformance skills | RAG:✅ progressive-disclosure mechanism; RAG:— local budget/inventory | 31 listed skills, no per-skill causal outcomes | H6/H7 remain `[UNVERIFIED]`; evaluate by task class, not file count |
| C07 | Eliminate thin projections | RAG:— canonical/projection layout and generated-doc drift | Activation handoff success not recorded | `[UNVERIFIED]` H11; drift alone does not prove runtime harm |
| C08 | Make workflows narrowly admitted / possibly separate | RAG:— workflow files and Task routing | No workflow intrusion denominator | `[UNVERIFIED]`; candidate only if P2 finds observed pain |
| C09 | Make maind lazy and never auto-repair on ordinary work | RAG:— provider-policy divergence; current MCP runtime includes duplicate/heavy processes | One point-in-time process scan; task failures not linked | H10 is a supported risk hypothesis, not a causal verdict |
| C10 | Retain memory/codegraph only if useful | RAG:— bounded report scan and existing telemetry symbols in `core/codegraph_telemetry.py`, run-report `_lib.py`, and `maind/codegraph_usage.py` | 319 reports for codegraph; selected 101 for memory; no Codex coverage/results | Coverage-first P3 pilot required; zero observations cannot justify deletion |
| C11 | Prefer semantic over structural provider parity | RAG:— MCP structural parity green while generated Task doc drifts | Configuration coverage, not behavior | `[UNVERIFIED]` H13; test with a bounded parity slice |
| C12 | Reduce repeated plan audits/carriers | RAG:— current plan journal and protocol implementation | One plan is not a representative denominator | `[UNVERIFIED]` H14; P2/P4 must establish repeated material cause |
| C13 | Consolidate duplicated documentation | RAG:— generated projections and repository docs inventory | No reader-navigation or maintenance-cost measure | Candidate only; no bulk documentation rewrite |
| C14 | Investigate failed merged checks | RAG:✅ PR #156 historical check record above | One merged PR; causes not read in P1 | Historical premise verified; remediation requires separate owning work |
| C15 | Preserve useful strengths (stdlib runtime, package boundaries, provenance, focused validation) | RAG:— root instructions and current source layout | Repository-wide invariant surface | Keep as guardrails unless a later slice supplies contrary evidence |

## Frozen hypothesis inventory

The audit's H1–H15 are all represented by C01–C12: root size/duplication (H1–H2), Task/review/durable carriers (H3–H4, H8–H9, H14–H15), model routing (H5, H12), skills/projections (H6–H7, H11), maind activation (H10), and provider parity (H13). None is promoted to an implementation verdict here. P2 supplies field denominators, P3 isolates memory/codegraph, and P4 may run at most the already bounded candidate experiments.

## Baseline conclusion

The audit identifies real measurable surfaces and two concrete trust defects: provider instruction drift and historical failed checks on a merged PR. Its broad deletion and simplification recommendations remain hypotheses. Existing measurements are sufficient to design small comparisons, but provider coverage—especially Codex run reports and structured maind results—is insufficient for interpreting zeros as absence of value.
