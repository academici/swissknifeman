Synthetic Layout-v2 scenarios are proven; P6 command integration and live fleet behavior are not proven.

# P5.5 producer-based acceptance report

The committed fixture queue is regression input only. Every scenario starts from a fresh copy, removes that queue, and reaches its observations through runtime producers.

| Scenario | Outcome | Queue events | Latest journal | Pending | Join | Retry | Continuation |
|:--|:--|:--|:--|:--|:--|--:|:--|
| policy-auto-answer-apply | apply | auto_answer:1, request:1 | in-progress | — | clear | 0 | none |
| policy-authorization-pending | pending-authorization | auto_answer:1, request:1 | blocked | policy-authorization-pending | blocks | 0 | none |
| owner-continue | apply | claim:1, request:1, response:1 | in-progress | — | clear | 0 | resume-root |
| owner-park | park | claim:1, request:1, response:1 | blocked | — | clear | 0 | none |
| owner-reject | reject | claim:1, request:1, response:1 | blocked | — | clear | 0 | none |
| options-2-substantive | pending | request:1 | blocked | options-2 | clear | 0 | none |
| options-5-substantive | pending | request:1 | blocked | options-5 | clear | 0 | none |
| options-mandatory-only-rejected | rejected-before-append | — | none | — | clear | 0 | none |
| request-projection-failure-retry | pending | request:1 | blocked | request-projection-retry | blocks | 1 | none |
| resolve-apply-projection-failure-retry | apply | claim:1, request:1, response:1 | in-progress | — | clear | 1 | resume-root |

The report is rendered only from results JSON. Volatile timestamps and temporary paths are checked while running but are not emitted.
