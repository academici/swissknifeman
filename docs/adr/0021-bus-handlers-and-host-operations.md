# ADR 0021: Two kinds of application code — bus handlers and host operations

Status: proposed
Date: 2026-10-25

## Context
In server mode the control plane runs on a server while checkouts and agent runtimes are on developer machines. Code
that runs git, reads checkout files or starts agent processes must not run on the API server.

## Decision
Bus handlers (`application/commands|queries`) touch only the database (through the Unit of Work) and control-plane
gateways. Host operations (`modules/<m>/host/*`) run on the host (CLI, worker, hook), use host gateways, and talk to the
control plane only through `SkmClient`, sending observed facts that the control plane re-validates with pure rules.

## Alternatives considered
- Run everything where the CLI runs: rejected (breaks server mode and worker separation).

## Consequences
Some features split into a host operation plus a recording command (bind checkout, detect runtimes, projections, stages).

## Compatibility
n/a.

## Verification
Architecture tests in [`tests/architecture/`](../../tests/architecture/) enforce the host and bus boundaries (historically DI-2 and DI-3).

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).

E19 bounds each live-input batch with fresh authorization/claim checks. Host stages receive only declared StageDeps/StageClient, not unrestricted HostContext or SkmClient.
