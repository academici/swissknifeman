#!/usr/bin/env python3
"""Focused tests for the P1.1 baseline carrier and diff-scope guard.

Every case runs in its own real, disposable git repository: the guard's whole job
is git attribution, so a mocked history would prove nothing.  Coverage follows the
item's Code Guidance — exclusive first capture, dirty-owner rejection with
unrelated dirt preserved, no-op resume reuse, malformed / non-commit /
non-ancestor rejection, owner/path mismatch, print-only validation, unchanged
generated-scope strength and D47 foreign-commit attribution in both directions.
"""
from __future__ import annotations

import io
import json
import contextlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import assert_generated_scope as guard  # noqa: E402

OWNER = "P1.2"
CARRIER = "plans/PLAN/artifacts/P1.2/base-sha.txt"
OWNER_PATHS = ["src/", "packages/skiller/package.json", CARRIER]
CONTRACT_TEXT = (
    "# fixture contract\n\n"
    "Version-first and generator-closed.\n"
    "Diff-scope guard with foreign-commit attribution: a foreign-commit path is "
    "reported, never reverted.\n"
)


def run(repo: Path, *args: str) -> str:
    completed = subprocess.run(["git", "-C", str(repo), *args],
                               capture_output=True, text=True, check=True)
    return completed.stdout


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def commit(repo: Path, message: str, *paths: str) -> str:
    run(repo, "add", "--", *paths)
    run(repo, "commit", "-q", "-m", message)
    return run(repo, "rev-parse", "HEAD").strip()


def make_repo(base: Path, *, version_bumps=(), guards=()) -> tuple[Path, Path, Path]:
    repo = base / "repo"
    repo.mkdir(parents=True)
    run(repo, "init", "-q", "-b", "main")
    run(repo, "config", "user.email", "fixture@example.invalid")
    run(repo, "config", "user.name", "Fixture")
    write(repo / "src/app.py", "print('one')\n")
    write(repo / "other/readme.md", "foreign area\n")
    scope_map = repo / "scope-map.json"
    write(scope_map, json.dumps({
        "schema_version": "remediation-map/v1",
        "private_source_prefix": "packages/skiller/skills/repository-bootstrap/",
        "class_a_identities": [{"identity": "docs-maintenance"}],
        "owners": {OWNER: {"paths": OWNER_PATHS, "baseline_file": CARRIER,
                           "version_bumps": list(version_bumps),
                           "byte_identical_guards": list(guards)}},
    }))
    contract = repo / "contract.md"
    write(contract, CONTRACT_TEXT)
    # The fixture's own carriers are committed: an untracked file in the fixture
    # root is real undeclared drift, and the guard is right to say so.
    commit(repo, "initial", "src/app.py", "other/readme.md",
           "scope-map.json", "contract.md")
    return repo, scope_map, contract


def baseline(repo: Path, scope_map: Path, *, mode: str = "--capture-or-verify",
             owner: str = OWNER, carrier: str = CARRIER) -> int:
    return guard.main(["baseline", "--repo", str(repo), "--owner", owner,
                       "--scope-map", str(scope_map),
                       "--baseline-file", str(repo / carrier), mode])


def scope(repo: Path, scope_map: Path, contract: Path, base: str,
          owner: str = OWNER) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = guard.main(["generated-scope", "--repo", str(repo), "--baseline", base,
                           "--contract", str(contract), "--scope-map", str(scope_map),
                           "--owner", owner])
    return code, json.loads(stream.getvalue())


class BaselineCarrierTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repo, self.scope_map, self.contract = make_repo(Path(self.directory.name))

    def test_first_capture_is_exclusive_and_records_head(self):
        self.assertEqual(baseline(self.repo, self.scope_map), 0)
        head = run(self.repo, "rev-parse", "HEAD").strip()
        self.assertEqual((self.repo / CARRIER).read_text(encoding="utf-8"), head + "\n")

    def test_dirty_owner_path_rejects_capture_and_preserves_unrelated_dirt(self):
        write(self.repo / "src/app.py", "print('dirty')\n")
        write(self.repo / "other/readme.md", "unrelated dirt\n")
        self.assertEqual(baseline(self.repo, self.scope_map), 1)
        self.assertFalse((self.repo / CARRIER).exists())
        # The guard never stashes, reverts or cleans anything — including its own area.
        self.assertEqual((self.repo / "src/app.py").read_text(encoding="utf-8"),
                         "print('dirty')\n")
        self.assertEqual((self.repo / "other/readme.md").read_text(encoding="utf-8"),
                         "unrelated dirt\n")

    def test_unrelated_dirt_alone_does_not_block_capture(self):
        write(self.repo / "other/readme.md", "unrelated dirt\n")
        self.assertEqual(baseline(self.repo, self.scope_map), 0)
        self.assertTrue((self.repo / CARRIER).is_file())

    def test_resume_reuses_bytes_without_writing(self):
        baseline(self.repo, self.scope_map)
        carrier = self.repo / CARRIER
        before = carrier.read_bytes()
        stamp = carrier.stat().st_mtime_ns
        write(self.repo / "src/app.py", "print('two')\n")
        commit(self.repo, "second", "src/app.py")
        self.assertEqual(baseline(self.repo, self.scope_map), 0)
        self.assertEqual(carrier.read_bytes(), before)
        self.assertEqual(carrier.stat().st_mtime_ns, stamp)

    def test_malformed_sha_is_rejected(self):
        write(self.repo / CARRIER, "not-a-sha\n")
        self.assertEqual(baseline(self.repo, self.scope_map), 1)

    def test_uppercase_sha_is_rejected(self):
        head = run(self.repo, "rev-parse", "HEAD").strip()
        write(self.repo / CARRIER, head.upper() + "\n")
        self.assertEqual(baseline(self.repo, self.scope_map), 1)

    def test_two_lines_are_rejected(self):
        head = run(self.repo, "rev-parse", "HEAD").strip()
        write(self.repo / CARRIER, head + "\n" + head + "\n")
        self.assertEqual(baseline(self.repo, self.scope_map), 1)

    def test_non_commit_object_is_rejected(self):
        blob = subprocess.run(["git", "-C", str(self.repo), "hash-object", "-w",
                               str(self.repo / "src/app.py")],
                              capture_output=True, text=True, check=True).stdout.strip()
        write(self.repo / CARRIER, blob + "\n")
        self.assertEqual(baseline(self.repo, self.scope_map), 1)

    def test_non_ancestor_commit_is_rejected(self):
        run(self.repo, "checkout", "-q", "-b", "side")
        write(self.repo / "src/side.py", "side\n")
        side = commit(self.repo, "side", "src/side.py")
        run(self.repo, "checkout", "-q", "main")
        write(self.repo / CARRIER, side + "\n")
        self.assertEqual(baseline(self.repo, self.scope_map), 1)

    def test_owner_path_mismatch_is_rejected(self):
        code = baseline(self.repo, self.scope_map, carrier="plans/PLAN/artifacts/P9.9/base-sha.txt")
        self.assertEqual(code, 1)

    def test_unknown_owner_is_rejected(self):
        self.assertEqual(baseline(self.repo, self.scope_map, owner="P9.9"), 1)

    def test_verify_and_print_emits_the_value_and_writes_nothing(self):
        baseline(self.repo, self.scope_map)
        carrier = self.repo / CARRIER
        stamp = carrier.stat().st_mtime_ns
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = baseline(self.repo, self.scope_map, mode="--verify-and-print")
        self.assertEqual(code, 0)
        self.assertEqual(stream.getvalue().strip(),
                         run(self.repo, "rev-parse", "HEAD").strip())
        self.assertEqual(carrier.stat().st_mtime_ns, stamp)

    def test_verify_and_print_without_carrier_fails(self):
        self.assertEqual(baseline(self.repo, self.scope_map, mode="--verify-and-print"), 1)

    def test_verify_and_print_rejects_a_corrupt_carrier(self):
        write(self.repo / CARRIER, "0" * 40 + "\n")
        self.assertEqual(baseline(self.repo, self.scope_map, mode="--verify-and-print"), 1)


class GeneratedScopeTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repo, self.scope_map, self.contract = make_repo(Path(self.directory.name))
        self.base = run(self.repo, "rev-parse", "HEAD").strip()

    def test_own_commit_inside_owner_paths_is_clean(self):
        write(self.repo / "src/app.py", "print('two')\n")
        commit(self.repo, "owned change", "src/app.py")
        code, report = scope(self.repo, self.scope_map, self.contract, self.base)
        self.assertEqual(code, 0)
        self.assertEqual(report["owned"], ["src/app.py"])
        self.assertEqual(report["failures"], [])

    def test_second_run_is_a_byte_identical_no_op(self):
        write(self.repo / "src/app.py", "print('two')\n")
        commit(self.repo, "owned change", "src/app.py")
        first = scope(self.repo, self.scope_map, self.contract, self.base)
        second = scope(self.repo, self.scope_map, self.contract, self.base)
        self.assertEqual(first, second)

    def test_foreign_commit_outside_owner_paths_is_attributed_not_drift(self):
        write(self.repo / "other/readme.md", "foreign edit\n")
        foreign = commit(self.repo, "foreign plan work", "other/readme.md")
        code, report = scope(self.repo, self.scope_map, self.contract, self.base)
        self.assertEqual(code, 0)
        self.assertEqual(report["undeclared_drift"], [])
        self.assertEqual(report["foreign_commit"],
                         [{"path": "other/readme.md", "commits": [foreign]}])
        self.assertEqual(report["own_commits"], [])
        # Attribution is read-only: the foreign content is still exactly there.
        self.assertEqual((self.repo / "other/readme.md").read_text(encoding="utf-8"),
                         "foreign edit\n")

    def test_foreign_commit_touching_an_owner_path_fails_closed(self):
        write(self.repo / "src/app.py", "print('foreign')\n")
        write(self.repo / "other/readme.md", "foreign too\n")
        foreign = commit(self.repo, "foreign touches owner path",
                         "src/app.py", "other/readme.md")
        code, report = scope(self.repo, self.scope_map, self.contract, self.base)
        self.assertEqual(code, 1)
        failure = "\n".join(report["failures"])
        self.assertIn("src/app.py", failure)
        self.assertIn(foreign, failure)
        self.assertIn("Owner question", failure)

    def test_uncommitted_change_outside_owner_paths_is_undeclared_drift(self):
        write(self.repo / "other/readme.md", "unexplained\n")
        code, report = scope(self.repo, self.scope_map, self.contract, self.base)
        self.assertEqual(code, 1)
        self.assertTrue(any("uncommitted" in item for item in report["undeclared_drift"]))

    def test_plan_carve_out_is_not_drift(self):
        write(self.repo / "plans/PLAN/handoff.md", "bookkeeping\n")
        commit(self.repo, "plan bookkeeping", "plans/PLAN/handoff.md")
        code, report = scope(self.repo, self.scope_map, self.contract, self.base)
        self.assertEqual(code, 0)
        self.assertEqual(report["undeclared_drift"], [])

    def test_missing_contract_fails(self):
        code = guard.main(["generated-scope", "--repo", str(self.repo),
                           "--baseline", self.base, "--contract", str(self.repo / "nope.md"),
                           "--scope-map", str(self.scope_map), "--owner", OWNER])
        self.assertEqual(code, 1)

    def test_contract_losing_a_frozen_rule_fails(self):
        write(self.contract, "# fixture contract\n\nVersion-first only.\n")
        code = guard.main(["generated-scope", "--repo", str(self.repo),
                           "--baseline", self.base, "--contract", str(self.contract),
                           "--scope-map", str(self.scope_map), "--owner", OWNER])
        self.assertEqual(code, 1)

    def test_non_ancestor_baseline_is_rejected(self):
        code = guard.main(["generated-scope", "--repo", str(self.repo),
                           "--baseline", "0" * 40, "--contract", str(self.contract),
                           "--scope-map", str(self.scope_map), "--owner", OWNER])
        self.assertEqual(code, 1)

    def test_private_source_leakage_is_detected(self):
        write(self.repo / ".agents/plugins/marketplace.json", json.dumps({
            "name": "swissknifeman",
            "plugins": [{"name": "repository-bootstrap",
                         "source": "./packages/skiller/skills/repository-bootstrap"}]}))
        commit(self.repo, "leak", ".agents/plugins/marketplace.json")
        code, report = scope(self.repo, self.scope_map, self.contract, self.base)
        self.assertEqual(code, 1)
        self.assertTrue(any("private-source leakage" in item for item in report["failures"]))

    def test_private_skill_listed_in_a_unit_is_detected(self):
        write(self.repo / ".claude-plugin/marketplace.json", json.dumps({
            "name": "swissknifeman",
            "plugins": [{"name": "core", "source": "./",
                         "skills": ["./packages/skiller/skills/repository-bootstrap/docs-maintenance"]}]}))
        commit(self.repo, "leak2", ".claude-plugin/marketplace.json")
        _code, report = scope(self.repo, self.scope_map, self.contract, self.base)
        self.assertTrue(any("private-source skill" in item for item in report["failures"]))

    def test_version_completeness_failure_when_carrier_is_missing(self):
        repo, scope_map, contract = make_repo(
            Path(self.directory.name) / "second",
            version_bumps=[{"owner_item": OWNER, "unit": "skiller package API",
                            "carrier": "packages/skiller/package.json",
                            "from": "0.4.0", "to": "0.4.1"}])
        base = run(repo, "rev-parse", "HEAD").strip()
        code, report = scope(repo, scope_map, contract, base)
        self.assertEqual(code, 1)
        self.assertTrue(any("version carrier is missing" in item
                            for item in report["failures"]))

    def test_version_completeness_failure_on_wrong_version(self):
        repo, scope_map, contract = make_repo(
            Path(self.directory.name) / "third",
            version_bumps=[{"owner_item": OWNER, "unit": "skiller package API",
                            "carrier": "packages/skiller/package.json",
                            "from": "0.4.0", "to": "0.4.1"}])
        write(repo / "packages/skiller/package.json", json.dumps({"version": "0.4.0"}))
        commit(repo, "unbumped", "packages/skiller/package.json")
        base = run(repo, "rev-parse", "HEAD~1").strip()
        _code, report = scope(repo, scope_map, contract, base)
        self.assertTrue(any("version is '0.4.0', declared '0.4.1'" in item
                            for item in report["failures"]))

    def test_version_completeness_passes_when_bumped(self):
        repo, scope_map, contract = make_repo(
            Path(self.directory.name) / "fourth",
            version_bumps=[{"owner_item": OWNER, "unit": "skiller package API",
                            "carrier": "packages/skiller/package.json",
                            "from": "0.4.0", "to": "0.4.1"}])
        write(repo / "packages/skiller/package.json", json.dumps({"version": "0.4.1"}))
        commit(repo, "bumped", "packages/skiller/package.json")
        base = run(repo, "rev-parse", "HEAD~1").strip()
        code, report = scope(repo, scope_map, contract, base)
        self.assertEqual(report["failures"], [])
        self.assertEqual(code, 0)

    def test_byte_identical_guard_catches_a_touched_class_a_projection(self):
        repo, scope_map, contract = make_repo(
            Path(self.directory.name) / "fifth",
            guards=[{"owner_item": OWNER, "unit": "repository-bootstrap class-A payload",
                     "rule": "class-A bytes stay identical"}])
        base = run(repo, "rev-parse", "HEAD").strip()
        write(repo / ".agents/skills/docs-maintenance/SKILL.md", "---\nname: x\n---\n")
        commit(repo, "touch class-A", ".agents/skills/docs-maintenance/SKILL.md")
        _code, report = scope(repo, scope_map, contract, base)
        self.assertTrue(any("byte-identical guard" in item for item in report["failures"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
