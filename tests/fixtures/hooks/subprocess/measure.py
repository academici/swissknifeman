"""Reproduce hook distributions with an actual bus-seeded policy and verified checkout.

Run: uv run --frozen python tests/fixtures/hooks/subprocess/measure.py
Fixture setup and cache refresh happen outside the timed console-script subprocesses.
"""

from __future__ import annotations

import json
import math
import platform
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tests"))

from fixtures.hooks.subprocess.harness import TARGETS, cached_invocation  # noqa: E402
from integration.integrations.test_hooks import env, hook_env  # noqa: E402


def distribution(samples: list[float]) -> dict[str, float]:
    return {
        "p50_ms": round(statistics.median(samples), 3),
        "p95_ms": round(sorted(samples)[math.ceil(0.95 * len(samples)) - 1], 3),
        "max_ms": round(max(samples), 3),
    }


def main() -> None:
    folder = Path(tempfile.mkdtemp(prefix="p1005b-measure-"))
    # Reuse the existing real memory bus/project fixture, without pytest's environment policy.
    generator = cast("Any", env).__wrapped__(SimpleNamespace(param="memory"), folder)
    world: Any = next(generator)
    results: dict[str, Any] = {
        "python": platform.python_version(),
        "machine": platform.platform(),
        "root": str(folder),
    }
    try:
        cast("Any", hook_env).__wrapped__(world)
        for target in TARGETS:
            samples: list[float] = []
            for _ in range(20):
                # Refresh from the live bus before each independent measurement, never time setup.
                cache = world.state_dir / "hooks" / f"{world.project_id}-{target}.json"
                cache.unlink(missing_ok=True)
                invocation = cached_invocation(world, target)
                result, elapsed = invocation.execute()
                assert result.returncode == 0, result
                assert "HOOK_BACKEND_UNAVAILABLE" not in result.stdout + result.stderr, result
                samples.append(elapsed)
            # importtime is kept separate from the latency sample population.
            cache.unlink(missing_ok=True)
            invocation = cached_invocation(world, target)
            result, _ = invocation.execute(importtime=True)
            (folder / f"{target}-importtime.txt").write_text(result.stderr)
            self_us = [
                int(line.split("|")[0].partition(":")[2])
                for line in result.stderr.splitlines()
                if line.startswith("import time:") and "self" not in line
            ]
            results[target] = {
                **distribution(samples),
                "samples_ms": samples,
                "import_self_ms": round(sum(self_us) / 1000, 3),
                "cached_backend_ms": 0,
            }
            cache.unlink(missing_ok=True)
            invocation = cached_invocation(world, target)
            stages = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("stages.py")), *invocation.argv[1:]],
                input=json.dumps(invocation.payload),
                text=True,
                capture_output=True,
                env=invocation.environ,
                cwd=invocation.cwd,
                timeout=15,
                check=True,
            )
            results[target]["stages"] = json.loads(stages.stderr.splitlines()[0])
            print(json.dumps({target: results[target]}), flush=True)
        (folder / "measurements.json").write_text(json.dumps(results, indent=2))
        print(json.dumps({"report": str(folder / "measurements.json")}))
    finally:
        generator.close()


if __name__ == "__main__":
    main()
