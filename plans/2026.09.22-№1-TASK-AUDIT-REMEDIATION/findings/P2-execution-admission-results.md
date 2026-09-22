# P2 execution admission results

## Outcome

P2.1 closes the five confirmed false-green paths at the Task package boundary.
The implementation stays deliberately narrow: it does not add provider authority,
journal durability, per-chunk signatures, bundle privacy policy, or consumer rollout.

| Claim | Before | P2 result | Regression evidence |
|:--|:--|:--|:--|
| N-01 | `check` returned zero when mutation allowed but final blocked. | The legacy full gate returns zero only for `allow/allow`; JSON output remains stable. | Real `python -m task.task_contract check` subprocess, blocked and valid controls. |
| N-02 | Chunk metadata could claim bytes that were never transported. | Every chunk is bound to snapshot/path/member digest/offset/actual bytes/terminal state; reconstructed bytes and digest are rechecked. | Substituted/empty/wrong-end/wrong-path/wrong-digest/post-terminal negatives plus valid multi-chunk flow. |
| N-04 | Caller-authored `completed_prefix` could skip work. | Mandatory and recommended branches derive the contiguous prefix from current validated terminal evidence; receipts only bind it. Plan/spec/routing/handoff drift stales continuation. | Fabricated-prefix negatives in both branch policies, terminal-evidence positive, identity-tamper matrix. |
| N-05 | Compiled declarations were labelled runtime proof. | Compiler emits `declared`; `validation-receipt/v1` binds command, contract, spec, current product tree, HEAD and environment. Missing/non-zero/stale receipts block final. | Declared-only, non-zero and stale-HEAD negatives plus successful bound receipt. |
| N-13 | Root CI omitted Task. | One Task matrix job runs the package validator once per supported Python; the sole Ruff step includes Task source and tests. | Structural workflow parser verifies job, matrix, command uniqueness and Ruff scope. |

## External sanity check

One bounded Perplexity `search` query checked the five-invariant design. It found no
coherence blocker and warned against per-chunk cryptographic objects, caller receipts as
authority, and mixing terminal concurrency/durability into this slice. P2 therefore uses
one immutable snapshot plus reconstructed-content verification; atomic terminal history
remains P4 scope. The answer cited GitHub Actions workflow semantics and SLSA artifact
verification. It was used as a design sanity check, not as acceptance authority.

## Compatibility

- `task.task_contract check` keeps its command and JSON result shape; scripts that relied
  on zero for `block:*` must migrate because that behavior was the defect.
- `batch-receipt/v1` stays readable. Newly compiled receipts carry the current handoff
  digest, and continuation refuses old/null or otherwise stale identity at admission.
- `validation-receipt/v1` and `validation-context/v1` are additive. A declared shell
  validation can no longer close final without a successful current receipt.
- `plan-context-chunk/v1` keeps its wire fields; metadata-only or altered-byte transports
  are intentionally rejected.

## Validation and field boundary

The owner explicitly kept real-project testing for P6. P2 performs package-level
regressions, the full Task suite, the package validator, plan lint/bundle checks and diff
hygiene only; no Corex, Agentools or Edufy source worktree is changed. P6 owns the paired
real-project runs and any consumer documentation/migration wording that field behavior
proves useful.

Package evidence on 2026-09-22:

- scoped Ruff over the changed Task implementation/tests: GREEN;
- `python3 -m unittest discover -s tests -v` from `packages/task` with the package
  `PYTHONPATH`: 1125 tests GREEN, one skipped;
- `bash packages/task/scripts/validate.sh --plan plans/2026.09.22-№1-TASK-AUDIT-REMEDIATION`:
  GREEN, including the same 1125 tests, plan lint, conflict scan and provider projection
  check.

The terminal journal event binds these successful commands to the final contract,
specification, product-tree, HEAD and environment digests.
