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
and `--mandate`; it compiles the frozen slice and creates a `READY` run only. `dispatch` requires
`--run-id` and one repository-relative indexed `--admission`; it verifies the frozen D74 carrier,
records one durable intent, and returns the bounded no-provider result with no process. `status` and
`report` replay the strict journal without writing. `resume` optionally takes `--observed`
(`preimage`, `postimage`, `partial`, or `third`); `reconcile` requires it. `stop` records an
explicit abort and is idempotent. Exit code `3` is a missing run; code `2` is a named refusal.

Run folders are contained below `--runs-root`, reject symlinks and foreign identities, and are
never inferred from cwd or home. Reports expose only state, event counts, and journal hashes.
# P3.4 provider readiness

The P3.4 activity boundary accepts only an indexed, provider-specific admission. Native tool
controls are required and have no ambient fallback: Claude maps the admitted empty set to
`--tools ""`, while Codex refuses the currently unproven global no-tool request before process
creation. `artifacts/P3/probe-adapters.py` writes two minimized non-green readiness rows when
preflight refuses; a non-green row has `process_count: 0` and is not an acceptance verdict.
