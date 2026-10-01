# Artifex

Artifex is the standalone deterministic supervisor runtime. It is stdlib-only and
keeps provider adapters additive over the shared scheduler and authority contract.

Run it directly from the checkout:

```bash
packages/artifex/bin/artifex --help
```

The caller supplies an explicit repository root, plan directory and run-state root;
the package never imports plan-local code. Before handoff, run
`bash packages/artifex/scripts/test.sh` and `bash packages/artifex/scripts/validate.sh`.

`telemetry --run-id <id>` emits a bounded, redacted owner-attention and terminal packet from
the verified journal replay. It never trusts snapshots, provider raw output or a self-declared
readiness status; unknown provider data stays explicit as an `unknown_reasons` entry.

Package tests are self-contained: plan-shaped inputs (authority contract and case banks, provider
matrix and parity mapping, indexed smoke admissions) live under `tests/fixtures_data/plan/` and
describe a synthetic `DEMO-PLAN`. No test or runtime path reads a local-only plan directory.
