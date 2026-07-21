# Provider instructions

Generated from the validated D86 catalog.

| Scope | Claude target | Codex target | Common IDs | Claude extensions | Codex extensions |
|:--|:--|:--|--:|--:|--:|
| `root` | `CLAUDE.md` | `AGENTS.md` | 11 | 3 | 3 |
| `skiller` | `packages/skiller/CLAUDE.md` | `packages/skiller/AGENTS.md` | 8 | 3 | 0 |
| `harness` | `packages/harness/CLAUDE.md` | `packages/harness/AGENTS.md` | 8 | 3 | 0 |
| `maind` | `packages/maind/CLAUDE.md` | `packages/maind/AGENTS.md` | 7 | 2 | 0 |
| `analyst` | `packages/analyst/CLAUDE.md` | `packages/analyst/AGENTS.md` | 8 | 2 | 0 |
| `task` | `packages/task/CLAUDE.md` | `packages/task/AGENTS.md` | 7 | 2 | 0 |

The frozen inventory contains 49 common and 18 provider-extension IDs (67 total) across exactly 12 targets.

## Public API

`InstructionRequest` carries contract/catalog versions, operation ID, explicit ordered scope/provider IDs, an absolute target root, and config/authorization provenance. `InstructionTargetResult` carries artifact/scope/provider/path, ordered semantic IDs, observation/action, source/render hashes, marker/block IDs, ordered structured diagnostics, and `changed`. `InstructionOperationResult` adds aggregate diagnostics and `green`.

The public operations are `plan_instructions`, `check_instructions`, `apply_instructions`, and `repair_instructions`; their serialized result is available through `as_dict()` without reinterpretation.

`plan` and `check` are no-write. `apply` requires explicit authorization for a missing create or stale-source update; `repair` requires explicit managed-drift hashes and an adjacent recoverable pre-image. Existing unmarked or unlocked files are ownership conflicts.
