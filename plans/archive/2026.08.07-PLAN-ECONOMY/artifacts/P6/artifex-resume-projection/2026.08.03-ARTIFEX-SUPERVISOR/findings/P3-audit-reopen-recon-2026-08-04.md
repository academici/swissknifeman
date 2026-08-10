# P3 audit reopen recon — 2026-08-04

## Source

- Owner refinement: `brief/13-p3-audit-reopen.md`.
- Audit input: `phases/P3.md` → `## Audit P3 — 2026-08-04`, findings F1–F6.
- Repository tree: `HEAD=7d34d261`; audit append is present as an uncommitted scoped
  change and is preserved.

## Reproduced repository facts

1. `artifacts/supervisor/artifex/cli.py::_dispatch` injects
   `scheduler.DefaultActivityPort()` for every explicit provider; the return path hard-codes
   `process_count=0`. `worker.run()` and `worker.transient_carrier()` have no runtime caller.
   RAG:— (repo-grounded: `artifacts/supervisor/artifex/cli.py:213-225`,
   `artifacts/supervisor/artifex/scheduler.py:20-25`, `artifacts/supervisor/artifex/worker.py`).
2. `artifacts/P3/probe-adapters.py` reads only admission-index metadata, does not validate
   `--project-root`, and writes fixed Codex/Claude outcomes. It neither opens an admission
   nor calls provider preflight, CLI dispatch or the bounded worker. RAG:— (repo-grounded:
   `artifacts/P3/probe-adapters.py`).
3. `artifacts/P3/validate-adapters.py` declares only three arguments and uses
   `parse_known_args()`. `adapter-manifest-v1.json` has no `base_prototype` anchor or
   closed current-file hash set. RAG:— (repo-grounded: the two named files).
4. Historical item commit `d1362247` predates the terminal P3.4 spec/evidence carrier and
   changed files omitted by the final `Files` list; the past commit cannot be repaired by
   rewriting terminal prose. A forward fix must exist as a separately committed spec before
   its implementation starts. RAG:— (repo-grounded: audit F4 and `git show d1362247`).
5. `packages/task/tests/test_task_contract.py::ArtifexOrdinaryAuthorityRegressionTests`
   hard-codes `32`, while the current plan already has 35 items; the test is an invariant
   test whose fixed cardinality became stale. RAG:— (repo-grounded:
   `packages/task/tests/test_task_contract.py:429-450`).
6. The append-only Update Log omits the item commits for P3.1–P3.4; authoritative hashes are
   `1a87d960`, `cbc20abf`, `f708310e`, `d1362247`. RAG:— (repo-grounded: audit F6 and
   the four Completion Notes/git history).

## Preflight boundary

- `codex doctor --json`: overall `ok`.
- `packages/maind/bin/maind health --cwd`: all project memory/MCP/round-trip checks `ok`.
- `packages/harness/bin/harness hooks --target <absolute-repo> --provider codex --trusted
  --observer --dry-run`: warning, both effective lifecycle surfaces are `stale-source → update`.
  This is the already-owned P4.6/P4.4 hook prerequisite and is not repaired in P3.
- The same hook command with relative `--target .` raises `ValueError: root must be explicit
  and absolute`; this is disclosed as an out-of-scope CLI/path defect and not treated green.

No external facts or provider-version claims were introduced in this recon.
