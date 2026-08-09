# P5.5 producer-based acceptance report

Synthetic Layout-v2 scenarios are proven; P6 command integration and live fleet behavior are not proven.

The committed fixture queue is retained only as regression input. Each scenario below starts from a fresh copy, removes that pre-built queue, and creates its evidence through the runtime producer APIs.

| Scenario | Outcome | Queue events | Journal rows | P1.1 | P1.2 | Continuation |
|:--|:--|--:|--:|:--|:--|:--|
| policy-auto-answer | apply | 2 | 11 | 🔴 Blocked | 🟡 In progress | none |
| owner-continue | apply | 3 | 11 | 🟡 In progress | 🟡 In progress | resume-root |
| owner-park | park | 3 | 11 | 🔴 Blocked | 🟡 In progress | none |
| owner-reject | reject | 3 | 11 | 🔴 Blocked | 🟡 In progress | none |

All scenario claims derive from the generated results JSON; volatile timestamps and temporary paths are checked during execution but are not emitted.
