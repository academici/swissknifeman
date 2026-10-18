"""Run a ``unittest discover`` suite in parallel worker processes.

    python3 -m aicore.util.par_unittest discover -s tests [-t TOP] [-p PATTERN] [-v] [-j N]

Tests are found with ``unittest discover`` itself (so an import error or a module-level skip behaves as usual), grouped by
test class and dealt out over ``N`` worker processes (``-j``, else ``SKM_TEST_JOBS``, else ``min(8, cpu_count)``), the
heaviest groups first. A group weighs what it took last time (kept per suite in the git directory of the repository,
``par-unittest/``, so it never dirties the tree and survives a throwaway HOME), else its number of tests. Each worker runs its classes in a fresh interpreter with its own throwaway ``HOME`` and ``TMPDIR``; a
``SKM_*HOME`` or ``XDG_*_HOME`` that lies inside the caller's ``HOME`` is copied into the worker's own, so state prepared by a
test script is there but never shared (one left unset stays unset: it follows the worker's ``HOME``, and a test that
passes its own home keeps it). The output is the one of ``unittest``: worker outputs
of failing shards, then one ``Ran N tests`` summary and ``OK`` or ``FAILED``; the exit code is 1 when a shard failed.

A failed shard is run once more alone. If it passes, the failure was a clash between parallel workers: a race in the
tests or in the code. ``--clash warn`` (default, or ``SKM_TEST_CLASH=warn``) says so on stderr and counts the shard as
passed; ``--clash fail`` (CI) keeps it failed, because a race hidden by a retry is still a race. ``-j 1`` or a single
class fall back to plain ``unittest discover``.
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


def _deal(units: Dict[Tuple[str, str], int], jobs: int, seconds: Optional[Dict[str, float]] = None) -> List[List[Tuple[str, str]]]:
    """Heaviest first, each unit to the lightest shard: a unit weighs its measured seconds of the last run, else its
    number of tests times the mean seconds of a measured test (or 1 when nothing was measured)."""
    seconds = seconds or {}
    known = [(seconds[name], units[(file, name)]) for file, name in units if name in seconds]
    per_test = (sum(sec for sec, _ in known) / max(1, sum(count for _, count in known))) if known else 1.0

    def weight(key: Tuple[str, str]) -> float:
        return seconds.get(key[1], units[key] * per_test)

    shards: List[List[Tuple[str, str]]] = [[] for _ in range(jobs)]
    load = [0.0] * jobs
    for key in sorted(units, key=lambda item: -weight(item)):
        index = load.index(min(load))
        shards[index].append(key)
        load[index] += weight(key)
    return [shard for shard in shards if shard]


def _times_file(start: Path) -> Optional[Path]:
    """Where the measured seconds of the suite at ``start`` are kept: the git directory, never the tree."""
    try:
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=start,
                                capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not common:
        return None
    import hashlib
    return Path(common) / "par-unittest" / (hashlib.sha256(str(start).encode("utf-8")).hexdigest()[:16] + ".json")


def _read_times(path: Optional[Path]) -> Dict[str, float]:
    import json
    try:
        found = json.loads(path.read_text(encoding="utf-8")) if path else {}
    except (OSError, ValueError):
        return {}
    return {str(key): float(value) for key, value in found.items() if isinstance(value, (int, float))} \
        if isinstance(found, dict) else {}


def _worker(args: argparse.Namespace) -> int:
    """One shard: ``--unit FILE::CLASS`` ... in this process."""
    top = Path(args.top_level_directory).resolve()
    wanted: Dict[str, set] = {}
    for unit in args.unit:
        file, _, name = unit.partition("::")
        wanted.setdefault(file, set()).add(name)
    suite, owner = unittest.TestSuite(), {}
    for file, names in wanted.items():
        for test in _tests(_load(Path(file), top)):
            key = _unit(test) if not type(test).__name__.startswith("_") else f"{Path(file).stem}:{type(test).__name__}"
            if key in names:
                suite.addTest(test)
                owner[id(test)] = key
    spent: Dict[str, float] = {}

    class Timed(unittest.TextTestResult):
        def startTest(self, test):
            self._began = time.monotonic()
            super().startTest(test)

        def stopTest(self, test):
            key = owner.get(id(test), "-")
            spent[key] = spent.get(key, 0.0) + time.monotonic() - getattr(self, "_began", time.monotonic())
            super().stopTest(test)

    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2 if args.verbose else 1, resultclass=Timed).run(suite)
    if args.times:
        import json
        Path(args.times).write_text(json.dumps(spent), encoding="utf-8")
    return 0 if result.wasSuccessful() else 1


def worker_env(env: dict, home: Path) -> dict:
    """The environment of one worker: its own HOME and TMPDIR, and the caller's SKM_*HOME and XDG_*_HOME folders that lie
    inside the caller's HOME copied into it (an unset one stays unset)."""
    out = dict(env, HOME=str(home), TMPDIR=str(home / "tmp"))
    (home / "tmp").mkdir(parents=True, exist_ok=True)
    caller = env.get("HOME")
    for key, value in env.items():
        if not (key.startswith(("SKM_", "XDG_")) and key.endswith("HOME")) or not value or not caller:
            continue
        try:
            inside = Path(value).resolve().relative_to(Path(caller).resolve())
        except ValueError:
            continue
        target = home / inside
        if Path(value).is_dir():
            shutil.copytree(value, target, symlinks=True, dirs_exist_ok=True)
        out[key] = str(target)
    return out


