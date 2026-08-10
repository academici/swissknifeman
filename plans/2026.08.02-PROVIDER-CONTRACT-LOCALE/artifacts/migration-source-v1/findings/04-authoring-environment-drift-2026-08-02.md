# Authoring environment drift — Codex defaults vs active runtime

**Observed:** 2026-08-02 during `task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P0`  
**Evidence class:** local environment observation; no configuration values beyond route/security enums are copied.

## Observation

The session-start `codex doctor --json` reported configured model `gpt-5.6-sol`, approval
`Never`, and an unrestricted active filesystem sandbox. The final preflight reported configured
model `gpt-5.6-terra` while the active doctor sandbox still reported `Never` and `unrestricted`.

Read-only inspection showed the user Codex config (`~/.codex/config.toml`) mtime
`2026-08-02 18:49:11 +03:00` and these non-secret defaults: model `gpt-5.6-terra`, effort
`high`, approval `never`, sandbox `workspace-write`. The edit happened after this authoring
session had already started with its separately supplied runtime envelope.

## Verdict and impact

- Configured defaults and the active session runtime are different evidence classes; neither
  may be substituted for the other.
- There is no evidence that the already-running session changed model or lost its active
  filesystem authority. The successful plan writes and final doctor output are consistent with
  the original active runtime envelope.
- A future cold session can inherit the new defaults unless the semantic command route pins
  `frontier/high` and the repository launch contract pins approval/sandbox explicitly.
- The global config is user-owned external state. This design session did not overwrite or
  repair it.

## P0 disposition

P0.1 must capture configured defaults, live hook/runtime evidence and their mismatch as separate
rows in the redacted evidence bundle. A mismatch is never silently green and does not authorize
mutation. P0.3 assigns any required remediation to an exact owner-gated action.

## P1 authoring preflight

The P1 fresh-agent pass observed `codex doctor --json` with `overallStatus=ok` and configured
default model `gpt-5.6-terra`. The semantic command was nevertheless routed explicitly to
`gpt-5.6-sol/high`, so the authoring minimum was satisfied without treating the mutable global
default as session provenance. `packages/harness/bin/harness doctor --provider-audit --json`
returned an empty diagnostic set, and `packages/maind/bin/maind health --cwd` reported connected
memory with a successful round trip.

The baseline lint invocation returned 0 errors and one warning because the entire active plan
directory is untracked, so the linter could not archive a HEAD baseline or compute new-error
attribution. This is an evidence limitation: it MUST NOT be reported as «0 new errors». The P1
authoring pass therefore uses a separate plain-lint result as its structural verdict and keeps
baseline attribution pending until the plan exists in a committed tree.

Final P1 authoring verification reproduced that boundary: baseline mode reported 0 errors and
1 warning with attribution unavailable, while a separate plain run reported 0 errors and
0 warnings. Only the plain-run structural verdict is green; the baseline delta remains unknown.
The corrected compatibility command with
`PYTHONPATH=packages/skiller/lib:packages/maind/lib:.` completed with unittest outcome `OK`.

## P2 authoring preflight

The P2 preflight again reported `overallStatus=ok` and global configured model
`gpt-5.6-terra`. The `task:plan-design` adapter route remains `gpt-5.6-sol/high`; doctor
reports the configured default, not a per-session route attestation. This pass therefore
records `gpt-5.6-sol/high` as the semantic command route in plan provenance but does **not**
claim doctor independently proved the active runtime model. `maind health --cwd` and `harness
doctor` were green; plain `plan-lint` was `0 errors, 0 warnings`. The plan directory remains
untracked, so baseline-attribution remains unavailable and is not represented as a green delta.

## Finish preflight

The design-pass 3 preflight reported `codex doctor --json` `overallStatus=ok`, configured
model `gpt-5.6-sol`, approval `Never`, and an unrestricted active filesystem sandbox.
The worktree-local `packages/maind/bin/maind health --cwd` passed memory round-trip, Claude/Codex
trust and MODE=maind hook checks. The registered Codex lifecycle hook accepted a representative
`SessionStart` payload with exit 0; no hook exit 127/path defect was observed. These checks prove
the configured/runtime envelope and hook callability only; active reasoning effort remains
self-attested by the semantic `frontier/high` route.

The adapter-prescribed runtime lint lookup failed honestly: `codex plugin list --json` contains
no installed `task@swissknifeman`, so there is no unique enabled plugin root from which to launch
`scripts/plan-lint.py`. This is an environment/deployment defect, not a green runtime check.
The same worktree source was validated directly with
`PYTHONPATH=packages/task/lib python3 packages/task/scripts/plan-lint.py ...`; that result proves
the worktree linter only and is reported separately from the skipped installed-runtime projection.
