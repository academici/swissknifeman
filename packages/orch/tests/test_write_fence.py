"""The write fence of a piece (PLAN9.P3.3, D14): files of another module than the write set names block the piece
(``OUTSIDE_MODULE``), runtime artifacts an executor left in the tree are moved to the artifacts of the piece
(``RUNTIME_ARTIFACT_RELOCATED``) or, when tracked, block it (``OUTSIDE_RUNTIME_ARTIFACT``), and checks that change the
tree run again once (``CHECKS_MUTATED`` when they change it every time)."""
from __future__ import annotations

import unittest
from unittest import mock

from orch.conductor import checks, options, scope

from tests.test_conductor import GREEN, ConductorCase, report


def module_check(ref: str, path: str, cmd: str = "") -> dict:
    return {"id": "V1", "cmd": cmd or f"test -f {path}", "expect": "exit 0", "kind": "acceptance"}


def module_report(path: str, cmd: str, **extra) -> dict:
    return report("W1", changed_paths=[path], checks_run=[{"id": "V1", "cmd": cmd, "exit": 0}], **extra)


class ModuleTests(unittest.TestCase):
    def test_a_path_belongs_to_its_package_bridge_or_the_hub(self):
        for path, module in (("packages/orch/lib/x.py", "packages/orch"), ("bridges/planner-orch/a.json", "bridges/planner-orch"),
                             ("scripts/x.py", "hub"), ("configs/c.toml", "hub"), ("README.md", "hub"), ("packages", "hub"),
                             ("packages/orch", "packages/orch"), ("./packages/orch/x", "packages/orch")):
            with self.subTest(path=path):
                self.assertEqual(scope.module_of(path), module)

    def test_the_modules_of_an_item_come_from_its_patterns_up_to_the_first_glob(self):
        self.assertEqual(scope.item_modules(["packages/orch/**", "packages/orch/lib/x*.py"]), {"packages/orch"})
        self.assertEqual(scope.item_modules(["packages/orch/lib/orch/x.py", "bridges/planner-orch/schemas/*.json"]),
                         {"packages/orch", "bridges/planner-orch"})
        self.assertEqual(scope.item_modules(["scripts/**", "packages/orch/a"]), {"hub", "packages/orch"})
        self.assertEqual(scope.item_modules(["*.md", "**/tests/x.py"]), {"hub"})
        self.assertEqual(scope.item_modules(["packages/*/lib/x.py"]), {"packages/*"})
        self.assertEqual(scope.item_modules(["packages/or*/lib/x.py"]), {"packages/or*"})
        self.assertEqual(scope.item_modules(["packages/"]), {"packages/*"})
        self.assertEqual(scope.item_modules([]), set())

    def test_the_changelog_and_the_docs_name_no_module(self):
        self.assertEqual(scope.item_modules(["CHANGELOG.md", "docs/**", "docs/x.md", "docs/"]), set())
        self.assertEqual(scope.item_modules(["packages/orch/**", "docs/**", "CHANGELOG.md"]), {"packages/orch"})

    def test_foreign_paths_are_those_of_a_module_the_write_set_does_not_name(self):
        write_set = ["packages/orch/**"]
        found = scope.foreign(["packages/other/x.py", "scripts/x.py", "docs/x.md", "CHANGELOG.md", "packages/orch/y.py",
                               "bridges/planner-orch/a"], write_set)
        self.assertEqual(found, ["bridges/planner-orch/a", "packages/other/x.py", "scripts/x.py"])
        self.assertEqual(scope.foreign(["scripts/x.py"], ["scripts/**"]), [])
        self.assertEqual(scope.foreign(["packages/anything/x.py"], ["packages/**"]), [])
        self.assertEqual(scope.foreign(["packages/other/x.py"], []), [])  # no write set: nothing to be foreign to

    def test_a_granted_directory_inside_the_project_is_not_foreign(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp).resolve()
            self.assertEqual(scope.foreign(["packages/other/x.py", "scripts/y.py"], ["packages/orch/**"],
                                           [str(project / "packages" / "other")], project), ["scripts/y.py"])
            self.assertEqual(scope.foreign(["packages/other-x/x.py"], ["packages/orch/**"],
                                           [str(project / "packages" / "other")], project), ["packages/other-x/x.py"])

    def test_under_reads_the_patterns_of_the_write_set(self):
        runtime = options.DEFAULT_SCOPE["runtime_paths"]
        for path in (".swissknifeman/orch-artifacts/foo/V1.log", ".swissknifeman/orch/x", "packages/orch/tests/evidence/x.json",
                     "tests/evidence/y.json"):
            with self.subTest(path=path):
                self.assertTrue(scope.under(path, runtime))
        for path in (".swissknifeman/state/x", "packages/orch/tests/test_x.py", "evidence/x.json"):
            with self.subTest(path=path):
                self.assertFalse(scope.under(path, runtime))


