# P5.6 provider instruction contract review

**Contract:** `root/contracts/provider-instruction-contract.md` v1.0.0

**Verdict:** APPROVED AND FROZEN — D86 under delegated Owner Approval D79

**Evidence tree:** `722d4825254b40cec52bdb6043403a242d116607`

**Authority:** contract-preserving P5.6 only; no package implementation, live instruction
target mutation/adoption, FOREMAN/fleet mutation or P6/P7 execution.

## Review method

The expected inventory was authored from the Owner refinement, the root/five-package guides,
root Codex bootstrap, frozen P2/P5.1 contracts and existing managed-block writers before any
instruction renderer exists. Actual future projections did not define or regenerate the
expected set.

The review checks four independent questions:

1. Are scopes, target pairs and source files an exact closed inventory?
2. Does each current instruction obligation map exactly once to common or an explicit
   provider extension semantic ID?
3. Can independent projections preserve user-owned bytes and prove full P2 provenance?
4. Do all invalid/adoption/drift states fail closed with an exact diagnostic and action?

## Exact scope and target inventory

Existence was observed at the evidence tree with this read-only command:

```bash
for path in CLAUDE.md AGENTS.md packages/skiller/CLAUDE.md packages/skiller/AGENTS.md packages/harness/CLAUDE.md packages/harness/AGENTS.md packages/maind/CLAUDE.md packages/maind/AGENTS.md packages/analyst/CLAUDE.md packages/analyst/AGENTS.md packages/task/CLAUDE.md packages/task/AGENTS.md; do test -f "$path" && printf 'present %s\n' "$path" || printf 'missing %s\n' "$path"; done
```

| Scope | Claude Code target | Baseline | Codex target | Baseline |
|:--|:--|:--|:--|:--|
| `root` | `CLAUDE.md` | present | `AGENTS.md` | present, unmanaged Codex bootstrap |
| `skiller` | `packages/skiller/CLAUDE.md` | present | `packages/skiller/AGENTS.md` | missing |
| `harness` | `packages/harness/CLAUDE.md` | present | `packages/harness/AGENTS.md` | missing |
| `maind` | `packages/maind/CLAUDE.md` | present | `packages/maind/AGENTS.md` | missing |
| `analyst` | `packages/analyst/CLAUDE.md` | present | `packages/analyst/AGENTS.md` | missing |
| `task` | `packages/task/CLAUDE.md` | present | `packages/task/AGENTS.md` | missing |

No other root file, package directory or provider alias is in v1. Missing package
`AGENTS.md` paths are expected non-green `missing` observations, not permission to write
during this item.

## Source-to-semantic matrix

The complete ordered IDs live in the contract. This matrix proves where each set came from
and separates common meaning from provider-native additions.

| Scope | Current source and headings | Common semantic IDs | Explicit provider extensions |
|:--|:--|:--|:--|
| `root` | `CLAUDE.md`: layout, packages, CLI, core, marketplace, philosophy, plans, development, provenance, methodology | `root.ecosystem-identity` through `root.decision-verification` in contract order | Claude: native surfaces, context budget, research routing. `AGENTS.md`: Codex bootstrap, launch/hook integrity, fresh-agent execution. |
| `skiller` | `packages/skiller/CLAUDE.md`: identity, channels/configs, CORE policy, layout/modules, conventions, development | `skiller.identity` through `skiller.validation-release` in contract order | Claude marketplace-connect, vendor targets and agent hub only. Codex set is explicitly empty. |
| `harness` | `packages/harness/CLAUDE.md`: semantic source, layout/modules, CLI, pack lifecycle, conventions, cross-dependencies, development | `harness.identity` through `harness.validation-release` in contract order | Claude config surfaces, lifecycle surfaces and settings precedence only. Codex set is explicitly empty. |
| `maind` | `packages/maind/CLAUDE.md`: identity/three planes, layout/modules, orchestration, conventions, development | `maind.identity` through `maind.validation-release` in contract order | Claude plugin+MCP and workspace trust only. Codex set is explicitly empty. |
| `analyst` | `packages/analyst/CLAUDE.md`: identity/human gate, layers, layout/modules, data, privacy, conventions, development | `analyst.identity-human-gate` through `analyst.validation-release` in contract order | Claude capture surfaces and plugin only. Codex set is explicitly empty. |
| `task` | `packages/task/CLAUDE.md`: identity/commands, plan protocol, layout, schema ownership, conventions, development | `task.identity` through `task.validation-release` in contract order | Claude slash projection and model pins only. Codex set is explicitly empty. |

### Root compatibility assertions

