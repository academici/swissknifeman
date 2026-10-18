"""Publish-safety rules, classification, the report and `workspace doctor --publish-safety`."""
import json
import os
import unittest

from aicore.util import schema
from aicore.util.redact import MASK
from aicore.workspace import new_id, write_project

from tests import MODULE_ROOT, TempCase, git, new_code
from workspace import doctor, layout, safety

TOKEN = "ghp_" + "a1B2" * 9  # 36 characters after the prefix
REPORT_SCHEMA = MODULE_ROOT / "schemas" / "publish-report" / "v1"
SMALL = safety.Settings(max_tracked_bytes=1000, max_binary_tracked_bytes=100)


class SafetyCase(TempCase):
    def setUp(self):
        super().setUp()
        layout.init("axioma")
        self.pid = new_code()
        write_project(self.ws, self.pid, "demo")
        git(self.ws, "add", "-A")
        git(self.ws, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "project")
        self.folder = self.ws / "projects" / self.pid

    def put(self, relative, content="x", mode=None, binary=False):
        path = self.ws / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if binary:
            path.write_bytes(content if isinstance(content, bytes) else content.encode())
        else:
            path.write_text(content, encoding="utf-8")
        if mode is not None:
            path.chmod(mode)
        return relative

    def plan(self, name):
        return f"projects/{self.pid}/plans/p1/{name}"

    def rules(self, report, level="block"):
        return sorted((item["rule"], item["path"]) for item in getattr(report, level))

    def report_valid(self, report):
        registry, kind = schema.load_contract(REPORT_SCHEMA, urn_prefix="urn:swissknifeman:workspace:")
        document = report.to_dict() if hasattr(report, "to_dict") else report
        self.assertEqual(schema.validate(document, kind, registry), [], document)
        return document


