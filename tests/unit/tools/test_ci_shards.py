"""ci_shards assigns every test file to exactly one shard and fails closed on stale shard flags."""

from __future__ import annotations

import importlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

ci_shards = importlib.import_module("tools.ci_shards")


def test_every_repository_test_file_has_exactly_one_shard() -> None:
    files = ci_shards.list_test_files()
    assert files, "the repository has test files"
    per_shard = {shard.name: ci_shards.files_of(shard.name, files) for shard in ci_shards.SHARDS}
    assigned = [path for paths in per_shard.values() for path in paths]
    assert sorted(assigned) == files
    assert len(set(assigned)) == len(assigned)


def test_no_shard_is_stale() -> None:
    # A shard without files is a renamed or deleted directory whose tests went to `other`; a module shard may
    # list a test level (unit/contracts/integration) the module has not grown yet.
    files = ci_shards.list_test_files()
    empty = [shard.name for shard in ci_shards.SHARDS if not ci_shards.files_of(shard.name, files)]
    missing = [
        prefix
        for shard in ci_shards.SHARDS
        for prefix in shard.prefixes
        if prefix.endswith(".py") and prefix not in files
    ]
    assert empty == []
    assert missing == []


def test_first_matching_prefix_wins_and_unknown_paths_land_in_other() -> None:
    assert ci_shards.shard_of("tests/e2e/test_projected_hooks.py").name == "hooks"
    assert ci_shards.shard_of("tests/e2e/test_local_lifecycle.py").name == "e2e-lifecycle"
    assert ci_shards.shard_of("tests/e2e/test_m3_execution.py").name == "e2e"
    assert ci_shards.shard_of("tests/contracts/execution/test_x.py").name == "execution"
    assert ci_shards.shard_of("tests/integration/postgres/test_x.py").name == "adapters"
    assert ci_shards.shard_of("tests/brand_new_area/test_x.py").name == "other"
    assert ci_shards.shard_of("tests/unit/test_top_level.py").name == "other"


def test_test_files_follows_pytest_naming_and_skips_caches(tmp_path: Path) -> None:
    for name in (
        "tests/unit/test_a.py",
        "tests/unit/b_test.py",
        "tests/unit/helper.py",
        "tests/unit/__pycache__/test_c.py",
        "tests/unit/test_d.txt",
    ):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    assert ci_shards.list_test_files(tmp_path) == ["tests/unit/b_test.py", "tests/unit/test_a.py"]


def test_suites_select_their_flagged_shards() -> None:
    unit = {shard.name for shard in ci_shards.shards_for("unit")}
    pg = {shard.name for shard in ci_shards.shards_for("pg")}
    e2e = {shard.name for shard in ci_shards.shards_for("e2e")}
    assert "hooks" not in unit
    assert {"hooks", "adapters", "execution"} <= pg
    assert "platform" not in pg
    assert "architecture" not in pg
    assert {"e2e", "e2e-lifecycle"} <= e2e


def test_pytest_argv_runs_only_the_shard_with_the_suite_marker() -> None:
    files = ["tests/e2e/test_compose.py", "tests/e2e/test_a.py", "tests/unit/platform/test_b.py"]
    argv = ci_shards.pytest_argv("e2e", "e2e", files, ["-x"])
    assert argv[:3] == [sys.executable, "-m", "pytest"]
    assert argv[argv.index("-m", 3) + 1] == ci_shards.MARKERS["e2e"]
    assert argv[-2:] == ["-x", "tests/e2e/test_a.py"]
    assert "tests/e2e/test_compose.py" not in argv


def test_pytest_argv_bounds_unit_tests_so_a_hang_names_the_test() -> None:
    files = ["tests/unit/platform/test_b.py"]
    unit = ci_shards.pytest_argv("platform", "unit", files)
    assert unit[unit.index("--timeout") + 1] == str(ci_shards.UNIT_TEST_TIMEOUT_SECONDS)
    assert unit[unit.index("--timeout-method") + 1] == "signal"
    assert f"faulthandler_timeout={ci_shards.UNIT_TEST_TIMEOUT_SECONDS}" in unit
    pg = ci_shards.pytest_argv("hooks", "pg", ["tests/e2e/test_projected_hooks.py"])
    e2e = ci_shards.pytest_argv("e2e", "e2e", ["tests/e2e/test_a.py"])
    assert "--timeout" not in pg
    assert "--timeout" not in e2e
    assert "--durations=20" in pg
    assert "--durations=20" not in e2e
    assert "--durations=20" not in unit


def test_pytest_argv_runs_serial_shards_without_xdist_distribution() -> None:
    argv = ci_shards.pytest_argv("hooks", "pg", ["tests/e2e/test_projected_hooks.py"])
    assert argv[argv.index("-n") + 1] == "0"
    assert "--dist" not in argv
    arch = ci_shards.pytest_argv("architecture", "unit", ["tests/architecture/test_x.py"])
    assert arch[arch.index("--dist") + 1] == "loadfile"


