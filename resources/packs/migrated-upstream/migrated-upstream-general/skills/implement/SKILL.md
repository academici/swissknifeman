---
name: implement
description: "Implement a chunk of work from a spec/PRD/issue via a minimal chain: tdd-discipline on agreed seams, risk-proportionate validation and review, commit to the current branch. Invoke EXPLICITLY (writes code) — the final step after spec-interview/grill-with-docs/to-issues."
---

# Implement

Implement the work described in the statement of work / PRD / issue. Minimalist skill: value is in discipline
chains, not in volume. Called **only explicitly** (`disable-model-invocation: true`).

## Algorithm

1. **Context.** Read the technical specifications/issue. If you touch the database schema, check the migrations first
   (`php artisan migrate:status` / schema state), then implement it.
2. **TDD where possible.** Use skill `tdd-discipline` on **pre-agreed seam'ah**
   (red→green→refactor vertical slices). Don't write all tests ahead.
3. **Risk checks.** Drive regularly typecheck and separate test files. Final check
   follows an explicit Validation or repository risk rules: this skill does not require
   full run by itself. Do not repeat a successful test without a change that could
   devalue its result, or the reproduced defect. Stack specific commands:
   - Laravel/PHP: `php artisan test` (or `./vendor/bin/pest`), `phpstan`/`./vendor/bin/phpstan`.
   - Dart/Flutter: `dart analyze`, `flutter test`.
   - TS/Vue: `vitest`, `tsc --noEmit` / `vue-tsc`.
4. **Review.** Apply `code-review` (or command `/code-review`) only when required
   risk, user or accepted PR-process; sufficient verification does not wait for additional
   reviewer verdict.
5. **Commit.** Commit to **current** thread (Conventional Commits, in Russian).

## Related skills

- `general/spec-interview` / `general/grill-with-docs` — where does the technical specification come from (input of this skill).
- `oss-dev/to-issues` — if the work came as a set issue vertical slices.
- `quality/tdd-discipline` — how to implement a slice (required dependency).
- `quality/code-review` — final check when required by risk, user or PR-process.
- `general/git-commit-rules` — commit format.
- `oss-dev/github-flow` — if further Issue→PR→Release.
