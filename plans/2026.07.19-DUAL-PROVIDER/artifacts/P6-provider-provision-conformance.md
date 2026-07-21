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
| public onboard instruction step | present |

All roots were temporary. `sync` used the frozen `harness.instructions`
plan/check/apply/repair API; mAInd did not parse, render or translate instruction files.
