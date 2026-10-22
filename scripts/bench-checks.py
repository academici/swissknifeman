#!/usr/bin/env python3
"""Time a set of check commands on a base revision and on the current tree, in bounded before/after pairs.

    bench-checks.py --before REV [--out FILE] [--commands-file FILE] [--label TEXT] [--pairs N] [--warm]
                    [--timeout S] [--log-dir DIR]

``REV`` is checked out as a detached git worktree in ``$TMPDIR/skm-bench-<pid>`` (always removed in ``finally``); the
current tree is measured as it is, uncommitted changes included. The default workload is ONE command per side of each
pair, ``python3 scripts/affected-tests.py --run --tier all --no-cache`` (*cold*: no result reuse, the timing cache of the
shared git directory is the same for both sides). It already contains the orch, planner and validate suites, so they are
not run again; commands marked ``"diagnostic": true`` in ``--commands-file`` are opt-in, are timed and reported, and are
never part of the total ratio. ``--warm`` adds, after the cold command of a side, the same tier without ``--no-cache``
twice inside one ``SKM_CHECK_RUN``: *warm scheduling* (everything runs, receipts are written) and *warm reuse* (greens of
the first run are reused). Pairs alternate which side runs first; two pairs is the default and three the most.

Every side gets the same Python, the same ``SKM_TEST_JOBS`` and its own partner roots (``PLANNER_ROOT``, ``AICORE_ROOT``,
...); ``SKM_CHECK_*`` of the caller is removed. A non-zero exit of a measured command is recorded, never raised. For the
case/context census each timed command gets ``SKM_PAR_UNITTEST_REPORT=<dir>/report-{pid}.json``: every runner that
understands it writes its own file (``{pid}`` is the runner's process id); a side whose runner does not is reported as
not comparable instead of being guessed. Timings are elapsed wall time: compare the ratio, not the seconds, and read
``loadavg``. The document is ``urn:swissknifeman:hub:bench-checks:v1``; exit 2 is an error of the bench itself
(``BENCH_REV_INVALID``, ``BENCH_WORKTREE_FAILED``, ``BENCH_COMMANDS_INVALID``, ``BENCH_PAIRS_INVALID``).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from fractions import Fraction

HUB = Path(__file__).resolve().parents[1]  # the hub that owns this script, its schema and aicore
ROOT = HUB  # the tree measured as "after" (tests point it at a scratch repository)
SCHEMA_ID = "urn:swissknifeman:hub:bench-checks:v1"
SCHEMA_FILE = HUB / "configs" / "schemas" / "bench-checks.schema.json"
DEFAULT_OUT = ".swissknifeman/orch/reports/p2-bench.json"
TIER_ALL = "python3 scripts/affected-tests.py --run --tier all"
TARGET_RATIO = 2 / 3
CAP = 6  # workload executions of the default workload: two pairs (4) plus one observation per side (2)
MAX_PAIRS = 3
MODES = ("cold", "warm_scheduling", "warm_reuse")
SAMPLE = 20
# partner roots a command of a worktree needs: each tree gets its own, never the live checkout's
PARTNER_ROOTS = {"PLANNER_ROOT": "packages/planner", "SKM_ORCH_ROOT": "packages/orch", "SKM_SKILLER_ROOT": "packages/skiller",
                 "SKM_HARNESS_ROOT": "packages/harness", "AICORE_ROOT": "packages/aicore", "SKM_GUI_ROOT": "packages/gui",
                 "SKM_WORKSPACE_MODULE_ROOT": "packages/workspace"}


class BenchError(Exception):
    """An error of the bench itself (not of a measured command)."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_average() -> float:
    try:
        return round(os.getloadavg()[0], 2)
    except (OSError, AttributeError):
        return 0.0


def git(*argv: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *argv], cwd=cwd or ROOT, capture_output=True, text=True)


