# P5.1 harness contract review

**Item:** P5.1 · **Tree inspected:** `36b38086090b7defc533f8594180c919176af376` ·
**Contract candidate:** `root/contracts/provider-harness-contract.md` v1.0.0 ·
**Decision:** D85 (delegated Approval Owner authority under D79)

## Entry and authority gate

- P0–P4 are terminal on the inspected tree; G03 and G04 are literal GREEN.
- The capability, configuration, artifact, migration-gates, skill-publication and
  command-routing contracts are frozen v1.0.0.
- The current Codex bootstrap/full-access authoring session is not contract or release
  evidence. No bootstrap/live target was inspected as expected output.
- P5.1 changes only the harness contract/review and plan bookkeeping. It does not authorize
  package implementation, live/user-global apply, P6+, FOREMAN, fleet or owner-dirt writes.

## Independent current-surface inventory

Expected groups were authored from the committed CLI, modules and `configs/claude-code`
source tree before the contract was written. A source group appears in exactly one row; an
alias shares its owner's row rather than creating a duplicate semantic surface.

| Current source/operator surface on `36b3808` | Common Surface ID | Disposition |
|:--|:--|:--|
| `permissions` plus alias `apply`, `permissions.py`, `apply-permissions.sh`, `settings.*.json` | `settings.permissions` | preserve named Claude preset discovery/merge; project neutral intent |
| `settings_audit.py`, `settings-keys.json`, `policy/*.json` | `settings.audit` | preserve as named Claude validator under provider doctor |
| `safe-dirs`, `safedirs.py`, auto-approve safe-dir evaluator | `security.safe-dirs` | preserve machine-owned fail-closed allowlist boundary |
| `hooks --auto-approve`, `hooks/auto-approve/**` | `lifecycle.auto-approval` | native provider mapping; never common event/key |
| `hooks --memory`, `hooks/memory/**` | `lifecycle.memory` | preserve semantic backend selection; native activation projected |
| `hooks/notify/**` | `lifecycle.notification` | provider-qualified native waiting/approval activation |
| `hooks/log-bash-command.sh` | `lifecycle.command-log` | provider-qualified command evidence |
| `router`, `hooks --router`, `router.py`, `hooks/agent-router/**` | `lifecycle.router` | one semantic routing surface; CLI generation is not a second identity |
| `hooks --run-report`, `hooks/run-report/**` | `lifecycle.run-report` | provider-qualified lifecycle capture |
| `hooks --pack-guard`, `hooks/pack-guard/**` | `lifecycle.pack-guard` | preserve managed-asset guard semantics |
| `hooks --changelog-gate`, `hooks/changelog-gate/**` | `lifecycle.changelog-gate` | preserve opt-in release gate semantics |
| `hooks/review-gate/**` and pack review-gate assets | `lifecycle.review-gate` | project through agent-pack/native lifecycle mapping |
| `hooks/daemon-safety/**` | `lifecycle.daemon-safety` | provider-native guard projection |
| `hooks/git-guardrails/**` | `lifecycle.git-guardrails` | provider-native guard projection |
| `hooks/observer/**`, `settings.observer.json` | `context.observer` | read-oriented provider context intent |
| `hooks --output-style`, `output-styles/**` | `context.output-style` | provider-native context/output projection |
| `hooks --plans-dir` | `context.plans-directory` | provider-native plan-directory projection |
| `mcp`, `mcp.py`, `mcp/*.json` | `mcp.catalog` | semantic server records; provider scope/path/serialization projected |
| agent role/content files inside `agent-packs/*/agents/**` | `agents.catalog` | semantic role/content/command requirements; native targets projected |
| `agent-packs`, `agentpacks.py`, pack manifests/templates/locks | `agent-packs.lifecycle` | preserve render/upgrade/remove/doctor/local-edit categories |
| `wf`, `wf_status.py`, pack workflow assets | `workflows.status` | read/report semantic workflow status; carrier projected through P4 |
| `doctor.py` environment branch | `doctor.environment` | preserve read-only package prerequisite diagnosis |
| `doctor --settings` composition point | `doctor.provider` | compose named validators; never relabel Claude merge semantics as universal |

Inventory result: `missing=[]`, `extra=[]`, `duplicates=[]` relative to the contract Surface
table. Reproduction sources:

```bash
rg -n '^COMMANDS|^[[:space:]]+"[a-z-]+":' packages/harness/lib/harness/cli.py
rg --files packages/harness/lib/harness packages/harness/configs/claude-code | sort
```

## Alternatives

| Alternative | Benefits | Failure/cost | Verdict |
|:--|:--|:--|:--|
| Keep `configs/claude-code` as the common schema and translate to Codex | smallest initial diff | Claude paths/events/permission vocabulary become a hidden public API; native trust/scope meaning is distorted | reject |
| Maintain independent Claude and Codex trees manually | native-looking outputs immediately | creates a second semantic canon and doubles security/repair drift | reject |
| Lowest-common-denominator settings object | compact schema | drops native lifecycle/trust/scope/agent features and hides unsupported states | reject |
| One universal autonomous/full-access profile | simple operator label | collapses approval and sandbox and permits implicit access expansion | reject |
| Stable semantic Profile/Surface catalog with independent provider projections | one intent catalog, native outputs, explicit unsupported/diagnostics, P2 ownership | requires frozen schema, provider mappings and independent conformance | accept |

