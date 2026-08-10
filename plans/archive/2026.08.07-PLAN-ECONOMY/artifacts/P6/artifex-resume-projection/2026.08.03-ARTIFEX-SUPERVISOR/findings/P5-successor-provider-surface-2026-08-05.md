# P5 successor provider surface — 2026-08-05

## Repository/runtime observations

- Terminal G2 `packages/artifex/lib/artifex/dispatch.py` remains smoke-only:
  `dispatch-task-manifest-v1`/`dispatch-grant-v1`/`dispatch-admission-v1`, parent `P3.4`,
  purpose `provider-readiness-smoke`, empty read/write/tool scope and exact two-row P2 index.
- Terminal `providers/codex.py` refuses every argv build with `CAPABILITY_UNSUPPORTED`; code below
  the unconditional refusal is unreachable and is not capability evidence.
- `ProviderActivityPort` re-loads the P2 smoke admission path even after receiving another
  admission, so accepting the P5 schema in a loader alone would still leave a second G2-only
  boundary.
- The 14 terminal P5.1 admissions are immutable and hash-bind `parent_item_id=P5.2/P5.3/P5.4`.
  Renumbering those pilot items would invalidate D105 evidence. RAG:— (repo-grounded:
  `packages/artifex/lib/artifex/{dispatch.py,activity.py,providers/codex.py}` and
  `artifacts/P5/trial-admission-index-v1.json`).
- A direct closed-set read of those indexed bytes gives exactly `3/6/5` rows for
  `P5.2/P5.3/P5.4`, exactly `7/7` Codex/Claude rows, 14 unique task/admission hashes and
  `used_slices=0` for all rows. Every task/grant pair pins the same G2 digest
  `ef08406d7ca630d46e9e9e8bca0d10ea73b141d984615bded75f19d7eea13f09` and the same expiry
  `2026-08-12T23:59:59Z`. Thus the phase has no spare dispatch or implicit retry admission, and
  G2B must validate a predecessor→successor link rather than compare D105 directly to current
  package bytes. RAG:— (repo-grounded: all paths in `artifacts/P5/trial-admission-index-v1.json`).

## Current local provider surface

- `codex --version` → `codex-cli 0.146.0`; `codex exec --help` still exports explicit cwd,
  sandbox, JSONL, ephemeral mode, user-config isolation, output schema and feature enable/disable.
- `claude --version` → `2.1.222 (Claude Code)`, superseding terminal P0/P3's observed `2.1.220`.
  Current local help exports structured output/schema, model/effort, no-session-persistence,
  permission mode, tool availability/allow rules, settings sources, strict MCP, turn and cost caps.
- Help/official documentation describe projection surfaces, not proof that an Artifex mapping
  confines a business write correctly. P5.5 must therefore create positive/negative provider
  assurance on two disposable capability roots; neither call may use a D105 admission or count as
  a business pilot.

RAG:✅ 2026-08-05 official Codex manual evidence already captured in
`findings/P5.2-terminal-g2-native-capability-conflict-2026-08-05.md`; 2026-08-03 official Claude
CLI/permission evidence in `findings/07-p3-provider-runtime-recon-2026-08-03.md`; current local
`--version`/`--help` rechecked 2026-08-05. Confidence high for exported local surfaces, medium for
negative/global-control claims.

## Preflight integrity

- `codex doctor --json`: overall `ok`, loaded model `gpt-5.6-sol`, CLI `0.146.0`.
- `packages/maind/bin/maind health --cwd`: GREEN for `project:swissknifeman`.
- exact trusted Harness Codex hook dry-run: `Статус: green`, two `clean → noop` rows.
- P4 hook-integrity validator and self-test: GREEN.
- `plan-lint` before this reconcile: 0 errors, 0 warnings.

The first `maind health --cwd <path>` invocation and the first hook-validator invocation were
invalid CLI forms; neither was counted as evidence. Both were rerun with their supported exact
arguments and passed.
