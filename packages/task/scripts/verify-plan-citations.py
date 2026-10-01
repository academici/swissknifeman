#!/usr/bin/env python3
"""Checking references-evidence of plans: `path:line`/`path::symbol` resolves before the fact.

A software gate that reuses a defect class that was found in
 (only checked
existence of FILE from `ref` to `::`, character after `::` was not validated - through this hole
passed mis-cite H06). That script is in `artifacts/` terminal plan and is not corrected
(additivity, D90); this script is a reusable replacement for its class for ALL living plans,
which also closes the second class - rotten linear anchors on files rewritten by another
plan.

Form and CLI repeat `packages/task/scripts/cross-plan-files.py` (see Required Reads P10.2): stdlib-only,
human-readable report always, `--strict` switches only exit-code.

Validated link forms (inside single backticks, the WHOLE token):
    `path/to/file.ext:123`            — one line inside the file
    `path/to/file.ext:123-145`        — string range
    `path/to/file.ext:123,145`        — pair of non-contiguous lines
    `path/to/file.ext::symbol`        — symbol name occurs in the file (search by name,
                                         WITHOUT AST; `a::B::c` — CLEAR LEAF `c`, border
                                         intentional, see docs/reference/plan-tooling.md)
    `path/to/file.json::a.b.c` — key path inside JSON, resolves
                                         `json.load` + greedy-bypass (at each level -
                                         LONGEST subsidized prefix, which is
                                         key; for a list - an integer index).
                                         Checks that the KEY EXISTS - not the value
                                         matches. Not JSON-path - old grep by sheet.

The path must contain at least one `/` (like `normalize()` y `cross-plan-files.py`) —
NAKED path-mention without suffix (`:line`/`::symbol`) NOT checked at all (class rejected
measurement, D128). The path resolution is TWO-STEP: (1) repository root, (2) source plan directory
(`plans/<PLAN-ID>/`) — the first base under which the file exists determines the resolve, suffix
is checked against HER. The order is intentional (the root of the repo is unambiguous and common to
of all plans, plan directory - contextual addition); internal short link like
`phases/P1.md:80` is resolved by the SECOND base - this is not «restoring implied context
prose», and the second deterministic base, known to the script by construction (bypasses itself
`plans/<PLAN-ID>/`). A file that does not resolve from ANY of the two databases is a find (Code Guidance
item'a P11.1, anti-fitting): the machine still doesn't guess.

Scan surface - seven patterns inside `plans/<PLAN-ID>/`: `plan.md`, `handoff.md`,
`roadmap.md`, `phases/*.md`, `findings/**/*.md`, `research/**/*.md`, `brief/**/*.md`
(recursively). `artifacts/`, `closure/`, `root/` deliberately beyond the surface (raw materials measurements /
generated reports / moves to `docs/` project - not a carrier of planned prose).

Known exceptions (links to FUTURE deliverables items, which are not yet on this tree
construction) — data, not code: `packages/task/configs/verify-citations-known-exceptions.json`
(`{"exceptions": [{"citation": "...", "reason": "..."}]}`), format - the same principle as
`cross-plan-files-known-intersections.json` at the next gate.

Usage:
    python3 packages/task/scripts/verify-plan-citations.py                        # all live plans
    python3 packages/task/scripts/verify-plan-citations.py plans/<PLAN-ID> ...     # named only (path OR ID)
    python3 packages/task/scripts/verify-plan-citations.py --strict                # exit 1 for any finding
    python3 packages/task/scripts/verify-plan-citations.py --include-archive        # + archived plans
    python3 packages/task/scripts/verify-plan-citations.py --selftest               # embedded unittest (Files
                                                                  # item'and does not start a separate
                                                                  # test file)
"""
from __future__ import annotations

import glob
import importlib
import json
import os
import re
import sys

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
PLANS_DIR = os.path.join(REPO_ROOT, "plans")
KNOWN_EXCEPTIONS_FILE = os.path.join(
    REPO_ROOT, "packages", "task", "configs", "verify-citations-known-exceptions.json")

