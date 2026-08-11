# Decision queue

`plan-decisions.py` writes requests, leases, responses, and automatic-answer events to the
append-only `decisions/queue.jsonl` carrier. The owner reads only the generated
`decisions/_gates.md` projection; the raw queue is never an executor read-path input.

Use `request`, then `claim`, then `resolve`. Before append, the writer validates the frozen request
or response shape, authority-frame assignment, timestamp, provenance, options, and recomputed
canonical/policy digests. The request must contain both reserved `escalate` and `reject` choices;
the frozen 2–5 bound applies only to substantive choices. The transient construction `action` is
folded into the durable `canonical_action` projection and is never stored as an extra request field
(D145).

A request parks only its subject through a journal `blocked` event. Resolution requires the lease
and exact continuation identity. One semantic outcome reducer governs item state, the owner-gate
view, unresolved phase join, and returned continuation: only `apply` returns a continuation and
sets the subject to `in-progress`; `park`, `reject`, and `escalate` remain blocked. An automatic
answer must carry its matching policy response and verified provenance; a reclassification to
`authorization` remains `pending-authorization`, is visible in the owner gate, and remains blocked.
Every other automatic-answer outcome is terminal and single-use: later owner `claim` or `resolve`
calls, and malformed late queue events, fail closed. Therefore `pending-authorization` is the only
automatic-answer state that may enter an owner flow.

The queue is append-only but repairable. Retrying the exact canonical request or response reuses its
existing queue event and regenerates the journal, item-state, status, and owner-gate views. A
different payload or resolver remains fail-closed. A durable response never stores a continuation:
the API returns it only after all four carriers have been regenerated and byte-checked.

The producer acceptance at
`plans/archive/2026.08.07-PLAN-ECONOMY/artifacts/P5/validate_acceptance.py` uses fresh fixture copies to
exercise policy apply and its single-use boundary, authorization reclassification with its permitted
owner flow, P4→P5 owner `continue`/`park`/`reject`,
the 2- and 5-substantive-option boundaries, mandatory-only rejection, and one-shot request/resolve
projection failures followed by an exact retry. Its generated results deliberately omit volatile
timestamps and temporary paths while recording queue cardinality, latest journal result, pending and
join verdicts, view freshness, retry count, and continuation mode; `--check` recomputes all twelve
scenarios and compares the committed results and report byte-for-byte.

The terminal-phase join is forward-only from its activation record in
`configs/lint-check-dispositions.json`: a post-boundary terminal phase cannot carry an unresolved
queue request. Historic phases remain outside the obligation without a Meta escape hatch.
