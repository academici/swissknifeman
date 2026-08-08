# Reader Contract v1

Status: proposed; freeze is reserved for `P1.5` and the owner's gate.

Machine-readable registry: [`reader-contract-v1.registry.json`](reader-contract-v1.registry.json).
The registry is the sole source of carrier rows; this document defines their meaning and does not
repeat them.

## Purpose and closed reader set

The contract has exactly four readers:

- `designer` creates or reconciles specifications and needs the owner brief, synthesized research,
  phase evidence, plan identity, execution rules, routing, and neighbouring contracts. It must not
  consume unrelated item detail or attempt history by default.
- `executor` performs one item and needs the stable plan core, current phase context, that item's
  specification and declared inputs, and a current state projection. It must not consume decision
  history, other item specifications, prior attempts, status boards, or the handoff by default.
- `auditor` reconstructs decisions, attempts, deviations, escalations, and evidence. Compactness is
  not an entitlement and no current-state view may replace primary records.
- `owner` decides gates and next actions from status, open risks, approval queues, and the cold-start
  handoff. Implementation detail is available by reference, not on the default owner path.

The set is closed by D20. A carrier with no owner among these readers, or a fifth reader discovered
in practice, requires a new decision; it cannot be repaired by an `other` value. Every carrier has
exactly one `owner_reader`; secondary readers are declared in `also_read_by`.

## Rebuildability invariant and authority

A reader can be replaced, but the meaning needed to rebuild its view cannot be absent from the log.
Generated views are disposable and rebuildable. The brief, item specifications, journal, decision
records, findings, and research are primary records and cannot be replaced by a projection.

`on_path_of` declares only path membership. It does not establish slot order or mandatory/optional
semantics; those belong to `read-path-v1`. Registry paths are templates, not permission to scan a
directory: a reader resolves only the instances selected by its path contract.

The registry contains both current layout-v1 carriers and target layout-v2 carriers. A superseded
layout-v1 carrier names its target successor with `superseded_by`. Absence from the target path is
therefore explicit, not inferred from a missing row.

## Mutability classes

The closed classes are:

- `handwritten`: an author writes the carrier; a generator never replaces it.
- `append-only`: existing records are immutable; correction is a later linked record.
- `generated-file`: a generator owns the whole file. Manual edits are defects, and freshness is
  checked by regeneration followed by byte comparison.
- `managed-block`: a generator owns a delimited region inside a handwritten carrier. This is an
  exception and every such registry row requires a non-empty `managed_block_justification`.

A managed block uses paired Markdown sentinels in the namespace
`swissknifeman:plan-projection`. Both sentinels carry the same stable opaque block id, generator name
and version, and SHA-256 of the canonical versioned input manifest. The updater fails closed when a
pair is missing, duplicated for one id, nested without explicit parser support, or malformed; it
never inserts or partially updates a damaged region. It replaces only bytes between the matched
sentinels. A recorded hash is provenance and fast diagnosis, not integrity proof: the final check is
regeneration and byte comparison.

## Volatility classes

The closed classes are `stable`, `slow`, and `volatile`. Assignment is based on the observable write
event recorded in each row's `volatility_basis`:

- `stable` does not change while a phase is executed;
- `slow` changes at a phase or explicit design boundary;
- `volatile` changes on item attempts, item closure, or other routine execution events.

These are ordering inputs, not estimates. A blank basis or an intuitive assignment without a named
writer and event is invalid.

## Registry schema and evolution

Every carrier row in the adjacent JSON has `id`, `path`, `owner_reader`, `also_read_by`,
`mutability`, `volatility`, `volatility_basis`, `on_path_of`, and `class`. The closed carrier classes
are `spec`, `state`, `history`, `evidence`, and `index`. `managed_block_justification` is permitted
only where the mutability class needs it; `superseded_by` records layout replacement.

The registry version describes the layout contract, not an implementation release. P2 consumes the
declared target ids and may copy the machine contract into runtime configuration only byte-for-byte
with an equality test, per D29. Expanding the minimum carrier set or the reader enum requires a new
D-record and contract version; adding a concrete instance under an existing path template does not.

## Boundaries

This contract does not order slots, define the state or history projection body, implement any
generator, change the sealed journal schema, define bundles, or enable lint gates. Those boundaries
belong respectively to P1.2–P1.4 and P2–P3. D5, D12, D20, D21, and D29 remain the governing
decisions.