def test_pytest_argv_rejects_an_empty_shard() -> None:
    with pytest.raises(ValueError, match="no test files"):
        ci_shards.pytest_argv("platform", "unit", ["tests/e2e/test_a.py"])


def test_problems_report_flags_that_disagree_with_collected_tests() -> None:
    counts = {
        suite: Counter({shard.name: 1 for shard in ci_shards.shards_for(suite)}) for suite in ci_shards.SUITES
    }
    assert ci_shards.problems(counts) == []
    counts["pg"]["platform"] = 3
    counts["pg"]["hooks"] = 0
    found = ci_shards.problems(counts)
    assert "platform: holds 3 pg tests but is excluded from the pg suite" in found
    assert "hooks: runs in the pg suite but holds no pg tests" in found


def test_matrix_command_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert ci_shards.main(["matrix", "--suite", "pg"]) == 0
    names = json.loads(capsys.readouterr().out)
    assert names == [shard.name for shard in ci_shards.shards_for("pg")]


def test_run_refuses_a_shard_outside_the_suite(capsys: pytest.CaptureFixture[str]) -> None:
    assert ci_shards.main(["run", "platform", "--suite", "pg"]) == 2
    assert "not part of the pg suite" in capsys.readouterr().err


def _plan(event: str = "push", ref: str = "refs/heads/ci/x", message: str = "", **filters: bool):
    return ci_shards.plan(event=event, ref=ref, message=message, filters=filters)


def test_push_runs_every_lane_and_every_cell() -> None:
    result = _plan()
    assert result.lanes == frozenset(ci_shards.LANES)
    assert len(result.unit) == len(ci_shards.shards_for("unit")) * len(ci_shards.PYTHONS)
    assert len(result.pg) == len(ci_shards.shards_for("pg")) * len(ci_shards.POSTGRES)
    assert {cell["postgres"] for cell in result.e2e} == {ci_shards.E2E_POSTGRES}


def test_pull_request_takes_lanes_from_changed_paths() -> None:
    assert _plan("pull_request").lanes == {"workflows"}
    assert _plan("pull_request", web=True).lanes == {"workflows", "web"}
    python = _plan("pull_request", python=True)
    assert {"lint", "typecheck", "unit", "pg", "e2e", "docs"} <= python.lanes
    assert "web" not in python.lanes


def test_ci_only_narrows_a_work_branch_push_to_the_listed_cells() -> None:
    result = _plan(message="fix: x\n\nCI-Only: lint, unit/platform@3.15, pg/hooks, web")
    assert result.lanes == {"lint", "unit", "pg", "web"}
    assert result.unit == [{"shard": "platform", "python": "3.15"}]
    assert {cell["postgres"] for cell in result.pg} == set(ci_shards.POSTGRES)
    assert {cell["shard"] for cell in result.pg} == {"hooks"}
    assert result.e2e == []
    assert "targeted run" in result.note


def test_ci_only_is_ignored_on_main_new_and_pull_requests() -> None:
    message = "CI-Only: web"
    for ref in ci_shards.PROTECTED_REFS:
        assert _plan(ref=ref, message=message).lanes == frozenset(ci_shards.LANES)
    assert _plan("pull_request", message=message, python=True).unit


def test_ci_only_rejects_a_token_that_names_nothing() -> None:
    with pytest.raises(ValueError, match="at least one"):
        _plan(message="CI-Only: , ")
    with pytest.raises(ValueError, match="unit/nonexistent"):
        _plan(message="CI-Only: unit/nonexistent, lint")
    with pytest.raises(ValueError, match="pg/platform"):
        _plan(message="CI-Only: pg/platform")


def test_plan_outputs_are_github_output_lines() -> None:
    lines = ci_shards.plan_outputs(_plan(message="CI-Only: e2e"))
    values = dict(line.split("=", 1) for line in lines)
    assert values["gate_name"] == "Targeted CI gate"
    assert "gate_name=CI gate" in ci_shards.plan_outputs(
        _plan("push", ref="refs/heads/new", message="CI-Only: e2e")
    )
    assert values["e2e"] == "true"
    assert values["unit"] == "false"
    assert json.loads(values["unit_matrix"]) == {"include": []}
    assert {cell["shard"] for cell in json.loads(values["e2e_matrix"])["include"]} == {
        "e2e",
        "e2e-lifecycle",
    }


def test_database_images_are_pinned_by_digest() -> None:
    # The workflow takes service images from the plan, so zizmor cannot see the pin; this test is the check.
    pattern = re.compile(r"^postgres:(?P<tag>[0-9.]+)@sha256:[0-9a-f]{64}$")
    for version, image in ci_shards.POSTGRES.items():
        match = pattern.match(image)
        assert match is not None, image
        assert match["tag"] == version
    assert ci_shards.E2E_POSTGRES in ci_shards.POSTGRES
