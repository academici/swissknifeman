# P6.5 bootstrap probes — RED

**Plan/item:** `2026.07.19-DUAL-PROVIDER` / `P6.5`
**Session:** `gpt-5.6-terra/medium`
**Tree anchor:** `91855d6f8da92fca9b93e8524b3fda73977fe25a`
**Timestamp:** 2026-07-22T04:08:03Z

## Terminal evidence

The worktree-local CLI was proved at
`/tmp/swissknifeman-p6.5/packages/maind/bin/maind`, with repository root
`/tmp/swissknifeman-p6.5`. Two isolated temporary-root executions of
`./packages/maind/bin/maind sync --conformance <temp>/round-{1,2}.md` both emitted:

- `ERROR: swissknifeman не найден: добавьте проект 'swissknifeman' с local_path в config.json, или задайте MAIND_SKM_BIN`
- `ERROR: harness не найден: добавьте проект 'swissknifeman' с local_path в config.json, или задайте MAIND_HARNESS_BIN`

The generated matrices were byte-identical and contained the expected dual-provider rows,
including `12` instruction targets, `49` common semantic IDs, managed-drift repair, and
outside-byte preservation. Those later rows do not erase the two required bootstrap command
resolution errors. The independent provisioner/provider matrix also records both instruction
rows as `failed / INSTRUCTION_TARGET_MISSING`, while the three top-level cases are rendered as
`GREEN`; the aggregate therefore falsely blesses a required-provider failure. Required-provider/
bootstrap availability is a P6.5 hard gate, so the verdict is **RED**.

## Owning seam and bounded next action

**Owning seam:** mAInd isolated conformance bootstrap in
`packages/maind/lib/maind/provision/sync.py` and its independent oracle in
`packages/maind/tests/test_provider_provision.py`. The isolated `onboard` fixture does not
resolve worktree-local `swissknifeman`/`harness` commands, and the aggregate/matrix oracle
explicitly blesses `instructions / adapter-projected / failed / INSTRUCTION_TARGET_MISSING`.
The fixture must use explicit worktree-local command roots and the aggregate must fail closed
until required instruction rows are successful before P6.5 can be rerun.

No package source was modified, no package validator was run, and no live probe or checkpoint
was written. This evidence does not authorize a P6.5 repair.