CITATION_RE = re.compile(
    r"`((?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]+)"
    r"(:[0-9]+(?:[-,][0-9]+)?|::[A-Za-z_][\w.:]*)`"
)


class Finding:
    def __init__(self, source: str, line: int, citation: str, reason: str) -> None:
        self.source = source
        self.line = line
        self.citation = citation
        self.reason = reason

    def render(self) -> str:
        return f"{self.source}:{self.line} → `{self.citation}` — {self.reason}"


class PhaseSourceResolutionError(RuntimeError):
    """Task's canonical phase resolver is unavailable or rejected the plan."""


def live_plan_dirs(include_archive: bool = False) -> list[str]:
    out = []
    for path in sorted(glob.glob(os.path.join(PLANS_DIR, "*", "plan.md"))):
        plan_dir = os.path.dirname(path)
        plan_id = os.path.basename(plan_dir)
        if plan_id in ("archive", "tools"):
            continue
        out.append(plan_dir)
    if include_archive:
        for path in sorted(glob.glob(os.path.join(PLANS_DIR, "archive", "*", "plan.md"))):
            out.append(os.path.dirname(path))
    return out


def resolve_plan_dir(arg: str) -> str:
    for candidate in (arg, os.path.join(PLANS_DIR, arg)):
        if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, "plan.md")):
            return os.path.normpath(candidate)
    raise SystemExit(f"verify-citations: not a plan ({arg}) — plan.md not found")


# Seven surface patterns (D128, `research/27-P11-citation-gate-target-design.md` §2.2):
# layers of knowledge `brief/`→`findings/`→`research/` canonized SKILL §16 as carriers, from
# of which the chain «raw materials → synthesis → solution» must be restored without chat - link in
# they are exactly the same proof as the link in the technical specifications. `artifacts/`/`closure/`/`root/` out
# surfaces deliberately (raw materials measurements / generated reports / moves to docs/ project).
_SOURCE_PATTERNS = (
    "plan.md",
    "handoff.md",
    "roadmap.md",
    os.path.join("findings", "**", "*.md"),
    os.path.join("research", "**", "*.md"),
    os.path.join("brief", "**", "*.md"),
)


def _phase_source_files(plan_dir: str) -> list[str]:
    """Ask task's resolver for phase carriers; this script owns no layout glob."""
    task_lib = os.path.join(REPO_ROOT, "packages", "task", "lib")
    if task_lib not in sys.path:
        sys.path.insert(0, task_lib)
    try:
        resolver = importlib.import_module("task.plan_layout")
    except ImportError as exc:
        raise PhaseSourceResolutionError(
            "canonical resolver task.plan_layout not available; check "
            "packages/task/lib in the runtime verifier"
        ) from exc
    try:
        return [str(path) for path in resolver.phase_paths(plan_dir).values()]
    except (ValueError, OSError) as exc:
        raise PhaseSourceResolutionError(
            f"canonical resolver did not read phase carriers plan {plan_dir}: {exc}"
        ) from exc


def plan_source_files(plan_dir: str) -> list[str]:
    files: set[str] = set()
    for pattern in _SOURCE_PATTERNS:
        for f in glob.glob(os.path.join(plan_dir, pattern), recursive=True):
            if os.path.isfile(f):
                files.add(f)
    files.update(f for f in _phase_source_files(plan_dir) if os.path.isfile(f))
    return sorted(files)


def load_known_exceptions() -> dict[str, str]:
    if not os.path.exists(KNOWN_EXCEPTIONS_FILE):
        return {}
    with open(KNOWN_EXCEPTIONS_FILE, encoding="utf-8") as fh:
        data = json.load(fh)
    return {item["citation"]: item.get("reason", "") for item in data.get("exceptions", [])}


def resolve_bases(repo_root: str, plan_dir: str) -> list[tuple[str, str]]:
    """Two path resolution bases, IN THIS ORDER (fixed, D128/`research/27-…` §2.1):
    (1) repository root - unambiguous and common for all plans; (2) source plan directory -
    contextual addition, resolves internal short links (`phases/P9.md:260`).
    The order is not rearranged: name collision on a living tree is unlikely, but when
    file in the root of the repo that matches the internal path, priority must remain with
    root is NOT a guess, but a declared rule."""
    return [("repo root", repo_root), ("plan directory", plan_dir)]


