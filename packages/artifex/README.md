# Artifex

Artifex is the standalone deterministic supervisor runtime. It is stdlib-only and
keeps provider adapters additive over the shared scheduler and authority contract.

Run it directly from the checkout:

```bash
packages/artifex/bin/artifex --help
```

The caller supplies an explicit repository root, plan directory and run-state root;
the package never imports plan-local prototype code. Before handoff, run
`bash packages/artifex/scripts/test.sh` and `bash packages/artifex/scripts/validate.sh`.

`telemetry --run-id <id>` emits a bounded, redacted owner-attention and terminal packet from
the verified journal replay. It never trusts snapshots, provider raw output or a self-declared
readiness status; unknown provider data stays explicit as an `unknown_reasons` entry.

`dispatch-business` is the separate, read-only G2→G2B admission projection for an indexed D105
carrier. It validates the frozen admission and reports zero usage; it never starts a provider or
creates business intent. Its required predecessor and successor digests make a G2 fallback fail
closed before a future pilot can run.
