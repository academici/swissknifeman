# ADR 0010: Transition through swissknifeman upgrade and an upgrade guide

## Status

Accepted

## Context

Live projects and a second computer must move to the new layout without manual file surgery.

## Decision

The hub CLI gets `swissknifeman upgrade` with `--dry-run` (a report of what changes), apply and `--rollback`, plus
a document `docs/upgrade/<version>.md` (requirements, backup, dry-run, apply, `doctor` check, rollback, second
computer). The upgrade is rehearsed on copies of projects in a sandbox and on a second computer; only then is the
branch merged and a major version tagged. The previous tag remains the rollback point.

## Alternatives considered

- Ask users to migrate by hand from release notes: rejected.

## Consequences

- Every change of file location needs a migration step that the dry-run can report.
- A provisioning stamp in each project (ADR 0023) tells the upgrade what configured it.

## Supersedes

None.
