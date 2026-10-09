# Provider instructions

Generated from the validated D86 catalog.

| Scope | claude-code target | codex target | cursor target | grok target | Common IDs | claude-code extensions | codex extensions | cursor extensions | grok extensions |
|:--|:--|:--|:--|:--|--:|--:|--:|--:|--:|
| `root` | `CLAUDE.md` | `AGENTS.md` | `.cursor/rules/swissknifeman-instructions.mdc` | `.grok/rules/swissknifeman-instructions.md` | 19 | 3 | 4 | 3 | 3 |
| `skiller` | `packages/skiller/CLAUDE.md` | `packages/skiller/AGENTS.md` | `packages/skiller/.cursor-instructions.mdc` | `packages/skiller/.grok-instructions.md` | 8 | 3 | 0 | 0 | 0 |
| `harness` | `packages/harness/CLAUDE.md` | `packages/harness/AGENTS.md` | `packages/harness/.cursor-instructions.mdc` | `packages/harness/.grok-instructions.md` | 8 | 4 | 0 | 0 | 0 |
| `maind` | `packages/maind/CLAUDE.md` | `packages/maind/AGENTS.md` | `packages/maind/.cursor-instructions.mdc` | `packages/maind/.grok-instructions.md` | 7 | 2 | 0 | 0 | 0 |
| `analyst` | `packages/analyst/CLAUDE.md` | `packages/analyst/AGENTS.md` | `packages/analyst/.cursor-instructions.mdc` | `packages/analyst/.grok-instructions.md` | 8 | 2 | 0 | 0 | 0 |
| `planner` | `packages/planner/CLAUDE.md` | `packages/planner/AGENTS.md` | `packages/planner/.cursor-instructions.mdc` | `packages/planner/.grok-instructions.md` | 8 | 2 | 0 | 0 | 0 |
| `artifex` | `packages/artifex/CLAUDE.md` | `packages/artifex/AGENTS.md` | `packages/artifex/.cursor-instructions.mdc` | `packages/artifex/.grok-instructions.md` | 6 | 1 | 1 | 0 | 0 |
| `brain` | `packages/brain/CLAUDE.md` | `packages/brain/AGENTS.md` | `packages/brain/.cursor-instructions.mdc` | `packages/brain/.grok-instructions.md` | 6 | 0 | 0 | 0 | 0 |

The frozen inventory contains 70 common and 28 provider-extension IDs (98 total) across exactly 32 targets.

## Public API

`InstructionRequest` carries contract/catalog versions, operation ID, explicit ordered scope/provider IDs, an absolute target root, and config/authorization provenance. `InstructionTargetResult` carries artifact/scope/provider/path, ordered semantic IDs, observation/action, source/render hashes, marker/block IDs, ordered structured diagnostics, and `changed`. `InstructionOperationResult` adds aggregate diagnostics and `green`.

The public operations are `plan_instructions`, `check_instructions`, `apply_instructions`, and `repair_instructions`; their serialized result is available through `as_dict()` without reinterpretation.

`plan` and `check` are no-write. `apply` requires explicit authorization for a missing create or stale-source update; `repair` requires explicit managed-drift hashes and an adjacent recoverable pre-image. Existing unmarked or unlocked files are ownership conflicts.