class SecretTests(SafetyCase):
    def test_a_token_in_a_text_file_blocks_and_is_never_printed(self):
        path = self.put(self.plan("notes.md"), f"line one\nthe key is {TOKEN} ok\nline three\n")
        report = safety.scan(self.ws, [path])
        self.assertEqual(self.rules(report), [("PS-SECRET", path)])
        finding = report.block[0]
        self.assertEqual(finding["line"], 2)
        self.assertIn(MASK, finding["detail"])
        text = json.dumps(report.to_dict(), ensure_ascii=False)
        self.assertNotIn(TOKEN, text)
        self.assertNotIn(TOKEN[4:], text)
        self.assertEqual(report.verdict, "block")
        self.report_valid(report)

    def test_named_secrets_and_other_token_formats(self):
        cases = {"a.json": '{"password": "hunter2hunter2"}', "b.txt": "API_KEY=abcdefgh12345678",
                 "c.txt": "sk-" + "xY1" * 8, "d.txt": "AKIA" + "A" * 16, "e.txt": "xoxb-1234567890-abcdef",
                 "f.txt": "Authorization: Bearer " + "z" * 24, "g.txt": "github_pat_" + "q" * 24}
        for name, content in cases.items():
            with self.subTest(name=name):
                path = self.put(self.plan(name), content)
                report = safety.scan(self.ws, [path])
                self.assertEqual(self.rules(report), [("PS-SECRET", path)])

    def test_slugs_placeholders_and_references_are_not_secrets(self):
        quiet = ["see task-development-workflow-and-more for details", "skill sk-plugin-development-guide", "findings-task-0204-lifecycle-compatibility-2026-09-22.json",
                 'token = "<SET-ME-LATER>"', "SECRET=<SECRET_VALUE>", 'api_key: ${API_KEY_VALUE}', 'token = "env://MY_TOKEN_NAME"',
                 "password: $PASSWORD_FROM_ENV"]
        for index, content in enumerate(quiet):
            with self.subTest(content=content):
                path = self.put(self.plan(f"quiet{index}.md"), content + "\n")
                self.assertEqual(safety.scan(self.ws, [path]).block, [])
        loud = ["sk-" + "Ab1" * 10, "sk-proj-" + "a1" * 12, 'token = "plainvalue123"', "SECRET=abcd1234efgh"]
        for index, content in enumerate(loud):
            with self.subTest(content=content):
                path = self.put(self.plan(f"loud{index}.md"), content + "\n")
                self.assertEqual(self.rules(safety.scan(self.ws, [path])), [("PS-SECRET", path)])

    def test_a_value_that_only_starts_like_a_placeholder_is_still_a_secret(self):
        loud = ['token = "<abcdefgh1234567890"', "SECRET={Abcd1234efgh5678", 'password: "$abcd1234efgh!x"',
                "api_key=env://a1b2c3d4e5f6?x=1", "token=<NAME>suffix1234", "password=${HOME}x1234567"]
        for index, content in enumerate(loud):
            with self.subTest(content=content):
                path = self.put(self.plan(f"loud{index}.md"), content + "\n")
                self.assertEqual(self.rules(safety.scan(self.ws, [path])), [("PS-SECRET", path)])

    def test_ordinary_prose_and_short_values_pass(self):
        path = self.put(self.plan("ok.md"), "the token budget is large\npassword: short\nsecret handling is discussed\n")
        self.assertEqual(safety.scan(self.ws, [path]).verdict, "ok")

    def test_secret_file_names_block_even_when_empty(self):
        names = [".env", ".env.local", "id.pem", "tls.KEY", "store.p12", "store.pfx", "credentials.json", "secrets.yaml"]
        paths = [self.put(self.plan(name), "") for name in names]
        report = safety.scan(self.ws, paths)
        self.assertEqual(self.rules(report), sorted(("PS-SECRET", path) for path in paths))
        self.assertTrue(all(MASK in item["detail"] for item in report.block))

    def test_gitignore_keeps_most_secret_files_out_of_the_scan_but_not_credentials(self):
        self.put(self.plan(".env"), "A=1")
        self.put(self.plan("tls.pem"), "x")
        credentials = self.put(self.plan("credentials.json"), "{}")
        self.assertEqual(safety.changed_paths(self.ws), [credentials])
        self.assertEqual(self.rules(safety.check(self.ws)), [("PS-SECRET", credentials)])

    def test_secrets_are_looked_for_only_in_utf8_text_within_the_limit(self):
        small_binary = self.put(self.plan("b.bin"), b"\0\0" + TOKEN.encode(), binary=True)
        latin1 = self.put(self.plan("l.txt"), b"\xff\xfe " + TOKEN.encode(), binary=True)
        big_text = self.put(self.plan("big.txt"), TOKEN + "\n" + "x" * 2000)
        report = safety.scan(self.ws, [small_binary, latin1, big_text], SMALL)
        self.assertEqual(report.block, [])
        self.assertEqual([item["path"] for item in report.local_only], [big_text])


class PathTests(SafetyCase):
    def test_home_paths_in_plan_data_only_warn(self):
        path = self.put(self.plan("phases/P1/P1.1.json"), json.dumps(
            {"a": "/home/someone/x", "b": "see /Users/me/y and /home/someone/z", "c": "C:\\Users\\me\\w"}))
        report = safety.scan(self.ws, [path])
        self.assertEqual((report.block, report.verdict), ([], "warn"))
        self.assertEqual(self.rules(report, "warn"), [("PS-HOME-PATH", path)])
        self.assertIn("4 home-directory path(s)", report.warn[0]["detail"])
        self.assertNotIn("someone", json.dumps(report.to_dict()))
        self.report_valid(report)

    def test_an_absolute_path_in_a_portable_manifest_blocks(self):
        project = f"projects/{self.pid}/project.json"
        local_only = f"projects/{self.pid}/local-only.json"
        migration = f"projects/{self.pid}/migrations/mig_X.json"
        workspace = "workspace.json"
        self.put(project, json.dumps({"name": "/home/someone/x", "ok": "relative/path"}))
        self.put(local_only, json.dumps({"files": [{"path": "C:\\data\\x"}]}))
        self.put(migration, json.dumps({"source": {"checkout_name": "~/x"}, "note": "at /Users/me/z now"}))
        self.put(workspace, json.dumps({"created_by": "/srv/x"}))
        report = safety.scan(self.ws, [project, local_only, migration, workspace])
        self.assertEqual([item["rule"] for item in report.block], ["PS-MANIFEST-PATH"] * 5)
        details = {item["path"]: item["detail"] for item in report.block}
        self.assertIn("/name", details[project])
        self.assertIn("/files/0/path", details[local_only])
        self.assertEqual(report.warn, [])  # a manifest is judged by the block rule alone
        self.assertNotIn("someone", json.dumps(report.to_dict()))

    def test_relative_manifests_and_non_manifest_json_pass(self):
        project = f"projects/{self.pid}/project.json"
        report = safety.scan(self.ws, [project])
        self.assertEqual(report.verdict, "ok")
        plan = self.put(self.plan("plan.json"), json.dumps({"root": "/srv/app"}))  # not a manifest, not a home path
        self.assertEqual(safety.scan(self.ws, [plan]).verdict, "ok")

    def test_invalid_json_manifest_is_not_a_path_finding(self):
        project = self.put(f"projects/{self.pid}/project.json", "{broken")
        self.assertEqual(safety.scan(self.ws, [project]).block, [])


