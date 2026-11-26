# ADR 0023: Bytes enter only through staged blob upload

Status: proposed
Date: 2026-10-25

## Context
Database commits and file storage are separate failure domains; workers in HTTP mode cannot write the server blob store.

## Decision
`SkmClient.upload_blob` stages, verifies (size, digest) and promotes bytes into the immutable content-addressed store
before any database reference exists, recording a `staged_blobs` row. Commands accept `StagedBlobRef` and link it in their
transaction. Unconsumed staged blobs expire. In v2.0 referenced blobs are never physically deleted.

## Alternatives considered
- Upload inside the command transaction: rejected (no cross-system atomicity).

## Consequences
Two calls for each file write; orphans are detectable by `skm storage verify`.

## Compatibility
n/a.

## Verification
Fault-injection tests between promote and commit.

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).

E12 coordinates promote, staged registration, consume and cleanup under the same digest guard. Cleanup rechecks references; referenced final blobs are never automatically deleted.
