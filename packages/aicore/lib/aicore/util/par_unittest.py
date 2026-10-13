"""Run a ``unittest discover`` suite in parallel worker processes.

    python3 -m aicore.util.par_unittest discover -s tests [-t TOP] [-p PATTERN] [-v] [-j N]

Tests are found with ``unittest discover`` itself (so an import error or a module-level skip behaves as usual), grouped by
test class and dealt out over ``N`` worker processes (``-j``, else ``SKM_TEST_JOBS``, else ``min(8, cpu_count)``), the
heaviest groups first. Each worker runs its classes in a fresh interpreter with its own throwaway ``HOME``. The output is the
one of ``unittest``: worker outputs of failing shards, then one ``Ran N tests`` summary and ``OK`` or ``FAILED``; the exit
code is 1 when a shard failed. A failed shard is run once more alone: if it passes, the failure was a clash between
parallel workers, which is said on stderr. ``-j 1`` or a single class fall back to plain ``unittest discover``.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

_RAN = re.compile(r"^Ran (\d+) tests? in ([0-9.]+)s", re.MULTILINE)
_COUNTS = re.compile(r"(failures|errors|skipped)=(\d+)")


def _tests(suite: unittest.TestSuite) -> Iterator[unittest.TestCase]:
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _tests(item)
        else:
            yield item


def _files(start: Path, pattern: str) -> List[Path]:
    import fnmatch
    return [path for path in sorted(start.rglob("*.py"))
            if fnmatch.fnmatch(path.name, pattern) and "__pycache__" not in path.parts]


def _load(path: Path, top: Path) -> unittest.TestSuite:
    """The tests of one file, found by ``discover`` (the same handling of errors and skips as a plain run)."""
    return unittest.TestLoader().discover(str(path.parent), pattern=path.name, top_level_dir=str(top))


def _unit(test: unittest.TestCase) -> str:
    cls = type(test)
    return f"{cls.__module__}.{cls.__qualname__}"


def _units(start: Path, top: Path, pattern: str) -> Dict[Tuple[str, str], int]:
    """``{(file, class): number of tests}``."""
    units: Dict[Tuple[str, str], int] = {}
    for path in _files(start, pattern):
        for test in _tests(_load(path, top)):
            key = (str(path), _unit(test) if not type(test).__name__.startswith("_") else f"{path.stem}:{type(test).__name__}")
            units[key] = units.get(key, 0) + 1
    return units


def _deal(units: Dict[Tuple[str, str], int], jobs: int) -> List[List[Tuple[str, str]]]:
    """Heaviest first, each unit to the lightest shard (the number of tests stands for the run time)."""
    shards: List[List[Tuple[str, str]]] = [[] for _ in range(jobs)]
    load = [0] * jobs
    for key in sorted(units, key=lambda item: -units[item]):
        index = load.index(min(load))
        shards[index].append(key)
        load[index] += units[key]
    return [shard for shard in shards if shard]


def _worker(args: argparse.Namespace) -> int:
    """One shard: ``--unit FILE::CLASS`` ... in this process."""
    top = Path(args.top_level_directory).resolve()
    wanted: Dict[str, set] = {}
    for unit in args.unit:
        file, _, name = unit.partition("::")
        wanted.setdefault(file, set()).add(name)
    suite = unittest.TestSuite()
    for file, names in wanted.items():
        for test in _tests(_load(Path(file), top)):
            key = _unit(test) if not type(test).__name__.startswith("_") else f"{Path(file).stem}:{type(test).__name__}"
            if key in names:
                suite.addTest(test)
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2 if args.verbose else 1).run(suite)
    return 0 if result.wasSuccessful() else 1


def _run(shard: Sequence[Tuple[str, str]], args: argparse.Namespace, top: Path, env: dict) -> subprocess.CompletedProcess:
    home = tempfile.mkdtemp(prefix="par-unittest-")
    try:
        argv = [sys.executable, "-m", "aicore.util.par_unittest", "discover", "--worker", "-t", str(top)]
        argv += (["-v"] if args.verbose else []) + [item for file, name in shard for item in ("--unit", f"{file}::{name}")]
        path = str(top) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")  # what discover does with -t
        return subprocess.run(argv, env=dict(env, HOME=home, PYTHONPATH=path), capture_output=True, text=True)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="par_unittest", description=__doc__.splitlines()[0])
    parser.add_argument("verb", choices=["discover"])
    parser.add_argument("-s", "--start-directory", default=".")
    parser.add_argument("-t", "--top-level-directory", default=None)
    parser.add_argument("-p", "--pattern", default="test*.py")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-j", "--jobs", type=int, default=0)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--unit", action="append", default=[], help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        return _worker(args)
    start = Path(args.start_directory).resolve()
    top = Path(args.top_level_directory).resolve() if args.top_level_directory else start
    jobs = args.jobs or int(os.environ.get("SKM_TEST_JOBS") or min(8, os.cpu_count() or 1))

    def plain() -> int:
        command = [sys.executable, "-m", "unittest", "discover", "-s", args.start_directory, "-p", args.pattern]
        if args.top_level_directory:
            command += ["-t", args.top_level_directory]
        return subprocess.call(command + (["-v"] if args.verbose else []))

    if jobs <= 1 or not start.is_dir():
        return plain()
    sys.path.insert(0, str(top))
    units = _units(start, top, args.pattern)
    if len(units) < 2:
        return plain()
    shards = _deal(units, min(jobs, len(units)))
    env = dict(os.environ)
    began = time.monotonic()
    with ThreadPoolExecutor(max_workers=len(shards)) as pool:
        done = list(pool.map(lambda shard: _run(shard, args, top, env), shards))
    total = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    failed = False
    for shard, result in zip(shards, done):
        if result.returncode != 0:
            alone = _run(shard, args, top, env)  # was it a clash between the parallel workers?
            if alone.returncode == 0:
                print(f"par_unittest: a shard of {len(shard)} class(es) failed in parallel but passes alone "
                      f"(a clash of parallel tests): {shard[0][1]} ...", file=sys.stderr)
                result = alone
            else:
                failed = True
        output = result.stderr + result.stdout
        match = _RAN.search(output)
        total["tests"] += int(match.group(1)) if match else 0
        for key, value in _COUNTS.findall(output):
            total[key] += int(value)
        if result.returncode != 0 or args.verbose:
            sys.stderr.write(output)
    extra = ", ".join(f"{key}={value}" for key, value in total.items() if key != "tests" and value)
    print("-" * 70, file=sys.stderr)
    print(f"Ran {total['tests']} tests in {time.monotonic() - began:.3f}s\n", file=sys.stderr)
    print((f"FAILED ({extra})" if failed else "OK" + (f" ({extra})" if extra else "")), file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
