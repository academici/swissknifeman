# P3 audit repair-forward evidence — 2026-08-12

**Scope:** bounded repair after `Audit P3 — 2026-08-12`; stable item Intent, Scope,
Files and Validation and all P3 product bytes remain unchanged.

## Committed-tree validation anchors

| Item | Terminal tree | Exact Validation evidence |
|:--|:--|:--|
| P3.1 | `a8867749` | `PYTHONPATH=packages/task/lib python3 -m unittest packages.task.tests.test_journal packages.task.tests.test_plan_item_state` — 45 focused tests; `bash packages/task/scripts/validate.sh` — 842 tests, 1 skipped, `0 ERROR / 7 WARN`, exit 0. |
| P3.2 | `c1a92619` (terminal bookkeeping; product `1e8b5651`) | `PYTHONPATH=packages/task/lib python3 -m unittest packages.task.tests.test_plan_command_routing packages.task.tests.test_route_evidence packages.task.tests.test_canon_literals` — 85 focused tests; `rg -l 'Continue-first block gate \\(v1\\)' packages/task/commands/plan-{exec,run,design,audit,close}.md \| sort` — 5/5 paths; `rg -n 'local-repair\|block-candidate\|routing-rejected\|ROUTE-UNVERIFIABLE' packages/task/commands/plan-{exec,run,design,audit,close}.md` — four classes in 5/5 commands; `bash packages/task/scripts/validate.sh` — 843 tests, 1 skipped, `0 ERROR / 8 WARN`, exit 0. |
| P3.3 | `381adc74` (terminal bookkeeping; product `2f795943`) | `PYTHONPATH=packages/task/lib python3 -m unittest packages.task.tests.test_plan_lint_conflicts packages.task.tests.test_plan_lint_contracts` — 79 focused tests; conflict gate, provider renderer `--check`, and `scripts/docs-sync.sh --check` — exit 0; `bash packages/task/scripts/validate.sh` — 846 tests, 1 skipped, `0 ERROR / 5 WARN`, exit 0. |

All three terminal records retain `write-site: pre_mutation: allow · pre_final: allow`.
The refs above are the only refs for interpreting their stated counts; product refs alone
are not substituted for the terminal bookkeeping trees.

## P3.3 material deviation

Product commit `2f795943` changed five carriers absent from the stable P3.3 `Files` field:
`CHANGELOG.md`, `packages/skiller/adapters/codex/core/publication-lock.json`,
`packages/skiller/adapters/codex/core/skills/general/plan-protocol/SKILL.md`,
`packages/skiller/docs/guide/budget.md`, and `packages/skiller/skills.json`.

D19 authorized owning regeneration but did not expand P3.3 `Files`. Per the status rule,
this is a material scope deviation: P3.3 is therefore `🟠 Done with deviations`. No product
bytes are changed by this repair-forward record.

## Pending risk for P5.2

**P5.2 pending risk — glob/brace fingerprint under-binding.** The fingerprint collector treats
declared glob/brace literals as direct `Path` values, so provider/runtime and brace-set files can
be represented as missing rather than fingerprinted. P5.2 owns the audit/closure-lifecycle fix;
this P3 repair records the risk only and makes no runtime change.