def _run(shard: Sequence[Tuple[str, str]], args: argparse.Namespace, top: Path, env: dict,
         spent: Optional[Dict[str, float]] = None) -> subprocess.CompletedProcess:
    home = Path(tempfile.mkdtemp(prefix="par-unittest-"))
    try:
        times = home / "times.json"
        argv = [sys.executable, "-m", "aicore.util.par_unittest", "discover", "--worker", "-t", str(top), "--times", str(times)]
        argv += (["-v"] if args.verbose else []) + [item for file, name in shard for item in ("--unit", f"{file}::{name}")]
        path = str(top) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")  # what discover does with -t
        done = subprocess.run(argv, env=dict(worker_env(env, home), PYTHONPATH=path), capture_output=True, text=True)  # no-timeout: a test worker runs as long as its tests
        if spent is not None:
            spent.update(_read_times(times))
        return done
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
    parser.add_argument("--clash", choices=["warn", "fail"], default=None,
                        help="a shard that fails in parallel but passes alone: warn (default) or fail (CI)")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--unit", action="append", default=[], help=argparse.SUPPRESS)
    parser.add_argument("--times", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        return _worker(args)
    # the environment of the workers is the caller's, taken before the tests are imported here to be counted: a test
    # package may change os.environ when it is imported (a fake partner), and that must not leak into every worker
    env = dict(os.environ)
    start = Path(args.start_directory).resolve()
    top = Path(args.top_level_directory).resolve() if args.top_level_directory else start
    jobs = args.jobs or int(os.environ.get("SKM_TEST_JOBS") or min(8, os.cpu_count() or 1))
    clash = args.clash or os.environ.get("SKM_TEST_CLASH") or "warn"

    def plain() -> int:
        command = [sys.executable, "-m", "unittest", "discover", "-s", args.start_directory, "-p", args.pattern]
        if args.top_level_directory:
            command += ["-t", args.top_level_directory]
        return subprocess.call(command + (["-v"] if args.verbose else []))  # no-timeout: the sequential fallback runs the whole suite

    if jobs <= 1 or not start.is_dir():
        return plain()
    sys.path.insert(0, str(top))
    units = _units(start, top, args.pattern)
    if len(units) < 2:
        return plain()
    times_file = _times_file(start)
    shards = _deal(units, min(jobs, len(units)), _read_times(times_file))
    began = time.monotonic()
    spent: Dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=len(shards)) as pool:
        done = list(pool.map(lambda shard: _run(shard, args, top, env, spent), shards))
    if times_file is not None and spent:
        try:
            import json
            times_file.parent.mkdir(parents=True, exist_ok=True)
            times_file.write_text(json.dumps(dict(_read_times(times_file), **spent), sort_keys=True), encoding="utf-8")
        except OSError:
            pass
    total = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    failed = False
    for shard, result in zip(shards, done):
        if result.returncode != 0:
            alone = _run(shard, args, top, env)  # was it a clash between the parallel workers?
            if alone.returncode == 0:
                print(f"par_unittest: CLASH: a shard of {len(shard)} class(es) failed in parallel but passes alone "
                      f"(a race in the tests or the code): {', '.join(name for _, name in shard)}", file=sys.stderr)
                if clash == "fail":
                    failed = True
                else:
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
