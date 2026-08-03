# TASK-AUTHORITY-CARRIER-01 — independent review

**Verdict:** RED
**Reviewer route:** gpt-5.6-sol/xhigh
**Reviewed implementation commit:** b74027dcf06c4b3e495519102d08b85119a89683
**Plan snapshot:** sha256:28a9d23ef8bf1888c74676cd28cc494e5ac2ad0ce83db2798a264fc4cedeaa87
**Review date:** 2026-08-03

The scoped implementation commit removes the foreign D50 default, preserves the ordinary
32-item path and keeps the canonical command boundaries on one compiler. It cannot terminalize
the carrier because the protected-transition resolver accepts forged and non-exact authority
claims that the carrier requires to fail closed.

## Finding

### F1 · Blocker · protected authority matching is fail-open

`packages/task/lib/task/task_contract.py:234-252` treats any single Decision Log row with a
numeric D# greater than 64, the exact gate marker, an `owner source` substring, and branch/scope
substrings as a verified grant. It does not verify a real owner-source carrier, and it uses
substring rather than exact branch/scope matching. Consequently all three adversarial cases below
return `allow` instead of `block:AUTHORITY_BOUNDARY`:

- synthetic `D999` plus `owner source: fabricated`;
- requested branch `go-branch` against recorded `go-branch-extra`;
- requested scope `finite-scope` against recorded `finite-scope-extra`.

This violates Required repair 2 and the forged/synthetic, wrong-branch and wrong-scope acceptance
cases. The existing test at `packages/task/tests/test_task_contract.py:346-361` exercises only an
old D50 forgery and wholly different wrong values, so it does not detect the prefix/synthetic
fail-open. One owning repair should replace the plan-specific numeric cutoff and substring checks
with a checked exact carrier parser that binds gate, branch, finite scope, owner-source reference,
uniqueness and later revocation, then add these three cases as permanent regression tests.

## Acceptance matrix

| Case | Expected | Observed at reviewed commit + plan snapshot | Result |
|:--|:--|:--|:--|
| Ordinary Artifex path | 32/32 build and both predicates allow; no foreign D50 | 32 unique items; routes `frontier/high=12`, `implementation/high=19`, `frontier/xhigh=1`; 32 allow; 0 foreign-D50; 32 distinct item carriers | GREEN |
| Exact matching owner grant | allow | exact D65 marker/branch/scope/owner-source fixture returned `allow` | GREEN |
| Missing marker | `block:AUTHORITY_BOUNDARY` | blocked | GREEN |
| Forged/synthetic D# | `block:AUTHORITY_BOUNDARY` | old D50 blocked, but synthetic D999 returned `allow` | RED |
| Wrong gate | `block:AUTHORITY_BOUNDARY` | blocked | GREEN |
| Wrong branch | `block:AUTHORITY_BOUNDARY` | different branch blocked, but `go-branch-extra` returned `allow` for `go-branch` | RED |
| Wrong scope | `block:AUTHORITY_BOUNDARY` | different scope blocked, but `finite-scope-extra` returned `allow` for `finite-scope` | RED |
| Later revocation | `block:AUTHORITY_BOUNDARY` | blocked | GREEN |
| Ambiguous duplicate grants | `block:AUTHORITY_BOUNDARY` | blocked | GREEN |
| Caller restores D50 through legacy kwargs | typed refusal or checked carrier wins | `authority_granted_by=` raised `TypeError` | GREEN |
| Two `plan-exec` boundaries and inherited `plan-run` | one checked compiler/resolver | 2 `plan-exec` build calls; 1 `plan-close` build call; `plan-run` inherits canonical `plan-exec`; 0 manual-authority kwargs in those commands | GREEN |

## Exact verification evidence

All package commands below ran in detached worktree
`/tmp/task-authority-review.sJ3yNy` at the reviewed implementation commit, with the exact plan
snapshot above copied in before execution:

| Command | Exit/result |
|:--|:--|
| `git diff-tree --no-commit-id --name-status -r b74027dcf06c4b3e495519102d08b85119a89683` | exit 0; only `CHANGELOG.md`, `packages/task/lib/task/task_contract.py`, `packages/task/tests/test_task_contract.py` |
| `rg -n -F 'D50 (G-EXEC for self-host P0-P3)' packages/task/lib packages/task/commands` | exit 1; no live runtime/canonical-command match |
| Independent Python 32-build evaluator over `phases/P*.md` using each routed actual route | exit 0; 32 items/32 unique; 32 `pre_mutation=allow` + `pre_final=allow`; 0 D50 provenance |
| Independent Python protected-transition matrix, including exact/missing/forged/wrong/ambiguous/revoked/manual-kwargs cases | process exit 0; 3 semantic failures: synthetic D999, branch superstring, scope superstring |
| Independent command-boundary counter over canonical `plan-exec.md`, `plan-run.md`, `plan-close.md` | exit 0; 2/1/1 expected calls/inheritance and 0 manual-authority kwargs |
| `PYTHONPATH=packages/task/lib python3 -m unittest discover -s packages/task/tests -p 'test_task_contract.py'` | exit 0; 78 tests; OK |
| `PYTHONPATH=packages/task/lib python3 -m unittest discover -s packages/task/tests -p 'test_canon_literals.py'` | exit 0; 15 tests; OK |
| `python3 packages/task/scripts/render-provider-commands.py --check --root .` | exit 0; check OK/no-op |
| `bash packages/task/scripts/validate.sh` | exit 0; 484 tests; `validate: OK` (archived-plan warnings remain non-fatal/pre-existing) |
| `python3 packages/task/scripts/plan-lint.py plans/2026.08.03-ARTIFEX-SUPERVISOR` | exit 0; 0 errors/0 warnings |
| `PYTHONPATH=packages/task/lib python3 packages/task/scripts/plan-lint.py --conflicts` | exit 0; 0 conflicts/0 warnings |
| `python3 plans/verify-citations.py --strict plans/2026.08.03-ARTIFEX-SUPERVISOR` | exit 0; 2 citations checked/0 findings |
| `find plans/2026.08.03-ARTIFEX-SUPERVISOR -type f -print0 \| sort -z \| xargs -0 sha256sum \| sha256sum` | exit 0; plan snapshot hash recorded above |

## Preflight and scope

- `codex doctor --json`: exit 0, overall `ok`, model `gpt-5.6-sol`; the assigned session effort is
  `xhigh` (the runtime does not export effort).
- `packages/maind/bin/maind health --cwd`: exit 0, connected, memory round-trip green.
- `packages/harness/bin/harness doctor --provider-audit --json`: exit 0, empty diagnostics.
- Trusted Codex hook dry-run: exit 0 but non-green `warning`; both lifecycle hook and handler are
  pre-existing `stale-source -> update (source-changed)` rows already owned by future P4.4. This
  review did not repair or waive them.
- Package implementation, generated artifacts, Producer evidence, P0.1-P6.4 state/deliverables,
  Artifex product code, docs, release/fleet/Brain/provider/pilot/hook state and unrelated dirty
  paths were not changed.

## Terminalization decision

Carrier `State` remains `waiting`. `Independent verification` remains unchanged, and P0.1 remains
closed even though the latest design audit is GREEN. The producer must repair F1 in a new scoped
implementation commit and relaunch a separate cold frontier/xhigh reviewer; this RED artifact is
durable evidence and is not overwritten.
