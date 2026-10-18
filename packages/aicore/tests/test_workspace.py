"""The workspace package: ids, codes, remotes, documents, bindings and the plan-store resolution (with the shared vectors)."""
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from aicore import workspace as ws
from aicore.state import locations
from aicore.workspace import bindings as bindings_module
from aicore.workspace import documents

VECTORS = Path(__file__).resolve().parent.parent / "schemas" / "workspace" / "v1" / "resolution-vectors.json"
PRJ = "billium"
OTHER = "commerz"
WS = "axioma"


def substitute(node, tmp):
    if isinstance(node, str):
        return node.replace("{tmp}", tmp)
    if isinstance(node, list):
        return [substitute(item, tmp) for item in node]
    if isinstance(node, dict):
        return {substitute(key, tmp): substitute(value, tmp) for key, value in node.items()}
    return node


class Sandbox(unittest.TestCase):
    """A temporary directory and an environment that never reaches the real home or the real workspace."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = os.path.realpath(self._tmp.name)
        self.env = {"SKM_HOME": self.tmp + "/home", "SKM_WORKSPACES_ROOT": self.tmp + "/wss", "SKM_WORKSPACE": WS,
                    "HOME": self.tmp + "/h"}

    def write(self, relative, text=""):
        path = Path(self.tmp) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class LinksExcludeTests(Sandbox):
    def repo(self):
        root = Path(self.tmp) / "repo"
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        return root

    def test_the_block_lists_exactly_the_names_and_keeps_the_other_lines(self):
        from aicore.workspace import links
        root = self.repo()
        exclude = root / ".git" / "info" / "exclude"
        exclude.write_text("*.log\n", encoding="utf-8")
        self.assertEqual(links.write_exclude(root, ["tasks", "plans"]), exclude)
        self.assertEqual(links.read_exclude(root), ["plans", "tasks"])
        links.write_exclude(root, ["plans"])
        self.assertEqual(links.read_exclude(root), ["plans"])
        self.assertTrue(exclude.read_text(encoding="utf-8").startswith("*.log\n"))
        links.write_exclude(root, [])
        self.assertEqual(exclude.read_text(encoding="utf-8"), "*.log\n")
        before = exclude.stat().st_mtime_ns
        links.write_exclude(root, [])  # no block, no names: not touched
        self.assertEqual(exclude.stat().st_mtime_ns, before)

    def test_a_half_block_is_refused_and_a_folder_that_is_not_a_repository_is_skipped(self):
        from aicore.workspace import links
        root = self.repo()
        exclude = root / ".git" / "info" / "exclude"
        exclude.write_text(links.BEGIN + "\n/plans\n", encoding="utf-8")
        with self.assertRaises(ws.WorkspaceError) as caught:
            links.write_exclude(root, ["plans"])
        self.assertEqual(caught.exception.code, "LINKS_EXCLUDE_INVALID")
        self.assertEqual(links.read_exclude(root), [])
        plain = Path(self.tmp) / "plain"
        plain.mkdir()
        self.assertIsNone(links.write_exclude(plain, ["plans"]))
        self.assertEqual(links.read_exclude(plain), [])

    def test_inspect_folder_tells_the_four_states_apart(self):
        project = Path(self.tmp) / "wss" / WS / "projects" / PRJ
        (project / "plans").mkdir(parents=True)
        root = Path(self.tmp) / "co"
        root.mkdir()
        self.assertEqual(ws.inspect_folder(root, "plans", project)["state"], "absent")
        os.symlink(project / "plans", root / "plans")
        found = ws.inspect_folder(root, "plans", project)
        self.assertEqual((found["state"], found["dangling"]), ("linked", False))
        (root / "other").mkdir()
        os.symlink(root / "other", root / "tasks")
        self.assertEqual(ws.inspect_folder(root, "tasks", project)["state"], "foreign")
        os.unlink(root / "tasks")
        (root / "tasks").mkdir()
        self.assertEqual(ws.inspect_folder(root, "tasks", project)["state"], "real")
        (project / "plans").rmdir()
        self.assertEqual(ws.inspect_folder(root, "plans", project)["dangling"], True)
        with self.assertRaises(ValueError):
            ws.inspect_folder(root, "docs", project)


class ResolutionVectorTests(Sandbox):
    def test_the_vector_file_is_complete(self):
        data = json.loads(VECTORS.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["vectors"]), 10)
        names = [vector["name"] for vector in data["vectors"]]
        self.assertEqual(len(names), len(set(names)))
        for vector in data["vectors"]:
            self.assertIn(vector["op"], ("resolve", "source_root"), vector["name"])

    def test_every_vector(self):
        for vector in json.loads(VECTORS.read_text(encoding="utf-8"))["vectors"]:
            with self.subTest(vector=vector["name"]), tempfile.TemporaryDirectory() as raw:
                tmp = os.path.realpath(raw)
                for relative, text in vector["files"].items():
                    path = Path(tmp) / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(substitute(text, tmp), encoding="utf-8")
                env = substitute(vector["env"], tmp)
                expect = substitute(vector["expect"], tmp)
                if vector["op"] == "resolve":
                    self.check_resolve(substitute(vector["project_root"], tmp), env, expect)
                else:
                    self.check_source_root(substitute(vector["plan_dir"], tmp), env, expect,
                                           substitute(vector.get("launcher"), tmp))

    def check_resolve(self, root, env, expect):
        if "error" in expect:
            with self.assertRaises(ws.WorkspaceError) as caught:
                ws.resolve_plans_store(root, env=env)
            self.assertEqual(caught.exception.code, expect["error"])
            return
        got = ws.resolve_plans_store(root, env=env)
        self.assertEqual((got.kind, str(got.plans_root), got.project_id, got.reason),
                         (expect["kind"], expect["plans_root"], expect["project_id"], expect["reason"]))

    def check_source_root(self, plan_dir, env, expect, launcher):
        if "error" in expect:
            with self.assertRaises(ws.WorkspaceError) as caught:
                ws.source_root_of(plan_dir, env=env, launcher=launcher)
            self.assertEqual(caught.exception.code, expect["error"])
            return
        got = ws.source_root_of(plan_dir, env=env, launcher=launcher)
        self.assertEqual(None if got is None else str(got), expect["source_root"])

    def test_resolution_creates_nothing(self):
        self.write("proj/.swissknifeman/project.json", json.dumps(
            {"$schema": "urn:swissknifeman:aicore:project-marker:v1", "workspace": WS, "project_id": PRJ,
             "plans_store": "legacy"}))
        before = sorted(str(p) for p in Path(self.tmp).rglob("*"))
        ws.resolve_plans_store(self.tmp + "/proj", env=self.env)
        ws.source_root_of(self.tmp + "/proj/plans/p1", env=self.env)
        self.assertEqual(sorted(str(p) for p in Path(self.tmp).rglob("*")), before)

    def test_legacy_plans_present(self):
        root = self.tmp + "/proj"
        self.assertFalse(ws.legacy_plans_present(root))
        self.write("proj/plans/notes.md", "x")
        self.write("proj/plans/empty/readme.md", "x")
        self.assertFalse(ws.legacy_plans_present(root))
        self.write("proj/plans/p1/plan.json", "{}")
        self.assertTrue(ws.legacy_plans_present(root))

    def test_a_plans_link_into_the_bound_workspace_is_not_legacy(self):
        self.write("proj/.swissknifeman/project.json", json.dumps(
            {"$schema": "urn:swissknifeman:aicore:project-marker:v1", "workspace": WS, "project_id": PRJ,
             "plans_store": "workspace"}))
        self.write(f"wss/{WS}/projects/{PRJ}/plans/p1/plan.json", "{}")
        root = self.tmp + "/proj"
        os.symlink(f"{self.tmp}/wss/{WS}/projects/{PRJ}/plans", root + "/plans")
        self.assertTrue(ws.is_workspace_link(root, "plans", env=self.env))
        self.assertFalse(ws.legacy_plans_present(root, env=self.env))
        os.unlink(root + "/plans")
        self.write("other/p1/plan.json", "{}")
        os.symlink(self.tmp + "/other", root + "/plans")
        self.assertFalse(ws.is_workspace_link(root, "plans", env=self.env))
        self.assertTrue(ws.legacy_plans_present(root, env=self.env))
        os.unlink(root + "/plans")
        self.write(f"wss/{WS}/projects/{OTHER}/plans/p1/plan.json", "{}")
        os.symlink(f"{self.tmp}/wss/{WS}/projects/{OTHER}/plans", root + "/plans")  # another project of the workspace
        self.assertFalse(ws.is_workspace_link(root, "plans", env=self.env))
        self.assertTrue(ws.legacy_plans_present(root, env=self.env))

    def test_without_a_usable_marker_no_link_is_a_workspace_link(self):
        root = self.tmp + "/proj"
        self.write("wss/axioma/projects/billium/plans/p1/plan.json", "{}")
        os.makedirs(root)
        os.symlink(f"{self.tmp}/wss/{WS}/projects/{PRJ}/plans", root + "/plans")
        self.assertFalse(ws.is_workspace_link(root, "plans", env=self.env))
        self.assertTrue(ws.legacy_plans_present(root, env=self.env))
        self.write("proj/.swissknifeman/project.json", "{broken")
        self.assertFalse(ws.is_workspace_link(root, "plans", env=self.env))
        self.assertTrue(ws.legacy_plans_present(root, env=self.env))

    def test_the_launcher_of_this_process_is_used_by_default(self):
        self.write("co1/.swissknifeman/project.json", json.dumps(
            {"$schema": "urn:swissknifeman:aicore:project-marker:v1", "workspace": WS, "project_id": PRJ,
             "plans_store": "workspace"}))
        env = dict(self.env, SKM_LAUNCHER_ACTIVE="1", SKM_LAUNCHER_PROJECT_ROOT=self.tmp + "/co1",
                   SKM_LAUNCHER_PID=str(os.getpid()))
        plan = self.tmp + "/wss/%s/projects/%s/plans/p1" % (WS, PRJ)
        self.assertEqual(ws.source_root_of(plan, env=env), Path(self.tmp + "/co1"))


class CodeTests(Sandbox):
    def test_codes(self):
        for good in ("a", "axioma", "billium", "skm-wt", "p2p", "a1-b2-c3", "a" * 40):
            self.assertTrue(ws.is_code(good), good)
        for bad in (None, 5, "", "A", "Axioma", "1a", "a_b", "a--b", "a-", "-a", "a b", "a/b", "..", "a" * 41,
                    "prj_01JC0Z8Q3M5T7V9XABCDEFGHJM"):
            self.assertFalse(ws.is_code(bad), bad)

    def test_the_layout_of_a_machine(self):
        env = {"SKM_HOME": self.tmp + "/home"}
        base = Path(self.tmp) / "home" / "workspaces"
        self.assertEqual(locations.workspaces_root(env), base)
        self.assertEqual(locations.workspace_root(env, code="axioma"), base / "axioma")
        self.assertEqual(locations.workspace_state_dir(env, code="axioma"),
                         Path(self.tmp) / "home" / "state" / "workspaces" / "axioma")
        with self.assertRaises(locations.WorkspaceSelectionError) as caught:
            locations.selected_workspace(env)
        self.assertEqual(caught.exception.code, "WORKSPACE_NOT_FOUND")
        for code in ("axioma", "other"):
            self.write("home/workspaces/%s/workspace.json" % code, "{}")
        self.write("home/workspaces/not-a-workspace/readme", "x")
        self.assertEqual(locations.list_workspaces(env), ["axioma", "other"])
        with self.assertRaises(locations.WorkspaceSelectionError) as caught:
            locations.selected_workspace(env)
        self.assertEqual(caught.exception.code, "WORKSPACE_AMBIGUOUS")
        self.assertEqual(locations.selected_workspace(dict(env, SKM_WORKSPACE="other")), "other")
        self.assertEqual(locations.workspace_root(dict(env, SKM_WORKSPACE="other")), base / "other")

    def test_a_single_workspace_is_selected_without_a_choice(self):
        env = {"SKM_HOME": self.tmp + "/home"}
        self.write("home/workspaces/axioma/workspace.json", "{}")
        self.assertEqual(locations.selected_workspace(env), "axioma")

    def test_bad_values_are_refused(self):
        env = {"SKM_HOME": self.tmp + "/home"}
        for call in (lambda: locations.workspace_root(env, code="../x"),
                     lambda: locations.selected_workspace(dict(env, SKM_WORKSPACE="Bad")),
                     lambda: locations.workspaces_root(dict(env, SKM_WORKSPACES_ROOT="relative"))):
            with self.assertRaises(ValueError):
                call()


class IdTests(unittest.TestCase):
    def test_shape_and_time_order(self):
        first = ws.new_id("prj", now_ms=1_000, rand=bytes(10))
        later = ws.new_id("prj", now_ms=2_000, rand=bytes(10))
        self.assertRegex(first, r"^prj_[0-9A-HJKMNP-TV-Z]{26}$")
        self.assertEqual(first[4:14], "00000000Z8")
        self.assertLess(first, later)
        self.assertEqual(first[14:], "0" * 16)

    def test_random_part_and_uniqueness(self):
        ids = {ws.new_id("dev") for _ in range(200)}
        self.assertEqual(len(ids), 200)
        self.assertEqual(ws.new_id("ws", now_ms=0, rand=b"\xff" * 10)[-16:], "ZZZZZZZZZZZZZZZZ")

    def test_is_id(self):
        value = ws.new_id("mig")
        self.assertTrue(ws.is_id(value, "mig"))
        self.assertFalse(ws.is_id(value, "prj"))
        for bad in (None, 5, "mig_", value.lower(), value + "0", value[:-1] + "U", "mig_" + "I" * 26):
            self.assertFalse(ws.is_id(bad, "mig"), bad)

    def test_bad_arguments(self):
        for kwargs in ({"prefix": "Bad"}, {"prefix": "prj", "rand": b"123"}, {"prefix": "prj", "now_ms": -1},
                       {"prefix": "prj", "now_ms": 1 << 48}):
            with self.assertRaises(ValueError):
                ws.new_id(**kwargs)


class RemoteTests(unittest.TestCase):
    TARGET = "github.com/academici/swissknifeman"

    def test_the_contract_examples(self):
        for url in ("git@github.com:academici/swissknifeman.git", "https://github.com/academici/swissknifeman.git",
                    "ssh://git@github.com/academici/swissknifeman.git", "https://token@github.com/academici/swissknifeman",
                    "https://user:secret@GitHub.com/academici/swissknifeman/", "git://github.com/academici/swissknifeman.git",
                    "ssh://git@github.com:2222/academici/swissknifeman.git", "http://github.com/academici/swissknifeman.git/",
                    "  git@github.com:academici/swissknifeman  "):
            with self.subTest(url=url):
                self.assertEqual(ws.normalize_remote(url), self.TARGET)

    def test_local_remotes_are_not_an_identity(self):
        for url in ("/srv/x.git", "file:///srv/x.git", "../x.git", "~/x.git", "C:\\repos\\x", "", "   ", "plain", "https://",
                    "https://github.com", "git@github.com:"):
            with self.subTest(url=url):
                self.assertIsNone(ws.normalize_remote(url))

    def test_path_case_is_kept_and_host_is_lowered(self):
        self.assertEqual(ws.normalize_remote("git@Example.COM:Owner/Repo.git"), "example.com/Owner/Repo")

    def test_normalized_remotes_fit_the_project_contract(self):
        for url in ("git@github.com:a/b.git", "https://gitlab.example.com:8443/team/sub/repo.git"):
            document = {"$schema": "urn:swissknifeman:aicore:workspace-project:v1", "project_id": PRJ, "name": "x",
                        "created_at": "2026-10-17T09:30:00Z", "identity": {"remotes": [ws.normalize_remote(url)]},
                        "aliases": [], "status": "active"}
            self.assertEqual(ws.validate_document("workspace-project", document), [], url)

    def test_redact_remote(self):
        self.assertEqual(ws.redact_remote("https://user:tok@github.com/a/b.git"), "https://github.com/a/b.git")
        self.assertEqual(ws.redact_remote("ssh://git@github.com/a/b.git"), "ssh://github.com/a/b.git")
        self.assertEqual(ws.redact_remote("git@github.com:a/b.git"), "github.com:a/b.git")
        self.assertEqual(ws.redact_remote("https://github.com/a/b.git"), "https://github.com/a/b.git")
        self.assertEqual(ws.redact_remote("/srv/x.git"), "/srv/x.git")

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_checkout_remotes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(ws.checkout_remotes(tmp), [])
            subprocess.run(["git", "-C", tmp, "init", "-q"], check=True, capture_output=True)
            self.assertEqual(ws.checkout_remotes(tmp), [])
            for name, url in (("origin", "git@github.com:academici/swissknifeman.git"),
                              ("mirror", "https://tok@github.com/academici/swissknifeman"),
                              ("backup", "/srv/backup.git"), ("other", "https://gitlab.com/a/b.git")):
                subprocess.run(["git", "-C", tmp, "remote", "add", name, url], check=True, capture_output=True)
            self.assertEqual(ws.checkout_remotes(tmp), [self.TARGET, "gitlab.com/a/b"])
        self.assertEqual(ws.checkout_remotes(Path(tmp) / "missing"), [])


class DocumentTests(Sandbox):
    def test_marker_round_trip(self):
        root = self.tmp + "/proj"
        self.assertIsNone(ws.read_marker(root))
        written = ws.write_marker(root, WS, PRJ, "legacy")
        self.assertEqual(written, {"$schema": "urn:swissknifeman:aicore:project-marker:v1", "workspace": WS,
                                   "project_id": PRJ, "plans_store": "legacy"})
        self.assertEqual(ws.read_marker(root), written)
        self.assertTrue((Path(root) / ws.MARKER_RELPATH).read_text(encoding="utf-8").endswith("}\n"))
        ws.write_marker(root, WS, PRJ, "workspace")
        self.assertEqual(ws.read_marker(root)["plans_store"], "workspace")

    def test_invalid_markers(self):
        root = Path(self.tmp) / "proj"
        for text in ("", "{not json", "[]", "5", "null", json.dumps({"project_id": PRJ, "plans_store": "legacy"}),
                     json.dumps({"$schema": "urn:swissknifeman:aicore:project-marker:v1", "project_id": PRJ,
                                 "plans_store": "legacy"}),  # no workspace
                     json.dumps({"$schema": "urn:swissknifeman:aicore:project-marker:v1", "workspace": WS,
                                 "project_id": "prj_01JC0Z8Q3M5T7V9XABCDEFGHJM", "plans_store": "legacy"})):
            with self.subTest(text=text):
                self.write("proj/" + ws.MARKER_RELPATH, text)
                with self.assertRaises(ws.WorkspaceError) as caught:
                    ws.read_marker(root)
                self.assertEqual(caught.exception.code, "PROJECT_MARKER_INVALID")

    def test_a_marker_that_is_a_directory_is_invalid(self):
        (Path(self.tmp) / "proj" / ws.MARKER_RELPATH).mkdir(parents=True)
        with self.assertRaises(ws.WorkspaceError) as caught:
            ws.read_marker(self.tmp + "/proj")
        self.assertEqual(caught.exception.code, "PROJECT_MARKER_INVALID")

    def test_marker_writes_refuse_bad_values_and_leave_nothing(self):
        for workspace, project_id, store in (("Bad_Id", PRJ, "legacy"), (WS, "Bad_Id", "legacy"), (WS, PRJ, "cloud")):
            with self.assertRaises(ValueError):
                ws.write_marker(self.tmp + "/proj", workspace, project_id, store)
        self.assertFalse((Path(self.tmp) / "proj").exists())

    def test_workspace_and_project_documents(self):
        root = self.tmp + "/wss/axioma"
        self.assertIsNone(ws.read_workspace(root))
        self.assertIsNone(ws.read_project(root, PRJ))
        device = ws.new_id("dev")
        created = ws.write_workspace(root, WS, ws.new_id("ws"), device)
        self.assertEqual(ws.read_workspace(root), created)
        self.assertEqual((created["layout"], created["code"]), (2, WS))
        project = ws.write_project(root, PRJ, "swissknifeman", remotes=["github.com/a/b"], aliases=["skm"])
        self.assertEqual(ws.read_project(root, PRJ), project)
        self.assertEqual(project["identity"], {"remotes": ["github.com/a/b"]})
        self.assertEqual(project["status"], "active")
        self.assertEqual(ws.project_dir(root, PRJ), Path(root) / "projects" / PRJ)

    def test_damaged_workspace_documents_are_layout_errors(self):
        self.write("ws/workspace.json", "{broken")
        self.write("ws/projects/%s/project.json" % PRJ, "[]")
        for call in (lambda: ws.read_workspace(self.tmp + "/ws"), lambda: ws.read_project(self.tmp + "/ws", PRJ)):
            with self.assertRaises(ws.WorkspaceError) as caught:
                call()
            self.assertEqual(caught.exception.code, "WORKSPACE_LAYOUT_INVALID")

    def test_portable_documents_hold_no_absolute_path(self):
        root = self.tmp + "/ws"
        for name in ("/home/u/skm", "~/skm", "C:\\Users\\u\\skm", "D:/skm"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    ws.write_project(root, PRJ, name)
                with self.assertRaises(ValueError):
                    ws.write_project(root, PRJ, "ok", aliases=[name])
        self.assertFalse((Path(root) / "projects").exists())

    def test_the_validator_finds_an_absolute_path_in_any_string(self):
        document = {"$schema": "urn:swissknifeman:aicore:workspace-migration:v1", "op_id": "mig_" + "0" * 26}
        issues = ws.validate_document("workspace-migration", dict(document, extra="/home/u"))
        self.assertTrue(any(issue.startswith("PORTABLE_ABSOLUTE_PATH: /extra") for issue in issues), issues)

    def test_project_ids_are_checked_before_a_path_is_built(self):
        for bad in ("../x", "prj_x", "", "Billium", "-x", "a--b", "a" * 41):
            with self.assertRaises(ValueError):
                ws.project_dir(self.tmp, bad)

    def test_device_file(self):
        self.assertIsNone(ws.read_device(self.env))
        written = ws.write_device(ws.new_id("dev"), "machine-a", env=self.env)
        self.assertEqual(ws.read_device(self.env), written)
        self.assertTrue((Path(self.tmp) / "home" / "state" / "workspaces" / "device.json").is_file())


class BindingTests(Sandbox):
    def make(self, name):
        path = Path(self.tmp) / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def test_empty_bindings(self):
        self.assertEqual(ws.read_bindings(self.env),
                         {"$schema": "urn:swissknifeman:aicore:workspace-bindings:v1", "projects": {}})
        self.assertFalse(ws.bindings_path(self.env).exists())

    def test_bind_stores_the_real_path_and_the_first_checkout_is_primary(self):
        first, second = self.make("one"), self.make("two")
        link = Path(self.tmp) / "link"
        link.symlink_to(first)
        entry = ws.bind(PRJ, link, self.env)
        self.assertEqual(entry["paths"], [str(first)])
        self.assertEqual(entry["primary"], str(first))
        again = ws.bind(PRJ, first, self.env)
        self.assertEqual(again["paths"], [str(first)])
        entry = ws.bind(PRJ, second, self.env)
        self.assertEqual((entry["paths"], entry["primary"]), ([str(first), str(second)], str(first)))
        self.assertEqual(ws.read_bindings(self.env)["projects"][PRJ], entry)
        self.assertEqual(ws.validate_document("workspace-bindings", ws.read_bindings(self.env)), [])

    def test_a_missing_primary_is_replaced_by_the_new_checkout(self):
        gone, fresh = self.make("gone"), self.make("fresh")
        ws.bind(PRJ, gone, self.env)
        shutil.rmtree(gone)
        entry = ws.bind(PRJ, fresh, self.env)
        self.assertEqual(entry["primary"], str(fresh))
        self.assertEqual(entry["paths"], [str(gone), str(fresh)])

    def test_unbind(self):
        first, second = self.make("one"), self.make("two")
        ws.bind(PRJ, first, self.env)
        ws.bind(PRJ, second, self.env)
        self.assertFalse(ws.unbind(PRJ, self.tmp + "/other", self.env))
        self.assertFalse(ws.unbind(OTHER, None, self.env))
        self.assertTrue(ws.unbind(PRJ, first, self.env))
        entry = ws.read_bindings(self.env)["projects"][PRJ]
        self.assertEqual((entry["paths"], entry["primary"]), ([str(second)], str(second)))
        self.assertTrue(ws.unbind(PRJ, second, self.env))
        self.assertEqual(ws.read_bindings(self.env)["projects"], {})
        ws.bind(PRJ, first, self.env)
        self.assertTrue(ws.unbind(PRJ, None, self.env))
        self.assertEqual(ws.read_bindings(self.env)["projects"], {})

    def test_set_paths(self):
        first, second, third = self.make("one"), self.make("two"), self.make("three")
        ws.bind(PRJ, first, self.env)
        stamp = ws.read_bindings(self.env)["projects"][PRJ]["bound_at"]
        entry = ws.set_paths(PRJ, [second, third, second], self.env)
        self.assertEqual((entry["paths"], entry["primary"], entry["bound_at"]), ([str(second), str(third)], str(second), stamp))
        entry = ws.set_paths(PRJ, [third, second], self.env)
        self.assertEqual(entry["primary"], str(second))
        self.assertIsNone(ws.set_paths(PRJ, [], self.env))
        self.assertEqual(ws.read_bindings(self.env)["projects"], {})

    def test_bad_project_ids(self):
        for call in (lambda: ws.bind("Bad_Id", self.tmp, self.env), lambda: ws.unbind("Bad_Id", None, self.env),
                     lambda: ws.set_paths("Bad_Id", [self.tmp], self.env)):
            with self.assertRaises(ValueError):
                call()

    def test_a_damaged_file_is_a_layout_error_and_is_not_overwritten(self):
        path = ws.bindings_path(self.env)
        path.parent.mkdir(parents=True)
        path.write_text("{broken", encoding="utf-8")
        for call in (lambda: ws.read_bindings(self.env), lambda: ws.bind(PRJ, self.tmp, self.env)):
            with self.assertRaises(ws.WorkspaceError) as caught:
                call()
            self.assertEqual(caught.exception.code, "WORKSPACE_LAYOUT_INVALID")
        self.assertEqual(path.read_text(encoding="utf-8"), "{broken")

    def test_the_lock_times_out(self):
        import fcntl
        folder = ws.bindings_path(self.env).parent
        folder.mkdir(parents=True)
        fd = os.open(str(folder / "bindings.json.lock"), os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        with self.assertRaises(ws.WorkspaceError) as caught:
            ws.bind(PRJ, self.tmp, self.env, timeout_s=0.2)
        self.assertEqual(caught.exception.code, "WORKSPACE_BINDINGS_LOCKED")
        self.assertFalse(ws.bindings_path(self.env).exists())
        self.assertEqual(ws.read_bindings(self.env)["projects"], {})  # readers take no lock

    def test_the_default_lock_timeout_is_ten_seconds(self):
        self.assertEqual(bindings_module.LOCK_TIMEOUT_S, 10.0)

    def test_concurrent_writers_lose_nothing(self):
        paths = [self.make("co%d" % index) for index in range(8)]
        errors = []

        def work(path):
            try:
                ws.bind(PRJ, path, self.env)
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(exc)

        threads = [threading.Thread(target=work, args=(path,)) for path in paths]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(sorted(ws.read_bindings(self.env)["projects"][PRJ]["paths"]), sorted(str(p) for p in paths))

    def test_the_machine_file_may_hold_absolute_paths_and_the_workspace_may_not(self):
        ws.bind(PRJ, self.make("one"), self.env)
        self.assertEqual(ws.validate_document("workspace-bindings", ws.read_bindings(self.env)), [])
        self.assertIn("workspace-bindings", documents.MACHINE_KINDS)


if __name__ == "__main__":
    unittest.main()
