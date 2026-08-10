---
id: D92
date: 2026-08-04
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

[OWNER-GRANT:G-OWNER-P6.2-HARNESS-ROOT-INSTRUCTIONS] branch=`p6.2-root-instruction-owner`; exact scope=`packages/harness/configs/common/instructions/catalog.json` · `packages/harness/configs/common/instructions/root/common.md` · `packages/harness/configs/common/instructions/root/claude-code.md` · `packages/harness/configs/common/instructions/root/codex.md` · `packages/harness/tests/fixtures_data/instruction-compatibility-v1.json` · `packages/harness/tests/fixtures_data/instruction-literal-coverage-v1.json` · `packages/harness/tests/test_provider_instructions.py` · `packages/harness/tests/test_instruction_compatibility.py` · `packages/harness/tests/test_instruction_literal_coverage.py` · `packages/harness/tests/test_instruction_size_gate.py` · `.swissknifeman/provider-artifacts.lock.json`; consumer=`P6.1 freeze then P6.2 only`; owner-message=`brief/16-audit8-owner-carriers-and-execution.md`. RAG:— (direct owner decision; repo-grounded exact source/test/lock reconciliation in `findings/P3-P6-audit8-owner-generator-recon-2026-08-04.md`).

## Почему

D87 authorizes root outputs, not Harness-owned producer bytes. This separate finite carrier exists before P6.1/P6.2 and does not let P3.8 pre-consume the later root generation or widen root commands.
