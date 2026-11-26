# P08.Z — Runtime and role porting acceptance

This record covers the P08 acceptance gate on branch `p08z-impl`, product revision
`26dbe09b1816ff7a51ef33e25f14560dfb8b5cc6`, inspected on 2026-11-17.
The documentation commit adds only this file and the
[runtime evidence matrix](../evidence/runtime-matrix.md). That matrix records the
actual commands, results, skips and limits of the acceptance claim.

The normative inputs were the P08.Z acceptance card, runtime owner §§4.3, 4.7.1, 4.9–4.11, 15–16 and 18,
the canonical name registry, and security rules S7, S12, S22, S22a and S23. Current behavior is
[runtimes, context and extensions](../architecture/runtimes-context-extensions.md) and
[`modules/runtimes/`](../../src/skm/modules/runtimes/).
The [codebase map](../architecture/CODEBASE-MAP.md) and `codegraph explore` in this
worktree were used to locate the final port, adapters and behavioral tests.

## Donor provenance

The donor inspected read-only was `/home/vostrikov/projects/packages/swissknifeman`,
HEAD `4170498110ccbdf147d9335cfe6d44a2a075a1c8`. In the table, `orch/` means
`<donor>/packages/orch/lib/orch/`, and `aicore/` means
`<donor>/packages/aicore/`. These are source coordinates, not relative links to
this isolated worktree. No donor packages were imported, donor tests run, or
donor files changed. Line numbers in older specifications have moved; names and
current source semantics were checked rather than assuming those offsets.

## Porting map

