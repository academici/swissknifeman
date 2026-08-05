# Owner directive — audit 8 exact carriers and executable continuation

## Owner directive — 2026-08-04

Finish `2026.08.03-ARTIFEX-SUPERVISOR` in design-only mode by closing F1–F4 from the last
`## Audit design — 2026-08-04` block (audit pass 8).

The owner requires the plan to:

1. record exact owner carriers for the Harness-owned source, tests and shared provider-artifact
   lock needed by P3.8 before P3.8 consumes them;
2. record a separate exact owner carrier for the Harness-owned root instruction source, tests and
   shared provider-artifact lock needed by P6.2 before P6.2 consumes them;
3. replace bare `harness instructions` prose with executable `instructions plan` → exact ordered
   `instructions apply --authorize` → `instructions check` sequences;
4. make the P3.8 post-generation Codex restart durable and cold-start complete: package cwd,
   routed model/effort, `-a never`, `-s danger-full-access`, exact plan/item reads and explicit
   continuation scope;
5. isolate P3.7 validation from P3.6-owned outputs: any fresh provider probe writes only to a
   disposable temporary directory, while the committed P3.6 carrier is consumed read-only;
6. return the repaired plan to a new cold design audit with all lint/conflict/citation/Task
   Contract and producer→consumer checks green.

The following finite scopes are explicitly owner-approved for the named consumers and no other
item:

- `[OWNER-GRANT:G-OWNER-P3.8-HARNESS-INSTRUCTIONS]`: P3.8 may change exactly
  `packages/harness/lib/harness/instructions.py`,
  `packages/harness/configs/common/instructions/catalog.json`,
  `packages/harness/configs/common/instructions/packages/artifex/common.md`,
  `packages/harness/configs/common/instructions/packages/artifex/claude-code.md`,
  `packages/harness/configs/common/instructions/packages/artifex/codex.md`,
  `packages/harness/tests/fixtures_data/instruction-compatibility-v1.json`,
  `packages/harness/tests/fixtures_data/instruction-literal-coverage-v1.json`,
  `packages/harness/tests/test_provider_instructions.py`,
  `packages/harness/tests/test_instruction_compatibility.py`,
  `packages/harness/tests/test_instruction_adoption.py`,
  `packages/harness/tests/test_instruction_size_gate.py`, and
  `.swissknifeman/provider-artifacts.lock.json` solely to add and generate the two Artifex
  package instruction projections already authorized by D86;
- `[OWNER-GRANT:G-OWNER-P6.2-HARNESS-ROOT-INSTRUCTIONS]`: P6.2 may change exactly
  `packages/harness/configs/common/instructions/catalog.json`,
  `packages/harness/configs/common/instructions/root/common.md`,
  `packages/harness/configs/common/instructions/root/claude-code.md`,
  `packages/harness/configs/common/instructions/root/codex.md`,
  `packages/harness/tests/fixtures_data/instruction-compatibility-v1.json`,
  `packages/harness/tests/fixtures_data/instruction-literal-coverage-v1.json`,
  `packages/harness/tests/test_provider_instructions.py`,
  `packages/harness/tests/test_instruction_compatibility.py`,
  `packages/harness/tests/test_instruction_literal_coverage.py`,
  `packages/harness/tests/test_instruction_size_gate.py`, and
  `.swissknifeman/provider-artifacts.lock.json` solely to update and regenerate the two root
  instruction projections already authorized by D87.

These grants are additive to D86/D87 rather than replacements. They do not authorize any other
Harness source, package/root output, rollout, implicit enablement, dependency change, hook repair,
tag, push, publish or release.

Protected anti-scope:

- do not execute items;
- do not change frozen P1/P2 or terminal P3.1–P3.4 status/spec/history/Completion Notes;
- do not change implementation, generated outputs or effective hook state during this design run;
- do not touch unrelated dirty worktree paths.

RAG:— (direct repository-owner directive in the active 2026-08-04 conversation; exact path sets
are reconciled against the repository-owned Harness instruction mechanism).
