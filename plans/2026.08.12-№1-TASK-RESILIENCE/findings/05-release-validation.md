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

## Release boundary

No tag, push, GitHub release, or channel rollout was performed. P6.2 alone may create and verify local annotated tag `v0.13.0`; P6.3 alone may roll out to registered channels.

## Documentation decision

Docs not needed: P6.1 changes release metadata and generated provider artifacts only; it introduces no new user-facing process, installation capability, script behavior, or schema.
