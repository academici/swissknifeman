# P4 plan-protocol contribution review

**Decision:** ACCEPTED for P4.4 under D79 owner delegation.

## Contribution gate

| Check | Evidence | Verdict |
|:--|:--|:--|
| Rule of Three | Claude plan commands, generated Codex task skills, and provider-neutral `plans/<ID>` handoffs consume the same routing/Next semantics. | pass |
| Shared contract | The frozen D84 command-routing contract defines ordered classes, effort, capabilities, semantic Next, and provider renderers. | pass |
| Dependency direction | `task.command_render` consumes the immutable command catalog; plan-protocol documents consume stable semantic IDs. Neither shared package imports a provider runtime or user config. | pass |
| Minimal public surface | One frozen carrier, one fail-closed dispatch planner, and compatible plan-lint parsing; no second command inventory or runner. | pass |
| Backward compatibility | Existing six statuses, 16 fields, journal/commit topology, historical slash Next inputs, and P4.3 Claude command/plugin bytes remain unchanged. | pass |
| Validation boundary | Contract-authored fixtures cover exact/overshoot/undershoot, missing/ambiguous mapping, orchestration capability, both renderers, and legacy Next. | pass |

## ADR

**Context.** Shared plans currently mix semantic routing with Claude model names and slash UI.
Codex cannot safely infer an equivalent tier or invocation, while two command canons would drift.

**Decision.** Store neutral classes (`economy < implementation < frontier`), independent effort
(`low < medium < high < xhigh`), and semantic Next kinds/command IDs. Validate mappings,
capabilities, and both route axes before rendering. Render Claude `/task:…` and Codex
`$ task:…` only at the provider boundary. Keep historical provider strings as compatibility
inputs and provider examples.

**Rejected alternatives.** Provider names in the shared schema were rejected because they make
Claude the implicit routing authority. Two provider-specific plan protocols were rejected because
they duplicate load-bearing lifecycle semantics. Lowest-common-denominator routing and silent
single-agent fallback were rejected because both weaken frozen gates.

**Consequences.** Plans and handoffs become portable; missing/unknown/ambiguous mappings,
undershoot, and missing orchestration support fail before invocation or write. Provider adapters
retain native selectors and UI syntax. P4.3 Claude bytes do not change.

**SemVer.** Additive carrier/renderer and compatibility parser: task routing contract minor;
plan-protocol skill minor. Any future change to status/field/Next meaning, axis order, or diagnostic
outcome requires a major contract decision.
