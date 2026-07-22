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

## Resumed P6.2 repair verification — GREEN

**Anchor:** `1ca0c398bf03af898313bf6f7ae128c127f84e64`
**Timestamp:** 2026-07-22T04:27:07Z

After the owning P6.2 repair (`24569b4b`, regression `887a714b`), the same worktree-local
`maind sync --conformance` operation was executed twice in new isolated temporary roots.
Neither run emitted the previous missing `swissknifeman` or `harness` sibling diagnostic.
The two generated reports were byte-identical with SHA-256
`60686d05fa8bf9830cad8a960782ce12cdcb369a44b49cd9b864db481bde453e`.

The dual-provider row is GREEN with 12 instruction targets; the public checker reports 49
common semantic IDs and 18 provider-owned extensions. Both managed-drift repair rows are
GREEN and explicitly prove outside-byte preservation. This is a repaired GREEN only for the
original P6.5(b) sibling-resolution failure; it does not supersede the original RED record.

## Terminal validation — RED

**Timestamp:** 2026-07-22T04:27:07Z
**Command position:** 3 of 8

`bash packages/maind/scripts/validate.sh` failed one test:
`test_independent_provisioner_provider_matrix_is_complete_and_honest` in
`packages/maind/tests/test_provider_provision.py`.

Its independent oracle expects the two `instructions` provider rows to be
`activation=planned, diagnostic=none`, while the current production matrix yields
`activation=failed, diagnostic=INSTRUCTION_TARGET_MISSING`. The owning seam is the P6.2
instruction-provision matrix/oracle contract between
`packages/maind/lib/maind/provision/sync.py` and
`packages/maind/tests/test_provider_provision.py`.

Commands 1 and 2 were GREEN (`206` core tests; `211` analyst tests). Per P6.5 stop-on-first-
RED discipline, commands 4–8, all live probes, checkpoint work, and package repair were not
run.

## Bounded P6.5 repair pointer — 2026-07-22

The owner authorized one repair only in the RED finding's owning P6.2 seam. Invocation
metadata is authoritative for this run (`gpt-5.6-terra/high`, approval `never`, sandbox
`danger-full-access`); `codex doctor --json` reports `gpt-5.6-sol` only as the loaded base
configuration default, not the command-line invocation override.

Commits `24569b4b` and `887a714b` restore isolated conformance with scoped, verified
same-worktree skiller/harness launchers; restore the environment afterwards; require successful
critical onboard environment/instruction operations; and require instruction matrix rows to be
actual non-failed planned/dry semantics. The focused worktree-local CLI regression ran twice
with exit `0`, no missing-sibling diagnostics, and byte-identical reports.

The RED evidence above remains the repair pointer and P6.5 remains **🟡 In progress**: no package
validators, live probes, checkpoint, P6.6, P7, FOREMAN, fleet, or self-host state were run or
changed. Continue through the existing structured `exec-items: task:plan-exec
2026.07.19-DUAL-PROVIDER P6.5` handoff route.

## Second RED and invalidation scope — 2026-07-22

After b/c GREEN, terminal core ran once and passed 206 tests; analyst ran once and passed
211 tests; maind ran once and failed only
`test_independent_provisioner_provider_matrix_is_complete_and_honest`: expected instruction
rows `planned / none`, actual `failed / INSTRUCTION_TARGET_MISSING`. The sequence stopped;
harness, integrated terminal conformance, lint, diff/protected checks, probes and checkpoint
did not run. Only maind validation and downstream checks are invalidated; core/analyst remain
valid and must not be rerun. P6.5 remains **🟡 In progress**.

## Second RED repair pointer — 2026-07-22

Commit `93b157bc` scopes verified worktree-local sibling launchers in the independent matrix fixture, restores every environment key exactly, and performs production-equivalent instruction preparation before the dry matrix. The focused unittest and one public conformance CLI are GREEN with exact `planned`/`none` instruction rows; only invalidated maind/downstream terminal checks remain. P6.5 stays **🟡 In progress**; P6.6/P7/FOREMAN/fleet/live self-host/push are untouched.

## Repair 2 terminal revalidation — GREEN

**Repair commits:** `93b157bc`, `d7d80c96`
**Anchor:** `d7d80c967d9145097d33c7875db5857101190554`

The invalidated worktree-local mAInd validator was rerun once and passed (`449` tests).
Previously valid broad commands were not repeated: core remains `206` GREEN and analyst
remains `211` GREEN. The remaining terminal tail each ran once and was GREEN: harness (`406`
tests), public dual-provider deploy/instruction conformance (two providers, 12 targets, 49
common IDs, managed-drift/outside-byte proof), target plan-lint (0 errors, 0 new warnings),
`git diff --check`, and protected P7+/FOREMAN/fleet/root-bootstrap delta (0).

## Live memory isolation — RED

**Timestamp:** 2026-07-22T04:44:42Z

The exact read-only call
`maind_memory_recall(scope="project:swissknifeman", query="P6 bootstrap checkpoint")`
returned project-scoped records but also `mem_mrjkvnib_8eaf537d482c`, whose declared scope is
`ns:axioma`. This does not prove the required `project:swissknifeman` isolation roundtrip.

Preceding read-only probes succeeded: `maind_graph_project(project="swissknifeman")` returned
the anchored `project:swissknifeman` node; Serena resolved `plan_instructions` at
`packages/harness/lib/harness/instructions.py:336`; Perplexity returned the official result
`Docs MCP | OpenAI API` at `https://platform.openai.com/docs/docs-mcp` for the fixed query.
These successes do not override the memory isolation RED.

Per the first-RED rule, no mAInd checkpoint write occurred. The owning seam is mAInd memory
scope filtering/namespace isolation. Terminal validation and the successful read-only probes
remain valid; only the memory-isolation recheck and downstream disk+mAInd checkpoint creation
are invalidated. P6.6 remains blocked and P6.5 remains **🟡 In progress**.

## D93 memory-isolation recovery — GREEN

## P6.6 cold-session reproof — GREEN

The verified new P6.6 thread recovered `p6.5-bootstrap-b7373334` disk-first and then
recalled the same exact-scope `project:swissknifeman` record
`mem_mrvm57ek_aa95bdbc51c7`; canonical payload SHA-256 matched
`22a9c7a82f48ae0e27449ca1be240398b3b8ecd36fbfd50bc2f8bd3a56d60dc9`.
Worktree-local public temporary-root P6 conformance reproduced the checkpointed instruction
render SHA-256 and its 12-target / 49-common-ID / 18-extension dual-provider proof; the
committed deploy-render SHA-256 also matched. Scoped graph, Serena and the fixed official
OpenAI Docs MCP query were GREEN. Broad environment doctor and live pre-P7 checker invocations
are recorded as supervisor-classified non-gating process deviations.

At `b7373334` after repair `884e146b`, the worktree-local public mAInd MCP server received
`maind_memory_recall` with explicit `scope=project:swissknifeman`. Every returned record
declared exactly that scope; no `ns:axioma`, global, or other scope was returned. The one
authorized checkpoint write and same-scope recall agree on checkpoint
`p6.5-bootstrap-b7373334`, memory ID `mem_mrvm57ek_aa95bdbc51c7`, and payload SHA-256
`22a9c7a82f48ae0e27449ca1be240398b3b8ecd36fbfd50bc2f8bd3a56d60dc9`.