| Donor source | v2 destination | Disposition and preserved or changed semantics |
|---|---|---|
| `orch/launch.py`, `orch/catalog.py`, `orch/bindings/native.py`; `packages/orch/configs/launch-catalog.json` | [AgentRuntime](../../src/skm/modules/runtimes/ports.py), [runtime registry](../../src/skm/bootstrap/runtimes.py), [adapters](../../src/skm/adapters/runtimes/), [model data](../../resources/packs/core/runtimes/models.toml) | REWRITE-KEEP-IDEA / MIGRATE AS DATA: admitted model/effort and launch arguments remain explicit; detection and start/events/cancel/result are per-runtime implementations behind one synchronous port. Role launch dictionaries are not runtime authority. |
| `orch/conductor/process.py`: `run_role`, `parse_stream`, `partial_usage`, `_wait`, `_reap_group` | [shared CLI session](../../src/skm/adapters/runtimes/_cli_session/), provider `stream_parser.py` / `usage.py` under [adapters](../../src/skm/adapters/runtimes/), [process ownership](../../src/skm/platform/process/) | PORT-REFACTOR: stdin prompts, partial usage, bounded drain and cancellation remain; typed events require a native terminal, one terminal event and an idempotent result. Exit 0 or plausible result text cannot repair a missing terminal. PID/process-group best effort alone does not prove containment. |
| `aicore/lib/aicore/provider/errors.py`: `ErrorRule.matches`, `classify_signals`; `aicore/configs/provider-errors.json` | [error rules](../../src/skm/modules/runtimes/domain/error_rules.py), adapter `error_rules.toml` | PORT-REFACTOR / MIGRATE AS DATA: ordered normalized signal/text classification, retryability and reset-aware waits. Process outcomes such as `RUNTIME_STREAM_INCOMPLETE` remain distinct from provider rules. Execution owns retry/fallback decisions. |
| `aicore/lib/aicore/provider/models.py`; `aicore/configs/model-catalog.json`, `provider-capabilities.json` | [catalog](../../src/skm/modules/runtimes/domain/catalog.py), [capabilities](../../src/skm/modules/runtimes/domain/capability.py), adapter `capabilities.toml`, [core models](../../resources/packs/core/runtimes/models.toml) | REWRITE-KEEP-IDEA / MIGRATE AS DATA: neutral selectors replace personal pools; static native/adapted claims carry tested versions and limitations. Exact host verification gates enforcing capabilities; inventory or replay alone cannot certify an installed CLI. |
| `orch/conductor/process.py`: `_usage`, `partial_usage`; `orch/conductor/infrastructure/usage.py` | [runtime usage](../../src/skm/modules/runtimes/domain/usage.py), provider usage parsers, [execution budgets](../../src/skm/modules/execution/domain/budget.py) | PORT-REFACTOR: fresh tokens = input + output + cache write, excluding cache read. Missing usage/cost remains unknown/null. Cumulative accounting, partial crash usage and subagent disclosure are explicit; runtime output does not establish billing authority. |
| `orch/conductor/policies/routing.py`: `correction_refusal`, `grown_paths`, `route_minimum` | [admission](../../src/skm/modules/runtimes/domain/admission.py), [routing](../../src/skm/modules/runtimes/domain/routing.py), [session decision](../../src/skm/modules/execution/domain/session.py) | PORT-REFACTOR: operation-specific minimum class/effort, bounded-fix scope and deterministic refusal; continuation cannot lower its original floor. Runtimes filters resume, execution alone chooses Resume/Fresh after authority, installation, scope and session guards. |
| `packages/orch/scripts/ro-run.py`, `orch/sandbox.py` | [sandbox adapters](../../src/skm/adapters/sandbox/), [security evidence](../evidence/runtime-config-isolation.md) | PORT-REFACTOR: retain inherited Landlock write restrictions; remove default shared `/tmp` write grants for unattended execution. Landlock alone proves neither read isolation nor network/lifecycle confinement. Required properties need a bound companion/container proof or `SANDBOX_UNAVAILABLE`. |
| `orch/conductor/heal.py`, `orch/conductor/domain/semantics.py`, role launch entries | [repair](../../src/skm/modules/execution/domain/repair.py), [semantics](../../src/skm/modules/execution/domain/semantics.py), [role stages](../../src/skm/modules/execution/host/stages/) | PORT-REFACTOR / DROP separate fixer role: deterministic form repair preserves raw evidence and cannot improve meaning. Seven roles use typed results; invalid form retries the same role with schema errors under ordinary admission. Registrar defaults to deterministic metadata without an LLM invocation. |
| `orch/conductor/questions.py`, supervisor/recovery and autopilot mechanisms | [recovery domain](../../src/skm/modules/execution/domain/recovery.py), [host recovery](../../src/skm/modules/execution/host/recovery.py), [consilium](../../src/skm/modules/execution/domain/consilium.py), [autopilot](../../src/skm/modules/execution/domain/autopilot.py), [execution commands](../../src/skm/modules/execution/application/commands/) | REWRITE-KEEP-IDEA: immutable question/answer bindings and live authority checks, conservative stall recovery, ordered consilium, approved queue only. Silence/unknown identity is not kill authority; continue does not reset spent counters or session origin. |
| Review/triage findings and fix-brief flow under `orch/conductor/` | [fix brief](../../src/skm/modules/execution/domain/fix_brief.py), [triage](../../src/skm/modules/execution/domain/triage.py), [read-only reproduction](../../src/skm/modules/execution/host/reproduce.py) | PORT-REFACTOR: stable finding identity and bounded feedback; a triager's unsupported rejection cannot clear a finding. Independent reproduction requires actual read-only enforcement, bounded execution and recorded evidence. |

## Retired mechanisms and explicit limits

Closed provider/role tuples, the hard-coded `claude-code` fallback, a separate
`report-fixer` runtime role, and a separate `bounded-implementer` role are not
carried into the seven-role v2 contract. Bounded fix is an admitted operation of
the executor. Provider aliases are resolved by registration, not by importing
donor launch/binding packages. The donor currently also has Antigravity launch
exceptions; these do not establish a fifth supported v2 adapter or widen P08.Z.

Personal client HOME fallback, untrusted checkout settings/hooks as authority,
and optimistic success from malformed streams or missing telemetry are excluded.
Client homes and exact verification identities replace ambient client state;
unsuppressible Codex `AGENTS.md` is recorded as runtime self-loaded context.
Grok's unsuppressible project settings refuse unattended routing outside the
explicit trusted profile; Cursor's unknown headless contract refuses start.

P08.Z does not re-certify the entire P07 execution phase. The
[execution porting record](execution.md) retains its own historical evidence;
the P08 command in the matrix checks roles, retry, reproduction, supervisor,
autopilot, fix feedback and M3 at the revision stated above. Paid live evals and
provider verification remain `not_run` / unverified. Independent manual review
is `not_requested`; executor self-check is recorded separately in the matrix.
