# P6 provider provision conformance

Generated through the worktree-local mAInd public APIs on temporary roots.

| Case | Providers | Root + five package consumers | Second run | Health/doctor | Verdict |
|:--|:--|--:|:--|:--|:--|
| Claude-only legacy | claude-code | 6 | no-op | untrusted non-green | GREEN |
| Codex-only | codex | 6 | no-op | untrusted non-green | GREEN |
| Dual-provider | claude-code, codex | 12 | no-op | untrusted non-green | GREEN |

| Boundary check | Result |
|:--|:--|
| Claude-only legacy: harness semantic parity/extensions | semantic IDs=64; single-provider projection; public checker GREEN |
| Codex-only: harness semantic parity/extensions | semantic IDs=52; single-provider projection; public checker GREEN |
| Dual-provider: harness semantic parity/extensions | common parity IDs=49; provider-own extensions=18; public checker GREEN |
| managed drift and explicit repair | non-green then repair GREEN; outside-before/outside-after preserved |
| unknown/unsupported provider | rejected before write |
| implicit full access | refused |
| missing/duplicate instruction scope | INSTRUCTION_SCOPE_INVALID |
| stale source hash | INSTRUCTION_STALE_SOURCE |
| managed drift repair only managed block | non-green then repair GREEN; outside bytes preserved |
| one-provider partial failure critical aggregate/allow-partial | non-green; explicit --allow-partial remains required |
| independent provisioner/provider matrix | 30 explicit support/activation/diagnostic rows |
| public onboard instruction step | present |

All roots were temporary. `sync` used the frozen `harness.instructions`
plan/check/apply/repair API; mAInd did not parse, render or translate instruction files.

| Provisioner | Provider | Support | Activation | Diagnostic |
|:--|:--|:--|:--|:--|
| mcp | claude-code | adapter-projected | planned | none |
| mcp | codex | adapter-projected | planned | none |
| code-graph | claude-code | provider-neutral | not-applicable | MAIND_PROVIDER_NEUTRAL |
| code-graph | codex | provider-neutral | not-applicable | MAIND_PROVIDER_NEUTRAL |
| graph | claude-code | provider-neutral | not-applicable | MAIND_PROVIDER_NEUTRAL |
| graph | codex | provider-neutral | not-applicable | MAIND_PROVIDER_NEUTRAL |
| memory | claude-code | provider-neutral | not-applicable | MAIND_PROVIDER_NEUTRAL |
| memory | codex | provider-neutral | not-applicable | MAIND_PROVIDER_NEUTRAL |
| memory-hook | claude-code | delegated | not-observed | MAIND_DELEGATED:memory-context |
| memory-hook | codex | delegated | not-observed | MAIND_DELEGATED:memory-context |
| health-hook | claude-code | delegated | not-observed | MAIND_DELEGATED:health |
| health-hook | codex | delegated | not-observed | MAIND_DELEGATED:health |
| health-doc | claude-code | delegated | not-observed | MAIND_DELEGATED:health |
| health-doc | codex | delegated | not-observed | MAIND_DELEGATED:health |
| feature-log-hook | claude-code | delegated | not-observed | MAIND_DELEGATED:health |
| feature-log-hook | codex | delegated | not-observed | MAIND_DELEGATED:health |
| ecosystem-skill | claude-code | delegated | not-observed | MAIND_DELEGATED:skills |
| ecosystem-skill | codex | delegated | not-observed | MAIND_DELEGATED:skills |
| setup-skill | claude-code | delegated | not-observed | MAIND_DELEGATED:skills |
| setup-skill | codex | delegated | not-observed | MAIND_DELEGATED:skills |
| skills-catalog | claude-code | delegated | not-observed | MAIND_DELEGATED:skills |
| skills-catalog | codex | delegated | not-observed | MAIND_DELEGATED:skills |
| agent-pack | claude-code | delegated | not-observed | MAIND_DELEGATED:agent-pack |
| agent-pack | codex | delegated | not-observed | MAIND_DELEGATED:agent-pack |
| output-style | claude-code | delegated | not-observed | MAIND_DELEGATED:memory-context |
| output-style | codex | delegated | not-observed | MAIND_DELEGATED:memory-context |
| router-config | claude-code | delegated | not-observed | MAIND_DELEGATED:router |
| router-config | codex | delegated | not-observed | MAIND_DELEGATED:router |
| instructions | claude-code | adapter-projected | failed | INSTRUCTION_TARGET_MISSING |
| instructions | codex | adapter-projected | failed | INSTRUCTION_TARGET_MISSING |
