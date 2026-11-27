---
name: implement
description: "Implement an approved ticket within scope and verify its acceptance criteria."
---

# Implement

Read the ticket, specification, and repository instructions. Identify the
normal entry points, supported callers, and acceptance criteria. Review the
working tree before editing and preserve unrelated work.

Make the smallest coherent change that meets the criteria. Use existing
abstractions that preserve behavior. When a test can capture the requested
behavior, demonstrate the gap and verify that the implementation closes it.
Check failure paths and existing data when the change touches persisted state.

Run the requested checks and inspect the diff against the ticket. Report the
implementation, verification results, and any criteria that remain blocked.
Use any required review, commit, or publication workflow only within the scope
authorized by the user.
