"""Run unittest discovery in bounded, isolated workers, retaining case outcomes and retry evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from aicore.util.schema import validate_node

# Private file contracts stay beside their sole reader/writer. Timing maps retain their old shape.
_SCHEMAS = {
    "times": {"type": "object", "additionalProperties": {"type": "number", "minimum": 0}},
    "failed": {"type": "array", "items": {"type": "string", "minLength": 1}, "uniqueItems": True},
    "outcomes": {"type": "array", "items": {"type": "object", "additionalProperties": False,
        "required": ["id", "outcome", "reason"], "properties": {
            "id": {"type": "string"}, "outcome": {"enum": ["passed", "failed", "error", "skipped", "expected_failure", "unexpected_success"]},
            "reason": {"type": "string"}}}},
}
_SCHEMAS["report"] = {"type": "object", "additionalProperties": False,
    "required": ["context", "requested_jobs", "effective_jobs", "inventory", "attempts", "elapsed_s"],
    "properties": {
        "context": {"type": "string"}, "requested_jobs": {"type": "integer"},
        "effective_jobs": {"type": "integer", "minimum": 1}, "elapsed_s": {"type": "number", "minimum": 0},
        "inventory": {"type": "array", "items": {"type": "object", "additionalProperties": False,
            "required": ["key", "id", "file", "context"], "properties": {
                name: {"type": "string"} for name in ("key", "id", "file", "context")}}},
        "attempts": {"type": "array", "items": {"type": "object", "additionalProperties": False,
            "required": ["retry", "exit", "units", "outcomes", "tests_run", "started", "executed"], "properties": {
                "retry": {"type": "boolean"}, "exit": {"type": "integer"},
                "tests_run": {"anyOf": [{"type": "integer", "minimum": 0}, {"type": "null"}]},
                "executed": {"anyOf": [{"type": "integer", "minimum": 0}, {"type": "null"}]},
                "started": {"type": "array", "items": {"type": "string"}},
                "units": {"type": "array", "items": {"type": "string"}}, "outcomes": _SCHEMAS["outcomes"]}}}}}
_SCHEMAS["worker"] = {"type": "object", "additionalProperties": False,
    "required": ["outcomes", "tests_run", "started", "executed"], "properties": {
        "started": {"type": "array", "items": {"type": "string"}},
        "executed": {"type": "integer", "minimum": 0},
        "outcomes": _SCHEMAS["outcomes"], "tests_run": {"type": "integer", "minimum": 0}}}
for _kind, _schema in _SCHEMAS.items():
    _schema["$id"] = "urn:swissknifeman:aicore:par-unittest-" + _kind + ":v1"
    _schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"


def _valid(value, kind):
    return not validate_node(None, _SCHEMAS[kind], _SCHEMAS[kind]["$id"], value)


def _read(path, kind, default):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if _valid(value, kind) else default
    except (OSError, ValueError, TypeError):
        return default


def _write_atomic(path, value, kind="times"):
    if not _valid(value, kind):
        raise ValueError("invalid par_unittest " + kind)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _tests(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _tests(item)
        else:
            yield item


def _unit(test):
    cls = type(test)
    return f"{cls.__module__}.{cls.__qualname__}"


def _discover(args):
    return unittest.TestLoader().discover(str(Path(args.start_directory).resolve()), pattern=args.pattern,
        top_level_dir=str(Path(args.top_level_directory or args.start_directory).resolve()))


def _file(test, start):
    module = sys.modules.get(type(test).__module__)
    return str(Path(getattr(module, "__file__", None) or start).resolve())


def _splittable(test):
    cls = type(test)
    module = sys.modules.get(cls.__module__)
    # TestCase defaults are safe; every other inherited override owns a fixture boundary.
    if any(name in vars(base) for base in cls.__mro__ if base not in (unittest.TestCase, object)
           for name in ("setUpClass", "tearDownClass", "run", "__call__")):
        return False
    if not module or any(hasattr(module, name) for name in ("setUpModule", "tearDownModule", "load_tests")):
        return False
    # A package's custom discovery can create parameterized instances or change suite semantics.
    parts = cls.__module__.split(".")
    return not any(hasattr(sys.modules.get(".".join(parts[:n])), "load_tests") for n in range(1, len(parts)))


def _units(start, top, pattern, details=None, discovery=None):
    args = argparse.Namespace(start_directory=str(start), top_level_directory=str(top), pattern=pattern)
    units = {}
    suite = _discover(args)
    def custom(node):
        return isinstance(node, unittest.TestSuite) and (type(node) is not unittest.TestSuite or any(custom(t) for t in node))
    if discovery is not None:
        discovery["custom"] = custom(suite)
    for test in _tests(suite):
        key = (_file(test, start), _unit(test))
        units[key] = units.get(key, 0) + 1
        if details is not None:
            details.setdefault(key, []).append(test)
        if discovery is not None:
            parts = type(test).__module__.split(".")
            discovery["custom"] |= any(hasattr(sys.modules.get(".".join(parts[:n])), "load_tests")
                                       for n in range(1, len(parts) + 1))
    return units


def _split(units, details, seconds, jobs):
    result = dict(units)
    # Old class and new method records coexist; count each class only once for the threshold.
    total = sum(seconds.get(name, sum(seconds.get(t.id(), 0) for t in details[key])) for key, name in
                ((key, key[1]) for key in units))
    threshold = max(30.0, total / max(1, jobs) / 2)
    for key, tests in details.items():
        ids = [test.id() for test in tests]
        if seconds.get(key[1], 0) <= threshold or len(ids) != len(set(ids)) or not all(_splittable(t) for t in tests):
            continue
        del result[key]
        for identity in ids:
            result[(key[0], identity)] = 1
    return result


def _deal(units, jobs, seconds=None):
    seconds = seconds or {}
    known = [(seconds[name], count) for (_, name), count in units.items() if name in seconds]
    per_test = sum(sec for sec, _ in known) / max(1, sum(count for _, count in known)) if known else 1.0
    shards, loads = [[] for _ in range(jobs)], [0.0] * jobs
    for key in sorted(units, key=lambda k: -seconds.get(k[1], units[k] * per_test)):
        index = loads.index(min(loads))
        shards[index].append(key)
        loads[index] += seconds.get(key[1], units[key] * per_test)
    return [shard for shard in shards if shard]


def _times_file(start):
    if os.environ.get("SKM_PAR_UNITTEST_TIMES"):
        return Path(os.environ["SKM_PAR_UNITTEST_TIMES"])
    try:
        done = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=start,
                              capture_output=True, text=True, timeout=10)
        if done.returncode or not done.stdout.strip():
            return None
        return Path(done.stdout.strip()) / "par-unittest" / (hashlib.sha256(str(start).encode()).hexdigest()[:16] + ".json")
    except (OSError, subprocess.SubprocessError):
        return None


def _read_times(path):
    values = _read(path, "times", {}) if path else {}
    return {key: float(value) for key, value in values.items() if math.isfinite(value)}


def _worker(args):
    discovered = _discover(args)
    tests = list(_tests(discovered))
    selected = set(args.unit)
    chosen = [test for test in tests if args.serial or
              f"{_file(test, args.start_directory)}::{_unit(test)}" in selected or
              f"{_file(test, args.start_directory)}::{test.id()}" in selected]
    matched = {f"{_file(t, args.start_directory)}::{name}" for t in chosen for name in (_unit(t), t.id())}
    if not args.serial and (not chosen or selected - matched):
        print("par_unittest: discovery changed or selected tests are missing", file=sys.stderr)
        return 1  # no receipt: the caller must retry the whole shard
    spent, outcomes, failed, started = {}, [], set(), []
    skipped_started = 0
    unsafe_failure = False
    parent_ids = {id(t): t.id() for t in chosen}

    class Timed(unittest.TextTestResult):
        def startTest(self, test):
            self.began = time.monotonic()
            started.append(test.id())
            super().startTest(test)

        def stopTest(self, test):
            elapsed = time.monotonic() - self.began
            for key in (_unit(test), test.id()):
                spent[key] = spent.get(key, 0.0) + elapsed
            super().stopTest(test)

        def record(self, test, outcome, reason=""):
            nonlocal unsafe_failure
            identity = parent_ids.get(id(test), test.id())
            outcomes.append({"id": identity, "outcome": outcome, "reason": str(reason)})
            if outcome in ("failed", "error", "unexpected_success"):
                failed.add(identity)
                if id(test) not in parent_ids or isinstance(test, unittest.loader._FailedTest):
                    unsafe_failure = True

        def addSuccess(self, test):
            self.record(test, "passed")
            super().addSuccess(test)

        def addFailure(self, test, err):
            self.record(test, "failed")
            super().addFailure(test, err)

        def addError(self, test, err):
            self.record(test, "error")
            super().addError(test, err)

        def addSkip(self, test, reason):
            nonlocal skipped_started
            skipped_started += int(id(test) in parent_ids)
            self.record(test, "skipped", reason)
            super().addSkip(test, reason)

        def addExpectedFailure(self, test, err):
            self.record(test, "expected_failure")
            super().addExpectedFailure(test, err)

        def addUnexpectedSuccess(self, test):
            self.record(test, "unexpected_success")
            super().addUnexpectedSuccess(test)

        def addSubTest(self, test, subtest, err):
            if err is not None:
                self.record(test, "failed" if issubclass(err[0], test.failureException) else "error", str(subtest))
            super().addSubTest(test, subtest, err)

    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2 if args.verbose else 1, resultclass=Timed).run(
        discovered if args.serial else unittest.TestSuite(chosen))
    if args.times:
        _write_atomic(args.times, spent)
    if args.failed:
        _write_atomic(args.failed, [] if unsafe_failure else sorted(failed), "failed")
    if args.outcomes:
        _write_atomic(args.outcomes, {"outcomes": outcomes, "tests_run": result.testsRun, "started": started,
                                      "executed": len(started) - skipped_started}, "worker")
    if not result.wasSuccessful():
        return 1
    return 5 if result.testsRun == 0 and not result.skipped else 0


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



def _run(shard, args, top, env, spent=None, serial=False):
    home = Path(tempfile.mkdtemp(prefix="par-unittest-"))
    try:
        times, failed, outcomes = (home / name for name in ("times.json", "failed.json", "outcomes.json"))
        argv = [sys.executable, "-m", "aicore.util.par_unittest", "discover", "--worker",
                "-s", str(Path(args.start_directory).resolve()), "-p", args.pattern, "-t", str(top),
                "--times", str(times), "--failed", str(failed), "--outcomes", str(outcomes)]
        argv += (["--serial"] if serial else []) + (["-v"] if args.verbose else [])
        argv += [item for file, name in shard for item in ("--unit", f"{file}::{name}")]
        path = str(top) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        child_env = env if serial else worker_env(env, home)
        done = subprocess.run(argv, env=dict(child_env, PYTHONPATH=path, SKM_TEST_JOBS="1"),
                              capture_output=True, text=True)  # no-timeout: tests own their timeouts
        if spent is not None:
            spent.update(_read_times(times))
        done.failed_ids = _read(failed, "failed", [])
        packet = _read(outcomes, "worker", None)
        done.outcomes = packet["outcomes"] if packet else []
        done.tests_run = packet["tests_run"] if packet else None  # a crash gives no execution count
        done.started = packet["started"] if packet else []
        done.executed = packet["executed"] if packet else None
        done.spent = _read_times(times)
        return done
    finally:
        shutil.rmtree(home, ignore_errors=True)


def _case(test, start, top, context):
    file = Path(_file(test, start))
    try:
        relative = file.relative_to(top).as_posix()
    except ValueError:
        relative = file.name
    module = next((p.name for p in (top, *top.parents) if (p / "unit.json").is_file()), top.name)
    return {"key": f"{module}:{relative}:{test.id()}", "id": test.id(), "file": relative, "context": context}


def _merge_times(path, spent):
    import fcntl
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _write_atomic(path, dict(_read_times(path), **spent))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="par_unittest", description=__doc__)
    parser.add_argument("verb", choices=["discover"])
    parser.add_argument("-s", "--start-directory", default=".")
    parser.add_argument("-t", "--top-level-directory", default=None)
    parser.add_argument("-p", "--pattern", default="test*.py")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-j", "--jobs", type=int, default=0)
    parser.add_argument("--clash", choices=["warn", "fail"], default=None)
    for flag in ("worker", "serial"):
        parser.add_argument("--" + flag, action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--unit", action="append", default=[], help=argparse.SUPPRESS)
    for flag in ("times", "failed", "outcomes"):
        parser.add_argument("--" + flag, help=argparse.SUPPRESS)
    parser.add_argument("--report", default=os.environ.get("SKM_PAR_UNITTEST_REPORT"), help="write case inventory and attempts")
    args = parser.parse_args(argv)
    if args.worker:
        return _worker(args)
    env = dict(os.environ)  # imports made by discovery must never leak into workers
    start = Path(args.start_directory).resolve()
    top = Path(args.top_level_directory).resolve() if args.top_level_directory else start
    requested = args.jobs or int(env.get("SKM_TEST_JOBS") or min(8, os.cpu_count() or 1))
    jobs = max(1, requested)
    clash = args.clash or env.get("SKM_TEST_CLASH") or "warn"
    context = env.get("SKM_TEST_CONTEXT", "local")
    args.start_directory = str(start)
    args.top_level_directory = str(top)
    sys.path.insert(0, str(top))
    details, discovery = {}, {}
    units = _units(start, top, args.pattern, details, discovery)
    times_file = _times_file(start)
    seconds = _read_times(times_file)
    units = _split(units, details, seconds, jobs)
    for (_, name), tests in details.items():
        for test in tests:
            if (_file(test, start), test.id()) in units:
                seconds.setdefault(test.id(), seconds.get(name, float(len(tests))) / len(tests))
    serial = jobs == 1 or len(units) < 2 or discovery.get("custom", False)
    shards = [list(units)] if serial else _deal(units, min(jobs, len(units)), seconds)
    began, spent = time.monotonic(), {}
    with ThreadPoolExecutor(max_workers=len(shards)) as pool:
        done = list(pool.map(lambda shard: _run(shard, args, top, env, serial=serial), shards))
    for result in done:
        for name, elapsed in result.spent.items():
            spent[name] = spent.get(name, 0.0) + elapsed
    if times_file is not None and spent:
        try:
            _merge_times(times_file, spent)
        except OSError as exc:
            print(f"par_unittest: cannot save timings: {exc}", file=sys.stderr)
    attempts, failed, clashes = [], False, 0
    inventory = [_case(t, start, top, context) for tests in details.values() for t in tests]
    id_files = {t.id(): file for (file, _), tests in details.items() for t in tests}
    for shard, result in zip(shards, done):
        attempts.append({"retry": False, "exit": result.returncode, "units": [name for _, name in shard],
                         "outcomes": result.outcomes, "tests_run": result.tests_run,
                         "started": result.started, "executed": result.executed})
        if result.returncode and not serial:
            ids = result.failed_ids
            retry = [(id_files[identity], identity) for identity in ids] if ids and all(i in id_files for i in ids) else shard
            # Failed IDs are a diagnostic, not proof that the original cohort passes alone.
            # Re-discovery filters the whole shard in its original order and worker context.
            sys.stderr.write(result.stderr + result.stdout)
            for selection in [retry] + ([shard] if retry != shard else []):
                label = "whole shard" if selection == shard else str(len(ids))
                print(f"par_unittest: retry {label} failed test(s) alone", file=sys.stderr)
                alone = _run(selection, args, top, env)
                attempts.append({"retry": True, "exit": alone.returncode, "units": [name for _, name in selection],
                                  "outcomes": alone.outcomes, "tests_run": alone.tests_run,
                                  "started": alone.started, "executed": alone.executed})
                if alone.returncode or args.verbose:
                    sys.stderr.write(alone.stderr + alone.stdout)
                if alone.returncode:
                    break
            if alone.returncode == 0 and alone.tests_run is not None:
                clashes += 1
                print("par_unittest: CLASH: a shard failed in parallel but the whole shard passes alone: " +
                      ", ".join(name for _, name in shard), file=sys.stderr)
                failed |= clash == "fail"
            else:
                failed = True
        else:
            failed |= result.returncode != 0
            if result.returncode or args.verbose or serial:
                sys.stderr.write(result.stderr + result.stdout)
    outcomes = [o for attempt in attempts if not attempt["retry"] for o in attempt["outcomes"]]
    count = sum(result.tests_run for result in done if result.tests_run is not None)
    executed = sum(result.executed for result in done if result.executed is not None)
    skipped = sum(o["outcome"] == "skipped" for o in outcomes)
    empty = count == 0 and skipped == 0 and all(r.returncode == 5 and r.tests_run == 0 for r in done)
    print("-" * 70, file=sys.stderr)
    print(f"Ran {count} tests in {time.monotonic() - began:.3f}s\n", file=sys.stderr)
    counts = [("failures", sum(o["outcome"] == "failed" for o in outcomes)),
              ("errors", sum(o["outcome"] == "error" for o in outcomes)),
              ("unexpected successes", sum(o["outcome"] == "unexpected_success" for o in outcomes))] if failed else []
    counts.append(("skipped", skipped))
    extra = ", ".join(f"{name}={number}" for name, number in counts if number)
    print(("NO TESTS RAN" if empty else "FAILED" if failed else "OK") + (f" ({extra})" if extra else ""), file=sys.stderr)
    print(f"par_unittest: context={context} requested_jobs={requested} effective_jobs={len(shards)} "
          f"discovered={len(inventory)} executed={executed} skipped={skipped} retries={len(attempts)-len(done)} "
          f"invocations={len(attempts)} unknown_invocations={sum(a['tests_run'] is None for a in attempts)} "
          f"clashes={clashes}", file=sys.stderr)
    if args.report:
        report = {"context": context, "requested_jobs": requested, "effective_jobs": len(shards),
                  "inventory": inventory, "attempts": attempts, "elapsed_s": time.monotonic() - began}
        _write_atomic(args.report, report, "report")
    return 5 if empty else 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