| Semantic ID | Current obligation, command, link or literal that must survive |
|:--|:--|
| `root.ecosystem-identity` | `swissknifeman` remains the umbrella/container; packages remain capabilities. |
| `root.repository-layout` | `core/`, five package roots, `.claude-plugin/marketplace.json`, `docs/` retain their declared roles. |
| `root.package-boundaries` | Package CLAUDE guides remain required reads when working in their package; task remains plugin-only. |
| `root.cli-routing` | Root `swissknifeman skills|env|maind|analyst|setup|doctor` routing and package CLIs remain distinct; task has no root CLI group. |
| `root.shared-core` | Shared primitives live in `core`; Python package runtime stays stdlib-only and PYTHONPATH-based. |
| `root.marketplace` | One generated umbrella marketplace; package provenance and unprefixed plugin names remain compatible. |
| `root.engineering-invariants` | No pip/npm Python runtime, no duplicated primitives, no renamed umbrella/state, no broken embedded maind paths, no implicit always-on context rollout. |
| `root.plan-lifecycle` | Executable plans remain in repository `plans/<ID>` and use plan-protocol. |
| `root.development-validation` | Package validation commands and Conventional Commits in Russian remain required. |
| `root.reference-provenance` | `docs/reference.md`, `upstream.json`, and `docs/rejected-optimizations.md` retain their stated ownership. |
| `root.decision-verification` | External claims follow context7 → perplexity-web → WebSearch; repo claims require code evidence. |
| `root.claude-code.context-budget` | `skiller budget --first-turn`, target `3–7K`, warning threshold `10K`, Owner verdict above gate. |
| `root.codex.bootstrap` | `.agents/skills` remain thin adapters; canonical content stays in skiller/task; local worktree CLI and Claude compatibility stay mandatory. |
| `root.codex.launch-and-hook-integrity` | Trusted launch must carry cwd/model/effort/`-a never`/`-s danger-full-access`; cold preflight and exit-127 hook repair remain explicit. |
| `root.codex.fresh-agent-execution` | Fresh delegated item execution and audit fix-forward remain bounded by frozen-contract/authority escalation. |

### Package compatibility assertions

| Scope | Required common compatibility anchors | Required `claude-code` extension anchors |
|:--|:--|:--|
| `skiller` | connect/vendor distinction; `.swissknife.json` vs `.swissknifeman/config.json`; nine-skill CORE policy; generated output list; RU-source→EN-canon flow; `bash scripts/test.sh`, `bash scripts/validate.sh`, `skiller registry` | `enabledPlugins`, `.claude/skills`, `skills-lock.json`, `.claude/settings*.json`, `.claude/agents`, Claude marketplace hub behavior |
| `harness` | immutable catalog/renderer ownership; CLI `permissions`, `mcp`, `hooks`, `router`, `agent-packs`, `safe-dirs`, `doctor`; merge-only+backup; agent-pack lifecycle; cross-package state boundaries; `bash scripts/validate.sh` | `configs/claude-code`, `.claude/settings*.json`, `.mcp.json`, `PreToolUse`, `plansDirectory`, `outputStyle`, `.claude/agent-pack.lock.json` |
| `maind` | independent memory/maind-graph/code-graph planes; namespace isolation; orchestration boundary; stdlib/atomic JSON; `federation.graph_reader`; `bash scripts/validate.sh` | command-only Claude plugin, per-project `.mcp.json`, `.claude/settings.local.json` workspace trust |
| `analyst` | on-demand/no daemon; layer-1 only; human-only curated promotion; local raw privacy; append-only audit/events; deterministic recompute; `bash scripts/validate.sh` | `.claude/analyst`, `.claude/runs`, `~/.claude/projects/<encoded-cwd>/*.jsonl`, command-only Claude plugin |
| `task` | plugin-only/no CLI; intent commands plus `plan-design`, `plan-exec`, `plan-run`, `plan-close`, `plan-audit`; plan-protocol and `plan_lint.py` shared schema ownership; stdlib-only; `bash packages/task/scripts/validate.sh` | Claude slash-command projection and per-command model/effort pins |

An assertion may move from provider-specific current prose into common canon only when its
meaning applies unchanged to both targets. Its current provider path/key stays in the
provider extension. No assertion may disappear during that split.

## Carrier alternatives

| Alternative | Evidence | Advantages | Failure mode | Verdict |
|:--|:--|:--|:--|:--|
| A. Explicit catalog + ordered common/provider fragments + independent adapters + P2 lock | P2 contract already freezes full source/render provenance and state machine; `core/block.py` proves bounded marker replacement; P3/P4/P5.1 already use explicit catalogs/adapters | One semantic carrier, native phrasing, exact IDs, deterministic parity and bounded repair | Requires a small explicit renderer and migration plan | **Accept** |
| B. Whole-file generated `CLAUDE.md` and `AGENTS.md` templates | Current guides contain substantial hand-authored prose; P2 whole-file mode requires prior ownership | Simple rendering | Claims all current bytes, destroys user ownership, makes initial adoption unsafe, and couples harmless local prose to generated hashes | Reject |
| C. Render Claude then translate `CLAUDE.md` to `AGENTS.md` | `generate-hub.sh` can write both root names but duplicates the same prepared output; owner refinement requires common canon plus native extensions | Reuses one renderer superficially | Makes Claude output the hidden source, loses Codex-native extensions/full source provenance, and lets Claude drift contaminate Codex | Reject |
| D. Generic Markdown AST or template-language expansion | Current files use ordinary headings, code fences, tables and provider literals; `core/block.py` needs only bounded markers; expected meaning is already expressible as structured IDs/obligations | Could support arbitrary document rewriting | Adds a new parser/language, infers semantics from prose, expands P5.6/P5.7 beyond the frozen need and creates another compatibility surface | **Reject explicitly** |

