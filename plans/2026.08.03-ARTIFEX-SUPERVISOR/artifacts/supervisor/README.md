# Artifex P2 prototype

This is a plan-local, stdlib-only deterministic supervisor candidate. It is not an installed
package or root command, and its P2 activity port cannot launch a provider.

Every invocation supplies all roots explicitly:

```text
PYTHONPATH=plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/supervisor \
python3 -m artifex --repo-root . --plan-dir plans/2026.08.03-ARTIFEX-SUPERVISOR \
  --runs-root plans/2026.08.03-ARTIFEX-SUPERVISOR/runs status --run-id RUN-ID
```

Commands emit one capped JSON result to stdout. `start` requires `--run-id`, `--phase`, `--item`,
and `--mandate`; it compiles the frozen slice and creates a `READY` run only. `status` and
`report` replay the strict journal without writing. `resume` optionally takes `--observed`
(`preimage`, `postimage`, `partial`, or `third`); `reconcile` requires it. `stop` records an
explicit abort and is idempotent. Exit code `3` is a missing run; code `2` is a named refusal.

Run folders are contained below `--runs-root`, reject symlinks and foreign identities, and are
never inferred from cwd or home. Reports expose only state, event counts, and journal hashes.