def _resolve_json_path(obj: object, remaining: str) -> str | None:
    """Greedy-bypass JSON-object: at each level - LONGEST subsidized prefix
    remainder, which is the key (for list - integer index). Returns the reason
    failure, or None if the entire path is resolved (P11.2, `research/27-…` §2.3 — greedy
    is required: the keys of the planned artifact themselves contain points, `owners.P2.2` = key
    `"P2.2"` inside `owners`, naive `split(".")` gives a false find)."""
    while remaining:
        if isinstance(obj, dict):
            matched = None
            for k in sorted(obj.keys(), key=lambda k: (-len(k), k)):
                if remaining == k or remaining.startswith(k + "."):
                    matched = k
                    break
            if matched is None:
                segment = remaining.split(".", 1)[0]
                return f"key {segment!r} not found"
            obj = obj[matched]
            remaining = remaining[len(matched):]
            remaining = remaining[1:] if remaining.startswith(".") else remaining
        elif isinstance(obj, list):
            m = re.match(r"(\d+)(?:\.(.*))?$", remaining)
            if not m:
                segment = remaining.split(".", 1)[0]
                return f"index {segment!r} not found"
            idx = int(m.group(1))
            if not (0 <= idx < len(obj)):
                return f"index {idx} out of range of list length {len(obj)}"
            obj = obj[idx]
            remaining = m.group(2) or ""
        else:
            segment = remaining.split(".", 1)[0]
            return f"key {segment!r} not found (parent is not an object or a list)"
    return None


