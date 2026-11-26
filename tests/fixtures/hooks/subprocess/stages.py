"""Optional subprocess instrumentation; production hook output stays unchanged."""

from __future__ import annotations

import argparse
import io
import json
import os
import statistics
import sys
from time import perf_counter

started = perf_counter()
from skm.bootstrap.hook import _cached_context, evaluate, write_output  # noqa: E402
from skm.entrypoints.hook.main import register_arguments  # noqa: E402

parser = argparse.ArgumentParser()
register_arguments(parser)
args = parser.parse_args()
raw = sys.stdin.buffer.read()
context = _cached_context(args, raw, os.environ, None)
assert context is not None
context_ready = perf_counter()
result = evaluate(args, io.BytesIO(raw), context)
first_evaluation = perf_counter()
elapsed: list[float] = []
for _ in range(5):
    before = perf_counter()
    result = evaluate(args, io.BytesIO(raw), context)
    elapsed.append((perf_counter() - before) * 1000)
sys.stderr.write(
    json.dumps(
        {
            "context_import_ms": (context_ready - started) * 1000,
            "first_evaluation_ms": (first_evaluation - context_ready) * 1000,
            "evaluation_p50_ms": statistics.median(elapsed),
            "evaluation_p95_ms": max(elapsed),
            "cached_backend_ms": 0,
        }
    )
    + "\n"
)
raise SystemExit(write_output(result, sys.stdout, sys.stderr))
