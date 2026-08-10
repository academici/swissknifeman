# History Projection v1

Status: frozen by D127 after the `P1.5` owner gate on 2026-08-08.

Machine-readable input declaration:
[`history-projection-v1.spec.json`](history-projection-v1.spec.json). The JSON is the sole source of
field lists and enum subsets; this document defines their semantics without copying them.

## Purpose, reader, and authority

The historical projection gives the `auditor` a chronological view of attempts, deviations,
escalations, decisions, and item-scoped findings. It is a replaceable view, never a primary record.
The authoritative inputs remain the sealed append-only journal, immutable decision records, and
item-scoped findings.

The view does not replace `plan-audit`, make a quality or policy judgement, or prove that an item was
well executed. It only assembles declared evidence. Deleting a materialized view must not delete any
meaning needed to rebuild it.

## Exact three-source declaration

For one subject item, input is the union of exactly three sets:

1. journal records whose `item_id` equals the subject;
2. decision records whose frontmatter `item` equals the subject;
3. findings whose frontmatter `item` equals the subject.

The adjacent specification names the journal fields already present in the sealed
`2026.07.18-FOREMAN` schema and the minimum frontmatter required on the other two sources. It cannot
require a journal field outside `task.journal.REQUIRED_FIELDS`; in particular, free-form `note`
cannot be treated as a structured relation.

P2 may add decision or finding metadata, but it cannot remove the declared minimum. Association is
subject-based and originates from decision/finding frontmatter, per D24; this contract does not add a
decision or finding link to `journal.jsonl`.

## Ordering and replacement links

All records are normalized to an event time. Journal `ts` is used directly; a date-only decision or
finding is normalized to midnight UTC. The total order is event time ascending, then the fixed
source rank `journal`, `decisions`, `findings`, then the source's stable identity ascending. This
tie-breaker is deterministic and is not a statement of causal precedence.

Decision replacement is bidirectional: an older record names `superseded_by`, and its successor
names `supersedes`. Both fields are present even when null or empty, so a projector never infers
current status from missing metadata. Findings carry subject and date; a finding may refer to
decisions in its body but does not manufacture journal relations.

## On-demand materialization

Materialization is `on-demand` under D23 and is not committed to the repository. The default target
is the non-authoritative cache address registered as `history-view`. An audit may preserve a copy as
evidence only when it records the projection boundary `through` and `inputs_sha256` of the canonical
versioned input manifest. Those values support reproduction; they do not turn the copy into truth.

For identical ordered inputs and projector version, output is deterministic and idempotent. The
projector cannot call a model, read wall-clock state into output, or mutate source records.

## Executor exclusion boundary

No carrier whose registry `class` is `history` may appear in any executor-path slot. This covers the
full journal, the materialized history view, historical decision records, and archived decision
views. The machine predicate joins the reader registry to `read-path-v1.spec.json`; it does not grep
documentation prose. History remains discoverable to the auditor and is never deleted for
convenience.

## Failure behavior and boundaries

Missing required frontmatter, a required journal field outside the sealed schema, an unknown enum
value, an unresolved bidirectional replacement link, an ambiguous stable identity, or malformed
projection metadata fails closed. The projector does not silently skip the record or weaken the
input declaration.

This contract does not define the full decision-record schema, implement the projector, alter the
journal writer, define read slots, or enable lint checks. Those responsibilities remain in P2, P1.4,
and P3. D12, D23, and D24 are the governing decisions.
