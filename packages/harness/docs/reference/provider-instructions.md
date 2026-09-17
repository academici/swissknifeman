# Provider instructions

Generated from the validated D86 catalog.

| Scope | Claude target | Codex target | Cursor target | Common IDs | Claude extensions | Codex extensions | Cursor extensions |
|:--|:--|:--|:--|--:|--:|--:|--:|
| `root` | `CLAUDE.md` | `AGENTS.md` | `.cursor/rules/swissknifeman-instructions.mdc` | 18 | 3 | 4 | 3 |
| `skiller` | `packages/skiller/CLAUDE.md` | `packages/skiller/AGENTS.md` | `packages/skiller/.cursor-instructions.mdc` | 8 | 3 | 0 | 0 |
| `harness` | `packages/harness/CLAUDE.md` | `packages/harness/AGENTS.md` | `packages/harness/.cursor-instructions.mdc` | 8 | 4 | 0 | 0 |
| `maind` | `packages/maind/CLAUDE.md` | `packages/maind/AGENTS.md` | `packages/maind/.cursor-instructions.mdc` | 7 | 2 | 0 | 0 |
| `analyst` | `packages/analyst/CLAUDE.md` | `packages/analyst/AGENTS.md` | `packages/analyst/.cursor-instructions.mdc` | 8 | 2 | 0 | 0 |
| `task` | `packages/task/CLAUDE.md` | `packages/task/AGENTS.md` | `packages/task/.cursor-instructions.mdc` | 7 | 2 | 0 | 0 |
| `artifex` | `packages/artifex/CLAUDE.md` | `packages/artifex/AGENTS.md` | `packages/artifex/.cursor-instructions.mdc` | 6 | 1 | 1 | 0 |

The frozen inventory contains 56 common and 23 provider-extension IDs (79 total) across exactly 18 targets.

## Public API

`InstructionRequest` carries contract/catalog versions, operation ID, explicit ordered scope/provider IDs, an absolute target root, and config/authorization provenance. `InstructionTargetResult` carries artifact/scope/provider/path, ordered semantic IDs, observation/action, source/render hashes, marker/block IDs, ordered structured diagnostics, and `changed`. `InstructionOperationResult` adds aggregate diagnostics and `green`.

The public operations are `plan_instructions`, `check_instructions`, `apply_instructions`, and `repair_instructions`; their serialized result is available through `as_dict()` without reinterpretation.

`plan` and `check` are no-write. `apply` requires explicit authorization for a missing create or stale-source update; `repair` requires explicit managed-drift hashes and an adjacent recoverable pre-image. Existing unmarked or unlocked files are ownership conflicts.
