# P6.1 — release validation

**Release tree anchor:** `4efef7a33e4f82738fc138252db505471812a5db`

- Target: `v0.13.0`; baseline: `v0.11.1` at `1ebd720a6397c294a4f58f23a9cf29e1b86ec832`.
- Exact inventory is stored in `artifacts/P6/release-manifest-v1.json`: `212` commits and `1399` changed paths, including every affected package.
- Task version parity is `0.13.0` across the canonical routing catalog, Claude descriptor/golden fixture and regenerated Codex artifacts. `skiller registry --check` confirms marketplace freshness without a byte change.

## Validation at the release-tree anchor

| Command | Result |
|:--|:--|
| `bash packages/task/scripts/validate.sh` | passed — 876 tests, 1 skipped |
| `bash packages/skiller/scripts/validate.sh` | passed — inherited listing/body warnings only |
| `bash packages/harness/scripts/validate.sh` | passed |
| `bash packages/maind/scripts/validate.sh` | passed |
| `bash packages/analyst/scripts/validate.sh` | passed |
| `packages/skiller/bin/skiller registry --check` | passed — no drift |
| `python3 packages/task/scripts/render-provider-commands.py --root . --check` | passed — no drift |
| `bash scripts/docs-sync.sh --check` | passed |
| `git diff --check` | passed |

## Audit correction — 2026-08-13

The Task and Harness rows above are the original P6.1 claim and are not reproducible
from the recorded release-tree anchor. A detached-worktree replay at
`4efef7a33e4f82738fc138252db505471812a5db` produced:

| Command | Observed result |
|:--|:--|
| `bash packages/task/scripts/validate.sh` | **failed** — 876 tests passed, 1 skipped, then aggregate plan validation reported a missing foreign bundle and stale `P6.1.json`; exit `1` |
| `bash packages/harness/scripts/validate.sh` | **failed** — 644 tests ran with 10 failures and 23 errors against the then-current v1 fixtures; exit `1` |

P6.2 later qualified a different candidate, `3c5548f7d15100e3b992e62e08f7e8ef2a92b0d0`,
with all five package gates green. That later result does not make the historical P6.1
GREEN assertion true. The immutable P6.1 release manifest is retained as historical
evidence and is not rewritten.

## Release boundary

No tag, push, GitHub release, or channel rollout was performed by P6.1. The final phase split assigns requalification to P6.2, local annotated tag creation to P6.3, and registered-channel rollout to P6.4.

## Documentation decision

Docs not needed: P6.1 changes release metadata and generated provider artifacts only; it introduces no new user-facing process, installation capability, script behavior, or schema.
