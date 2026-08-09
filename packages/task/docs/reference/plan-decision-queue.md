# Decision queue

`plan-decisions.py` writes requests, leases, responses, and automatic-answer events to the
append-only `decisions/queue.jsonl` carrier. The owner reads only the generated
`decisions/_gates.md` projection; the raw queue is never an executor read-path input.

Use `request`, then `claim`, then `resolve`. A request parks only its subject through an existing
journal `blocked` event. Resolution requires the lease and the exact continuation identity; it
resumes the original root when available, otherwise records an explicit `cold-start-root` reason.

`Decision Queue Gate | v1` in plan Meta enables the opt-in join check: terminal phases cannot carry
an unresolved queue request. It is absent by default.
