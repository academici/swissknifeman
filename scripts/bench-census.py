#!/usr/bin/env python3
"""Execution census of a test workload and the validity gate of a bench document.

    bench-census.py gate BENCH.json        # artifact-only: is result.target_met consistent with its own evidence?

The library part is used by ``bench-checks.py``. A *census* is a ledger of what ran, not of what was discovered: an observer
(``usercustomize.py`` in an isolated ``PYTHONUSERBASE``, transparent to the tested code) wraps ``unittest.TestCase.run`` in
every Python process that starts with it and appends one JSON line per start and per end (outcome, skip reason, subtest
failures) to ``<ledger>/p<pid>.jsonl``, plus one ``activate`` line per process. Nothing selects, orders or alters a test.
Missing markers (a start without an end), a unit with no activated process and an unreadable ledger stay *unknown*; they are
never counted as zero or as equal. ``usercustomize`` is read from ``PYTHONUSERBASE`` after ``test.sh`` replaced
``PYTHONPATH``, so it survives the runner; activation is proven by the ledger itself, not assumed. Python 3.9-compatible.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import textwrap
from collections import Counter, defaultdict
from fractions import Fraction

TARGET = Fraction(2, 3)
OBSERVER = textwrap.dedent('''\
    import json, os, sys
    _dir = os.environ.get("SKM_CENSUS_DIR")
    if _dir and os.environ.get("SKM_CENSUS_ON") == "1":
        try:
            import unittest.case as _case
            if getattr(_case.TestCase, "_skm_census", False):  # a second channel (shim + user site) never wraps twice
                raise ImportError("already observed")

            _out = open(os.path.join(_dir, "p%d.jsonl" % os.getpid()), "a", buffering=1, encoding="utf-8")

            def _w(record):
                _out.write(json.dumps(record, separators=(",", ":")) + "\\n")

            _w({"ev": "activate", "pid": os.getpid(), "ppid": os.getppid(), "exe": sys.executable, "argv": sys.argv[:8],
                "cwd": os.getcwd(), "ctx": os.environ.get("SKM_TEST_CONTEXT", "")})
            _KINDS = ("failures", "errors", "skipped", "expectedFailures", "unexpectedSuccesses")
            _orig = _case.TestCase.run

            def _mine(test, entry):
                found = getattr(entry[0], "test_case", entry[0])
                return found is test

            def _run(self, result=None):
                kinds = {k: len(getattr(result, k)) for k in _KINDS if isinstance(getattr(result, k, None), list)}
                module = sys.modules.get(type(self).__module__)
                _w({"ev": "s", "id": self.id(), "file": getattr(module, "__file__", None),
                    "cls": type(self).__qualname__, "m": getattr(self, "_testMethodName", None)})
                try:
                    return _orig(self, result)
                finally:
                    outcome, reason, subtests = "unknown", "", 0
                    if len(kinds) == len(_KINDS):
                        new = {k: [e for e in getattr(result, k)[kinds[k]:] if _mine(self, e)] for k in _KINDS}
                        subtests = sum(1 for k in ("failures", "errors") for e in new[k] if e[0] is not self)
                        if new["errors"]:
                            outcome = "error"
                        elif new["failures"]:
                            outcome = "failed"
                        elif new["unexpectedSuccesses"]:
                            outcome = "unexpected_success"
                        elif new["skipped"]:
                            outcome, reason = "skipped", str(new["skipped"][0][1])[:200]
                        elif new["expectedFailures"]:
                            outcome = "expected_failure"
                        else:
                            outcome = "passed"
                    _w({"ev": "e", "id": self.id(), "o": outcome, "r": reason, "sub": subtests})

            _case.TestCase.run = _run
            _case.TestCase._skm_census = True
        except ImportError:
            pass
        except Exception as error:  # the observer never breaks the tested process
            sys.stderr.write("census observer inactive: %r\\n" % (error,))
''')


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()  # a path may hold undecodable bytes


def install_observer(base: Path, env: dict) -> dict:
    """Write the observer into the user site of ``base`` for the ``python3`` that ``env`` finds; the provenance. Every path
    handed to a child process is absolute: a child runs in another working directory."""
    base = Path(os.path.abspath(str(base)))
    probe = subprocess.run(["python3", "-c", "import sys,site;print(sys.executable);print(sys.version.split()[0]);"
                            "print(site.getusersitepackages())"], env=dict(env, PYTHONUSERBASE=str(base)),
                           capture_output=True, text=True, timeout=60)
    lines = probe.stdout.split("\n")
    if probe.returncode != 0 or len(lines) < 3:
        raise RuntimeError(f"cannot probe python3: {probe.stderr.strip()}")
    site = Path(lines[2])
    site.mkdir(parents=True, exist_ok=True)
    (site / "usercustomize.py").write_text(OBSERVER, encoding="utf-8")
    return {"python": lines[0], "version": lines[1], "user_site": str(site), "observer_sha256": sha256_text(OBSERVER)}


def install_shim(folder: Path, python: str) -> dict:
    """The second activation channel: a ``python3`` shim that prepends the observer directory to ``PYTHONPATH`` and execs the
    SAME absolute interpreter, so it works after ``test.sh`` replaced ``PYTHONPATH``; ``sitecustomize.py`` there is the
    observer. A process that starts the interpreter directly (``sys.executable``) inherits that ``PYTHONPATH``."""
    folder = Path(os.path.abspath(str(folder)))
    obs, binary = folder / "obs", folder / "bin"
    obs.mkdir(parents=True, exist_ok=True)
    binary.mkdir(parents=True, exist_ok=True)
    (obs / "sitecustomize.py").write_text(OBSERVER, encoding="utf-8")
    shim = binary / "python3"
    shim.write_text('#!/bin/sh\nPYTHONPATH="%s${PYTHONPATH:+:$PYTHONPATH}" exec "%s" "$@"\n' % (obs, python), encoding="utf-8")
    shim.chmod(0o755)
    return {"bin": str(binary), "obs": str(obs), "python": python, "shim_sha256": sha256_text(shim.read_text(encoding="utf-8"))}


def census_env(env: dict, base: Path, ledger: Path, root: Path, shim: dict | None = None) -> dict:
    """The environment of an observed child: the user base, the ledger folder, the tree root and the shim are all absolute, so
    they stay valid when the child changes its working directory."""
    base, ledger, root = (Path(os.path.abspath(str(item))) for item in (base, ledger, root))
    ledger.mkdir(parents=True, exist_ok=True)
    out = dict(env, PYTHONUSERBASE=str(base), SKM_CENSUS_DIR=str(ledger), SKM_CENSUS_ON="1", SKM_CENSUS_ROOT=str(root))
    if shim:
        out["PATH"] = os.path.abspath(shim["bin"]) + os.pathsep + env.get("PATH", "")
    return out


def _unit(relative: str) -> str:
    parts = relative.split("/")
    return "/".join(parts[:2]) if parts[0] in ("packages", "bridges") and len(parts) > 2 else "hub"


def read_ledger(ledger: Path, root: Path) -> dict:
    """Summary of a ledger folder: executions by normalized key, outcomes, skips, retries, activation, unknowns."""
    root_real = os.path.realpath(str(root))
    processes, executions, problems = {}, [], 0
    unmatched = 0
    for file in sorted(Path(ledger).glob("p*.jsonl")):
        open_tests: dict = defaultdict(list)
        context = ""
        for text in file.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(text)
            except ValueError:
                problems += 1
                continue
            kind = record.get("ev")
            if kind == "activate":
                context = record.get("ctx") or ""
                processes[file.name] = {"cwd": record.get("cwd"), "ctx": context, "argv": record.get("argv", [])[:4]}
            elif kind == "s":
                open_tests[record["id"]].append(record)
            elif kind == "e" and open_tests.get(record.get("id")):
                start = open_tests[record["id"]].pop()
                path = os.path.realpath(start["file"]) if start.get("file") else ""
                relative = os.path.relpath(path, root_real).replace(os.sep, "/") if path.startswith(root_real) else path
                unit = _unit(relative)
                ctx = context or ("partner" if unit.startswith("bridges/") else "local")
                executions.append({"key": f"{unit}|{relative}|{start.get('cls')}|{start.get('m')}", "ctx": ctx, "unit": unit,
                                   "file": relative, "cls": start.get("cls"), "m": start.get("m"), "o": record.get("o"),
                                   "reason": record.get("r") or "", "sub": record.get("sub", 0), "pid": file.name})
        unmatched += sum(len(v) for v in open_tests.values())
    keys = {(row["ctx"], row["key"]) for row in executions}
    outcomes = Counter(row["o"] for row in executions)
    skips = Counter(row["reason"] for row in executions if row["o"] == "skipped")
    units = Counter(row["unit"] for row in executions)
    return {"activations": len(processes), "processes": processes, "executions": len(executions), "unique": len(keys),
            "duplicates": len(executions) - len(keys), "outcomes": dict(sorted(outcomes.items())),
            "skips": dict(sorted(skips.items())), "units": dict(sorted(units.items())),
            "contexts": dict(sorted(Counter(ctx for ctx, _ in keys).items())),
            "subtest_failures": sum(row["sub"] for row in executions), "unmatched_starts": unmatched,
            "unreadable_lines": problems, "digest": sha256_text("\n".join(sorted(f"{c}|{k}" for c, k in keys))),
            "_keys": keys, "_rows": executions}


def public(summary: dict) -> dict:
    return {key: value for key, value in summary.items() if not key.startswith("_")}


def missing_units(summary: dict, expected: list) -> list:
    """Workload test units (folders) that ran no observed test: their evidence is unknown, not zero."""
    seen = set(summary["units"])
    return sorted(unit for unit in expected if unit not in seen)


def complete(summary: dict, expected: list, exit_code=0) -> list:
    """Why a ledger cannot be called complete (empty list: complete as far as the markers can show)."""
    why = []
    if not summary["executions"]:
        why.append("no observed execution")
    if summary["unmatched_starts"] or summary["unreadable_lines"]:
        why.append("unmatched starts or unreadable ledger lines")
    gone = missing_units(summary, expected)
    if gone:
        why.append("no observed test in units " + ", ".join(gone))
    if exit_code != 0:
        why.append(f"the workload exited {exit_code}")
    return why


def _definitions(text: str) -> set:
    return set(re.findall(r"^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)", text, re.M))


def _show(repo: Path, rev: str, relative: str):
    done = subprocess.run(["git", "show", f"{rev}:{relative}"], cwd=repo, capture_output=True, text=True, timeout=60)
    return done.stdout if done.returncode == 0 else None


def explain(repo: Path, rev: str, after_root: Path, side: str, row: tuple) -> str:
    """Source-backed reason for a case that ran on one side only; ``unexplained`` when the source does not show it."""
    _ctx, key = row
    _unit_name, relative, _cls, method = key.split("|", 3)
    base_text = _show(repo, rev, relative)
    try:
        after_text = (Path(after_root) / relative).read_text(encoding="utf-8")
    except OSError:
        after_text = None
    if side == "after":
        if base_text is None and after_text is not None:
            return "added: new file"
        if base_text is not None and after_text is not None and method not in _definitions(base_text) \
                and method in _definitions(after_text):
            return "added: new method"
        return "unexplained"
    if after_text is None:
        return "removed: file gone"
    if base_text is not None and method in _definitions(base_text) and method not in _definitions(after_text):
        return "removed: method gone (renamed or deleted)"
    return "unexplained"


KNOWN_OUTCOMES = ("passed", "failed", "error", "skipped", "expected_failure", "unexpected_success")


def _valid_mapping(entry, after_rows: dict) -> bool:
    """An explicit, justified replacement: a non-empty reason and replacement cases that exist in the after ledger and passed."""
    if not isinstance(entry, dict) or not str(entry.get("reason") or "").strip():
        return False
    replacement = entry.get("replacement")
    replacement = [replacement] if isinstance(replacement, str) else replacement
    if not isinstance(replacement, list) or not replacement:
        return False
    return all(isinstance(name, str) and after_rows.get(name) and after_rows[name] == {"passed"} for name in replacement)


def compare(before: dict, after: dict, repo: Path, rev: str, after_root: Path, expected_units: list,
            mappings: dict | None = None) -> dict:
    """The census comparison. ``conserved`` is true only with complete ledgers on both sides, known outcomes, no failing or
    changed case, every one-sided case explained by the source AND every case that disappeared replaced by an explicit,
    justified mapping (``mappings``: ``{"ctx|key": {"replacement": "ctx|key" | [...], "reason": text}}``) whose replacements ran
    and passed. A method that merely vanished from the source is an observation (``removals``), never proof that its
    assertion is still covered: without a mapping the verdict is ``None`` (unknown). ``None`` also for missing evidence or an
    unknown primary outcome; ``False`` for an unexplained delta, a failure or a changed outcome."""
    gone, new = sorted(before["_keys"] - after["_keys"]), sorted(after["_keys"] - before["_keys"])
    notes = {"before": {"unmatched_starts": before["unmatched_starts"], "missing_units": missing_units(before, expected_units)},
             "after": {"unmatched_starts": after["unmatched_starts"], "missing_units": missing_units(after, expected_units)}}
    after_outcomes: dict = defaultdict(set)
    for row in after["_rows"]:
        after_outcomes[f"{row['ctx']}|{row['key']}"].add(row["o"])
    mapped, unmapped = {}, []
    deltas = []
    for c, k in gone[:200]:
        name = f"{c}|{k}"
        why = explain(repo, rev, after_root, "before", (c, k))
        entry = (mappings or {}).get(name)
        if entry is not None and _valid_mapping(entry, after_outcomes):
            mapped[name] = entry
            deltas.append({"side": "before", "key": name, "why": why, "coverage": "mapped", "mapping": entry})
        else:
            deltas.append({"side": "before", "key": name, "why": why, "coverage": "unproven"})
            unmapped.append(name)
    deltas += [{"side": "after", "key": f"{c}|{k}", "why": explain(repo, rev, after_root, "after", (c, k)), "coverage": "added"}
               for c, k in new[:200]]
    unmapped += [f"{c}|{k}" for c, k in gone[200:]]  # beyond the listed deltas: no mapping can have been checked
    unexplained = [d for d in deltas if d["why"] == "unexplained"] + (
        [{"side": "before", "key": "...", "why": "unexplained"}] if len(gone) > 200 else []) + (
        [{"side": "after", "key": "...", "why": "unexplained"}] if len(new) > 200 else [])
    unknown = []
    for side, summary in (("before", before), ("after", after)):
        if not summary["executions"]:
            unknown.append(f"{side}: no observed execution")
        if summary["unmatched_starts"] or summary["unreadable_lines"]:
            unknown.append(f"{side}: unmatched starts or unreadable ledger lines")
        if notes[side]["missing_units"]:
            unknown.append(f"{side}: no observed test in units {', '.join(notes[side]['missing_units'])}")
        odd = sum(1 for row in summary["_rows"] if row.get("o") not in KNOWN_OUTCOMES)
        if odd or summary["outcomes"].get("unknown"):
            unknown.append(f"{side}: {odd or summary['outcomes'].get('unknown')} execution(s) with an unknown primary outcome")
    failed = [side for side, summary in (("before", before), ("after", after))
              if summary["outcomes"].get("failed") or summary["outcomes"].get("error")]
    changed = sorted(f"{c}|{k}" for (c, k) in before["_keys"] & after["_keys"]
                     if {r["o"] for r in before["_rows"] if (r["ctx"], r["key"]) == (c, k)}
                     != {r["o"] for r in after["_rows"] if (r["ctx"], r["key"]) == (c, k)})
    if unknown:
        conserved = None
    elif failed or unexplained or changed:
        conserved = False
    elif unmapped:
        conserved = None  # a case disappeared and nothing shows its assertion is still run
    else:
        conserved = True
    return {"conserved": conserved, "unknown": unknown, "failed_sides": failed,
            "before": public(before), "after": public(after), "notes": notes,
            "only_before": len(gone), "only_after": len(new), "deltas": deltas[:100], "unexplained": len(unexplained),
            "removals": {"total": len(gone), "mapped": len(mapped), "unmapped": unmapped[:100]},
            "outcome_changes": changed[:50], "duplicate_executions": {"before": before["duplicates"], "after": after["duplicates"]}}


def decide(doc: dict):
    """The honest ``result.target_met`` of a bench document: ``None`` unless the timings are valid and comparable;
    ``False`` for a valid ratio above exactly 2/3; ``True`` only at or below 2/3 with conserved case evidence."""
    result, total = doc.get("result") or {}, doc.get("total") or {}
    runs = {side: [value for command in (doc.get(side) or {}).get("commands", []) if command.get("id") in total.get("counted", [])
                   for value in command.get("runs", [])] for side in ("before", "after")}
    if (doc.get("sources") or {}).get("stable") is False:
        return None
    if "timing_source" in doc and (doc["timing_source"] or {}).get("valid") is not True:
        return None
    if result.get("failed_runs") or not total.get("counted") or not runs["before"] or len(runs["before"]) != len(runs["after"]):
        return None
    if not (doc.get("coverage") or {}).get("workload", {}).get("equal"):
        return None
    before = sum(Fraction(str(value)) for value in runs["before"])
    after = sum(Fraction(str(value)) for value in runs["after"])
    if before <= 0:
        return None
    if after / before > TARGET:
        return False
    census = doc.get("census") or {}
    return True if census.get("conserved") is True else None


def gate(path: Path) -> list:
    """Problems that make a bench document invalid as evidence (empty: acceptable)."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [f"cannot read {path}: {error}"]
    problems = []
    result = doc.get("result") or {}
    claimed, honest = result.get("target_met"), decide(doc)
    if claimed is True and (result.get("failed_runs") or 0):
        problems.append("target_met is true although measured runs failed")
    if claimed is True and (doc.get("census") or {}).get("conserved") is not True:
        problems.append("target_met is true without a conserved execution census")
    if claimed != honest:
        problems.append(f"target_met is {claimed!r} but the document's own evidence decides {honest!r}")
    census = doc.get("census")
    if isinstance(census, dict) and census.get("conserved") is True:
        for side in ("before", "after"):
            if not (census.get(side) or {}).get("executions"):
                problems.append(f"census conserved without an execution ledger on the {side} side")
    if isinstance(census, dict) and census.get("conserved") is True:
        exits = census.get("exits") or {}
        if any((exits.get(side) or {}).get("exit") != 0 for side in ("before", "after")):
            problems.append("census conserved although an observation workload did not exit 0")
        if census.get("workload_executions", 0) > 2:
            problems.append("census used more than the two admitted observation workloads")
    if (doc.get("sources") or {}).get("stable") is False and claimed is not None:
        problems.append("the source changed during the measurement, so no verdict is valid")
    return problems


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 2 and argv[0] == "gate":
        problems = gate(Path(argv[1]))
        for problem in problems:
            print(f"BENCH_GATE_FAILED: {problem}", file=sys.stderr)
        if not problems:
            print("bench-gate: OK")
        return 1 if problems else 0
    print(__doc__.split("\n\n")[0], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
