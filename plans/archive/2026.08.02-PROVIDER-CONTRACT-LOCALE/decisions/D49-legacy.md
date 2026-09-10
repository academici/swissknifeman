---
id: D49
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P7.4's decision denominator is computed at audit time from every `D#` row in `plan.md` Decision Log, not from a static upper bound. The current exact set is D1–D49, including this remediation. `artifacts/P7-decision-crosswalk.json` must contain exactly one row per parsed D# and no other row; each row carries disposition, evidence paths, recomputed commands/results and tree anchor. The P7.1 committed helper's `verify-decision-crosswalk` subcommand fails on missing, extra, duplicate or post-crosswalk D# before P7.4 can emit GREEN. RAG:— (repo-grounded: audit F16, P7.1/P7.4 and append-only Decision Log).

## Почему

Future decisions enter the release audit automatically and stale exact-set reports fail closed; the audit pays for a full decision-to-evidence crosswalk rather than a range checklist.