class LayoutTests(SafetyCase):
    def test_entries_outside_the_layout_block(self):
        stray = self.put("stray.txt")
        loose = self.put("projects/loose.txt")
        bad_id = self.put("projects/prj_bad/project.json")
        scratch = self.put(f"projects/{self.pid}/scratch/x")
        nested_top = self.put("other/x.md")
        report = safety.scan(self.ws, [stray, loose, bad_id, scratch, nested_top])
        self.assertEqual(self.rules(report), sorted([("PS-TOP-LEVEL", stray), ("PS-PROJECT-LEVEL", loose),
                                                     ("PS-PROJECT-LEVEL", bad_id), ("PS-PROJECT-LEVEL", scratch),
                                                     ("PS-TOP-LEVEL", nested_top)]))

    def test_the_layout_files_pass(self):
        paths = [".gitignore", ".gitattributes", "workspace.json", "README.md", "projects/.gitkeep",
                 f"projects/{self.pid}/project.json", self.plan("plan.json"),
                 f"projects/{self.pid}/legacy-plans/x/a.md", f"projects/{self.pid}/migrations/mig_X.json",
                 f"projects/{self.pid}/local-only.json"]
        for path in paths[7:]:
            self.put(path, "{}")
        self.put(paths[6], "{}")
        self.assertEqual(safety.scan(self.ws, paths).block, [])

    def test_a_symlink_blocks_and_is_not_followed(self):
        target = self.put(self.plan("real.md"), TOKEN)
        link = self.plan("link.md")
        os.symlink("real.md", self.ws / link)
        dangling = self.plan("dangling.md")
        os.symlink("missing", self.ws / dangling)
        report = safety.scan(self.ws, [link, dangling])
        self.assertEqual(self.rules(report), sorted([("PS-SYMLINK", link), ("PS-SYMLINK", dangling)]))
        self.assertEqual(self.rules(safety.scan(self.ws, [target])), [("PS-SECRET", target)])

    def test_the_execute_bit_warns(self):
        script = self.put(self.plan("run.sh"), "echo hi\n", mode=0o755)
        plain = self.put(self.plan("plain.md"), "x", mode=0o644)
        report = safety.scan(self.ws, [script, plain])
        self.assertEqual(self.rules(report, "warn"), [("PS-EXECUTABLE", script)])
        self.assertIn("update-index --chmod=-x", report.warn[0]["detail"])
        self.assertEqual(report.block, [])

    def test_missing_files_and_directories_are_skipped(self):
        (self.ws / "projects" / self.pid / "plans" / "empty").mkdir(parents=True)
        report = safety.scan(self.ws, ["projects/none.txt", f"projects/{self.pid}/plans/empty"])
        self.assertEqual((report.files_checked, report.verdict), (0, "ok"))


