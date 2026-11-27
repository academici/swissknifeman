---
name: tdd
description: "Drive a behavior change with a failing test, a minimal implementation, and a verified refactor."
---

# TDD

Identify one observable behavior and use the current test suite's normal
entry point. Write a test that expresses the behavior from a caller's
perspective. Run it and confirm it fails because the behavior is missing.

Implement enough to make that test pass without weakening its assertions.
Keep fixtures and implementation focused on the behavior under test. Run
related tests to verify callers and surrounding behavior.

Improve clarity after the tests pass. Re-run verification after each refactor.
Repeat for the next behavior, and report the checks that ran and any coverage
constraints.
