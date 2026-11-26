---
name: code-review
description: Review code changes for correctness, safety, conventions, and test coverage without modifying files.
---
# Code Review

For a requested diff review, stay read-only and inspect the affected contract, implementation, and tests.

## Rules
1. Inspect the contract, implementation, and tests against adopted project decisions.
2. Trace concrete failure scenarios: correctness, security, data integrity, concurrency, and performance.
3. Verify that test assertions cover changed paths and error branches.
4. Report actionable findings with location, trigger, impact, and proposed resolution.
5. Never modify code or files directly during a review step.
