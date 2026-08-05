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
