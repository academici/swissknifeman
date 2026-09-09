# P2 design baseline — 2026-09-09

RAG:— (local source, preserved incident carriers and preflight observations).

## Preflight

- Route evidence matched the exact invocation and repository cwd: `gpt-5.6-sol/high`, class
  `frontier`, source `provider-thread-state`.
- `codex doctor --json`, `packages/maind/bin/maind health --cwd` and
  `packages/harness/bin/harness doctor` were green. The first mAInd probe supplied a value after the
  boolean `--cwd` flag and failed as a procedural input error; the corrected local-CLI invocation was
  green.
- Initial plan-lint was green with one optional warning for absent `index.md`.
- The worktree already contained unrelated root-roadmap deletions and this untracked plan directory;
  P2 design treats them as owner work and changes only this plan's carriers.

## Current seams

- `plan_blocking` validates a closed block capsule but has no baseline/diff or original-carrier
  consistency fields; after a `JUSTIFIED` review, concrete boundary evidence is sufficient for
  `terminal-block`. A misclassified clean-baseline failure can therefore survive the reducer.
  RAG:— (repo-grounded: packages/task/lib/task/plan_blocking.py:41-54,164-203).
- `plan_downstream.discover_consumers()` derives an edge from path intersection and the gate then
  selects executable Validation text. It has no typed producer mode, no explicit empty-by-decision
  result and no producer-readiness payload for the consumer bundle.
  RAG:— (repo-grounded: packages/task/lib/task/plan_downstream.py:104-163).
- `plan_returns.returns()` observes execution→plan-design returns, but not pre-terminal re-entry
  proposals or priority-fix outcomes, matching the preserved P7.1 visibility gap.
  RAG:— (repo-grounded: packages/task/lib/task/plan_returns.py:580-632).
- The current locale ledger is no longer the empty historical scaffold: it declares three inventory
  roots and admitted rows. Its old empty/no-op cases remain valid regression evidence, but rewriting
  corpus content is not a current P2 prerequisite.
  RAG:— (repo-grounded: configs/locale-corpus-v1.json:11-24).
- The canonical archive command still makes `brain sync` a precondition before `git mv`, even though
  terminal state, journal, home and delivery are repository-owned.
  RAG:— (repo-grounded: packages/task/commands/plan-close.md:365-393).

## Design verdict

Put one closed repair classifier before both block confirmation and redesign; let producer readiness
and terminal-phase re-entry consume that decision instead of defining another repair policy. Keep
`block-candidate/v1` as the downstream terminal-boundary proof. Represent readiness and re-entry as
validated additive journal evidence, project the producer payload into the consumer bundle, and keep
archive entirely repo-local. No external fact class or RAG retrieval is required for P2.

## P2.2 item-design delivery observation — 2026-09-09

The first design delivery probe accepted a handoff whose metadata table still declared
`frontier/gpt-5.6-sol` while its native successor command correctly launched
`implementation/gpt-5.6-terra`. The design root rejected that receipt, repaired the persisted
handoff source before final delivery, and reran bundle/lint/delivery checks. This is retained as a
validation-trust observation only; it does not add a second routing policy or widen P2.2 beyond its
existing lint/delivery/provider-parity surface. RAG:— (repo-grounded: `handoff.md` design repair;
`plan.md` §3 `B-P2-CONTINUE`).