The accepted alternative is the only one that preserves D2/D3/D5, D29 and the frozen
artifact/configuration boundaries without treating either provider output as source.

## Security-axis review

| Profile | Trust requirement | Approval intent | Sandbox intent | Selection rule |
|:--|:--|:--|:--|:--|
| `observe` | not required; no project executable activation | provider read/check policy | read-only | safe no-write baseline |
| `workspace-contained` | explicit trusted project | provider interactive or non-interactive | workspace/declared managed targets only | approval never widens sandbox |
| `trusted-full-access` | explicit trusted repository | exact explicit operation | provider-native full-access boundary | operation-only, target-specific, non-inheritable |

No provider default, project, fleet-project, fleet-default or legacy layer can select
`trusted-full-access`. Project trust alone cannot select it. Non-interactive approval alone
cannot select it. An unsupported sandbox/mapping cannot fall back to a wider mode.

## Negative/misuse cases

| Case | Required diagnostic/outcome |
|:--|:--|
| Full access is present in project/default/fleet/legacy input | `HARNESS_FULL_ACCESS_INHERITANCE_FORBIDDEN`; no render/write |
| Full access lacks exact current operation or target | `HARNESS_FULL_ACCESS_EXPLICIT_REQUIRED`; no render/write |
| Workspace profile is requested for an untrusted project | `HARNESS_TRUST_REQUIRED`; no activation/write |
| Required provider Capability is missing/unsupported | `HARNESS_CAPABILITY_UNSUPPORTED`; aggregate non-green |
| Provider surface/security binding is missing or ambiguous | `HARNESS_MAPPING_MISSING`; no nearest-profile fallback |
| Required secret reference is absent | `HARNESS_SECRET_REFERENCE_MISSING`; no write/activation |
| Resolved secret appears in output/lock/report/fixture | `HARNESS_SECRET_VALUE_EXPOSED`; block/redact, never publish |
| Existing target/value is unmanaged or user-owned | `HARNESS_OWNERSHIP_CONFLICT` / `HARNESS_USER_OWNED_CONFLICT`; preserve/refuse |
| Managed bytes drift | `HARNESS_MANAGED_DRIFT`; update refuses, explicit bounded repair only |
| Native activation is unsupported | `HARNESS_ACTIVATION_UNSUPPORTED`; visible unsupported row, no wrapper/polling emulation |
| One selected provider succeeds and the other required provider fails | provider-qualified partial result; aggregate non-green |

## Projection and compatibility verdict

- Common Profile/Surface records contain no provider path, hook event, low-level
  permission/model key or resolved secret value.
- Provider-native data exists only in projection `native_binding`, with capability/trust/
  activation evidence and independent Claude/Codex rendering.
- Current Claude preset names, merge-only writes, hook kill switches, MCP merge, agent-pack
  lock/upgrade/remove categories and settings doctor are frozen compatibility inputs.
- Actual provider output cannot regenerate the expected catalog, alternatives, misuse cases
  or golden results.
- Unknown/missing/unsupported mappings and corrupt ownership fail before write.

## Consumer handoff

| Consumer | Exact contract input |
|:--|:--|
| P5.2 | Profile/Surface records, three security axes, scopes/precedence, provider projection and diagnostics schemas; settings/security goldens G1–G4/G7. |
| P5.3 | Lifecycle/context Surface IDs, activation/trust requirements and unsupported-no-emulation rule. |
| P5.4 | MCP/agents/agent-pack Surface IDs, secret-reference boundary and P2 ownership/lock rules. |
| P5.5 | Independent exact-set inventory, all diagnostics/goldens, Claude compatibility and partial-provider non-green rule. |
| P5.6–P5.7 | Frozen harness provider registry/ownership/security boundary; no permission to weaken it from instruction projections. |
| Declared P6/P7 consumers | Immutable public profile/render/check/repair inputs only; deployment/live authority remains in their own gates and items. |

## Approval verdict

D79 authorizes evidence-backed contract-preserving decisions inside the active-plan scope.
This candidate creates the planned P5 contract without changing frozen P0–P4 semantics,
without expanding live/data authority and without opening an owner-level fork. D85 records
the delegated Approval Owner verdict:

```text
APPROVE P5.1 HARNESS H1-H7 AS WRITTEN UNDER D79
```

Accepted together: provider-neutral exact identity/catalog; independent trust/approval/
sandbox axes; operation-only non-inheritable full access; independent native projections;
explicit scopes/P1 precedence/P2 ownership; secret-reference-only diagnostics; Claude
compatibility; normative goldens; P5.2–P5.7 and declared later consumer boundary.