def _check_json_suffix(abs_path: str, dotted_path: str) -> str | None:
    """Quote class `file.json::a.b.c`: the key exists - and NOTHING else
    (value is not verified, the same limit as P10.2 «symbol = name occurs»)."""
    with open(abs_path, encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError:
            return "JSON is not parsed"
    return _resolve_json_path(data, dotted_path)


def _check_suffix(abs_path: str, suffix: str) -> str | None:
    with open(abs_path, encoding="utf-8", errors="replace") as fh:
        content = fh.read()
    if suffix.startswith("::"):
        # a::B::c — We are not building AST (Implementation Rules item'a); grab the name SHEET.
        leaf = suffix[2:].split("::")[-1]
        if not re.search(r"\b" + re.escape(leaf) + r"\b", content):
            return f"symbol {leaf!r} not found in file"
        return None
    body = suffix[1:]
    if "-" in body:
        numbers = body.split("-", 1)
    elif "," in body:
        numbers = body.split(",")
    else:
        numbers = [body]
    total = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
    for raw in numbers:
        n = int(raw)
        if not (1 <= n <= total):
            return f"string {n} out of range 1..{total}"
    return None


def check_citation(path_token: str, suffix: str, bases: list[tuple[str, str]]) -> str | None:
    """Return reason for refusal, or None if the link resolves. `bases` — list
    `(label, directory)`, are tried IN ORDER (`resolve_bases`); first base under which the file
    exists, defines a resolve, suffix is checked RELATIVE TO IT (mixing the bases would give
    false «line number out of range» — suffix and the found file must be from the same database)."""
    for _label, base in bases:
        abs_path = os.path.join(base, path_token)
        if os.path.isfile(abs_path):
            if suffix.startswith("::") and path_token.lower().endswith(".json"):
                return _check_json_suffix(abs_path, suffix[2:])
            return _check_suffix(abs_path, suffix)
    if not bases:
        return "file not found (resolution database not specified)"
    tried = ", neither ".join(f"from {label}" for label, _ in bases)
    return f"file not found {tried}"



def scan_plan(plan_dir: str, known: dict[str, str], repo_root: str) -> tuple[list[Finding], int]:
    bases = resolve_bases(repo_root, plan_dir)
    findings: list[Finding] = []
    checked = 0
    for src in plan_source_files(plan_dir):
        rel_src = os.path.relpath(src, repo_root)
        with open(src, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                for m in CITATION_RE.finditer(line):
                    path_token, suffix = m.group(1), m.group(2)
                    citation = f"{path_token}{suffix}"
                    checked += 1
                    if citation in known:
                        continue
                    reason = check_citation(path_token, suffix, bases)
                    if reason:
                        findings.append(Finding(rel_src, lineno, citation, reason))
    return findings, checked


def _selftest() -> int:
    """Embedded unittest — the only test media item'a (Files does not start a separate
    file: script stdlib-only and self-sufficient, like its neighbor `cross-plan-files.py`)."""
    import tempfile
    import unittest
    from unittest import mock

    class VerifyCitationsTests(unittest.TestCase):
        def setUp(self) -> None:
            self._tmp = tempfile.TemporaryDirectory()
            self.addCleanup(self._tmp.cleanup)
            self.repo_root = self._tmp.name
            os.makedirs(os.path.join(self.repo_root, "pkg"))
            with open(os.path.join(self.repo_root, "pkg", "mod.py"), "w", encoding="utf-8") as fh:
                fh.write("line1\nline2\ndef target():\n    pass\n")
            # plan directory - second resolve base; carries YOUR file, which is missing under the root.
            self.plan_dir = os.path.join(self.repo_root, "plans", "P11-BASES-FIXTURE")
            os.makedirs(os.path.join(self.plan_dir, "phases"))
            with open(os.path.join(self.plan_dir, "plan.md"), "w", encoding="utf-8") as fh:
                fh.write("# legacy layout fixture\n")
            with open(os.path.join(self.plan_dir, "phases", "P1.md"), "w", encoding="utf-8") as fh:
                fh.write("line1\nline2\n")
            self.bases = resolve_bases(self.repo_root, self.plan_dir)

        def test_a_valid_line_ref_passes(self) -> None:
            self.assertIsNone(check_citation("pkg/mod.py", ":2", self.bases))

        def test_a2_valid_range_and_pair_pass(self) -> None:
            self.assertIsNone(check_citation("pkg/mod.py", ":1-4", self.bases))
            self.assertIsNone(check_citation("pkg/mod.py", ":1,4", self.bases))

        def test_b_line_out_of_range_is_finding(self) -> None:
            reason = check_citation("pkg/mod.py", ":99", self.bases)
            self.assertIsNotNone(reason)
            self.assertIn("range", reason)

        def test_c_missing_symbol_is_finding(self) -> None:
            reason = check_citation("pkg/mod.py", "::nope", self.bases)
            self.assertIsNotNone(reason)
            self.assertIn("symbol", reason)

        def test_c2_existing_symbol_passes(self) -> None:
            self.assertIsNone(check_citation("pkg/mod.py", "::target", self.bases))

        def test_c3_nested_symbol_greps_leaf(self) -> None:
            self.assertIsNone(check_citation("pkg/mod.py", "::Suite::target", self.bases))

        def test_d_missing_file_is_finding(self) -> None:
            reason = check_citation("pkg/absent.py", ":1", self.bases)
            self.assertIsNotNone(reason)
            self.assertIn("not found", reason)

        # --- P11.1: two-step resolver + extended surface ---------------------

        def test_e_resolves_only_from_plan_dir(self) -> None:
            """(a) quote resolves ONLY from the plan directory (`phases/P1.md:2`) — passes."""
            self.assertIsNone(check_citation("phases/P1.md", ":2", self.bases))

        def test_e2_resolves_from_repo_root(self) -> None:
            """(b) quote resolved from repo root - passes (regression: base 1 not broken)."""
            self.assertIsNone(check_citation("pkg/mod.py", ":1", self.bases))

        def test_e3_resolves_from_neither_base_names_both(self) -> None:
            """(c) does not resolve from any database → find names BOTH bases."""
            reason = check_citation("phases/absent.md", ":1", self.bases)
            self.assertIsNotNone(reason)
            self.assertIn("repo root", reason)
            self.assertIn("plan directory", reason)

        def test_e4_out_of_range_checked_against_correct_base(self) -> None:
            """(d) file is under the plan directory, line number is outside ITS range (2 lines) —
            find is tied to the correct base, rather than falsely checked against the root of the repo."""
            reason = check_citation("phases/P1.md", ":99", self.bases)
            self.assertIsNotNone(reason)
            self.assertIn("range", reason)

        def test_e5_recursive_glob_finds_nested_findings_file(self) -> None:
            """(e) `findings/sub/x.md` hits the surface (recursive glob)."""
            sub_dir = os.path.join(self.plan_dir, "findings", "sub")
            os.makedirs(sub_dir)
            with open(os.path.join(sub_dir, "x.md"), "w", encoding="utf-8") as fh:
                fh.write("see `pkg/mod.py:1`\n")
            files = plan_source_files(self.plan_dir)
            self.assertIn(os.path.join(sub_dir, "x.md"), files)

        def test_e6_base_order_is_fixed_repo_root_first(self) -> None:
            """Database order is FIXED: repo root first (`resolve_bases`)."""
            self.assertEqual(
                [label for label, _ in resolve_bases(self.repo_root, self.plan_dir)],
                ["repo root", "plan directory"],
            )

        def test_e7_phase_resolver_import_failure_is_fail_closed(self) -> None:
            """Unavailable Task runtime does not convert phase surface to nothing."""
            with mock.patch.object(importlib, "import_module", side_effect=ImportError("fixture")):
                with self.assertRaises(RuntimeError):
                    _phase_source_files(self.plan_dir)

        def test_e8_incomplete_v2_phase_tree_is_fail_closed(self) -> None:
            """`phases/Pn/` without `Pn.md` does not disappear from citation surface silently."""
            with open(os.path.join(self.plan_dir, "plan.md"), "w", encoding="utf-8") as fh:
                fh.write(
                    "## 0. Meta\n\n| Field | Meaning |\n"
                    "|:--|:--|\n| Layout | v2 |\n"
                )
            os.remove(os.path.join(self.plan_dir, "phases", "P1.md"))
            os.makedirs(os.path.join(self.plan_dir, "phases", "P1"))

            with self.assertRaisesRegex(PhaseSourceResolutionError, r"phases/P1/P1\.md"):
                _phase_source_files(self.plan_dir)

        # --- P11.2: quote class `file.json::a.b.c` (greedy-resolve) --------------------

        def test_f_json_path_resolves_nested_key(self) -> None:
            """(a) `pkg/data.json::a.b` when `{"a":{"b":1}}` — passes."""
            with open(os.path.join(self.repo_root, "pkg", "data.json"), "w", encoding="utf-8") as fh:
                json.dump({"a": {"b": 1}}, fh)
            self.assertIsNone(check_citation("pkg/data.json", "::a.b", self.bases))

        def test_f2_json_path_greedy_key_with_dot(self) -> None:
            """(b) key with a dot in the name (`owners.P2.2` = key `"P2.2"` inside `owners`) —
            naive regression `split(".")`, must pass (greedy)."""
            with open(os.path.join(self.repo_root, "pkg", "owners.json"), "w", encoding="utf-8") as fh:
                json.dump({"owners": {"P2.2": "carrier"}}, fh)
            self.assertIsNone(check_citation("pkg/owners.json", "::owners.P2.2", self.bases))

        def test_f3_json_path_missing_key_names_segment(self) -> None:
            """(c) non-existent key → find, EXACTLY the missing part is named."""
            with open(os.path.join(self.repo_root, "pkg", "data2.json"), "w", encoding="utf-8") as fh:
                json.dump({"a": {"b": 1}}, fh)
            reason = check_citation("pkg/data2.json", "::a.nope", self.bases)
            self.assertIsNotNone(reason)
            self.assertIn("nope", reason)

        def test_f4_json_path_list_index(self) -> None:
            """(d) list index (`::items.0.name`) passes, exceeding the length - a find."""
            with open(os.path.join(self.repo_root, "pkg", "list.json"), "w", encoding="utf-8") as fh:
                json.dump({"items": [{"name": "x"}]}, fh)
            self.assertIsNone(check_citation("pkg/list.json", "::items.0.name", self.bases))
            reason = check_citation("pkg/list.json", "::items.9.name", self.bases)
            self.assertIsNotNone(reason)
            self.assertIn("range", reason)

        def test_f5_broken_json_is_finding(self) -> None:
            """(e) broken JSON → find «JSON is not parsed», is not a silent pass."""
            with open(os.path.join(self.repo_root, "pkg", "broken.json"), "w", encoding="utf-8") as fh:
                fh.write("{not valid json")
            reason = check_citation("pkg/broken.json", "::a.b", self.bases)
            self.assertIsNotNone(reason)
            self.assertIn("is not parsed", reason)

        def test_f6_non_json_symbol_branch_unchanged(self) -> None:
            """(f) NOT-json file with `::symbol` — old behavior (grep sheet) has not changed."""
            self.assertIsNone(check_citation("pkg/mod.py", "::target", self.bases))

        def test_scan_plan_end_to_end(self) -> None:
            plan_dir = os.path.join(self.repo_root, "plans", "X")
            os.makedirs(os.path.join(plan_dir, "phases"))
            with open(os.path.join(plan_dir, "plan.md"), "w", encoding="utf-8") as fh:
                fh.write("see `pkg/mod.py:2` and `pkg/mod.py::missing_symbol`\n")
            findings, checked = scan_plan(plan_dir, {}, self.repo_root)
            self.assertEqual(checked, 2)
            self.assertEqual(len(findings), 1)
            self.assertIn("missing_symbol", findings[0].citation)

        def test_known_exception_suppresses_finding(self) -> None:
            plan_dir = os.path.join(self.repo_root, "plans", "Y")
            os.makedirs(os.path.join(plan_dir, "phases"))
            with open(os.path.join(plan_dir, "plan.md"), "w", encoding="utf-8") as fh:
                fh.write("future deliverable `pkg/not-yet.py:1`\n")
            known = {"pkg/not-yet.py:1": "deliverable of the future item'a"}
            findings, checked = scan_plan(plan_dir, known, self.repo_root)
            self.assertEqual(checked, 1)
            self.assertEqual(findings, [])

        def test_determinism_two_runs_identical(self) -> None:
            plan_dir = os.path.join(self.repo_root, "plans", "Z")
            os.makedirs(os.path.join(plan_dir, "phases"))
            with open(os.path.join(plan_dir, "plan.md"), "w", encoding="utf-8") as fh:
                fh.write("`pkg/mod.py:2` and `pkg/absent.py:1`\n")
            first = [f.render() for f in scan_plan(plan_dir, {}, self.repo_root)[0]]
            second = [f.render() for f in scan_plan(plan_dir, {}, self.repo_root)[0]]
            self.assertEqual(first, second)

    suite = unittest.TestLoader().loadTestsFromTestCase(VerifyCitationsTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def main() -> int:
    argv = sys.argv[1:]
    if "--selftest" in argv:
        return _selftest()
    strict = "--strict" in argv
    include_archive = "--include-archive" in argv
    args = [a for a in argv if not a.startswith("--")]
    plan_dirs = [resolve_plan_dir(a) for a in args] if args else live_plan_dirs(include_archive)
    known = load_known_exceptions()

    total_findings: list[Finding] = []
    total_checked = 0
    print(f"Checking evidence links by {len(plan_dirs)} plan(am)\n")
    for plan_dir in plan_dirs:
        plan_id = os.path.basename(plan_dir)
        try:
            findings, checked = scan_plan(plan_dir, known, REPO_ROOT)
        except PhaseSourceResolutionError as exc:
            print(f"  {plan_id}: ERROR RESOLVER_UNAVAILABLE — {exc}", file=sys.stderr)
            return 2
        total_checked += checked
        total_findings += findings
        print(f"  {plan_id}: quotes verified {checked} · finds {len(findings)}")

    print(f"\nTotal citations: {total_checked}")
    print(f"Known exceptions listed: {len(known)}")
    print(f"Finds: {len(total_findings)}\n")
    if total_findings:
        for f in total_findings:
            print(f"  {f.render()}")
    else:
        print("  (no finds)")

    if not strict:
        return 0
    return 1 if total_findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
