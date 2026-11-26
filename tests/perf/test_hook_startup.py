"""Cold installed console script: real cache, native decision, import graph and distribution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from fixtures.hooks.subprocess.harness import TARGETS, cached_invocation
from integration.integrations.test_hooks import env, hook_env
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "env", "hook_env", "pg_session", "test_database"]
pytestmark = [pytest.mark.perf, pytest.mark.parametrize("env", ["memory"], indirect=True)]

# Local reference budget, including process creation and exit; no silent CI multiplier.
BUDGET_MS = 150
SAMPLES = 20


@pytest.mark.parametrize("target", TARGETS)
def test_cold_cached_native_hook(hook_env: Any, target: str, measure: Any) -> None:
    elapsed: list[float] = []
    for _ in range(SAMPLES):
        # Keep every input genuinely valid even if a regression exceeds the policy TTL.
        cache = hook_env.state_dir / "hooks" / f"{hook_env.project_id}-{target}.json"
        cache.unlink(missing_ok=True)
        invocation = cached_invocation(hook_env, target)
        result, duration = invocation.execute()
        assert result.returncode == 0, result.stderr
        assert "HOOK_BACKEND_UNAVAILABLE" not in result.stdout + result.stderr
        assert result.stdout.strip() == ('{"permission": "allow"}' if target == "cursor" else "")
        elapsed.append(duration)
    stats = measure("cold_hook_ms", elapsed, target=target, budget_ms=BUDGET_MS)
    assert stats["p95"] <= BUDGET_MS, (target, stats)


@pytest.mark.parametrize("target", TARGETS)
def test_cached_import_graph(hook_env: Any, target: str, tmp_path: Path) -> None:
    invocation = cached_invocation(hook_env, target)
    cache = hook_env.state_dir / "hooks" / f"{hook_env.project_id}-{target}.json"
    cache_before = cache.read_bytes(), cache.stat().st_mtime_ns
    result, _ = invocation.execute(importtime=True)
    assert result.returncode == 0, result.stderr
    assert "HOOK_BACKEND_UNAVAILABLE" not in result.stdout + result.stderr
    modules = [line.rsplit("|", 1)[-1].strip() for line in result.stderr.splitlines() if "|" in line]
    forbidden = (
        "psycopg",
        "starlette",
        "uvicorn",
        "skm.bootstrap.composition",
        "skm.bootstrap.modules",
        "skm.adapters.integrations.registry",
        "skm.adapters.runtimes",
    )
    assert not [name for name in modules if name.startswith(forbidden)]
    loaded = {
        name.split(".")[3]
        for name in modules
        if name.startswith("skm.adapters.integrations.") and name.split(".")[3] in TARGETS
    }
    assert loaded == {target}
    assert (cache.read_bytes(), cache.stat().st_mtime_ns) == cache_before
    (tmp_path / f"{target}-importtime.txt").write_text(result.stderr)
