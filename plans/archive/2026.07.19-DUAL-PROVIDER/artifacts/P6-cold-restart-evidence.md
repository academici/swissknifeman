# P6.6 cold-restart evidence

**Plan/item:** `2026.07.19-DUAL-PROVIDER` / `P6.6`  
**Runtime:** `gpt-5.6-terra` / `medium`; approval `never`; sandbox `danger-full-access`  
**Thread:** `019f8836-faeb-74c1-b32c-411034285edc` · first turn `019f8836-fb3c-71b3-905f-35efa4bfd559`

## Checkpoint recovery

Disk-first checkpoint `p6.5-bootstrap-b7373334` and exact-scope
`project:swissknifeman` recall agree on record `mem_mrvm57ek_aa95bdbc51c7`, payload
SHA-256 `22a9c7a82f48ae0e27449ca1be240398b3b8ecd36fbfd50bc2f8bd3a56d60dc9`, provider
IDs `claude-code,codex`, and all recorded contract/catalog hashes.

## Public P5/P6 temporary-root proof

`maind sync --conformance` ran through the worktree-local public P6 API in a Python
`TemporaryDirectory`. It reproduced instruction render SHA-256
`60686d05fa8bf9830cad8a960782ce12cdcb369a44b49cd9b864db481bde453e`: dual-provider
row GREEN, 12 targets, 49 common IDs, 18 allowed provider extensions, no-op second run,
and managed-drift repair preserving outside bytes. The committed deploy conformance SHA-256
is `f3b4b1d07e120ede573c6a053615da3c67219ee14483524fcabfd20f1eebd95d`; its focused
worktree-local public deploy suite passed 13 tests.

## Read-only probes

- Harness provider audit: GREEN.
- Focused analyst provider-reader suite: GREEN (8 tests); the neutral public analytics
  slice reports contract `1.0.0` and no invented provider data for an empty local store.
- mAInd graph query returned `project:swissknifeman`; Serena resolved public
  `plan_instructions`; exact Perplexity query returned **Docs MCP | OpenAI API**,
  https://platform.openai.com/docs/docs-mcp.
- Target plan-lint: 0 errors, 2 historical warnings, 0 new warnings; diff and protected
  path checks are clean.

## Process deviations

The prior broad `maind doctor --quiet` and real-worktree instruction check were
supervisor-classified non-gating deviations. Neither is a P6.6 contract verdict; no
dependency installation, live apply, package change, P7, FOREMAN, fleet, or push occurred.

**Verdict:** GREEN.

## Compact checkpoint correction

The malformed self-created post-restart record `mem_mrvmoo1y_7ebb427a0100` was forgotten
without touching the original P6.5 record `mem_mrvm57ek_aa95bdbc51c7`. Replacement
`mem_mrvmr84r_ca0a356274a5` in the same exact scope has canonical JSON payload SHA-256
`7645617fd8ae3124aebe89702deade80deda6eb036e35a13b5c4f7e1c2afae25`; exact-scope recall
returned byte-equivalent parseable JSON. The original P6.5 record remains the pre-restart
checkpoint; this record is only the compact P6.6 verdict.
