# Native hook startup — P10.05.b

Status: **executor validation passed**; manual review: `passed` (`01a1ebb4-a537-7bb2-bb4b-3dd9f9e27ef1`).

Measured after rebasing onto `new` at `ca89b9c94`, on 2026-11-18 Europe/Astrakhan
(2026-11-17 UTC). All four native targets pass the strict cold-process budget
(**p95 <= 150 ms**, with every observed sample across all 80 cold processes also
below 144 ms).

## Reference and method

Intel Xeon E5-2683 v4 @ 2.10 GHz, x86_64, 16 cores / 32 threads;
Linux-7.0.0-31-generic-x86_64-with-glibc2.39; CPython 3.12.3.
Shared development host; idle measurement window.
`uv sync --frozen` completed before modification and measurement.

Twenty separate installed `.venv/bin/skm-hook` processes per target receive a
native `git status` payload on stdin. Timing includes process creation, imports,
checkout/marker validation, evaluation, rendering and process exit. The OS page
cache is warm; interpreter/module state is fresh. Fixture setup, `uv` startup and
policy-cache seeding are outside the timed interval. Cache refresh uses the real
embedded memory bus and a verified Git checkout before each sample. Each child
receives an unreachable backend address, so a successful native response also
checks cache use. No backend call occurs on this cached path.

p50 is the median; p95 is nearest-rank observation 19 of 20. The strict local and
CI test threshold remains **p95 <= 150 ms**, without a multiplier or a relaxed
calibration. No measurements were discarded.

## Cold-process distribution

| Target | n | p50 ms | p95 ms | Max ms | Import self sum ms |
|---|---:|---:|---:|---:|---:|
| claude_code | 20 | 128.578 | 143.715 | 143.841 | 110.054 |
| codex | 20 | 112.531 | 139.567 | 140.658 | 88.766 |
| cursor | 20 | 110.567 | 137.657 | 142.668 | 110.369 |
| grok | 20 | 112.342 | 133.514 | 139.759 | 95.533 |

**All four targets pass the strict 150 ms budget** (down from 1850–1936 ms p95
initially and 287–333 ms p95 prior to the Wave-2/Wave-3 import-graph cuts).

## Separate stage measurements

These are separate instrumented subprocesses, excluded from the cold-process
distribution. Context/import and first evaluation are single observations;
warm evaluation uses five repetitions in the same instrumented process.

| Target | Context/import ms | First evaluation ms | Warm eval p50 ms | Warm eval p95 ms | Cached backend ms |
|---|---:|---:|---:|---:|---:|
| claude_code | 59.847 | 13.809 | 2.085 | 2.388 | 0 |
| codex | 59.353 | 13.767 | 2.272 | 2.616 | 0 |
| cursor | 79.251 | 15.109 | 2.334 | 2.451 | 0 |
| grok | 76.510 | 15.867 | 2.486 | 2.563 | 0 |

Different populations must not be added as though they were one trace. Warm
evaluation is approximately 2.1–2.5 ms; cold-process execution is dominated by
interpreter startup and the minimal target-specific import graph (88.8–110.4 ms
self import time).

## Bootstrap changes and invariants

`_cached_context` reads policy and snapshot together using
`LocalHookState.load_with_snapshot`, exposes `cached_snapshot` on `CachedClient`
so cached evaluations validate checkout/marker state without importing generated
workspace views, and defers `argparse` and view codecs off the cached path. The
local `CachedHookState` subclass was removed: upstream `LocalHookState.remember`
already suppresses identical durable writes. The import regression test verifies
unchanged cache bytes and `mtime_ns`.

Target-specific codec loading remains lazy. The real subprocess import trace
checks that `psycopg`, `starlette`, `uvicorn`, runtime adapters, the global target
registry, `bootstrap.composition` and the global `bootstrap.modules` catalog are
absent, and that only the requested target codec is loaded. Project/target/host
binding, TTL/generation validation and the live review-receipt path are retained.
Public bootstrap exports are unchanged.

## Reproduction and native protocol coverage

```sh
uv sync --frozen
uv run --frozen python tests/fixtures/hooks/subprocess/measure.py
uv run --frozen pytest -q -n 0 tests/perf/test_hook_startup.py
SKM_TEST_DATABASE_URL=postgresql://skm:skm_dev@127.0.0.1:54329/skm_test SKM_REQUIRE_PG=1 \
  uv run --frozen pytest -q -n 2 --dist worksteal \
  tests/e2e/test_projected_hooks.py tests/security/test_hook_fail_closed.py
uv run --frozen python tools/check_touched.py --base new
git diff --check
```

The measurement driver prints the artifact path for the raw population and
writes `measurements.json` and separate `TARGET-importtime.txt` traces.
`stages.py` provides the instrumented stage breakdown. To inspect a prepared
cache directly, invoke the installed script with `python -X importtime` and the
same native stdin payload and target/project arguments.

The projected-hook tests apply native configuration using real target adapters
and PostgreSQL through the existing CLI host-composition fixture, read the
commands from those files and execute the installed `skm-hook` for Claude Code,
Codex, Cursor and Grok. They cover live denial, cached success, missing/refused
backends, enforcement denial with `HOOK_BACKEND_UNAVAILABLE`, and workflow/
observation native `none`. Real PostgreSQL locks exercise configured backend
timeouts of 50 and 800 ms, with process exit required before lock release.
The e2e records warm PostgreSQL policy-query timing separately as test properties.

## Executor checks

`tests/perf/test_hook_startup.py`: **8 passed in 23.36 s**. All four import-graph
and unchanged-cache checks passed, and all four strict cold-start budget checks
(`p95 <= 150 ms`) passed without relaxing the threshold.

The requested PostgreSQL e2e/security selection passed: **48 passed in 205.80 s**
(`tests/e2e/test_projected_hooks.py`, `tests/security/test_hook_fail_closed.py`).
This includes all four projected native targets, backend-outage class semantics,
real locked-query timeout checks and the security regressions.

`tools/check_touched.py --base new` passed: Ruff check/format, Pyright,
**379 architecture tests**, and documentation links. `git diff --check` passed.
All changed files are below 600 lines and remain within the leaf write set.

The P10.05.b cold-start budget and the integrations hook-evaluation rule are the
recorded bar. The measurement is [`tests/perf/test_hook_startup.py`](../../tests/perf/test_hook_startup.py);
hook behavior lives in [`modules/integrations/`](../../src/skm/modules/integrations/).
