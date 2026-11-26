# Performance measurements

Opt-in performance measurements use the `perf` marker. Run the suite against a
disposable PostgreSQL 16 test server with `SKM_REQUIRE_PG=1`. Allow space for
20 million event rows, 10 million audit rows, indexes, WAL and the dump.
Use `--perf-history-dsn` when the main test server has limited capacity.
`--perf-results=PATH` appends raw observations and percentile summaries in JSON Lines format.

See the [P15.03 report](../../docs/measurements.md) for commands, dataset sizes,
methodology and measured budgets.
