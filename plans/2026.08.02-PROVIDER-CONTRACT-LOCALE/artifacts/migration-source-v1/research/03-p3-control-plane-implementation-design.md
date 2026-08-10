# P3 control-plane implementation design

## Traceability

| Requirement or fact | Destination |
|:--|:--|
| Canonical intent is separate from provider observations | P3.1 immutable desired snapshot and P3.2 one-way adapter input |
| Provider projections remain independently owned | P3.2 target declaration, capability gate and readback protocol |
| Locale policy is canonical and surface-independent | P3.1 typed P2 input only; P4 owns rendered text |
| Fleet migration must preserve local work | P3.3 diagnostic/action recommendation; P5 owns any mutation |
| No health claim without both providers' evidence | P3.3 complete provider rows and non-masking aggregate; P6 owns fleet claim |

Sources: `brief/00-brief.md`, `research/01-target-architecture.md`,
`findings/05-p1-contract-verification-2026-08-02.md`,
`findings/07-p3-control-plane-recon-2026-08-02.md`, frozen P1/P2 contracts once their
producer items are terminal, and the archived dual-provider contracts.

## Ownership map

`core/provider` is the only shared semantic layer. P3.1 adds a pure desired-snapshot
composition over existing provider selection, capability support and managed artifact
provenance. It neither reads host state nor serializes a new configuration file. P3.2 adds a
small reconciliation protocol around existing artifact plans: the protocol may coordinate
observe/diff/apply/readback, but does not reimplement target ownership, hashes, repair or
capability semantics. P3.3 adds a redacted, adapter-scoped status record and aggregate result.

Each package supplies a thin adapter over its present domain: Harness owns runtime profile and
hook/MCP projections; Maind owns fleet-layer config/deploy planning; Skiller owns project
selection/publication/update; Task owns semantic command projections. An adapter receives a
desired snapshot and can inspect/write only its declared provider-owned target. It cannot
modify canonical intent, other-adapter status, or another provider's target.

## Execution sequence and gates

P3.1 must finish first because P3.2 needs a stable desired snapshot. P3.2 must finish before
P3.3 because status is evidence of an adapter readback, not a speculative inventory. All three
items remain closed until P0 supplies recovery evidence and P1/P2 create the frozen contract
files named in P3 Inputs. Absence of a contract or unknown major refuses; P3 never derives its
own replacement schema from the plan prose.

The status aggregate is intentionally not a fleet-health verdict. It has a complete row for
each required provider and returns non-green when one is missing, unreadable or erroneous.
P5 turns classified migration recommendations into owner-safe actions; P6 later aggregates
per-project evidence. This leaves P3 useful for P4–P7 without smuggling a fleet operation into
the implementation phase.

## Проверка

RAG: no new external fact class. Existing desired/observed and versioned-upgrade rationale is
verified in `findings/05-p1-contract-verification-2026-08-02.md`; every new claim here is
repo-grounded by the P3 reconnaissance.

Непроверено → ПОВТОРНЫЙ ПРОХОД: frozen P1/P2 contract content does not yet exist and must be
read, version-pinned and reconciled immediately before P3 execution.

Обходки/[POSSIBLE-DEFECT]: none. The current untracked runtime locator and stale hook plan are
explicit P0 evidence, not a P3 implementation shortcut.