class FloorTests(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(options.DEFAULT_SCOPE["outside_module"], "deviation")
        self.assertIn(".swissknifeman/orch-artifacts/**", options.DEFAULT_SCOPE["runtime_paths"])

    def test_a_layer_of_the_work_source_cannot_set_outside_module_to_deviation_or_drop_runtime_paths(self):
        for layer in ({"scope": {"outside_module": "deviation"}}, {"scope": {"runtime_paths": ["x/**"]}}):
            with self.subTest(layer=layer):
                with self.assertRaises(options.OptionsError) as caught:
                    options.effective({}, {}, [{"source": "invocation:--options", "trusted": True,
                                                "options": {"scope": {"outside_module": "block"}}},
                                               {"source": "item:W1", "options": layer}])
                self.assertEqual(caught.exception.code, "OPTIONS_UNTRUSTED")

    def test_a_work_source_layer_may_add_runtime_paths_and_a_trusted_one_may_loosen(self):
        found = options.effective({}, {}, [{"source": "item:W1", "options": {"scope": {
            "runtime_paths": [*options.DEFAULT_SCOPE["runtime_paths"], "build/logs/**"]}}}])[0]
        self.assertIn("build/logs/**", found["scope"]["runtime_paths"])
        found = options.effective({}, {}, [{"source": "invocation:--options", "trusted": True,
                                            "options": {"scope": {"outside_module": "deviation"}}}])[0]
        self.assertEqual(found["scope"]["outside_module"], "deviation")


STRICT = [{"source": "item:W1", "options": {"scope": {"outside_module": "block"}}}]


class OutsideModuleTests(ConductorCase):
    def piece(self, write_set, cmd="test -f packages/orch/x.txt", **fields):
        self.set_items({"W1": {"write_set": write_set, "checks": [module_check("W1", "", cmd)], **fields}})

    def blocked_by(self, err, code):
        self.assertEqual((self.outcome(err)), ("stopped", "ITEM_BLOCKED"), err)
        issues = self.source()["items"]["W1"]["report"]["open_issues"]
        self.assertTrue(any(code in issue["text"] for issue in issues if issue["kind"] != "note"), issues)

    def test_under_block_a_file_of_another_module_blocks_the_piece_and_nothing_is_committed(self):
        self.piece(["packages/orch/**"], options=STRICT)
        self.script({"executor": [{"write": {"packages/orch/x.txt": "ok\n", "packages/other/x.py": "y\n"},
                                   "result": module_report("packages/orch/x.txt", "test -f packages/orch/x.txt")}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        self.blocked_by(err, "OUTSIDE_MODULE")
        self.assertIn("packages/other/x.py", self.source()["items"]["W1"]["report"]["open_issues"][-1]["text"])
        self.assertEqual((self.calls("executor"), self.calls("reviewer")), (1, 0))
        self.assertEqual(self.source()["commits"], [])

    def test_under_block_the_changelog_and_the_docs_stay_a_deviation_and_are_committed(self):
        self.piece(["packages/orch/**"], options=STRICT)
        self.script({"executor": [{"write": {"packages/orch/x.txt": "ok\n", "docs/x.md": "d\n", "CHANGELOG.md": "c\n"},
                                   "result": module_report("packages/orch/x.txt", "test -f packages/orch/x.txt")}],
                     "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        item = self.source()["items"]["W1"]
        self.assertEqual(item["status"], "done_with_deviations")
        deviation = next(issue for issue in item["report"]["open_issues"] if issue["kind"] == "deviation")
        self.assertEqual((deviation["class"], deviation["evidence"]), ("write_set", ["CHANGELOG.md", "docs/x.md"]))
        self.assertEqual(sorted(self.source()["commits"][0]["paths"]).count("docs/x.md"), 1)
        self.assertIn("CHANGELOG.md", self.source()["commits"][0]["paths"])

    def test_under_block_a_hub_path_is_not_a_module_of_a_package_piece(self):
        self.piece(["packages/orch/**"], options=STRICT)
        self.script({"executor": [{"write": {"packages/orch/x.txt": "ok\n", "scripts/x.py": "y\n"},
                                   "result": module_report("packages/orch/x.txt", "test -f packages/orch/x.txt")}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        self.blocked_by(err, "OUTSIDE_MODULE")
        self.assertEqual(self.source()["commits"], [])

    def test_a_path_of_the_hub_next_to_a_hub_write_set_is_a_deviation_as_before(self):
        self.script({"executor": [{"write": {"out/W1.txt": "ok\n", "lib/other.py": "y\n"}, "result": report("W1")}],
                     "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.source()["items"]["W1"]["status"], "done_with_deviations")

    def test_by_default_a_file_of_another_module_is_a_deviation_and_is_committed(self):
        self.piece(["packages/orch/**"])
        self.script({"executor": [{"write": {"packages/orch/x.txt": "ok\n", "packages/other/x.py": "y\n"},
                                   "result": module_report("packages/orch/x.txt", "test -f packages/orch/x.txt")}],
                     "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        item = self.source()["items"]["W1"]
        self.assertEqual(item["status"], "done_with_deviations")
        self.assertIn("packages/other/x.py", self.source()["commits"][0]["paths"])

    def test_outside_block_keeps_the_stricter_outside_write_set_stop(self):
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {"scope": {"outside": "block"}}}]}})
        self.script({"executor": [{"write": {"out/W1.txt": "ok\n", "lib/other.py": "x\n"}, "result": report("W1")}]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        self.assertIn("OUTSIDE_WRITE_SET", self.source()["items"]["W1"]["report"]["open_issues"][-1]["text"])


class RuntimeArtifactTests(ConductorCase):
    def test_new_untracked_runtime_files_are_moved_aside_and_not_committed(self):
        self.script({"executor": [{"write": {"out/W1.txt": "ok\n", ".swissknifeman/orch-artifacts/foo/V1.log": "log\n",
                                             "packages/orch/tests/evidence/x.json": "{}\n"},
                                   "result": report("W1", changed_paths=["out/W1.txt", ".swissknifeman/orch-artifacts/foo/V1.log",
                                                                          "packages/orch/tests/evidence/x.json"])}],
                     "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertFalse((self.project / ".swissknifeman/orch-artifacts/foo/V1.log").exists())
        self.assertFalse((self.project / "packages/orch/tests/evidence/x.json").exists())
        moved = [line for line in self.lines(err) if line.get("reason_code") == "RUNTIME_ARTIFACT_RELOCATED"]
        self.assertEqual(len(moved), 1, err)
        self.assertIn("packages/orch/tests/evidence/x.json", moved[0]["message"])
        item = self.source()["items"]["W1"]
        self.assertEqual(item["report"]["changed_paths"], ["out/W1.txt"])
        self.assertEqual(item["status"], "done_with_deviations" if any(
            issue["kind"] == "deviation" for issue in item["report"]["open_issues"]) else "done")
        self.assertTrue(any(issue["kind"] == "note" and "runtime artifacts" in issue["text"]
                            for issue in item["report"]["open_issues"]))
        self.assertEqual(self.source()["commits"][0]["paths"].count("out/W1.txt"), 1)
        for path in self.source()["commits"][0]["paths"]:
            self.assertNotIn("V1.log", path)
            self.assertNotIn("tests/evidence", path)
        stray = self.state(err)["items"]["W1"]["relocated"]["executor.1"]
        self.assertEqual(sorted(stray), [".swissknifeman/orch-artifacts/foo/V1.log", "packages/orch/tests/evidence/x.json"])
        for where in stray.values():
            self.assertIn("/stray/", where)
            self.assertTrue((self.project / where).is_file() or (self.project / where).exists(), where)
        self.assertEqual(self.git("status", "--porcelain", "--", "packages").strip(), "")

    def test_a_changed_tracked_runtime_file_blocks_the_piece(self):
        tracked = self.project / "packages" / "orch" / "tests" / "evidence" / "x.json"
        tracked.parent.mkdir(parents=True)
        tracked.write_text("{}\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "history")
        self.script({"executor": [{"write": {"out/W1.txt": "ok\n", "packages/orch/tests/evidence/x.json": '{"a": 1}\n'},
                                   "result": report("W1")}]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        self.assertIn("OUTSIDE_RUNTIME_ARTIFACT", self.source()["items"]["W1"]["report"]["open_issues"][-1]["text"])
        self.assertIn("packages/orch/tests/evidence/x.json", self.source()["items"]["W1"]["report"]["open_issues"][-1]["text"])
        self.assertEqual(self.source()["commits"], [])
        self.assertEqual(self.calls("reviewer"), 0)


class CommitPathsTests(unittest.TestCase):
    """The commit of a piece takes the records of its artifact folder, never the runtime artifacts set aside in ``stray``."""

    def commit_of(self, folder: str, ignore: str = ""):
        import subprocess
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from orch.conductor.infrastructure import roles, work_source
        from orch.conductor.stages import finish
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()

        def git(*args):
            return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, check=True,
                                  capture_output=True, text=True).stdout

        git("init", "-q")
        (root / ".gitignore").write_text(ignore, encoding="utf-8")
        (root / folder).mkdir(parents=True)
        (root / folder / "stage-report.json").write_text("{}\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", "x")  # the artifact folder is tracked already
        (root / folder / "stage-report.json").write_text('{"a": 1}\n', encoding="utf-8")  # a record, rewritten
        (root / folder / "research-1.json").write_text("{}\n", encoding="utf-8")  # a new record
        if ignore:
            (root / folder / "scratch.tmp").write_text("x\n", encoding="utf-8")  # an ignored file
        (root / folder / "stray" / "tests" / "evidence").mkdir(parents=True)
        (root / folder / "stray" / "log.txt").write_text("runtime\n", encoding="utf-8")
        (root / folder / "stray" / "tests" / "evidence" / "x.json").write_text("{}\n", encoding="utf-8")
        me = SimpleNamespace(project=root, _research_paths=lambda item: set())
        me._relative = lambda path: roles.relative(me, path)
        me._local_records = lambda item: work_source.local_records(me, item)
        item = SimpleNamespace(artifacts=root / folder)
        paths = finish.commit_paths(me, item, {"changed_paths": ["out/W1.txt"]})
        git("add", "--", *[path for path in paths if path != "out/W1.txt"])  # the product file is not made here
        return paths, git("diff", "--cached", "--name-only").splitlines()

    def test_a_tracked_artifact_folder_commits_its_records_and_not_the_stray_files(self):
        paths, staged = self.commit_of("plans/T/artifacts/W1/run-1")
        self.assertEqual(staged, ["plans/T/artifacts/W1/run-1/research-1.json", "plans/T/artifacts/W1/run-1/stage-report.json"])
        self.assertFalse([path for path in paths if "stray" in path], paths)
        self.assertNotIn("plans/T/artifacts/W1/run-1/", paths)

    def test_an_ignored_record_does_not_break_the_commit(self):
        paths, staged = self.commit_of("plans/T/artifacts/W1/run-1", ignore="*.tmp\n")
        self.assertFalse([path for path in paths if path.endswith("scratch.tmp")], paths)
        self.assertEqual(staged, ["plans/T/artifacts/W1/run-1/research-1.json", "plans/T/artifacts/W1/run-1/stage-report.json"])

    def test_the_local_fallback_folder_commits_nothing(self):
        paths, staged = self.commit_of(".swissknifeman/orch-artifacts/cnd-x/W1")
        self.assertEqual((paths, staged), (["out/W1.txt"], []))


class MutatingChecksTests(ConductorCase):
    FORMAT = "test -f out/W1.txt && (grep -q formatted out/W1.txt || echo formatted >> out/W1.txt)"

    def piece(self, cmd, **fields):
        self.set_items({"W1": {"checks": [{"id": "V1", "cmd": cmd, "expect": "exit 0", "kind": "acceptance"}], **fields}})
        self.script({"executor": [{"write": {"out/W1.txt": "ok\n"},
                                   "result": report("W1", checks_run=[{"id": "V1", "cmd": cmd, "exit": 0}])}],
                     "reviewer": [GREEN]})

    def test_a_check_that_formats_a_file_once_is_run_again_and_the_commit_takes_the_change(self):
        self.piece(self.FORMAT)
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        said = [line for line in self.lines(err) if line.get("reason_code") == "CHECK_CHANGED_TREE"]
        self.assertEqual(len(said), 1, err)
        self.assertIn("run again", said[0]["message"])
        logs = sorted(path.parent.name for path in (self.run_dir(err) / "W1" / "checks").rglob("V1.log"))
        self.assertEqual(logs, ["1", "1-rerun"])
        self.assertEqual((self.project / "out" / "W1.txt").read_text(encoding="utf-8"), "ok\nformatted\n")
        self.assertIn("out/W1.txt", self.source()["commits"][0]["paths"])
        self.assertEqual(self.git("show", "HEAD:out/W1.txt"), "ok\nformatted\n")
        self.assertEqual(self.git("status", "--porcelain", "--", "out").strip(), "")

    def test_the_evidence_of_the_rerun_proves_the_changed_tree(self):
        self.piece(self.FORMAT)
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        import json
        evidence = sorted((self.project / ".swissknifeman").rglob("evidence/V1.json")) \
            + sorted(self.run_dir(err).rglob("evidence/V1.json"))
        if not evidence:  # the source keeps the artifacts of the piece elsewhere: find it by its content
            evidence = [path for path in self.project.parent.rglob("V1.json") if "evidence" in path.parts]
        self.assertTrue(evidence)
        docs = [json.loads(path.read_text(encoding="utf-8")) for path in evidence]
        self.assertTrue(all(doc["procedure"]["cmd"] == self.FORMAT for doc in docs))

    def test_a_check_that_changes_the_tree_every_time_stops_the_run(self):
        self.piece("test -f out/W1.txt && date +%s%N >> out/W1.txt")
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "CHECKS_MUTATED")), err)
        self.assertEqual(self.source()["commits"], [])
        self.assertEqual(self.calls("reviewer"), 0)
        said = [line for line in self.lines(err) if line.get("reason_code") == "CHECK_CHANGED_TREE"]
        self.assertEqual(len(said), 1, err)
        end = [line for line in self.lines(err) if line["event"] == "run.end"][-1]
        self.assertIn("out/W1.txt", end["message"])
        self.assertIn("idempotent", end["message"])

    def test_under_block_a_check_that_writes_a_file_of_another_module_stops_the_run(self):
        cmd = "test -f packages/orch/x.txt && mkdir -p packages/other && echo gen > packages/other/gen.py"
        self.set_items({"W1": {"write_set": ["packages/orch/**"], "checks": [{"id": "V1", "cmd": cmd, "expect": "exit 0",
                                                                          "kind": "acceptance"}], "options": STRICT}})
        self.script({"executor": [{"write": {"packages/orch/x.txt": "ok\n"},
                                   "result": module_report("packages/orch/x.txt", cmd)}], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "OUTSIDE_MODULE")), err)
        self.assertEqual(self.source()["commits"], [])

    def test_a_runtime_file_of_a_check_stays_out_of_the_commit_and_a_product_file_goes_in(self):
        cmd = ("test -f out/W1.txt && mkdir -p tests/evidence && echo e > tests/evidence/y.json "
               "&& (grep -q formatted out/W1.txt || echo formatted >> out/W1.txt)")
        self.piece(cmd)
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        paths = self.source()["commits"][0]["paths"]
        self.assertIn("out/W1.txt", paths)
        self.assertFalse([path for path in paths if "tests/evidence" in path], paths)
        self.assertEqual(self.git("show", "HEAD:out/W1.txt"), "ok\nformatted\n")

    def test_a_runtime_file_of_a_check_is_set_aside_and_leaves_no_dirty_tree_and_no_ownership(self):
        cmd = "test -f out/W1.txt && mkdir -p packages/orch/tests/evidence && echo '{}' > packages/orch/tests/evidence/x.json"
        self.piece(cmd)
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.git("status", "--porcelain", "--", "packages").strip(), "")
        self.assertFalse((self.project / "packages/orch/tests/evidence/x.json").exists())
        item = self.state(err)["items"]["W1"]
        self.assertNotIn("checks_changed", item)
        self.assertEqual(sorted(item["relocated"]["checks.1"]), ["packages/orch/tests/evidence/x.json"])
        where = item["relocated"]["checks.1"]["packages/orch/tests/evidence/x.json"]
        self.assertIn("/stray/", where)
        self.assertTrue((self.project / where).is_file())
        self.assertFalse(list((self.run_dir(err) / "W1" / "checks").glob("*-rerun")))  # a runtime file is no mutation
        self.assertFalse([line for line in self.lines(err) if line.get("reason_code") == "CHECK_CHANGED_TREE"])

    def test_a_runtime_log_rewritten_with_a_timestamp_on_every_run_does_not_stop_the_run(self):
        cmd = "test -f out/W1.txt && mkdir -p packages/orch/tests/evidence && date +%s%N > packages/orch/tests/evidence/run.log"
        self.piece(cmd)
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.git("status", "--porcelain", "--", "packages").strip(), "")
        for path in self.source()["commits"][0]["paths"]:
            self.assertNotIn("tests/evidence", path)

    def test_a_product_change_runs_the_checks_again_once_beside_a_regenerated_runtime_log(self):
        cmd = ("test -f out/W1.txt && mkdir -p packages/orch/tests/evidence && date +%s%N > packages/orch/tests/evidence/run.log "
               "&& (grep -q formatted out/W1.txt || echo formatted >> out/W1.txt)")
        self.piece(cmd)
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(len([line for line in self.lines(err) if line.get("reason_code") == "CHECK_CHANGED_TREE"]), 1)
        self.assertTrue(list((self.run_dir(err) / "W1" / "checks").glob("*-rerun")))
        self.assertEqual(self.git("show", "HEAD:out/W1.txt"), "ok\nformatted\n")
        self.assertEqual(self.git("status", "--porcelain", "--", "packages", "out").strip(), "")
        self.assertEqual(self.state(err)["items"]["W1"]["checks_changed"], {"1": ["out/W1.txt"]})

    def test_a_product_change_that_repeats_stops_even_beside_a_runtime_log(self):
        cmd = ("test -f out/W1.txt && mkdir -p packages/orch/tests/evidence && date +%s%N > packages/orch/tests/evidence/run.log "
               "&& date +%s%N >> out/W1.txt")
        self.piece(cmd)
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "CHECKS_MUTATED")), err)
        end = [line for line in self.lines(err) if line["event"] == "run.end"][-1]
        self.assertIn("out/W1.txt", end["message"])
        self.assertNotIn("run.log", end["message"])
        self.assertEqual(self.source()["commits"], [])

    def test_a_check_that_changes_a_tracked_runtime_file_still_blocks(self):
        tracked = self.project / "packages" / "orch" / "tests" / "evidence" / "x.json"
        tracked.parent.mkdir(parents=True)
        tracked.write_text("{}\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "history")
        self.piece("test -f out/W1.txt && date +%s%N > packages/orch/tests/evidence/x.json")
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "OUTSIDE_RUNTIME_ARTIFACT")), err)
        self.assertEqual(self.source()["commits"], [])

    def test_a_failed_rerun_keeps_the_ownership_of_the_formatted_file_across_the_retry(self):
        self.piece(self.FORMAT)
        real = checks.run_checks

        def failing_rerun(*args, **kwargs):
            if str(kwargs["log_dir"]).endswith("-rerun"):
                raise OSError("disk went away")
            return real(*args, **kwargs)

        with mock.patch.object(checks, "run_checks", side_effect=failing_rerun):
            code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "CHECKS_FAILED")), err)
        self.assertEqual(self.state(err)["items"]["W1"]["checks_changed"], {"1": ["out/W1.txt"]})
        self.assertEqual(self.source()["commits"], [])
        code, _, err = self.conduct("resume", "--run", self.run_dir(err).name, "--json-lines")  # the formatter is idempotent now
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.state(err)["items"]["W1"]["checks_changed"], {"1": ["out/W1.txt"]})
        self.assertIn("out/W1.txt", self.source()["commits"][0]["paths"])
        self.assertEqual(self.git("show", "HEAD:out/W1.txt"), "ok\nformatted\n")
        self.assertEqual(self.calls("executor"), 1)

    def test_checks_that_change_nothing_run_once(self):
        self.piece("test -f out/W1.txt")
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertFalse([line for line in self.lines(err) if line.get("reason_code") == "CHECK_CHANGED_TREE"])
        self.assertFalse(list((self.run_dir(err) / "W1" / "checks").glob("*-rerun")))
        self.assertNotIn("checks_changed", self.state(err)["items"]["W1"])


if __name__ == "__main__":
    unittest.main()
