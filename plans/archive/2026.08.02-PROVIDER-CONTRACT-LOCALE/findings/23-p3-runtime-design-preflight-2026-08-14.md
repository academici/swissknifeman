# P3.2–P3.3 design preflight — 2026-08-14

## Trusted route and environment

- Codex route evidence resolved from provider thread state as
  `gpt-5.6-sol/high`, cwd `/home/vostrikov/projects/packages/swissknifeman`, approval
  `never`, sandbox `danger-full-access`, exact invocation
  `$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P3.2-P3.3`.
- `codex doctor --json` returned `overallStatus=ok`.
- `packages/maind/bin/maind health --cwd` returned green for memory, MCP, hooks,
  project configuration and both provider trust rows.

## Reproduced hook boundary defect

From repository root:

```text
packages/harness/bin/harness hooks --target . --provider codex --observer --trusted --dry-run
```

returned exit `1` at `core/provider/lock.py:_root` with
`ValueError: root must be explicit and absolute`. The same command with
`--target /home/vostrikov/projects/packages/swissknifeman` returned exit `0`, plan
`sha256:46826563e47eb9a2362640a8ab435ec8830832480a9af675c4b46a4e36b9c3e8`, and two
`clean → noop` operation rows. Both runs were dry-run; no hook target was written.

This reproduces D42/F10 at the public Harness CLI boundary. P3.2 owns target
normalization before the explicit-absolute shared lock invariant; `core/provider/lock.py`
must not gain a relative-path exception. RAG:— (repo-grounded: observed commands above,
`packages/harness/lib/harness/hooks.py`, `core/provider/lock.py`, D42).

## Plan gate baseline

The initial worktree-local plan lint reported five errors and one warning:

- P3.2 mandatory-read weight `125817 > 100000`;
- P3.3 mandatory-read weight `3408343 > 100000`;
- P3.3 named the 11,724,457-byte fleet-classification corpus directly;
- terminal P2.2/P2.3 states lacked the printed write-site line although their terminal
  evidence already carried green Task Contract receipts;
- the P3 DoR checklist contained the literal clarification marker it claimed absent.

The first three are owned by this P3 design refinement. The P2 carrier defect is a
bounded append-only bookkeeping repair; the DoR literal is corrected in `phases/P3/P3.md`.

## Post-repair gate

Two append-only `local-repair` events added the already-proved
`write-site: pre_mutation: allow · pre_final: allow` line to P2.2/P2.3 projections without
changing their `🟢 Done` status. P3.2/P3.3 state views were regenerated after their stable specs
changed. The final worktree-local plan lint returned
`plan-lint: OK (1 план(ов), 0 ошибок, 0 предупреждений)`.