class SizeTests(SafetyCase):
    def test_a_large_text_file_is_local_only_by_size(self):
        path = self.put(self.plan("big.log"), "x" * (6 * 1024 * 1024))
        report = safety.scan(self.ws, [path])
        self.assertEqual(report.local_only, [{"path": path, "bytes": 6 * 1024 * 1024, "reason": "size"}])
        self.assertEqual(report.verdict, "ok")
        self.report_valid(report)

    def test_a_large_binary_is_local_only_by_binary_and_a_small_one_is_not(self):
        big = self.put(self.plan("big.bin"), b"\0" + b"x" * (2 * 1024 * 1024), binary=True)
        small = self.put(self.plan("small.bin"), b"\0" + b"x" * (900 * 1024), binary=True)
        huge = self.put(self.plan("huge.bin"), b"\0" + b"x" * (6 * 1024 * 1024), binary=True)
        report = safety.scan(self.ws, [big, small, huge])
        self.assertEqual({item["path"]: item["reason"] for item in report.local_only}, {big: "binary", huge: "size"})

    def test_the_limits_are_inclusive(self):
        at = self.put(self.plan("at.txt"), "x" * 1000)
        over = self.put(self.plan("over.txt"), "x" * 1001)
        at_bin = self.put(self.plan("at.bin"), b"\0" * 100, binary=True)
        over_bin = self.put(self.plan("over.bin"), b"\0" * 101, binary=True)
        report = safety.scan(self.ws, [at, over, at_bin, over_bin], SMALL)
        self.assertEqual({item["path"] for item in report.local_only}, {over, over_bin})

    def test_a_local_only_file_is_not_scanned_for_content_but_its_name_still_counts(self):
        path = self.put(self.plan("dump.sql"), f"token {TOKEN}\n/home/me/x\n" + "x" * 2000)
        script = self.put(self.plan("big.sh"), "x" * 2000, mode=0o755)
        key = self.put(self.plan("big.pem"), "x" * 2000)
        report = safety.scan(self.ws, [path, script, key], SMALL)
        self.assertEqual(self.rules(report), [("PS-SECRET", key)])
        self.assertEqual(report.warn, [])
        self.assertEqual(len(report.local_only), 3)

    def test_the_limits_come_from_the_machine_configuration(self):
        config = self.root / "skm" / "config" / "config.toml"
        config.parent.mkdir(parents=True)
        config.write_text("schema_version = 1\n[workspace.publish]\nmax_tracked_bytes = 300\n"
                          "max_binary_tracked_bytes = 50\n", encoding="utf-8")
        self.assertEqual(safety.load_settings(), safety.Settings(300, 50))
        path = self.put(self.plan("mid.txt"), "x" * 400)
        self.assertEqual([item["path"] for item in safety.check(self.ws).local_only], [path])

    def test_default_limits(self):
        self.assertEqual(safety.load_settings(), safety.Settings(5242880, 1048576))

    def test_a_tracked_file_that_became_local_only_warns(self):
        path = self.put(self.plan("data.txt"), "small")
        git(self.ws, "add", "-A")
        git(self.ws, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "data")
        self.put(path, "x" * 2000)
        report = safety.scan(self.ws, [path], SMALL)
        self.assertEqual([item["path"] for item in report.local_only], [path])
        self.assertEqual(self.rules(report, "warn"), [("PS-TRACKED-LOCAL-ONLY", path)])
        self.assertEqual(report.verdict, "warn")
        untracked = self.put(self.plan("new.txt"), "x" * 2000)
        self.assertEqual(safety.scan(self.ws, [untracked], SMALL).warn, [])


