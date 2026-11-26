"""Split the pytest suite into per-module CI shards and run one of them.

Every test file belongs to exactly one shard: the first shard whose prefix matches its path, or ``other``,
which catches whatever no prefix claims (top-level test files, a test directory added later). A new file can
therefore never fall out of CI; it only lands in ``other`` until a shard claims it.

Suites select tests by marker, exactly like the Makefile targets they parallelise:

* ``unit``: ``make test`` plus ``make arch`` (no external services);
* ``pg``: ``make test-pg`` (needs ``SKM_TEST_DATABASE_URL``);
* ``e2e``: end-to-end tests that are not already part of ``pg``; the compose stack runs in its own job.

``check`` collects every suite once and fails when a shard's ``pg``/``e2e`` flag disagrees with the tests it
actually holds, so a shard with database tests cannot silently drop out of the database matrix.

Usage::

    python tools/ci_shards.py matrix --suite pg     # JSON list of shard names for a CI matrix
    python tools/ci_shards.py files platform         # the test files of one shard
    python tools/ci_shards.py run platform --suite unit [-- extra pytest args]
    python tools/ci_shards.py check
    python tools/ci_shards.py plan                   # CI lanes and matrices from the event (GitHub env)

``plan`` selects the CI lanes. A pull request takes the lanes its changed paths need; a push takes all
of them. On a push to a work branch (not main or new), a ``CI-Only:`` line in the head commit narrows
the run to the listed lanes or matrix cells, so a fix is verified on the cells that failed before one
full run at the end::

    CI-Only: lint, unit/platform@3.15, pg/hooks@19.0, e2e, web
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

Suite = Literal["unit", "pg", "e2e"]
SUITES: tuple[Suite, ...] = ("unit", "pg", "e2e")

MARKERS: dict[Suite, str] = {
    "unit": "not pg and not e2e and not evals and not perf",
    "pg": "pg and not perf and not evals",
    "e2e": "e2e and not pg and not perf and not evals",
}

# The compose test builds and starts the whole stack with Docker; it has a dedicated CI job.
E2E_OWN_JOB = ("tests/e2e/test_compose.py",)


@dataclass(frozen=True, slots=True)
class Shard:
    name: str
    prefixes: tuple[str, ...]
    unit: bool = True
    pg: bool = True
    e2e: bool = False
    # pytest-xdist workers; "0" runs in-process for timing-sensitive tests.
    workers: str = "auto"
    dist: str = "worksteal"


def _module(name: str, *, pg: bool = True) -> Shard:
    return Shard(
        name, (f"tests/unit/{name}/", f"tests/contracts/{name}/", f"tests/integration/{name}/"), pg=pg
    )


# Order matters: the first matching prefix wins.
SHARDS: tuple[Shard, ...] = (
    # Native hook deadline checks must not compete with xdist workers (see `make test-pg`).
    Shard("hooks", ("tests/e2e/test_projected_hooks.py",), unit=False, workers="0"),
    # The pg/e2e cell is the CI wall-time critical path (8-13 min of pytest). A more specific
    # shard runs first; remaining tests/e2e/ files stay in `e2e`. Two workers per job keep
    # one shared Postgres from being oversubscribed the way `-n auto` can be.
    Shard(
        "e2e-lifecycle",
        (
            "tests/e2e/test_local_lifecycle.py",
            "tests/e2e/test_local_lifecycle_shutdown.py",
            "tests/e2e/test_plan_authoring.py",
            "tests/e2e/test_http_execution.py",
            "tests/e2e/test_http_hook.py",
            "tests/e2e/test_http_worker.py",
            "tests/e2e/test_http_worker_resilience.py",
            "tests/e2e/test_execution_cli.py",
            "tests/e2e/test_extensions_cli.py",
            "tests/e2e/test_instance_profiles.py",
            "tests/e2e/test_review_request.py",
            "tests/e2e/test_integrations_acceptance.py",
            "tests/e2e/test_integrations_cli.py",
            "tests/e2e/test_integrations_doctor.py",
        ),
        e2e=True,
        workers="2",
    ),
    Shard("e2e", ("tests/e2e/",), e2e=True, workers="2"),
    # Architecture rules share expensive per-file AST caches; `make arch` keeps them per worker.
    Shard("architecture", ("tests/architecture/",), pg=False, workers="2", dist="loadfile"),
    Shard("security", ("tests/security/",)),
    Shard("recovery", ("tests/recovery/",)),
    Shard("platform", ("tests/unit/platform/",), pg=False),
    Shard(
        "kernel",
        (
            "tests/unit/kernel/",
            "tests/unit/application_bus/",
            "tests/unit/background/",
            "tests/unit/bootstrap/",
            "tests/contracts/core/",
            "tests/integration/bootstrap/",
        ),
    ),
    Shard(
        "adapters",
        (
            "tests/unit/adapters/",
            "tests/integration/postgres/",
            "tests/integration/storage/",
            "tests/integration/git/",
            "tests/integration/http/",
            "tests/integration/research/",
            "tests/integration/checks/",
        ),
    ),
    Shard(
        "entrypoints",
        (
            "tests/unit/entrypoints/",
            "tests/integration/api/",
            "tests/integration/cli/",
            "tests/integration/mcp/",
            "tests/integration/worker/",
            "tests/integration/packaging/",
        ),
    ),
    _module("access"),
    _module("artifacts"),
    _module("context"),
    _module("execution"),
    _module("exports"),
    _module("extensions"),
    _module("integrations"),
    _module("knowledge"),
    _module("learning"),
    _module("planning"),
    _module("policy"),
    _module("runtimes"),
    _module("settings"),
    _module("workspace"),
    Shard("other", ("",), pg=False),
)

BY_NAME = {shard.name: shard for shard in SHARDS}


def _is_test_file(path: Path) -> bool:
    return path.suffix == ".py" and (path.name.startswith("test_") or path.stem.endswith("_test"))


def list_test_files(root: Path = ROOT) -> list[str]:
    """Every pytest test file under ``tests/`` as a POSIX path relative to ``root``, sorted."""
    base = root / "tests"
    return sorted(
        path.relative_to(root).as_posix()
        for path in base.rglob("*.py")
        if _is_test_file(path) and "__pycache__" not in path.parts
    )


def shard_of(path: str) -> Shard:
    for shard in SHARDS:
        if any(path.startswith(prefix) for prefix in shard.prefixes):
            return shard
    raise AssertionError("the catch-all shard matches every path")


def files_of(name: str, files: Iterable[str]) -> list[str]:
    return [path for path in files if shard_of(path).name == name]


def shards_for(suite: Suite) -> list[Shard]:
    if suite == "pg":
        return [shard for shard in SHARDS if shard.pg]
    if suite == "e2e":
        return [shard for shard in SHARDS if shard.e2e]
    return [shard for shard in SHARDS if shard.unit]


# Unit tests are short; a hang must fail with the test name instead of the CI job limit.
# pg and e2e keep their own longer waits, so this bound is unit-only.
UNIT_TEST_TIMEOUT_SECONDS = 60


def pytest_argv(name: str, suite: Suite, files: Sequence[str], extra: Sequence[str] = ()) -> list[str]:
    shard = BY_NAME[name]
    selected = [path for path in files_of(name, files) if suite != "e2e" or path not in E2E_OWN_JOB]
    if not selected:
        raise ValueError(f"shard {name!r} has no test files")
    workers = shard.workers
    # Print the slowest tests on the long PostgreSQL cells so the next timing pass is not a guess.
    durations = ["--durations=20"] if suite == "pg" else []
    timeout = (
        [
            "--timeout",
            str(UNIT_TEST_TIMEOUT_SECONDS),
            "--timeout-method",
            "signal",
            "-o",
            f"faulthandler_timeout={UNIT_TEST_TIMEOUT_SECONDS}",
        ]
        if suite == "unit"
        else []
    )
    return [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "-n",
        workers,
        *(["--dist", shard.dist] if workers != "0" else []),
        "-m",
        MARKERS[suite],
        *durations,
        *timeout,
        *extra,
        *selected,
    ]


def _collect(suite: Suite) -> Counter[str]:
    """Collected test counts per shard for one suite (a collection only; nothing runs)."""
    argv = [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"]
    argv += ["-m", MARKERS[suite], "tests"]
    if suite == "e2e":
        argv += [f"--deselect={path}" for path in E2E_OWN_JOB]
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode not in (0, 5):
        sys.stderr.write(result.stdout[-4000:] + result.stderr[-4000:])
        raise RuntimeError(f"collecting the {suite} suite failed with exit code {result.returncode}")
    counts: Counter[str] = Counter()
    for line in result.stdout.splitlines():
        if "::" in line:
            counts[shard_of(line.split("::", 1)[0]).name] += 1
    return counts


def problems(counts: Mapping[Suite, Counter[str]]) -> list[str]:
    """Disagreements between the declared shard flags and the collected tests."""
    found: list[str] = []
    for suite in SUITES:
        selected = {shard.name for shard in shards_for(suite)}
        for shard in SHARDS:
            held = counts[suite][shard.name]
            if shard.name in selected and held == 0:
                found.append(f"{shard.name}: runs in the {suite} suite but holds no {suite} tests")
            if shard.name not in selected and held:
                found.append(
                    f"{shard.name}: holds {held} {suite} tests but is excluded from the {suite} suite"
                )
    return found


def check() -> int:
    counts: dict[Suite, Counter[str]] = {suite: _collect(suite) for suite in SUITES}
    for suite in SUITES:
        summary = ", ".join(f"{name}={count}" for name, count in sorted(counts[suite].items()))
        print(f"{suite}: {sum(counts[suite].values())} tests ({summary})")
    found = problems(counts)
    for problem in found:
        print(f"error: {problem}", file=sys.stderr)
    return 1 if found else 0


# Matrix axes of the CI lanes. Python: the requires-python floor and the latest release. PostgreSQL: the two
# latest majors, pinned by digest; e2e runs on the newest one.
PYTHONS: tuple[str, ...] = ("3.12", "3.15")
POSTGRES: dict[str, str] = {
    "18.7": "postgres:18.7@sha256:c699303802144847d238196173655dbbecf7a96aeca1565f2b02eb671a1f0b6b",
    "19.0": "postgres:19.0@sha256:aaa10f7ba7328b4a221a6c3184d83eef885bd16bf1f6de864757863156b0a4d1",
}
E2E_POSTGRES = "19.0"

LANES: tuple[str, ...] = (
    "lint",
    "typecheck",
    "contracts",
    "docs",
    "workflows",
    "shell",
    "unit",
    "pg",
    "e2e",
    "compose",
    "web",
)
# Path-filter outputs of a pull request and the lanes each one needs; `workflows` always runs.
FILTER_LANES: dict[str, tuple[str, ...]] = {
    "python": ("lint", "typecheck", "contracts", "docs", "unit", "pg", "e2e"),
    "docs": ("docs",),
    "web": ("web",),
    "compose": ("compose",),
    "shell": ("shell",),
}
PROTECTED_REFS = ("refs/heads/main", "refs/heads/new")
_ONLY = re.compile(r"^CI-Only:[ \t]*(?P<cells>.*)$", re.MULTILINE)
Cell = dict[str, str]


@dataclass(frozen=True, slots=True)
class Plan:
    lanes: frozenset[str]
    unit: list[Cell]
    pg: list[Cell]
    e2e: list[Cell]
    note: str
    targeted: bool


def _cells() -> dict[str, list[Cell]]:
    return {
        "unit": [{"shard": s.name, "python": py} for s in shards_for("unit") for py in PYTHONS],
        "pg": [
            {"shard": s.name, "postgres": version, "image": image}
            for s in shards_for("pg")
            for version, image in POSTGRES.items()
        ],
        "e2e": [
            {"shard": s.name, "postgres": E2E_POSTGRES, "image": POSTGRES[E2E_POSTGRES]}
            for s in shards_for("e2e")
        ],
    }


def parse_only(message: str) -> list[str] | None:
    """Tokens of the last ``CI-Only:`` line of a commit message, or None without one."""
    found = _ONLY.findall(message)
    if not found:
        return None
    return [token for token in re.split(r"[,\s]+", found[-1]) if token]


def _matches(token: str, lane: str, cell: Cell) -> bool:
    head, _, variant = token.partition("@")
    name, _, shard = head.partition("/")
    if name != lane or (shard and shard != cell["shard"]):
        return False
    return not variant or variant in (cell.get("python"), cell.get("postgres"))


def plan(*, event: str, ref: str, message: str, filters: Mapping[str, bool]) -> Plan:
    """Lanes and matrix cells for one workflow run; raises ValueError on an unknown CI-Only token."""
    cells = _cells()
    if event == "pull_request":
        lanes = {"workflows"}
        for name, needed in FILTER_LANES.items():
            if filters.get(name, False):
                lanes.update(needed)
    else:
        lanes = set(LANES)
    only = parse_only(message) if event == "push" and ref not in PROTECTED_REFS else None
    note = "pull request: lanes from changed paths" if event == "pull_request" else "full run"
    if only is not None:
        if not only:
            raise ValueError("CI-Only requires at least one lane or matrix cell")
        known = [t for t in only if any(_matches(t, lane, c) for lane in cells for c in cells[lane])]
        known += [t for t in only if t in LANES]
        unknown = sorted(set(only) - set(known))
        if unknown:
            raise ValueError(f"CI-Only names no lane or matrix cell: {', '.join(unknown)}")
        lanes &= {token.partition("/")[0].partition("@")[0] for token in only}
        for lane in cells:
            cells[lane] = [c for c in cells[lane] if any(_matches(t, lane, c) for t in only)]
        note = "targeted run (CI-Only): " + ", ".join(only)
    selected = {lane: cells[lane] if lane in lanes else [] for lane in cells}
    lanes -= {lane for lane, chosen in selected.items() if not chosen}
    return Plan(
        frozenset(lanes), selected["unit"], selected["pg"], selected["e2e"], note, targeted=only is not None
    )


def plan_outputs(result: Plan) -> list[str]:
    lines = [f"{lane}={'true' if lane in result.lanes else 'false'}" for lane in LANES]
    lines.append("gate_name=" + ("Targeted CI gate" if result.targeted else "CI gate"))
    for lane, chosen in (("unit", result.unit), ("pg", result.pg), ("e2e", result.e2e)):
        lines.append(f"{lane}_matrix={json.dumps({'include': chosen}, separators=(',', ':'))}")
    return lines


def _plan_from_env() -> int:
    filters = {name: os.environ.get(f"FILTER_{name.upper()}", "") == "true" for name in FILTER_LANES}
    try:
        result = plan(
            event=os.environ.get("GITHUB_EVENT_NAME", ""),
            ref=os.environ.get("GITHUB_REF", ""),
            message=os.environ.get("HEAD_MESSAGE", ""),
            filters=filters,
        )
    except ValueError as error:
        print(f"::error::{error}", file=sys.stderr)
        return 1
    lines = plan_outputs(result)
    print("\n".join(lines))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"### CI plan\n\n{result.note}\n\nLanes: {', '.join(sorted(result.lanes))}\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    matrix = commands.add_parser("matrix", help="JSON list of shard names for a suite")
    matrix.add_argument("--suite", choices=SUITES, default="unit")
    files = commands.add_parser("files", help="test files of one shard")
    files.add_argument("shard", choices=sorted(BY_NAME))
    run = commands.add_parser("run", help="run one shard of a suite")
    run.add_argument("shard", choices=sorted(BY_NAME))
    run.add_argument("--suite", choices=SUITES, default="unit")
    run.add_argument("extra", nargs="*", help="extra pytest arguments (after --)")
    commands.add_parser("check", help="verify shard flags against the collected suites")
    commands.add_parser("plan", help="CI lanes and matrices for the current GitHub event")
    args = parser.parse_args(argv)

    if args.command == "matrix":
        print(json.dumps([shard.name for shard in shards_for(args.suite)]))
        return 0
    if args.command == "files":
        print("\n".join(files_of(args.shard, list_test_files())))
        return 0
    if args.command == "run":
        if BY_NAME[args.shard] not in shards_for(args.suite):
            print(f"shard {args.shard!r} is not part of the {args.suite} suite", file=sys.stderr)
            return 2
        command = pytest_argv(args.shard, args.suite, list_test_files(), args.extra)
        print("+ " + " ".join(command[1:]), flush=True)
        return subprocess.run(command, cwd=ROOT, env=os.environ.copy(), check=False).returncode
    if args.command == "plan":
        return _plan_from_env()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
