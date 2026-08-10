# Downstream Gate Contract v1

Status: frozen by `P3.7` on 2026-08-08.

The machine-readable shape is
[`downstream-gate-v1.spec.json`](downstream-gate-v1.spec.json). The JSON is the sole source of
field names, outcome flags, activation, and result-key members; this document defines their
semantics without copying those lists.

## Purpose and boundary

When one plan item produces a path consumed by another item, the producer must smoke-check the
consumer's recorded expectations before the producer closes. The check executes the consumer's
declared `Validation`; it does not execute the consumer's implementation or infer expectations from
prose. The gate is deterministic except for the commands being executed and does not call a model.

The contract is shared and provider-neutral. It does not change `journal.jsonl`, define escalation
qualification, or enable the closing-command integration. P6 owns command integration and rollout.

## Mechanical consumer discovery

A consumer is discovered only through normalized repository-relative path identity and forward item
order. Paths declared by the producer's output fields are intersected with paths declared by later
items' input fields. A prose similarity, phase adjacency, or manually maintained consumer list never
creates an edge; item order supplies direction but cannot create an edge without a path match.

An empty consumer set is observable. Callers may treat an unexpected empty set as a specification
defect, but they must not add a remembered consumer by hand.

## Applicable Validation subset

Validation commands remain in declared order. A command is applicable when every repository path it
addresses exists in the tree of the producer commit. Dotted `unittest` module names are resolved
relative to the command's declared `cd` directory. Commands with no addressed repository path are
applicable by construction.

Non-applicable commands are not executed. If the applicable subset is empty, the result is
`unknown`; this is recorded and is neither pass nor failure. An applicable command that exits
non-zero produces `red`; otherwise a non-empty applicable subset produces `green`.

## Blocking force and refusal semantics

`red` blocks producer closure. `green` and `unknown` do not, but all three outcomes are records, not
absence of data. The tool has no advisory or warn-only switch: output-format and record-writing
options never change the exit status of `red`.

The aggregate result is `red` if any applicable command fails, `green` if at least one command is
applicable and all applicable commands pass, and `unknown` only when no command is applicable.
Per-consumer records preserve an individual `unknown` even when another consumer makes the aggregate
green.

## Result identity and carrier

Each consumer result is keyed by the SHA-256 of the exact consumer item-spec bytes and the resolved
producer commit. Both values are mandatory. A changed consumer specification therefore invalidates
an older record even when item IDs are unchanged. Among append-only records for the current consumer
specification, the record for the newest producer commit in the current `HEAD` ancestry is effective;
incomparable producer branches are an error. This lets a green rerun after a producer fix supersede
an earlier red without erasing evidence.

The record is an item-scoped finding whose `item` is the producer. One finding is written per
consumer, and its frontmatter carries the result key, consumer identity, outcome, date, and gate ID.
The existing history projection can discover the record without adding a journal field or a new
carrier class.

## Linter rollout

The linter check is disabled by default and activates only through the exact Meta opt-in declared by
the adjacent specification. Once active, each terminal producer with mechanically discovered
consumers must have a structurally valid current-spec record; a recorded `red` remains an error.
P3.7 does not enable the opt-in on any plan.

## Transferred evidence and limits

The design transfers only contract-testing semantics recorded in
`findings/08-gates-and-manifests-2026-08-07.md` R10: verify published consumer expectations, retain
an explicit unknown state, bind a verification to contract content and producer version, and do not
leave a gate in an always-successful advisory mode. Broker services, environments, deployment
matrices, and production-version reasoning are outside this single-repository plan boundary.