def resolve(rev: str) -> str:
    found = git("rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    if found.returncode != 0 or not found.stdout.strip():
        raise BenchError("BENCH_REV_INVALID", f"{rev!r} is not a commit of this repository")
    return found.stdout.strip()


def default_commands(warm: bool) -> list:
    commands = [{"id": "cold", "cmd": TIER_ALL + " --no-cache", "mode": "cold", "diagnostic": False}]
    if warm:
        commands += [{"id": "warm_scheduling", "cmd": TIER_ALL, "mode": "warm_scheduling", "diagnostic": False},
                     {"id": "warm_reuse", "cmd": TIER_ALL, "mode": "warm_reuse", "diagnostic": False}]
    return commands


def read_commands(path: str) -> list:
    """The workload of ``--commands-file``: a JSON list of command strings or of ``{cmd, id?, mode?, diagnostic?}``."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise BenchError("BENCH_COMMANDS_INVALID", f"{path}: {error}") from error
    if not isinstance(data, list) or not data:
        raise BenchError("BENCH_COMMANDS_INVALID", f"{path}: expected a non-empty JSON list")
    found = []
    for number, entry in enumerate(data, 1):
        entry = {"cmd": entry} if isinstance(entry, str) else entry
        if not isinstance(entry, dict) or not isinstance(entry.get("cmd"), str) or not entry["cmd"].strip():
            raise BenchError("BENCH_COMMANDS_INVALID", f"{path}: entry {number} needs a command string")
        mode = entry.get("mode", "cold")
        if mode not in MODES:
            raise BenchError("BENCH_COMMANDS_INVALID", f"{path}: entry {number} mode {mode!r} is not one of {MODES}")
        found.append({"id": str(entry.get("id") or f"c{number}"), "cmd": entry["cmd"], "mode": mode,
                      "diagnostic": bool(entry.get("diagnostic", False))})
    if len({entry["id"] for entry in found}) != len(found):
        raise BenchError("BENCH_COMMANDS_INVALID", f"{path}: command ids must be unique")
    return found


def tree_env(tree: Path, jobs: int, extra: dict) -> dict:
    """The environment of one side: no ``SKM_CHECK_*`` of the caller, the same jobs budget, partner roots of ``tree``."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("SKM_CHECK_")}
    for name, folder in PARTNER_ROOTS.items():
        if (tree / folder).is_dir():
            env[name] = str(tree / folder)
    if (tree / "packages/planner/scripts/plan.py").is_file():
        env["PLANNER_PLAN_PY"] = str(tree / "packages/planner/scripts/plan.py")
    env["SKM_TEST_JOBS"] = str(jobs)
    env.update(extra)
    return env


def run_command(cmd: str, tree: Path, env: dict, log: Path, timeout_s: int) -> tuple:
    """``(seconds, exit, timed_out)`` of ``bash -c cmd`` in ``tree``; its output goes to ``log``."""
    log.parent.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    timed_out = False
    with open(log, "wb") as out:
        process = subprocess.Popen(["bash", "-c", cmd], cwd=tree, env=env, stdout=out, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            code = process.wait(timeout=timeout_s or None)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            code = 124
    return round(time.monotonic() - began, 2), code, timed_out


def read_cases(folder: Path) -> tuple:
    """``(summary, keys)`` of the ``par_unittest`` reports in ``folder``. ``keys`` are ``context|key`` of every case.
    A file still named ``{pid}`` means the runner took the path literally (it cannot name its process): not comparable."""
    keys: set = set()
    contexts: dict = {}
    files = inventory = executed = skipped = retries = invocations = 0
    literal = False
    for file in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        if "{pid}" in file.name:
            literal = True
            continue
        try:
            doc = json.loads(file.read_text(encoding="utf-8"))
            rows = doc["inventory"]
            attempts = doc["attempts"]
            context = str(doc["context"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        files += 1
        inventory += len(rows)
        for row in rows:
            keys.add(f"{row.get('context', context)}|{row.get('key')}")
            contexts[row.get("context", context)] = contexts.get(row.get("context", context), 0) + 1
        invocations += len(attempts)
        retries += sum(1 for attempt in attempts if attempt.get("retry"))
        for attempt in attempts:
            executed += attempt.get("executed") or 0
            skipped += sum(1 for outcome in attempt.get("outcomes", []) if outcome.get("outcome") == "skipped")
    summary = {"available": files > 0 and not literal, "files": files, "inventory": inventory, "unique": len(keys),
               "digest": hashlib.sha256("\n".join(sorted(keys)).encode("utf-8")).hexdigest() if keys else "",
               "contexts": dict(sorted(contexts.items())), "executed": executed, "skipped": skipped, "retries": retries,
               "invocations": invocations}
    if not summary["available"]:
        summary["reason"] = ("the runner took the {pid} report path literally (it predates the placeholder)" if literal
                             else "no runner wrote a case report")
    return summary, keys


def workload(cmd: str, tree: Path, env: dict) -> list:
    """The logical commands ``cmd`` stands for: what ``affected-tests.py --json`` lists (not run), else the command."""
    if "affected-tests.py" not in cmd or "--run" not in cmd:
        return [cmd]
    dry = " ".join(part for part in cmd.split() if part not in ("--run", "--no-cache", "--json")) + " --json"
    found = subprocess.run(["bash", "-c", dry], cwd=tree, env=env, capture_output=True, text=True)
    try:
        commands = json.loads(found.stdout)["commands"]
        return sorted(f"{row.get('folder')}: {' '.join(row.get('argv', []))}" for row in commands)
    except (ValueError, KeyError, TypeError, AttributeError):
        return [cmd]


def mean(values: list) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def summarize(rev: str, results: list, commands: list, side: str) -> dict:
    out = []
    for command in commands:
        mine = [row for row in results if row["side"] == side and row["id"] == command["id"]]
        out.append({"id": command["id"], "cmd": command["cmd"], "mode": command["mode"],
                    "diagnostic": command["diagnostic"], "seconds": mean([row["seconds"] for row in mine]),
                    "exit": max([row["exit"] for row in mine], default=0), "runs": [row["seconds"] for row in mine],
                    "exits": [row["exit"] for row in mine]})
    return {"rev": rev, "commands": out}


def compare_cases(commands: list, cases: dict) -> dict:
    """Per command id: whether the case census of the first pair is comparable and equal between the sides."""
    out = {}
    for command in commands:
        before, after = cases.get(("before", command["id"])), cases.get(("after", command["id"]))
        entry = {"comparable": False, "equal": None, "before_unique": None, "after_unique": None,
                 "only_before": 0, "only_after": 0, "sample": []}
        if before is None or after is None:
            entry["reason"] = "a side did not run this command"
        elif not before[0]["available"] or not after[0]["available"]:
            entry["reason"] = "; ".join(f"{side}: {summary['reason']}" for side, (summary, _keys) in
                                        (("before", before), ("after", after)) if not summary["available"])
        else:
            gone, new = sorted(before[1] - after[1]), sorted(after[1] - before[1])
            entry.update(comparable=True, equal=not gone and not new, before_unique=before[0]["unique"],
                         after_unique=after[0]["unique"], only_before=len(gone), only_after=len(new),
                         sample=[f"-{key}" for key in gone[:SAMPLE // 2]] + [f"+{key}" for key in new[:SAMPLE // 2]])
        out[command["id"]] = entry
    return out


def _census_lib():
    spec = importlib.util.spec_from_file_location("bench_census", HUB / "scripts" / "bench-census.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TimingCache:
    """The timing/green cache of ``affected-tests`` (in the shared git directory): snapshot it once, put the same bytes back
    before every timing leg (``--no-cache`` stops result reuse but not the scheduling history) and restore the owner's state
    at the end. Files that did not exist at the snapshot are removed again; nothing else is deleted."""
    NAMES = ("durations.json", "green.json")

    def __init__(self):
        found = git("rev-parse", "--path-format=absolute", "--git-common-dir")
        self.dir = Path(found.stdout.strip()) / "affected-tests" if found.returncode == 0 and found.stdout.strip() else None
        self.saved = {}
        if self.dir is not None:
            for name in self.NAMES:
                try:
                    self.saved[name] = (self.dir / name).read_bytes()
                except OSError:
                    pass

    def digest(self) -> str:
        return hashlib.sha256(b"".join(name.encode() + b"\0" + self.saved[name] for name in sorted(self.saved))).hexdigest()

    def restore(self) -> None:
        if self.dir is None:
            return
        for name in self.NAMES:
            target = self.dir / name
            if name in self.saved:
                self.dir.mkdir(parents=True, exist_ok=True)
                handle, temporary = tempfile.mkstemp(prefix=name + ".", dir=str(self.dir))
                with os.fdopen(handle, "wb") as stream:
                    stream.write(self.saved[name])
                os.replace(temporary, target)
            elif target.exists():
                target.unlink()

    def document(self) -> dict:
        return {"dir": str(self.dir) if self.dir else "", "files": sorted(self.saved), "digest": self.digest(),
                "restored_before_each_leg": True}


def source_identity(tree: Path) -> dict:
    """What the tree's sources are: HEAD plus a digest of tracked changes and untracked, non-ignored files."""
    head = git("rev-parse", "HEAD", cwd=tree).stdout.strip()
    digest = hashlib.sha256(git("diff", "HEAD", cwd=tree).stdout.encode("utf-8", "replace"))
    names = git("ls-files", "--others", "--exclude-standard", cwd=tree).stdout.split("\n")
    for name in sorted(filter(None, names)):
        try:
            digest.update(name.encode() + b"\0" + (tree / name).read_bytes())
        except OSError:
            digest.update(name.encode() + b"\0-")
    return {"head": head, "dirty_digest": digest.hexdigest()}


CONTROL = {
    "tests/test_a.py": "import unittest\n\nclass A(unittest.TestCase):\n    def test_pass(self):\n        self.assertTrue(True)\n"
                       "    @unittest.skip('why not')\n    def test_skip(self):\n        pass\n"
                       "    def test_sub(self):\n        for n in (1, 2):\n            with self.subTest(n=n):\n"
                       "                self.assertTrue(n)\n",
    "tests/test_b.py": "import unittest\n\nclass B(unittest.TestCase):\n    @unittest.expectedFailure\n"
                       "    def test_xfail(self):\n        self.fail('expected')\n    def test_pass(self):\n        pass\n",
}
CONTROL_CASES = 5  # A.test_pass, A.test_skip, A.test_sub, B.test_xfail, B.test_pass


def _control_suite(folder: Path, extra: dict | None = None) -> None:
    (folder / "tests").mkdir(parents=True, exist_ok=True)
    (folder / "tests" / "__init__.py").write_text("")
    for name, text in {**CONTROL, **(extra or {})}.items():
        (folder / name).write_text(text)


def _unittest_shape(done) -> list:
    return [line for line in done.stderr.splitlines() if line.startswith(("Ran ", "OK", "FAILED"))]


def preflight(trees: dict, jobs: int, work: Path) -> dict:
    """Tiny, workload-free proof that the observer sees real execution before any full observation is admitted: plain driver
    transparency, a replaced ``PYTHONPATH`` through ``test.sh``-style invocation, a child started with ``sys.executable``,
    outcomes of skips, subtests, expected failures and an import failure, the multi-worker ``par_unittest`` driver of EACH
    tree (``--worker`` processes, two modules) and a lossless surrogate checkpoint. ``ok`` is true only when every check holds;
    an unavailable ``par_unittest`` in a tree is recorded as ``null`` and does not fail the proof."""
    lib = _census_lib()
    work = Path(os.path.abspath(str(work)))  # children run in other directories: nothing relative may reach them
    env0 = tree_env(ROOT, jobs, {})
    python = subprocess.run(["bash", "-c", "command -v python3"], env=env0, capture_output=True, text=True).stdout.strip()
    python = os.path.realpath(python) if python else sys.executable
    base = work / "userbase"
    provenance = lib.install_observer(base, env0)
    shim = lib.install_shim(work / "shim", python)
    checks, details = {}, {}
    tiny = work / "tiny"
    _control_suite(tiny)
    discover = ["python3", "-m", "unittest", "discover", "-s", "tests", "-t", "."]
    plain = subprocess.run(discover, cwd=tiny, env=env0, capture_output=True, text=True, timeout=120)
    ledger = work / "ledger-plain"
    seen = subprocess.run(discover, cwd=tiny, env=lib.census_env(env0, base, ledger, tiny, shim), capture_output=True,
                          text=True, timeout=120)
    summary = lib.read_ledger(ledger, tiny)
    details["plain"] = {"plain": _unittest_shape(plain), "observed": _unittest_shape(seen), "outcomes": summary["outcomes"],
                        "skips": summary["skips"], "executions": summary["executions"], "subtest_failures": summary["subtest_failures"]}
    checks["transparent"] = bool(_unittest_shape(plain) == _unittest_shape(seen) and plain.returncode == seen.returncode)
    checks["outcomes"] = bool(summary["executions"] == CONTROL_CASES and summary["skips"] == {"why not": 1}
                              and summary["outcomes"].get("expected_failure") == 1 and summary["outcomes"].get("passed") == 3)
    ledger = work / "ledger-pythonpath"
    done = subprocess.run(["bash", "-c", "PYTHONPATH=lib:/nonexistent python3 -m unittest discover -s tests -t ."], cwd=tiny,
                          env=lib.census_env(env0, base, ledger, tiny, shim), capture_output=True, text=True, timeout=120)
    found = lib.read_ledger(ledger, tiny)
    checks["replaced_pythonpath"] = bool(done.returncode == 0 and found["executions"] == CONTROL_CASES)
    child = work / "child"
    _control_suite(child, {"tests/test_child.py": "import unittest\n\nclass C(unittest.TestCase):\n    def test_c(self):\n        pass\n"})
    child_driver = ("import os, subprocess, sys, unittest\n\nclass P(unittest.TestCase):\n    def test_spawn(self):\n"
                    "        done = subprocess.run([sys.executable, '-m', 'unittest', 'tests.test_child'], env=dict(os.environ, PYTHONPATH='/nonexistent'),"
                    " capture_output=True, text=True)\n        self.assertEqual(0, done.returncode, done.stderr)\n")
    (child / "tests" / "test_parent.py").write_text(child_driver)
    ledger = work / "ledger-child"
    done = subprocess.run(["python3", "-m", "unittest", "tests.test_parent"], cwd=child,
                          env=lib.census_env(env0, base, ledger, child, shim), capture_output=True, text=True, timeout=120)
    found = lib.read_ledger(ledger, child)
    names = sorted(key.rsplit("|", 1)[1] for _c, key in found["_keys"])
    checks["sys_executable_child"] = bool(done.returncode == 0 and "test_c" in names and "test_spawn" in names)
    details["child"] = {"activations": found["activations"], "tests": names}
    broken = work / "broken"
    _control_suite(broken, {"tests/test_import.py": "import not_a_real_module_xyz\n"})
    ledger = work / "ledger-broken"
    done = subprocess.run(discover, cwd=broken, env=lib.census_env(env0, base, ledger, broken, shim), capture_output=True,
                          text=True, timeout=120)
    found = lib.read_ledger(ledger, broken)
    checks["import_failure_is_an_error_outcome"] = bool(done.returncode != 0 and found["outcomes"].get("error", 0) >= 1)
    drivers = {}
    for side, tree in trees.items():
        aicore = tree / "packages" / "aicore" / "lib"
        ledger = work / f"ledger-par-{side}"
        env = lib.census_env(tree_env(tree, jobs, {"PYTHONPATH": str(aicore)}), base, ledger, tiny, shim)
        done = subprocess.run(["python3", "-m", "aicore.util.par_unittest", "discover", "-s", "tests", "-t", ".", "-j", "2"],
                              cwd=tiny, env=env, capture_output=True, text=True, timeout=180)
        found = lib.read_ledger(ledger, tiny)
        workers = [row for row in found["processes"].values() if "--worker" in row.get("argv", [])]
        modules = sorted({key.split("|")[1] for _c, key in found["_keys"]})
        if "No module named" in done.stderr:
            drivers[side] = None
        else:
            drivers[side] = bool(done.returncode == 0 and found["executions"] == CONTROL_CASES and workers and len(modules) >= 2)
        details[f"par_unittest_{side}"] = {"workers": len(workers), "modules": modules, "executions": found["executions"]}
    checks["par_unittest"] = drivers
    sample = "caf\udcff/te\udcfest.py"
    probe = work / "surrogate.json"
    write_atomic(probe, {"path": sample})
    checks["lossless_checkpoint"] = json.loads(probe.read_text(encoding="utf-8"))["path"] == sample
    ok = all(value for key, value in checks.items() if key != "par_unittest") and all(value is not False for value in drivers.values())
    return {"ok": bool(ok), "checks": checks, "details": details, "observer": provenance, "shim": shim, "python": python}


def observe_side(side: str, tree: Path, cmd: str, jobs: int, timeout_s: int, ledger: Path, log_dir: Path, probe: dict) -> dict:
    """One observed run of the workload on one tree: its raw ledger stays in ``ledger`` (never cleaned up)."""
    lib = _census_lib()
    ledger, log_dir = Path(os.path.abspath(str(ledger))), Path(os.path.abspath(str(log_dir)))
    env = lib.census_env(tree_env(tree, jobs, {}), Path(probe["observer"]["user_site"]).parents[2], ledger, tree, probe["shim"])
    seconds, code, timed_out = run_command(cmd, tree, env, log_dir / f"census-{side}.log", timeout_s)
    print(f"[bench] census {side} {cmd} {seconds} s exit {code} (observation, excluded from timings)", file=sys.stderr, flush=True)
    return {"exit": code, "timed_out": timed_out, "seconds_excluded": seconds, "ledger": str(ledger)}


def expected_units(cmd: str, jobs: int) -> list:
    return sorted({line.split(": ", 1)[0] for line in workload(cmd, ROOT, tree_env(ROOT, jobs, {}))
                   if ": " in line and "scripts/test.sh" in line and not line.startswith("hub")})


def census_document(rev: str, cmd: str, before_tree: Path, exits: dict, probe: dict, expected: list, sides: tuple) -> dict:
    """The comparison of the retained ledgers (recomputable at any time from the raw files)."""
    lib = _census_lib()
    trees = {"before": before_tree, "after": ROOT}
    summaries = {side: lib.read_ledger(Path(exits[side]["ledger"]), trees[side]) for side in sides}
    problems = []
    if not probe.get("ok", False):
        problems.append("the observer preflight did not hold")
    for side in sides:
        if exits[side]["exit"] != 0:
            problems.append(f"the {side} observation workload exited {exits[side]['exit']}")
    if len(sides) < 2:
        missing = [side for side in ("before", "after") if side not in sides]
        problems.append("no observation of the " + " and ".join(missing) + " side")
        empty = {"activations": 0, "processes": {}, "executions": 0, "unique": 0, "duplicates": 0, "outcomes": {}, "skips": {},
                 "units": {}, "contexts": {}, "subtest_failures": 0, "unmatched_starts": 0, "unreadable_lines": 0,
                 "digest": "", "_keys": set(), "_rows": []}
        summaries.update({side: empty for side in ("before", "after") if side not in sides})
    document = lib.compare(summaries["before"], summaries["after"], ROOT, rev, ROOT, expected)
    if problems:
        document["conserved"] = None
    document.update(status="observed" if not problems else "unproven", problems=problems, command=cmd, exits=exits,
                    workload_executions=len(sides), observer=probe.get("observer"), preflight=probe,
                    transparency={"ok": probe.get("checks", {}).get("transparent")},
                    propagation=probe.get("checks", {}).get("par_unittest"), expected_units=expected,
                    ledger_dir=str(Path(exits[sides[0]]["ledger"]).parent) if sides else "")
    return document


def observe(before_tree: Path, rev: str, cmd: str, jobs: int, timeout_s: int, work: Path, log_dir: Path) -> dict:
    """The execution census of ``cmd`` on the base and on the current tree: preflight, then one observed run per side (their
    timings are excluded from every ratio). Raw ledgers stay in ``work`` so the aggregation can be recomputed."""
    work.mkdir(parents=True, exist_ok=True)
    probe = preflight({"before": before_tree, "after": ROOT}, jobs, work)
    write_atomic(work / "preflight.json", probe)
    exits = {}
    if probe["ok"]:
        for side, tree in (("before", before_tree), ("after", ROOT)):
            exits[side] = observe_side(side, tree, cmd, jobs, timeout_s, work / f"ledger-{side}", log_dir, probe)
    sides = tuple(exits)
    return census_document(rev, cmd, before_tree, exits, probe, expected_units(cmd, jobs), sides) if sides else {
        "status": "unproven", "conserved": None, "problems": ["the observer preflight did not hold"], "command": cmd, "exits": {},
        "workload_executions": 0, "preflight": probe, "before": {}, "after": {}, "ledger_dir": str(work)}


def measure(before_tree: Path, commands: list, *, pairs: int, jobs: int, timeout_s: int, log_dir: Path,
            cache: "TimingCache | None" = None) -> dict:
    trees = {"before": before_tree, "after": ROOT}
    results, pair_rows, cases = [], [], {}
    census = Path(tempfile.mkdtemp(prefix=f"skm-bench-cases-{os.getpid()}-"))
    try:
        for number in range(1, pairs + 1):
            order = ["before", "after"] if number % 2 else ["after", "before"]
            started, rows = load_average(), []
            for side in order:
                for command in commands:
                    run_id = f"bench-{os.getpid()}-{side}-{number}"
                    extra = {} if command["mode"] == "cold" else {"SKM_CHECK_RUN": run_id}
                    report_dir = census / f"{side}-{number}-{command['id']}"
                    extra["SKM_PAR_UNITTEST_REPORT"] = str(report_dir / "report-{pid}.json")
                    env = tree_env(trees[side], jobs, extra)
                    log = log_dir / f"{side}-{number}-{command['id']}.log"
                    if cache is not None and command["mode"] == "cold":
                        cache.restore()  # the same scheduling history before every cold leg
                    seconds, code, timed_out = run_command(command["cmd"], trees[side], env, log, timeout_s)
                    print(f"[bench] {side} {command['cmd']} {seconds} s exit {code}", file=sys.stderr, flush=True)
                    summary, keys = read_cases(report_dir)
                    if number == 1:
                        cases[(side, command["id"])] = (summary, keys)
                    row = {"side": side, "id": command["id"], "cmd": command["cmd"], "mode": command["mode"],
                           "seconds": seconds, "exit": code, "timed_out": timed_out, "log": str(log), "cases": summary}
                    rows.append(row)
                    results.append(row)
            pair_rows.append({"n": number, "order": order, "loadavg": [started, load_average()], "results": rows})
    finally:
        shutil.rmtree(census, ignore_errors=True)
    return {"results": results, "pairs": pair_rows, "cases": cases}


def compose(args, rev: str, commands: list, measured: dict, before_tree: Path | None, loadavg: list, jobs: int,
            extra: dict | None = None, workloads: dict | None = None) -> dict:
    results = measured["results"]
    before = summarize(rev, results, commands, "before")
    after = summarize("worktree", results, commands, "after")
    ratio = {}
    for old, new in zip(before["commands"], after["commands"]):
        ratio[old["id"]] = round(new["seconds"] / old["seconds"], 3) if old["seconds"] else None
    counted = [(old, new) for old, new in zip(before["commands"], after["commands"])
               if old["mode"] == "cold" and not old["diagnostic"]]
    total_before = round(sum(old["seconds"] for old, _new in counted), 2)
    total_after = round(sum(new["seconds"] for _old, new in counted), 2)
    total = round(total_after / total_before, 3) if total_before else None
    failed = sum(1 for row in results if row["exit"] != 0)
    env = tree_env(ROOT, jobs, {})
    if workloads is None:
        workloads = {side: sorted({item for command in commands for item in workload(command["cmd"], tree, tree_env(tree, jobs, {}))})
                     for side, tree in (("before", before_tree), ("after", ROOT))}
    gone, new = sorted(set(workloads["before"]) - set(workloads["after"])), sorted(set(workloads["after"]) - set(workloads["before"]))
    python = None
    if failed:
        note = f"{failed} measured run(s) exited non-zero (recorded, not an error of the bench): no timing verdict"
    elif not counted:
        note = "no cold non-diagnostic command: no total"
    elif total is None:
        note = "the cold commands took no measurable time: no total"
    elif not (not gone and not new):
        note = "the logical workload differs between the sides: the ratio is not comparable"
    else:
        note = "timings are valid"
    python = subprocess.run(["bash", "-c", "python3 -c 'import platform;print(platform.python_version())'"], env=env,
                            capture_output=True, text=True).stdout.strip() or sys.version.split()[0]
    doc = {"$schema": SCHEMA_ID, "label": args.label, "at": utc(), "cpu_count": os.cpu_count() or 1, "jobs": jobs,
            "python": python, "loadavg": loadavg, "target_ratio": round(TARGET_RATIO, 4), "pairs_run": len(measured["pairs"]),
            "before": before, "after": after, "ratio": ratio,
            "total": {"before_s": total_before, "after_s": total_after, "ratio": total,
                      "counted": [old["id"] for old, _new in counted]},
            "pairs": measured["pairs"],
            "coverage": {"workload": {"before": workloads["before"], "after": workloads["after"],
                                      "equal": not gone and not new, "only_before": gone[:SAMPLE], "only_after": new[:SAMPLE]},
                         "cases": compare_cases(commands, measured["cases"])},
            "result": {"target_met": None, "failed_runs": failed, "note": note}}
    doc.update(extra or {})
    census = doc.get("census")
    met = _census_lib().decide(doc)
    doc["result"]["target_met"] = met
    if met is True:
        doc["result"]["note"] = "target wall <= 2/3 met on valid, comparable timings with a conserved execution census"
    elif met is False:
        doc["result"]["note"] = "target wall <= 2/3 NOT met on valid, comparable timings: read the per-command ratios and the load"
    elif total is not None and not failed and total_before and Fraction(str(total_after)) / Fraction(str(total_before)) <= Fraction(2, 3):
        doc["result"]["note"] = ("the ratio is within 2/3 but the execution census is " +
                                 ("not requested" if census is None else "not conserved or unknown") +
                                 ": closure is unproven, the ratio is only a diagnostic")
    return doc


def validate(doc: dict) -> list:
    """The schema problems of ``doc`` (aicore's validator, same as the other hub documents)."""
    sys.path.insert(0, str(HUB / "packages" / "aicore" / "lib"))
    from aicore.util.jsonschema_core import validate_node
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    return [issue.message for issue in validate_node(None, schema, schema["$id"], doc)]


def write_atomic(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(doc, stream, ensure_ascii=True, indent=2)  # lossless for undecodable path bytes
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


# ---- explicit recovery (item.rules[25]): reuse the four timing legs, at most two NEW observation workloads ----
RECOVERY_CAP = 2
_SECONDS = ("seconds", "wall_s", "elapsed_s", "duration_s")
_EXITS = ("exit", "exit_code", "returncode")
_SHA = __import__("re").compile(r"^[0-9a-f]{40}$")


def _walk(value):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def normalize_evidence(raw: dict) -> dict:
    """What recovery needs from the operator's timing evidence, found by shape (the file is the operator's, not ours): the
    timing legs per side (seconds + exit), the base revision, Python, jobs, the source identity of the timed candidate and an
    optional ``relevant_inputs`` map ``{path: sha256}``. Anything absent is ``None``: unknown, never invented."""
    legs = {"before": [], "after": []}
    skip = set()  # the exit lists next to a timing list are not timings
    for node in _walk(raw):
        if not isinstance(node, dict) or id(node) in skip:
            continue
        if isinstance(node.get("exits"), dict):
            skip.add(id(node["exits"]))
        side = node.get("side") or node.get("tree")
        seconds = next((node[key] for key in _SECONDS if isinstance(node.get(key), (int, float)) and not isinstance(node.get(key), bool)), None)
        code = next((node[key] for key in _EXITS if isinstance(node.get(key), int) and not isinstance(node.get(key), bool)), None)
        if side in legs and seconds is not None and code is not None:
            legs[side].append({"seconds": float(seconds), "exit": code})
        elif all(isinstance(node.get(side), list) and node[side] and all(isinstance(v, (int, float)) for v in node[side])
                 for side in ("before", "after")):
            exits = node.get("exits") if isinstance(node.get("exits"), dict) else {}
            for name in legs:
                codes = exits.get(name) if isinstance(exits.get(name), list) else [None] * len(node[name])
                legs[name] += [{"seconds": float(v), "exit": c} for v, c in zip(node[name], codes)]

    def first(keys, test=lambda v: True):
        for node in _walk(raw):
            if isinstance(node, dict):
                for key in keys:
                    if key in node and test(node[key]):
                        return node[key]
        return None
    source = next((node for node in _walk(raw) if isinstance(node, dict) and "dirty_digest" in node and "head" in node), None)
    inputs = first(("relevant_inputs",), lambda v: isinstance(v, dict) and v and all(isinstance(k, str) and isinstance(x, str)
                                                                                      for k, x in v.items()))
    jobs = first(("jobs", "skm_test_jobs"), lambda v: isinstance(v, int) and not isinstance(v, bool))
    return {"legs": legs, "rev": first(("baseline", "baseline_sha", "before_rev", "base_rev", "rev"),
                                       lambda v: isinstance(v, str) and bool(_SHA.match(v))),
            "python": first(("python", "python_version"), lambda v: isinstance(v, str)), "jobs": jobs,
            "source": {"head": source["head"], "dirty_digest": source["dirty_digest"]} if source else None,
            "relevant_inputs": inputs}


def load_evidence(path: str) -> tuple:
    file = Path(path)
    try:
        data = file.read_bytes()
        raw = json.loads(data.decode("utf-8"))
    except (OSError, ValueError) as error:
        raise BenchError("BENCH_RECOVERY_EVIDENCE_INVALID", f"{path}: {error}") from error
    found = normalize_evidence(raw)
    legs = found["legs"]
    if not legs["before"] or len(legs["before"]) != len(legs["after"]) or any(
            leg["exit"] is None for side in legs.values() for leg in side):
        raise BenchError("BENCH_RECOVERY_EVIDENCE_INVALID",
                         f"{path}: expected the same number (>0) of timing legs with seconds and exit on both sides, found "
                         f"{len(legs['before'])} before / {len(legs['after'])} after")
    return found, hashlib.sha256(data).hexdigest()


def reuse_checks(found: dict, rev: str, python: str, jobs: int, workloads: dict) -> dict:
    """Is the recorded timing still the timing of this workload, Python, jobs and source? ``None`` is unknown."""
    after_now = source_identity(ROOT)
    checks = {"baseline_rev": None if found["rev"] is None else found["rev"] == rev,
              "python": None if found["python"] is None else found["python"] == python,
              "jobs": None if found["jobs"] is None else found["jobs"] == jobs,
              "workload_equal": workloads["before"] == workloads["after"], "legs_successful": all(
                  leg["exit"] == 0 for side in found["legs"].values() for leg in side)}
    if found["relevant_inputs"] is not None:
        changed = []
        for name, digest in found["relevant_inputs"].items():
            try:
                now = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            except OSError:
                now = None
            if now != digest:
                changed.append(name)
        checks["relevant_inputs_unchanged"] = not changed
        checks["relevant_inputs_changed"] = changed[:20]
    elif found["source"] is not None:
        checks["relevant_inputs_unchanged"] = found["source"] == after_now
    else:
        checks["relevant_inputs_unchanged"] = None
    return checks


def _state_file(directory: Path) -> Path:
    return directory / "attempts.json"


def load_state(directory: Path) -> dict:
    try:
        state = json.loads(_state_file(directory).read_text(encoding="utf-8"))
        if isinstance(state, dict) and isinstance(state.get("attempts"), list):
            return state
    except (OSError, ValueError):
        pass
    return {"cap": RECOVERY_CAP, "attempts": [], "stopped": None, "preflight": None, "workload": None}


def save_state(directory: Path, state: dict) -> None:
    write_atomic(_state_file(directory), state)  # durable before the next workload starts


def recover(args) -> int:
    """``--recovery-evidence``: reuse the recorded timing legs and take at most two NEW observation workloads (before, then
    after), only after a workload-free preflight, never a timed run. The attempt count lives in ``attempts.json`` beside the
    output and survives corrections: a later invocation recomputes from the retained raw ledgers and runs nothing."""
    out = Path(os.path.abspath(args.out))
    directory = out.with_name(out.stem + ".recovery")
    log_dir = Path(os.path.abspath(args.log_dir)) if args.log_dir else directory / "logs"
    worktree = Path(tempfile.gettempdir()) / f"skm-bench-{os.getpid()}"
    created = False
    try:
        found, evidence_sha = load_evidence(args.recovery_evidence)
        rev = resolve(args.before)
        cmd = args.recovery_command or default_commands(False)[0]["cmd"]
        jobs = found["jobs"] or max(1, int(os.environ.get("SKM_TEST_JOBS", os.cpu_count() or 2)))
        state = load_state(directory)
        started_before = len(state["attempts"])
        spent = len(state["attempts"])
        finished = {a["side"] for a in state["attempts"] if a.get("status") in ("complete", "incomplete")}
        if not spent and str(state.get("stopped") or "").startswith("the observer preflight"):
            # no workload was ever admitted: the tiny preflight may run again after a fix; the failed receipt is kept
            state.setdefault("preflight_history", []).append({"at": utc(), "stopped": state["stopped"],
                                                              "preflight": state.get("preflight")})
            state["stopped"] = None
        artifact_only = bool(state.get("stopped") or spent >= RECOVERY_CAP or {"before", "after"} <= finished)
        before_tree = None
        if not artifact_only or state.get("workload") is None:
            added = git("worktree", "add", "--detach", str(worktree), rev)
            created = added.returncode == 0 or worktree.exists()
            if added.returncode != 0:
                raise BenchError("BENCH_WORKTREE_FAILED", (added.stderr or added.stdout).strip())
            before_tree = worktree
            state["before_root"] = str(worktree)  # the root the ledgers' paths are relative to, for a later recomputation
            state["workload"] = {side: sorted(workload(cmd, tree, tree_env(tree, jobs, {})))
                                 for side, tree in (("before", before_tree), ("after", ROOT))}
            state["expected"] = expected_units(cmd, jobs)
        probe = state.get("preflight") or {"ok": False, "checks": {}}
        if not artifact_only:
            tries = len(state.get("preflight_history", []))  # a rerun never appends to the ledgers of a failed earlier try
            probe = preflight({"before": before_tree, "after": ROOT}, jobs,
                              directory / ("preflight-work" if not tries else f"preflight-work-{tries}"))
            state["preflight"] = probe
            save_state(directory, state)
            if probe["ok"]:
                for side, tree in (("before", before_tree), ("after", ROOT)):
                    if side in finished:
                        continue
                    if spent >= RECOVERY_CAP:
                        break
                    state["attempts"].append({"n": spent + 1, "side": side, "status": "started", "at": utc()})
                    spent += 1
                    save_state(directory, state)  # counted before it runs: a crash cannot buy a free retry
                    run = observe_side(side, tree, cmd, jobs, args.timeout, directory / f"ledger-{side}", log_dir, probe)
                    lib = _census_lib()
                    why = lib.complete(lib.read_ledger(Path(run["ledger"]), tree), state["expected"], run["exit"])
                    state["attempts"][-1].update(status="incomplete" if why else "complete", exit=run["exit"], why=why, **{
                        "seconds_excluded": run["seconds_excluded"], "ledger": run["ledger"]})
                    if why:
                        state["stopped"] = f"the {side} observation is incomplete: " + "; ".join(why)
                        save_state(directory, state)
                        break
                    save_state(directory, state)
            else:
                state["stopped"] = "the observer preflight did not hold: " + ", ".join(
                    k for k, v in probe["checks"].items() if v is False or (isinstance(v, dict) and False in v.values()))
                save_state(directory, state)
        exits = {a["side"]: {"exit": a.get("exit"), "timed_out": False, "seconds_excluded": a.get("seconds_excluded"),
                             "ledger": a.get("ledger")} for a in state["attempts"] if a.get("ledger")}
        sides = tuple(side for side in ("before", "after") if side in exits)
        trees = {"before": Path(state.get("before_root") or worktree), "after": ROOT}
        census = (census_document(rev, cmd, trees["before"], exits, probe, state.get("expected", []), sides)
                  if sides else {"status": "unproven", "conserved": None, "workload_executions": 0, "exits": {}, "before": {},
                                 "after": {}, "problems": [state.get("stopped") or "no observation was admitted"],
                                 "preflight": probe, "command": cmd, "ledger_dir": str(directory)})
        census["attempts"] = state["attempts"]
        census["stopped"] = state.get("stopped")
        census["cap"] = RECOVERY_CAP
        census["new_workloads_this_invocation"] = len(state["attempts"]) - started_before
        current_python = subprocess.run(["bash", "-c", "python3 -c 'import platform;print(platform.python_version())'"],
                                        env=tree_env(ROOT, jobs, {}), capture_output=True, text=True).stdout.strip()
        checks = reuse_checks(found, rev, current_python, jobs, state["workload"])
        verdicts = [v for k, v in checks.items() if k in ("baseline_rev", "python", "jobs", "workload_equal", "legs_successful",
                                                           "relevant_inputs_unchanged")]
        valid = False if any(v is False for v in verdicts) else (True if all(v is True for v in verdicts) else None)
        rows, pairs = [], []
        for number in range(len(found["legs"]["before"])):
            order = ["before", "after"] if number % 2 == 0 else ["after", "before"]
            result = []
            for side in order:
                leg = found["legs"][side][number]
                result.append({"side": side, "id": "cold", "cmd": cmd, "mode": "cold", "seconds": round(leg["seconds"], 2),
                               "exit": leg["exit"], "timed_out": False, "log": "", "cases": {
                                   "available": False, "files": 0, "inventory": 0, "unique": 0, "digest": "", "contexts": {},
                                   "executed": 0, "skipped": 0, "retries": 0, "invocations": 0,
                                   "reason": "recovered timing leg: no per-leg case report"}})
            rows += result
            pairs.append({"n": number + 1, "order": order, "loadavg": [], "results": result})
        commands = [{"id": "cold", "cmd": cmd, "mode": "cold", "diagnostic": False}]
        measured = {"results": rows, "pairs": pairs, "cases": {}}
        extra = {"census": census, "sources": {"before": {"head": rev, "dirty_digest": ""}, "after": source_identity(ROOT),
                                               "stable": checks.get("relevant_inputs_unchanged") is not False},
                 "budget": {"timing_executions": 0, "observation_executions": len(state["attempts"]), "cap": RECOVERY_CAP,
                            "total": len(state["attempts"])},
                 "timing_source": {"kind": "recovered", "evidence": str(args.recovery_evidence), "sha256": evidence_sha,
                                   "checks": checks, "valid": valid,
                                   "note": "four recorded timing legs reused; load average was not recorded and is absent"},
                 "loadavg_reason": "the load average of the recovered timing legs was not recorded"}
        doc = compose(args, rev, commands, measured, None, [], jobs, extra, workloads=state["workload"])
        doc["python"] = found["python"] or doc["python"]
        doc["loadavg"] = []
        doc["result"]["target_met"] = _census_lib().decide(doc)
        if valid is not True and doc["result"]["target_met"] is not None:
            doc["result"]["target_met"] = None
        doc["result"]["note"] = ("recovery: " + ("timings reusable" if valid else "timing reuse unproven or invalid") +
                                 f"; census {census.get('status')}; target_met {doc['result']['target_met']!r}")
        problems = validate(doc)
        if problems:
            raise BenchError("BENCH_DOCUMENT_INVALID", "; ".join(problems[:3]))
        write_atomic(out, doc)
        print(str(out))
        return 0
    except BenchError as error:
        print(str(error), file=sys.stderr)
        return 2
    finally:
        if created:
            git("worktree", "remove", "--force", str(worktree))
            git("worktree", "prune")
            shutil.rmtree(worktree, ignore_errors=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--before", required=True, metavar="REV", help="base revision, measured in a detached worktree")
    parser.add_argument("--out", default=str(HUB / DEFAULT_OUT), help="the bench document (default %(default)s)")
    parser.add_argument("--commands-file", help="JSON list of commands or {cmd, id, mode, diagnostic}")
    parser.add_argument("--label", default="", help="free text stored in the document")
    parser.add_argument("--pairs", type=int, default=2, help=f"before/after pairs, 1..{MAX_PAIRS} (default 2)")
    parser.add_argument("--warm", action="store_true", help="also time warm scheduling and warm reuse of the default tier")
    parser.add_argument("--timeout", type=int, default=3600, help="seconds per measured command (0: none)")
    parser.add_argument("--log-dir", help="command output (default: <out>-logs)")
    parser.add_argument("--census", action="store_true", help="also observe one run per side for the execution census "
                        "(on by default for the default workload)")
    parser.add_argument("--no-census", action="store_true", help="timings only: the target can then never be met")
    parser.add_argument("--recovery-evidence", metavar="FILE", help="explicit recovery: reuse the timing legs recorded in FILE "
                        "(absolute path) and take at most two new observation workloads; see docs/develop.md")
    parser.add_argument("--recovery-command", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.recovery_evidence:
        if args.commands_file or args.warm or args.census or args.no_census:
            print("BENCH_RECOVERY_ARGS: --recovery-evidence takes no workload, warm or census options", file=sys.stderr)
            return 2
        return recover(args)
    worktree = Path(tempfile.gettempdir()) / f"skm-bench-{os.getpid()}"
    created = False
    try:
        if not 1 <= args.pairs <= MAX_PAIRS:
            raise BenchError("BENCH_PAIRS_INVALID", f"--pairs must be 1..{MAX_PAIRS}, got {args.pairs}")
        rev = resolve(args.before)
        commands = read_commands(args.commands_file) if args.commands_file else default_commands(args.warm)
        try:
            jobs = max(1, int(os.environ.get("SKM_TEST_JOBS", os.cpu_count() or 2)))
        except ValueError:
            jobs = os.cpu_count() or 2
        added = git("worktree", "add", "--detach", str(worktree), rev)
        created = added.returncode == 0 or worktree.exists()
        if added.returncode != 0:
            raise BenchError("BENCH_WORKTREE_FAILED", (added.stderr or added.stdout).strip())
        out = Path(args.out)
        log_dir = Path(args.log_dir) if args.log_dir else out.with_name(out.stem + "-logs")
        census_on = (args.census or not args.commands_file) and not args.no_census
        timed = [c for c in commands if c["mode"] == "cold" and not c["diagnostic"]]
        budget = {"timing_executions": args.pairs * 2 * len(commands), "observation_executions": 2 if census_on else 0,
                  "cap": CAP}
        budget["total"] = budget["timing_executions"] + budget["observation_executions"]
        if not args.commands_file and not args.warm and budget["total"] > CAP:
            raise BenchError("BENCH_BUDGET_EXCEEDED", f"{budget['total']} workload executions exceed the predeclared cap {CAP}: "
                             "two pairs plus one observation per side, or --no-census")
        cache = TimingCache()
        start = load_average()
        sources = {"before": {"head": rev, "dirty_digest": ""}, "after": source_identity(ROOT)}
        measured, census = None, None
        try:
            measured = measure(worktree, commands, pairs=args.pairs, jobs=jobs, timeout_s=args.timeout, log_dir=log_dir,
                               cache=cache)
            if census_on and timed:
                cache.restore()
                census = observe(worktree, rev, timed[0]["cmd"], jobs, args.timeout, out.with_name(out.stem + "-census"), log_dir)
        finally:
            cache.restore()  # the owner's timing history is exactly what it was
        later = source_identity(ROOT)
        sources["stable"] = later == sources["after"]
        sources["after_after"] = later
        extra = {"sources": sources, "timing_cache": cache.document(), "budget": budget}
        if census is not None:
            extra["census"] = census
        doc = compose(args, rev, commands, measured, worktree, [start, load_average()], jobs, extra)
        if not sources["stable"]:
            doc["result"]["target_met"] = None
            doc["result"]["note"] = "the source of the current tree changed during the measurement: no verdict"
        problems = validate(doc)
        if problems:
            raise BenchError("BENCH_DOCUMENT_INVALID", "; ".join(problems[:3]))
        write_atomic(out, doc)
        print(str(out))
        return 0
    except BenchError as error:
        print(str(error), file=sys.stderr)
        return 2
    finally:
        if created:
            git("worktree", "remove", "--force", str(worktree))
            git("worktree", "prune")
            shutil.rmtree(worktree, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
