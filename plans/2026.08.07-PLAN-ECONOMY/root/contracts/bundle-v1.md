# Bundle Contract v1

Status: frozen by `P3.1` on 2026-08-08.

The machine-readable shape and its single illustrative instance are defined by
[`bundle-v1.schema.json`](bundle-v1.schema.json). The schema is the sole source of field names,
required members, and value constraints. This document defines their semantics and does not restate
the schema.

## Purpose, reader, and location

A bundle is the committed, deterministic input manifest for one plan item. Its reader is the
executor-path resolver and the gates that validate that path. Under `read-path` v1 it occupies slot
4, after the stable plan core, phase context, and selected item specification, and before the
volatile item-state projection. The carrier path is `bundles/<Pn.m>.json`.

The manifest replaces informal resolution of `Inputs` and `Required Reads`. It binds the normalized
declaration from those two specification fields to exact, ordered input units. A unit is either a
whole file or an explicitly declared section/symbol slice. In the latter case the entry binds both
the raw bytes of the source file and the selected bytes; an inferred or unanchored slice is invalid.

## Two independent assertions

The declaration block proves **resolution freshness**: its canonical digest is recomputed from the
normalized `Inputs` and `Required Reads` of the selected item. The entries prove **input integrity**:
the digest of each complete source file is recomputed from its raw bytes, without newline, encoding,
or content normalization. A sliced unit additionally carries the digest of its selected raw bytes.
For a whole-file unit the selected-byte digest MUST equal the complete-source digest.

These assertions are deliberately independent. A bundle can be fresh relative to the item
specification while an input file has changed, or can retain intact input bytes after the item
specification changed. They therefore produce different failure codes and different remediation.

## Provenance, weight, and canonical manifest digest

Provenance identifies the generator and its version, plus the `calibration_id` and `model_id` that
define the `estimated_tokens` unit. A weight without all four values is not reproducible.

The top-level manifest digest is SHA-256 over the UTF-8 JSON serialization of the complete instance
with only the top-level manifest-digest member omitted to avoid self-reference. Canonical JSON uses
lexicographically sorted object keys, separators `,` and `:` with no surrounding whitespace, LF for
the final newline, no trailing spaces, and array order exactly as declared. `$schema`, when present,
is part of the payload. Entry order is declaration order and is not sorted by path.

The declaration digest uses the same serialization rules over the declaration block with only its
own digest member omitted. Both declaration arrays preserve their source-field order; ordinal values
are one-based within each source field.

Recorded declaration, source, selection, and manifest digests are provenance and fast diagnostics,
not guarantees. A gate MUST reconstruct the normalized declaration, resolve each unit, read the
actual bytes, and recompute every applicable digest. It MUST NOT accept a recorded digest merely
because the rest of the recorded manifest agrees with it.

## Closed failure taxonomy

The taxonomy is closed; there is no catch-all code.

| Code | Severity | Condition and remediation |
|:--|:--|:--|
| `missing_entry` | ERROR | A declared input has no corresponding entry. Rebuild the bundle after fixing resolution. |
| `stale_vs_spec` | ERROR | The recomputed normalized declaration differs from the recorded declaration digest or ordered declaration. Rebuild from the current item specification. |
| `hash_mismatch` | ERROR | Recomputed raw source bytes or selected bytes differ from their recorded digest. Inspect the input change, then rebuild only if the change is intended. |
| `unresolvable_entry` | ERROR | A declaration cannot resolve to an existing file or to its explicit slice. Repair the declaration; this is not proof of tampering and MUST remain distinct from `hash_mismatch`. This is the fail-closed implementation of deferred decision D16. |
| `extraneous_entry` | WARNING | An entry has no declaration counterpart. Regenerate the bundle; the readable declared set is not made invalid by the stale surplus record. |

The schema blocks support these outcomes without implementation-specific inference: the ordered
declaration and its digest support `missing_entry`, `stale_vs_spec`, and `extraneous_entry`; the
path plus explicit selector support `unresolvable_entry`; the source and selected-byte digests
support `hash_mismatch`; provenance makes every estimated weight reproducible. A new failure class
or a field unrelated to one of these checks requires a new contract version.

## Commit and regeneration policy

Bundles are generated files and are committed. Committing makes resolution reviewable and lets CI
detect drift from the item specification and input bytes. The known failure modes are handled as
follows:

- generator-version churn is visible in provenance and produces a reviewed regeneration diff;
- merge conflicts are resolved by regenerating from the merged specification and tree, never by
  manually merging bundle records;
- environment-dependent false staleness is forbidden by raw repository bytes, explicit selectors,
  and the named calibration/model pair; a generator that cannot reproduce those inputs fails closed;
- incomplete coverage is detected against both authoritative declaration fields, not against a
  separately maintained inventory.

## Rejected alternatives

- **One digest for declaration, inputs, and manifest.** Rejected because it cannot distinguish
  `stale_vs_spec` from `hash_mismatch`, which have different causes and repairs (D39; R8.1).
- **`extraneous_entry` as ERROR.** Rejected because a surplus record is a regeneration diff, not a
  failure to read the declared set; weight enforcement already penalizes the surplus (D41; R8.4).
- **Trust the recorded digest without recomputation.** Rejected because body and digest can drift or
  be edited together; frozen verification recomputes from actual bytes (D40; R8.2).
- **Normalize input contents before hashing.** Rejected because inputs are repository files, not
  transported archives; a second definition of “the same file” would weaken the byte identity
  required by `read-path` v1 (D40; R8.3).

Supply-chain signatures, publisher identity, and SLSA/in-toto build provenance are outside this
contract. There is no registry or untrusted publisher in this boundary; only the manifest form,
content digests, frozen verification, and failure separation are transferred from lock-file
practice.
