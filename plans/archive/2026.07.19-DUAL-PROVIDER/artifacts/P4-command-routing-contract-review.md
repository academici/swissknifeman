# P4 command-routing contract review

**Item:** P4.1 · **Candidate:** `root/contracts/provider-command-routing-contract.md`
v1.0.0 · **Verdict:** approved/frozen by D84 under delegated owner authority D79

## Entry and evidence

- G03 is satisfied by the latest committed P3 audit literal `GREEN`; PR #142 merged that
  evidence to `main` at `e4e94f2`.
- Provider capability, config, artifact, migration-gates and skill-publication inputs are
  frozen v1.0.0.
- Exact command discovery found the canonical Markdown set directly below
  `packages/task/commands`. The earlier P4 Required Reads brace omitted the existing
  `make-workflow` source; D79 authorizes the contract-preserving exact-set reconciliation.
- Claude selector/invocation evidence comes from committed command frontmatter and
  plan-protocol. Codex selectors use D38/D44 verified evidence; invocation uses owner D19.

No package/runtime/live target was changed by this design item.

## Alternatives

| Alternative | Benefits | Failure modes | Verdict |
|:--|:--|:--|:--|
| Duplicate Claude and Codex command trees | Native files are immediately obvious | Two editable workflow bodies, divergent fixes/literals and no exact source identity | reject |
| Claude-named common contract | Small initial diff; existing frontmatter can be copied | Makes `sonnet`/`opus` and slash syntax universal, forcing Codex to guess equivalence | reject |
| Neutral catalog plus independent provider projections | One intent/source, native invocation, explicit mapping provenance and exhaustive parity | Requires a frozen schema, mapping/version gates and compatibility fixtures | accept |
| Runtime “best available model” selection | Little configuration | Non-reproducible downgrade, unavailable audit route and unverifiable history | reject |
| Lowest-common-denominator wrapper | Simple surface | Loses provider-native pins/subagents and silently weakens plan orchestration | reject |

The accepted design is the only alternative that preserves current Claude bytes while making
Codex mapping explicit without a second semantic source.

## Contract review

| Approval clause | Evidence reviewed | Verdict |
|:--|:--|:--|
| C1 identity/inventory | canonical directory exact-set comparison; one stable `task:*` row per source | accept |
| C2 semantic schema | source/path/hash, inputs/outputs, routing/capabilities and provider projection separation | accept |
| C3 routing axes | `economy < implementation < frontier`; independent `low < medium < high < xhigh` | accept |
| C4 mappings/invocation | versioned selector/evidence table; `/task:*` versus mandatory-space `$ task:*` | accept |
| C5 plan/capability safety | six statuses, ordered item fields, semantic Next/orchestration carriers, fail-closed diagnostics | accept |
| C6 compatibility/evidence | Claude-only legacy, normative positive/negative goldens, authority exclusions | accept |

## Independent exact-set proof

The P4.1 validation reads canonical basenames independently from the contract table and asserts:

```text
canonical = contract = 11
missing = []
extra = []
duplicates = []
```

The expected set is not derived from a provider renderer. The command added by reconciliation
is not a new ID: `make-workflow.md` was already canonical on the entry tree.

## Delegated verdict D84

Under D79 the owner delegated evidence-backed contract-preserving decisions inside the active
plan. The review found no frozen-upstream change, authority expansion or owner-level fork.
D84 therefore records the atomic approval:

```text
APPROVE P4.1 COMMAND-ROUTING C1-C6 AS WRITTEN UNDER D79
```

**Verdict:** freeze `provider-command-routing-contract.md` as v1.0.0 and open only the
declared P4.2–P4.5 consumers. P5+, FOREMAN, fleet, live/user-global config, bootstrap root
adapters and package implementation remain closed.
