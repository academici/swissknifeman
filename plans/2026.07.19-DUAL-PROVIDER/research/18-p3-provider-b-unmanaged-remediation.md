# P3.4 remediation design — unmanaged provider-B vendor target

## Inputs

- `findings/P3.5-provider-b-unmanaged-partial-success-2026-07-20.md`
- frozen `root/contracts/provider-skill-publication-contract.md` v1.0.0
- `phases/P3.md` P3.4/P3.5 and D58

## Diagnosis and choice

The defect is in P3.4's already-declared `skillset.py` ownership/apply seam, discovered by
P3.5 before it made conformance claims. P3 itself is non-terminal, so phase-reopen rules do
not apply. Reopening P3.4 is smaller and more traceable than adding P3.6: its existing Scope,
Files, routing and frozen-contract inputs already cover provider-selected vendor planning,
unmanaged ownership, partial failure and repair.

P3.4 returns to `🟡 In progress`; P3.5 remains `🔴 Blocked` until its prerequisite repair
commits and validates. This preserves historical P3.4 completion evidence in git while making
the current status truthful. D78 records the narrow sequencing/acceptance correction; neither
the P3.1 contract nor P4+ scope changes.

## Prescribed repair

Before the first selected provider's managed vendor write, `do_sync()` must examine every
precomputed immutable provider plan. Any unmanaged `conflicts` entry without the caller's
explicit `--force` must terminate with provider-qualified `SPUB_OWNERSHIP_CONFLICT`, name the
provider/channel/target and give a repair action. It must not call `_do_sync_provider()`, write
Claude or Codex skills/locks, or register a project. An explicit `--force` remains the existing
opt-in overwrite path and is not evidence for the safe default.

The repair uses the existing `plan_sync()` conflict classification; it adds no resolver,
provider-specific selection formula, public symbol, lock schema or rollback promise. A runtime
copy failure after a clean preflight remains an honestly blocked/mixed outcome under the
existing P3.4 behavior and test; this narrow repair closes only the unvalidated prerequisite.

## Acceptance evidence

Add a `TemporaryDirectory` dual-provider test in P3.4's distribution suite that seeds an
unmanaged selected Codex skill directory and asserts: `SystemExit` with
`SPUB_OWNERSHIP_CONFLICT`/`codex`; no `.claude/skills`, no managed Codex copy, no
`skills-lock.json`, and no registered provider record. Re-run the existing provider-B
copy-failure-and-repair case to preserve its distinct post-preflight semantics. P3.4's focused
suite and package validation must be green before P3.5 resumes.

RAG:— (repo-grounded: the inputs above; frozen contract's Diagnostics and P3.4 Implementation
Rules).