Alternative A is the smallest carrier that satisfies independent projection, provider-native
extension, P2 provenance and outside-marker ownership simultaneously. The contract tightens
the permissive legacy `core.block.upsert_block` behavior: absence of matching lock+markers is
an ownership conflict, not permission to append.

## Managed-boundary and provenance review

| Requirement | Frozen result |
|:--|:--|
| Two distinct blocks | exact common block followed by exact provider-extension block for every target, including empty extension sets |
| Stable markers | `swissknifeman:instructions:<scope>:<provider>:<common|extension>:<begin|end>` only |
| Outside ownership | every byte outside both pairs is user-owned and byte-preserved |
| Existing target | without both matching pairs plus matching valid P2 record: unmanaged `ownership-conflict`; update/repair refuse |
| Source provenance | full contract, catalog, common fragment, own extension fragment hashes; adapter/provider/scope/target/IDs/markers/capabilities in source envelope |
| Render provenance | exact two blocks including markers, concatenated in block-ID order; authoritative full SHA-256 in P2 record |
| Lock failure | absent/foreign/corrupt/newer/mismatched record fails closed; inline/short hash never backfills ownership |

## Observation and operation review

| Case | Observation/diagnostic | `check` | `apply/update` | `repair` |
|:--|:--|:--|:--|:--|
| Absent package AGENTS | `missing` / `INSTRUCTION_TARGET_MISSING` | non-green, no write | explicit authorized create only while still absent | refuse |
| Valid current managed state | `clean` | green, no write | noop | refuse/noop |
| Source/adapter changed, managed bytes untouched | `stale-source` / `INSTRUCTION_STALE_SOURCE` | non-green, no write | matching blocks+record only | refuse |
| Local edit inside managed block | `managed-drift` / `INSTRUCTION_MANAGED_DRIFT` | non-green, no write | refuse | explicit diff+pre-image, matching blocks only |
| Duplicate/malformed markers | `boundary-invalid` / `INSTRUCTION_BOUNDARY_INVALID` | non-green, no write | refuse | refuse |
| Corrupt/newer/unsupported lock | `provenance-invalid` / `INSTRUCTION_PROVENANCE_INVALID` | non-green, no write | refuse | refuse |
| Existing file without marker+lock | `ownership-conflict` / `INSTRUCTION_OWNERSHIP_CONFLICT` | non-green, no write | refuse; no adoption | refuse; no adoption |
| Extension weakens/duplicates common | semantic conflict / `INSTRUCTION_EXTENSION_CONFLICT` | non-green, no write | refuse before render | refuse |

This table preserves the P2 meanings. Instruction semantic conflicts are a pre-render
validation refusal and do not add a competing P2 artifact observation class.

## Normative golden coverage

The contract contains all required positive and negative goldens:

- independent common parity with allowed provider extension delta;
- outside-marker preservation;
- extension override/weakening;
- missing and duplicate semantic ID;
- unmanaged existing path;
- local managed drift;
- stale source hash;
- corrupt/newer lock;
- missing package `AGENTS.md`.

Each case names an exact diagnostic, action and write boundary. No fixture-update-from-actual,
skip, implicit adoption or precedence fallback is permitted.

## Consumer handoff

P5.7 receives the frozen exact scope/section/extension inventories, marker grammar, P2 lock
record, compatibility assertions, diagnostics and temp-root `plan/check/apply/repair` API.
It must implement independent catalog adapters and prove the goldens without changing live
root/package files.

Later provider-aware deployment consumes the same result rather than reclassifying states.
Durable checkpoint/restart evidence records catalog/source/render/lock hashes. Self-host,
explicit adoption, cleanup and release verification call the same API and do not create a
new schema or repair mechanism.

## Atomic approval decision

D86 records one indivisible approval set:

- I1 identity/scopes and exact target pairs;
- I2 ordered common semantic canon;
- I3 explicit non-overriding extensions and independent projections;
- I4 two-block markers, outside-byte ownership and unmanaged-by-default adoption boundary;
- I5 full P2 provenance/lock and parity;
- I6 exact states/actions/no-write/write boundaries;
- I7 initial compatibility inventory, diagnostics and normative goldens;
- I8 public consumer API and unchanged authority boundary.

Exact delegated approval record:

```text
APPROVE P5.6 PROVIDER-INSTRUCTION I1-I8 AS WRITTEN UNDER D79
```

This is contract-preserving under D79: it creates the planned P5.6 contract without changing
any frozen P0–P5.1 semantic, implementation or authority boundary.
