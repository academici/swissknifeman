# Journal historical schema exception — audit-r2 F1 remediation

**Дата:** 2026-07-19  
**Вход:** `findings/design-audit-2026-07-19-r2.md` F1; historical
`journal.jsonl:11`; repo seams `packages/task/lib/task/{journal.py,plan_lint.py}`;
read-only sealed v1 contract `plans/2026.07.18-FOREMAN/root/contracts/plan-journal-schema.md`.

## Problem and baseline

Event journal v1 одновременно требует: (a) existing lines never change; (b) every line
passes the current closed `friction` enum. Row 11 predates that discipline and carries five
free-form findings. Rows 22/25 preserve meaning but cannot make row 11 valid because current
linter validates lines independently. Baseline: HEAD
`9844f499797faf063aede49b79703c71f7ef666e`, plan-directory snapshot
`sha256:e388c95e3a901edd952cea4f0d2180b930a1985e0eadb400b36d16bb9c832095`, command
`python3 packages/task/scripts/plan-lint.py plans/2026.07.19-DUAL-PROVIDER` →
`1 ERROR / 0 WARN` at row 11. RAG:— (repo-grounded reproduction in this remediation).

## Alternatives

1. **Rewrite row 11.** Minimal runtime change, but violates append-only and loses the exact
   historical audit payload. Rejected.
2. **Correction record inside event journal.** Could define supersession, but changes the
   sealed event union and forces every progress/analytics reader to distinguish administrative
   corrections from executions. A legacy reader could count it as retry/no-op. Rejected.
3. **Owner-gated exception sidecar (selected, D51).** Keep event bytes/schema unchanged;
   add an optional append-only provenance carrier used only by writer/linter. Additive package
   surface, no event/current-state duplication.

RAG:— (repo-grounded: sealed v1 §1–§3; `journal.py`/`plan_lint.py`; owner approval D51).

## Sealed exception schema v1

Carrier: optional `plans/<ID>/journal-exceptions.jsonl`, NDJSON, append-only. One record has
exactly these required fields: `ts`, `plan_id`, `target_line`, `target_sha256`,
`invalid_fields`, `owner_decision`, `actor`, `reason`.

Invariants:

- `target_line` is a physical non-empty line in sibling `journal.jsonl`;
- `target_sha256` hashes exact UTF-8 bytes without newline;
- target is valid JSON, belongs to the same plan, and its actual schema-error field set equals
  `invalid_fields`; v1 allows only `friction`;
- `owner_decision` is a D# present in sibling `plan.md`;
- a target has at most one exception; hash mismatch, duplicate, already-valid target,
  malformed JSON, missing D#, or extra schema failures are ERROR;
- exception sidecar cannot target itself or another sidecar record, so cycles and exception
  supersession chains are structurally absent;
- exception waives only schema admission for the exact historical bytes. It does not change
  `note`, audit verdict, event ordering, Status Board, handoff, or current state.

## Writer, linter, lifecycle synchronization

- Writer: `python3 -m task.journal exception --plan-dir ... --target-line N
  --invalid-fields friction --owner-decision D# ...` computes raw hash and validates target,
  owner gate and duplicates before one append.
- Schema SSOT: `task.journal` exposes structured event errors plus strict exception validation;
  sealed event `REQUIRED_FIELDS`/enums remain unchanged.
- Linter: validates sidecar first, suppresses an event diagnostic only when one fully valid
  exception matches the physical line and exact error field set; sidecar defects remain errors.
- Lifecycle canon: plan-protocol 2.10.0 and journal template state that compensating events do
  not repair schema-invalid history; new D# supersedes the failed remediation, old D#/event stay.
- Package contribution: this cannot be solved consumer-side because shared writer and shared
  plan-lint enforce opposite gates for every dated plan. The optional sidecar is the minimal
  additive contract; `task` plugin bumps 0.1.0→0.2.0, event data format stays v1.

## Scope proof and verification

Allowed package files are limited to task journal/linter/tests/version and plan-protocol
journal lifecycle references. P0.1–P7.4 specs/implementation, instruction sequence P5.6→P7,
FOREMAN, ACTIVE, fleet and unrelated worktree files are unchanged.

Verification commands:

```bash
PYTHONPATH=packages/task/lib:packages/task/tests python3 -m unittest \
  packages.task.tests.test_journal \
  packages.task.tests.test_plan_lint.TestJournalIndexLayer
python3 packages/task/scripts/plan-lint.py plans/2026.07.19-DUAL-PROVIDER
```

## Проверка

- Внешних claims нет; RAG не требовался.
- Repo-grounded: baseline воспроизведён; target/event/sidecar invariants покрыты адресными tests.
- Final anchored lint и post-change snapshot: `findings/journal-remediation-verification-2026-07-19.md`.
