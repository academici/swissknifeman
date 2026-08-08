# Item State Projection v1

Status: frozen by D127 after the `P1.5` owner gate on 2026-08-08.

Machine-readable shape and its single illustrative instance:
[`item-state-projection-v1.schema.json`](item-state-projection-v1.schema.json). The schema is the
sole source of field names and constraints; this document defines semantics without duplicating it.

## Purpose, authority, and location

The projection answers an executor's current-state question: what exists in this item's scope, where
the item stands, and what executable step comes next. It is a disposable read model over the
append-only journal, decision and finding records, and the repository tree. Those inputs remain
authoritative; the projection never authorizes a write-side decision and can be deleted and rebuilt.

The committed carrier is a separate generated file at `phases/<Pn>/<Pn.m>.state.md`, adjacent to the
stable item specification. Its registry identity is `item-state`, and its ownership class is
`generated-file`.

The rejected alternative is a `managed-block` (managed-блок) inside the item specification. D21
rejects it because separate file ownership makes manual edits structurally visible, removes marker
parsing and partial-update failure modes, and lets the freshness gate compare the complete generated
output. The additional file overhead is measured by P1.5 rather than hidden.

## Projection metadata

Every instance identifies the projection and reducer version, precisely declares its ordered input
scope, records the journal boundary included by the reduction, carries the SHA-256 of a canonical
versioned input manifest, and identifies the generator and its version. The adjacent schema makes
all six metadata members mandatory.

The input digest is provenance and a fast stale-state diagnostic. It is not an integrity boundary:
both body and digest could be edited together. The `through` boundary is meaningful only with the
declared ordering in `source_scope`.

## Closed current-state content

The body has five semantic positions only: current world facts in scope; item position and last
attempt outcome; one executable next step; item-specific active risks, workarounds, and decision
references; and a pointer plus command for the separately generated historical view. The schema
closes the object against additional properties so a convenience field cannot silently turn the
snapshot into an unbounded handoff or history log.

The historical pointer is navigation, not embedded history. Completion prose, old attempts,
superseded decisions, and unrelated phase status do not belong in the state projection.

## Routing exclusion and write-side safety

The resolved route is intentionally absent and forbidden by the closed schema (D22). `route` and
`routing` are not aliases or extension points. Routing remains authoritative in the stable plan core
and is read before expensive inputs. A last-slot projection cannot decide whether that reading was
permitted: doing so would trust a replaceable read model at the write-side safety boundary and would
recreate the F7 class of bypass.

## Determinism, freshness, and failure behavior

For identical ordered inputs and the same reducer version, generation is deterministic and
idempotent. The reducer cannot call a model, read wall-clock time as state, resolve live permissions,
or perform irreversible effects.

Freshness is checked by regenerating from authoritative inputs and comparing bytes with the
committed carrier. A matching recorded digest alone is insufficient. Missing files, schema-invalid
content, malformed metadata, unsupported projection versions, or byte drift fail closed with a
diagnostic naming the carrier and reason; the tool does not partially update or infer defaults.

## Boundaries

This contract does not implement the reducer, define history materialization, establish read-path
slot order, define the bundle, alter `journal.jsonl`, or enable lint gates. Those responsibilities
remain in P1.3–P1.4 and P2–P3. D5, D12, D21, and D22 are the governing decisions.
