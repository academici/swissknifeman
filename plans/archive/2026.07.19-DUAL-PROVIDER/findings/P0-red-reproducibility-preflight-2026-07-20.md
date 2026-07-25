# P0 RED reproducibility preflight — 2026-07-20

## Scope and anchors

- Repository: `/home/vostrikov/projects/packages/swissknifeman`.
- Audited committed input: `1544cfe113acc03174c17d40085b553c0a9187f9`.
- Audit carrier: `phases/P0.md` → `## Audit P0 — 2026-07-20`.
- This finding is repo-grounded; it introduces no external capability claim.

## Cold preflight

- Effective session: `gpt-5.6-sol/xhigh`; launch uses unrestricted execution with no
  approval prompts. `codex doctor --json` returned overall `ok`.
- Every registered hook command resolved. Synthetic logger, daemon-safety allow/deny,
  review-gate and SessionStart probes returned their prescribed results.
- `maind health --cwd` returned `connected`; an independent MCP
  write → recall → forget round trip succeeded and removed its synthetic fact.
- The worktree was dirty before this task. In particular, the current
  `packages/task/**` and plan-protocol source changes are user-owned input: they may be
  inspected read-only, but must not be staged, modified, copied into, or claimed by P0.6.

## Lint split

The live effective tree returned:

```text
plan-lint: OK (1 план(ов), 0 ошибок, 0 предупреждений; новых от рабочего дерева: 0)
```

The same command in a clean detached worktree at `1544cfe` returned exit 1:

```text
ERROR: .../journal.jsonl:11: запись не проходит схему P1.1: friction: обязан быть массивом ...
plan-lint: ПРОВАЛ (1 план(ов), 1 ошибок, 0 предупреждений; новых от рабочего дерева: 0)
```

Therefore the live 0/0 result is not G01 evidence: it depends on uncommitted validator
bytes that are absent from the committed tree.

## Why a plan-local-only repair is impossible

At `1544cfe`, `packages/task/lib/task/{journal,plan_lint}.py` has no
`journal-exceptions.jsonl` reader/writer contract, and the committed plan-protocol canon
has no historical-exception schema. The active plan already carries the D51 sidecar, but
the committed linter cannot consume it. The remaining plan-local ways to make that linter
green would be to rewrite/remove historical `journal.jsonl:11` or weaken/skip the strict
journal gate. Both violate the explicit audit anti-scope and append-only/fail-closed rules.

Conclusion: P0.6 needs a separately approved, exact-scope shared-package prerequisite.
The prerequisite must be reimplemented from a clean committed worktree; the current dirty
package bytes are not an admissible implementation input.

## Historical evidence anchors

| Evidence | Source tree recorded by finding | Item commit | Bookkeeping commit | Finding SHA-256 |
|:--|:--|:--|:--|:--|
| P0.1 | `9844f499797faf063aede49b79703c71f7ef666e` | `f4d230e6e83aac56ab7fe82a085b7bb18d59d6de` | `d8ac22c04fc4d4219dc95244ee9d181e92553a74` | `23f8bccce5fcbfc1841ef0373fad4bf0ed5c341b25b037f797eb3c5695550b88` |
| P0.5 | `d8ac22c04fc4d4219dc95244ee9d181e92553a74` | `56239e92dfaa3aa7ec51e15727e94783f14c9370` | `566719e2602b2571726c91e72d5f71cec99c441d` | `39913b25e9dd3a454f311ab69b2e072d117438b1c23c6aa0f1ae54ed4a682996` |

`config.json` is ignored by `.gitignore:25` and absent from the committed tree. P0.1's
historical finding already records the redacted project-ID set, but its checker reads the
ignored live file. P0.5's finding records a pre-item HEAD/status, while its checker compares
against the post-commit live HEAD/status byte-for-byte. Both checks therefore need one
committed anchor manifest and must stop depending on the live worktree.

## Verification status

- Repo evidence: complete for the RED reproduction and the no-plan-local-solution verdict.
- External claims: none.
- Workarounds: none accepted; dirty-tree green is explicitly rejected as evidence.
