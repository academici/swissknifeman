---
id: D135
date: 2026-08-06
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

F15 is resolved INSIDE P5.4 and creates no package work: `run-battle-waves.py` imports `artifex.activity.BusinessProviderActivityPort` and reads the measured `economy` envelope off its return value for the candidate lane, and reaches the same extraction for the baseline lane through the public `claude_code.fold_business_records` with a request built by `business_dispatch.request` (D124's «the same measurement extraction», satisfied without re-implementing it). Exposing `economy` through `cli.py`'s `dispatch-business-intent` — P5.5's other named exit — is NOT done: it would write a package byte, hence force an EIGHTH G2B re-freeze, for a convenience the runner does not need. If a later item surfaces the field on the CLI anyway, the runner may simply read it there; nothing in this decision forecloses that. RAG:— (repo-grounded: `findings/P5.4-package-authority-gap-2026-08-06.md` §5, `findings/P5.5-measured-economy-envelope.md` §6, `packages/artifex/lib/artifex/cli.py:246-249`, `security.py:98-114`; owner-grounded: D119 reserves every package byte to P5.5).

## Почему

The measured envelope already exists on the port's return value; adding a CLI field to read what the runner can import would buy one JSON key at the price of another irreversible generation freeze.
