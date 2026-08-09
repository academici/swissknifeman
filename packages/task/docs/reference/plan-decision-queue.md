# Decision queue

`plan-decisions.py` writes requests, leases, responses, and automatic-answer events to the
append-only `decisions/queue.jsonl` carrier. The owner reads only the generated
`decisions/_gates.md` projection; the raw queue is never an executor read-path input.

Use `request`, then `claim`, then `resolve`. Before append, the writer validates the frozen request
or response shape, authority-frame assignment, timestamp, provenance, options, and recomputed
canonical/policy digests. The transient construction `action` is folded into the durable
`canonical_action` projection and is never stored as an extra request field (D145).

A request parks only its subject through a journal `blocked` event. Resolution requires the lease
and exact continuation identity. Only an option whose outcome is `apply` returns a continuation and
sets the subject to `in-progress`; `park`, `reject`, and `escalate` remain blocked. An automatic
answer must carry its matching policy response and verified provenance; a reclassification to
`authorization` remains blocked. Every subject transition regenerates and verifies its item-state
and owner-status projections before it is reported successful.

`Decision Queue Gate | v1` in plan Meta enables the opt-in join check: terminal phases cannot carry
an unresolved queue request. It is absent by default.