class PathListTests(SafetyCase):
    def test_changed_paths_from_status(self):
        self.assertEqual(safety.changed_paths(self.ws), [])
        untracked = self.put(self.plan("new file ü.md"), "x")
        modified = f"projects/{self.pid}/project.json"
        (self.ws / modified).write_text("{}", encoding="utf-8")
        staged = self.put("README2.md", "x")
        git(self.ws, "add", staged)
        ignored = self.put(self.plan("note.tmp"), "x")
        self.assertEqual(safety.changed_paths(self.ws), sorted([untracked, modified, staged]))
        self.assertNotIn(ignored, safety.changed_paths(self.ws))

    def test_renames_and_deletions(self):
        git(self.ws, "mv", "README.md", "README-old.md")
        git(self.ws, "rm", "-q", ".gitattributes")
        paths = safety.changed_paths(self.ws)
        self.assertIn("README-old.md", paths)
        report = safety.scan(self.ws, paths)
        self.assertEqual(self.rules(report), [("PS-TOP-LEVEL", "README-old.md")])
        self.assertEqual(report.files_checked, 1)  # the file removed from the index and the disk is skipped

    def test_staged_content_is_checked_even_when_the_file_on_disk_is_clean_or_gone(self):
        edited = self.put(self.plan("edited.md"), f"key {TOKEN}\n")
        removed = self.put(self.plan("removed.md"), f"key {TOKEN}\n")
        git(self.ws, "add", edited, removed)
        (self.ws / edited).write_text("clean\n", encoding="utf-8")  # the commit still takes the staged blob
        (self.ws / removed).unlink()
        report = safety.check(self.ws)
        self.assertEqual(self.rules(report), sorted([("PS-SECRET", edited), ("PS-SECRET", removed)]))
        self.assertNotIn(TOKEN, json.dumps(report.to_dict()))

    def test_staged_symlink_and_mode_are_judged_by_the_index(self):
        link = f"projects/{self.pid}/plans/link"
        os.makedirs(self.ws / link.rsplit("/", 1)[0], exist_ok=True)
        os.symlink("elsewhere", self.ws / link)
        git(self.ws, "add", link)
        os.unlink(self.ws / link)
        self.put(self.plan("link"), "now a file")  # the disk differs from the index
        self.assertIn(("PS-SYMLINK", link), self.rules(safety.check(self.ws)))

    def test_a_name_that_is_not_utf8_is_still_inspected(self):
        folder = os.fsencode(self.ws / "projects" / self.pid / "plans")
        os.makedirs(folder, exist_ok=True)
        raw = folder + b"/caf\xe9.md"
        with open(raw, "wb") as handle:
            handle.write(f"key {TOKEN}\n".encode())
        rel = os.fsdecode(raw[len(os.fsencode(self.ws)) + 1:])
        self.assertIn(rel, safety.changed_paths(self.ws))
        self.assertIn(rel, safety.all_paths(self.ws))
        report = safety.check(self.ws)
        self.assertEqual([item["rule"] for item in report.block], ["PS-SECRET"])
        self.assertEqual(report.files_checked, 1)
        self.assertIn("caf\\xe9.md", report.block[0]["path"])  # printable, not a lone surrogate
        json.dumps(report.to_dict(), ensure_ascii=False).encode("utf-8")
        git(self.ws, "add", "-A")
        self.assertEqual([item["rule"] for item in safety.check(self.ws).block], ["PS-SECRET"])

    def test_all_paths_lists_tracked_and_untracked_but_not_ignored(self):
        untracked = self.put(self.plan("new.md"), "x")
        self.put(self.plan("skip.tmp"), "x")
        listed = safety.all_paths(self.ws)
        for expected in (".gitignore", ".gitattributes", "workspace.json", "README.md", "projects/.gitkeep",
                         f"projects/{self.pid}/project.json", untracked):
            self.assertIn(expected, listed)
        self.assertNotIn(self.plan("skip.tmp"), listed)
        self.assertEqual(listed, sorted(listed))

    def test_the_default_check_looks_at_the_next_commit_and_all_looks_at_everything(self):
        self.assertEqual(safety.check(self.ws).files_checked, 0)
        full = safety.check(self.ws, every_file=True)
        self.assertEqual((full.files_checked, full.verdict), (6, "ok"))  # init's 5 files and the project record

    def test_a_folder_that_is_not_a_repository(self):
        from aicore.workspace import WorkspaceError
        with self.assertRaises(WorkspaceError):
            safety.check(self.root / "home")


