---
id: D91
date: 2026-08-04
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

[OWNER-GRANT:G-OWNER-P3.8-HARNESS-INSTRUCTIONS] branch=`p3.8-artifex-instruction-owner`; exact scope=`packages/harness/lib/harness/instructions.py` · `packages/harness/configs/common/instructions/catalog.json` · `packages/harness/configs/common/instructions/packages/artifex/common.md` · `packages/harness/configs/common/instructions/packages/artifex/claude-code.md` · `packages/harness/configs/common/instructions/packages/artifex/codex.md` · `packages/harness/tests/fixtures_data/instruction-compatibility-v1.json` · `packages/harness/tests/fixtures_data/instruction-literal-coverage-v1.json` · `packages/harness/tests/test_provider_instructions.py` · `packages/harness/tests/test_instruction_compatibility.py` · `packages/harness/tests/test_instruction_adoption.py` · `packages/harness/tests/test_instruction_size_gate.py` · `.swissknifeman/provider-artifacts.lock.json`; consumer=`P3.8 stage 1 only`; owner-message=`brief/16-audit8-owner-carriers-and-execution.md`. RAG:— (direct owner decision; repo-grounded exact source/test/lock reconciliation in `findings/P3-P6-audit8-owner-generator-recon-2026-08-04.md`).

## Почему

D86 authorizes package outputs, not Harness-owned producer bytes. This additive finite carrier exists before P3.8 and authorizes only the sources/tests/lock needed to generate the two package guides; no other Harness or rollout scope is granted.
