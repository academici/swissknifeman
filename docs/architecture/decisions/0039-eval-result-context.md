# ADR 0039: An evaluation result carries the context it was produced in

## Status

Accepted

## Context

A benchmark number is comparable with another only when the skill, the fixtures, the grading rules and the runner are
the same. The earlier benchmark files recorded the numbers and not these facts, so two files could not be told apart
after the skill, the grader or the model changed.

## Decision

- **A context record.** Every result carries `context` in `eval-context/v1`
  (`packages/aicore/schemas/eval-context/v1/eval-context.schema.json`): `skill` (`id` and `digest`, or `null` for a
  bank that is not about one skill), `fixtures` (`id`, `version`, `digest`), `grader` (`id`, `version`) and `runner`
  (`provider`, `cli_version`, `models`).
- **Digests.** The skill digest is `aicore.content.skill.skill_digest`. The fixtures digest is the digest of the
  canonical JSON (`aicore.util.digest.digest_json`) of the evals and pressure documents of the skill, or of the case
  document of the system bank.
- **Observed values only.** `cli_version` is read from `--version` (null on error or after 10 seconds); `models` is the
  sorted union of the `modelUsage` keys of the run answers, and `[]` when none was seen. Nothing is invented.
- **Grader version.** `GRADER_VERSION` in `aicore.content.eval` is raised whenever the rules of `grade_assertion`
  change; the system bank keeps the version of its own grader document.
- **Comparison.** `compare_eval_context(a, b)` returns the sorted paths that differ (`skill.digest`,
  `runner.models`, ...); an empty list means the results are comparable.
- **Result versions.** `skill-benchmark/v2` becomes `v3` and `system-bank-benchmark/v1` becomes `v2`; both add
  `context` and keep every other key, so readers of the old keys still work. The report prints a `Context:` line.
  Old benchmark files are not rewritten.

## Alternatives considered

- Store only a model name: rejected, a changed skill or grader would still go unnoticed.
- Put the context in a separate file: rejected, it separates the number from the facts it depends on.

## Consequences

- Results with different contexts are shown as not comparable instead of being compared silently.
- A fake runner in tests can state its version and models, so the record is tested without a real CLI.

## Supersedes

None.
