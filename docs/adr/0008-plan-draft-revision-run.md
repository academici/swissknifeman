# ADR 0008: Plan / Draft / Revision / Run separation

Status: proposed
Date: 2026-10-25

## Context
Legacy item and unit documents hold both specification and mutable result (status, outcome).

## Decision
`Plan` is a stable identity. `Draft` is the editable canonical specification document with `edit_version`.
Publishing a draft creates an immutable `Revision` (typed spec rows + canonical payload + digest) with a linear
`revision_no`. A revision-backed `Run` executes exactly one pinned revision. An ad hoc `Run` has kind `adhoc`
and executes a pinned inline spec file version owned by its project. Execution state lives only in execution
tables. A draft based on an outdated revision fails to publish with `BASE_REVISION_CHANGED`. Publishing an
unchanged specification fails with `NO_CHANGES`.

### Run persistence

When writing a run row, `0013_execution_runs.sql` must verify that the pre-existing scope at `runs.id`
has `kind = 'run'` and `workspace_id = runs.workspace_id`. It must also verify exact `scope.parent_id`
equality with `runs.project_id` for `adhoc` runs and with `runs.plan_id` for every other run kind.
An absent scope or a null or mismatched scope field must fail validation. See [ADR 0007](0007-identity-uuidv7-display-keys.md#run-scope-parentage).

An `adhoc` row must have SQL `NULL` in `plan_id`, `revision_id`, and `revision_no` and must reference
an inline spec file version. SQL 0013 must resolve that version through `skm_artifacts.file_versions`
to `skm_artifacts.files` by workspace and file ID. The file must be in the run's workspace and its
`project_id` must equal `runs.project_id`. A missing version or a workspace-level file is invalid.
All other run kinds must have non-null `plan_id`, `revision_id`, and `revision_no`, retain their
project and revision constraints, and leave the inline spec reference null.

### Ephemeral execution

`--ephemeral` selects a host-local execution mode independently of run kind. The execution must be able
to run without a control plane. Consumption of `HOST_PRIVATE` episodes is recorded durably on the host
for every local run. Release 0.1.0 keeps local runs on the machine that executed them.

## Alternatives considered
- Mutable plan with history table: rejected — runs could observe changing requirements.
- Git-like merge graph of revisions: deferred.

## Consequences
Carry-forward of accepted results to a new revision is an explicit, manual operation in v2.0.

## Compatibility
Legacy statuses import as historical, unverified execution records.

## Verification
Domain and contract tests listed in `05` §8.3 and `06` §13.

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).

E18 preserves imported history as lossless imported_unverified data, without creating verified execution state. E52 requires prepared-candidate digest comparison on publication.