class CommandTests(SafetyCase):
    def test_a_clean_workspace_is_ok_and_exits_zero(self):
        code, out, err = self.run_cli("doctor", "--publish-safety", "--json")
        document = json.loads(out)
        self.assertEqual((code, err, document["verdict"], document["files_checked"]), (0, "", "ok", 0))
        self.report_valid(document)

    def test_a_block_exits_one_prints_the_report_and_names_publish_blocked(self):
        self.put(self.plan("notes.md"), f"key {TOKEN}\n")
        code, out, err = self.run_cli("doctor", "--publish-safety", "--json")
        self.assertEqual(code, 1)
        document = self.report_valid(json.loads(out))
        self.assertEqual((document["verdict"], document["block"][0]["rule"]), ("block", "PS-SECRET"))
        self.assertTrue(err.startswith("PUBLISH_BLOCKED: "), err)
        self.assertNotIn(TOKEN, out + err)

    def test_warnings_and_local_only_do_not_fail(self):
        self.put(self.plan("p.json"), '{"a": "/home/me/x"}')
        self.put(self.plan("big.log"), "x" * (6 * 1024 * 1024))
        code, out, _ = self.run_cli("doctor", "--publish-safety")
        self.assertEqual(code, 0)
        self.assertIn("publish-safety: warn", out)
        self.assertIn("[warn] PS-HOME-PATH", out)
        self.assertIn("[local-only]", out)
        self.assertIn("(size, 6291456 bytes)", out)

    def test_text_output_shows_the_line_and_never_the_secret(self):
        self.put(self.plan("notes.md"), f"a\nb\n{TOKEN}\n")
        code, out, err = self.run_cli("doctor", "--publish-safety")
        self.assertEqual(code, 1)
        self.assertIn("[block] PS-SECRET", out)
        self.assertIn("notes.md:3", out)
        self.assertNotIn(TOKEN, out + err)

    def test_all_covers_files_already_committed(self):
        self.put(self.plan("old.md"), f"key {TOKEN}\n")
        git(self.ws, "add", "-A")
        git(self.ws, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "oops")
        self.assertEqual(self.run_cli("doctor", "--publish-safety")[0], 0)
        code, out, _ = self.run_cli("doctor", "--publish-safety", "--all", "--json")
        self.assertEqual((code, json.loads(out)["verdict"]), (1, "block"))

    def test_all_alone_is_a_usage_error_and_a_missing_workspace_is_refused(self):
        code, _, err = self.run_cli("doctor", "--all")
        self.assertEqual(code, 2)
        self.assertIn("--publish-safety", err)
        os.environ["SKM_WORKSPACE"] = "no-workspace"
        code, _, err = self.run_cli("doctor", "--publish-safety")
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("WORKSPACE_NOT_INITIALIZED: "), err)

    def test_plain_doctor_is_unchanged(self):
        code, out, _ = self.run_cli("doctor", "--json")
        self.assertEqual((code, set(json.loads(out))), (0, {"checks"}))
        self.assertIsInstance(doctor.publish_safety(), safety.Report)


class ReportTests(SafetyCase):
    def test_verdicts_and_the_document(self):
        self.assertEqual(safety.Report().verdict, "ok")
        self.assertEqual(safety.Report(warn=[{"rule": "PS-EXECUTABLE", "path": "a", "detail": "d"}]).verdict, "warn")
        both = safety.Report(block=[{"rule": "PS-SYMLINK", "path": "a", "detail": "d"}],
                             warn=[{"rule": "PS-EXECUTABLE", "path": "b", "detail": "d"}],
                             local_only=[{"path": "z", "bytes": 1, "reason": "size"}, {"path": "a", "bytes": 2, "reason": "binary"}])
        document = self.report_valid(both)
        self.assertEqual((document["verdict"], [item["path"] for item in document["local_only"]]), ("block", ["a", "z"]))
        self.assertEqual(document["$schema"], "urn:swissknifeman:workspace:publish-report:v1")

    def test_the_schema_rejects_absolute_paths_and_unknown_fields(self):
        registry, kind = schema.load_contract(REPORT_SCHEMA, urn_prefix="urn:swissknifeman:workspace:")
        good = safety.Report().to_dict()
        for broken in (dict(good, extra=1), dict(good, verdict="fine"),
                       dict(good, block=[{"rule": "PS-SYMLINK", "path": "/home/me/x", "detail": "d"}]),
                       dict(good, block=[{"rule": "secret", "path": "a", "detail": "d"}]),
                       dict(good, local_only=[{"path": "a", "bytes": 1, "reason": "huge"}])):
            self.assertNotEqual(schema.validate(broken, kind, registry), [])

    def test_the_contract_is_registered_in_the_unit(self):
        unit = json.loads((MODULE_ROOT / "unit.json").read_text(encoding="utf-8"))
        ids = {item["id"]: item["path"] for item in unit["provides"]["contracts"]}
        self.assertEqual(ids["urn:swissknifeman:workspace:publish-report"], "schemas/publish-report/v1")


if __name__ == "__main__":
    unittest.main()
