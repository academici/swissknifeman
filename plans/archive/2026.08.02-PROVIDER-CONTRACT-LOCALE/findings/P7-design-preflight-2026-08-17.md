# P7 RED-recovery design preflight — 2026-08-17

## Route and repository

- Current route evidence: `gpt-5.6-sol/frontier/high`, thread
  `01a00e98-3b37-79b3-8c17-aefe38fa50bc`, cwd
  `/home/vostrikov/projects/packages/swissknifeman`, approval `never`, sandbox
  `danger-full-access`; the Task Codex route gate returned 0.
- `codex doctor --json` returned `overallStatus=ok`; `packages/maind/bin/maind health --cwd
  --json` returned `status=connected` with both provider trust rows green.
- The worktree was already dirty across owner, package, documentation, roadmap and P7 carriers.
  This design classifies rather than overwrites those bytes and authorizes no broad staging.

## Hook integrity

The first full-surface Codex lifecycle dry-run returned exit 1 with
`harness.codex.lifecycle.hooks: provenance-invalid → refuse (record-provenance-mismatch)`.
The owning worktree-local Harness command was then run once with the registered observer surface:

```text
packages/harness/bin/harness hooks --provider codex --target <repository-root> --observer --trusted --repair
packages/harness/bin/harness hooks --provider codex --target <repository-root> --observer --trusted --dry-run
```

Both final observations were `Статус: green`, plan
`sha256:46826563e47eb9a2362640a8ab435ec8830832480a9af675c4b46a4e36b9c3e8`, with hooks and
handler `clean → noop`. `.codex/hooks.json` parsed, `.codex/hooks/lifecycle.py` compiled, and the
`packages/` + `core/` diff digest was unchanged before/after
(`3f348b08d9cd15f94c4a706b6c34af593e9c3a358495f93c03a130ca27b91cc3`). RAG:—
(repo-grounded: observed worktree-local Harness outputs in this design session).

## Initial plan gate

The pre-mutation worktree-local plan lint reproduced exactly two P7 errors:

1. terminal P7.3 had the write-site codes embedded in one prose line instead of a standalone
   projection line;
2. P7.4's mandatory read weight was `112743/100000`.

These are deterministic bookkeeping/read-contract defects owned by this design pass. The P7.4
RED product/release findings remain authoritative and are not relabelled by their repair. RAG:—
(repo-grounded: `artifacts/P7-final-release-audit.md` and observed plan-lint output).
