"""ConfigService: modules, view with provenance, preview without side effects, commit with CAS, lock and audit."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aicore.state import machine_config_file, project_config_file
from aicore.util.digest import sha256_tagged

from gui import contracts, settings
from gui.core.config import ConfigService, PreviewRecord, PreviewStore
from gui.errors import GuiError

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "units"
SECRET_VALUE_SENTINEL = "s3cr3t-value-of-the-test-0123456789"
MUTATION = "urn:swissknifeman:gui:config-mutation:v1"
EMPTY = sha256_tagged(b"")


def request(layer, patch, revision, module="config-demo", kind="preview_request"):
    return {"$schema": MUTATION, "kind": kind, "module": module, "layer": layer, "expected_revision": revision,
            "patch": patch}


def set_op(key, value):
    return {"op": "set", "key": key, "value": value}


def unset_op(key):
    return {"op": "unset", "key": key}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class ServiceCase(unittest.TestCase):
    units = "config-demo"

    def setUp(self):
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "home").mkdir()
        self.env = {"HOME": str(self.tmp / "home"), "SKM_HOME": str(self.tmp / "skm"), "PATH": os.environ["PATH"],
                    "SKM_UNITS_PATH": str(FIXTURES / self.units), "SKM_TEST_SECRET": SECRET_VALUE_SENTINEL}
        self.root = self.tmp / "proj"
        (self.root / ".git").mkdir(parents=True)
        self.clock = Clock()
        self.audits = []
        self.project_events = []
        self.machine_events = []
        self.timeout = 5.0
        self.service = self.make()
        self.machine = Path(machine_config_file(env=self.env))
        self.project = Path(project_config_file(self.root))

    def make(self, env=None):
        config = settings.Config(lock_timeout_s=self.timeout, preview_ttl_s=600)
        return ConfigService(env or self.env, lambda: settings.Config(self.timeout, config.preview_ttl_s),
                             audit=lambda *args: self.audits.append(args),
                             emit_project=lambda *args: self.project_events.append(args),
                             emit_machine=lambda *args: self.machine_events.append(args), clock=self.clock)

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def revision(self, path):
        return sha256_tagged(path.read_bytes() if path.exists() else b"")

    def view(self, project=True, service=None):
        document = (service or self.service).view("config-demo", str(self.root) if project else None,
                                                  "proj-1" if project else None)
        self.assertEqual([], contracts.validate(document, "config-view"))
        return document

    def entry(self, document, key):
        return next(entry for entry in document["entries"] if entry["key"] == key)

    def preview(self, layer, patch, project=True, revision=None, service=None):
        path = self.machine if layer == "machine" else self.project
        body = request(layer, patch, revision or self.revision(path))
        document = (service or self.service).preview("config-demo", str(self.root) if project else None,
                                                     "proj-1" if project else None, body)
        self.assertEqual([], contracts.validate(document, "config-mutation"))
        return document

    def commit(self, preview, layer, confirmed=False, revision=None, project=True):
        body = {"$schema": MUTATION, "kind": "commit_request", "preview_id": preview["preview_id"],
                "expected_revision": revision or preview["revision"], "confirmed": confirmed}
        return self.service.commit("config-demo", layer, str(self.root) if project else None,
                                   "proj-1" if project else None, body)

    def tree(self):
        found = {}
        for base, _dirs, files in os.walk(self.tmp):
            for name in files:
                path = Path(base, name)
                found[str(path)] = path.stat().st_mtime_ns
            found[base] = 0
        return found


class TestModulesAndView(ServiceCase):
    def test_modules(self):
        document = self.service.modules()
        self.assertEqual([], contracts.validate(document, "config-view"))
        self.assertEqual(["config-demo"], [module["id"] for module in document["modules"]])
        self.assertEqual("config-demo config", document["modules"][0]["title"])

    def test_view_without_project(self):
        document = self.view(project=False)
        self.assertEqual(["defaults", "machine", "project", "env", "invocation", "flags"],
                         [layer["name"] for layer in document["layers"]])
        layers = {layer["name"]: layer for layer in document["layers"]}
        self.assertTrue(layers["machine"]["writable"])
        self.assertEqual(EMPTY, layers["machine"]["revision"])
        self.assertEqual("", layers["machine"]["raw"])
        self.assertFalse(layers["project"]["writable"])
        self.assertIsNone(layers["project"]["revision"])
        self.assertIsNone(layers["project"]["raw"])
        self.assertIsNone(document["project_id"])
        self.assertTrue(document["schema_digest"].startswith("sha256:"))
        self.assertEqual("config-demo config", document["schema"]["title"])

    def test_entries_follow_the_schema_and_carry_defaults(self):
        document = self.view()
        self.assertEqual(["title", "limits.max", "limits.ratio", "limits.retries", "verbose", "mode", "sources",
                          "token", "cache_dir"], [entry["key"] for entry in document["entries"]])
        maximum = self.entry(document, "limits.max")
        self.assertEqual({"value": 4, "layer": "defaults", "file": None, "line": None, "source": None},
                         maximum["effective"])
        self.assertEqual(4, maximum["default"])
        self.assertEqual({"machine": None, "project": None}, maximum["layer_values"])
        retries = self.entry(document, "limits.retries")
        self.assertNotIn("default", retries)
        self.assertIsNone(retries["effective"]["layer"])
        self.assertEqual(["defaults", "machine"], self.entry(document, "cache_dir")["allowed_layers"])
        self.assertTrue(self.entry(document, "token")["secret"])
        self.assertEqual("array", self.entry(document, "sources")["type"])

    def test_provenance_and_layer_values_after_a_write(self):
        self.write(self.machine, "schema_version = 1\n\n[config-demo.limits]\nmax = 7\n")
        self.write(self.project, "schema_version = 1\n\n[config-demo]\nmode = \"fast\"\n\n[config-demo.limits]\n"
                                 "max = 9\n")
        document = self.view()
        maximum = self.entry(document, "limits.max")
        self.assertEqual(9, maximum["effective"]["value"])
        self.assertEqual("project", maximum["effective"]["layer"])
        self.assertEqual(str(self.project), maximum["effective"]["file"])
        self.assertEqual(7, maximum["effective"]["line"])
        self.assertEqual({"machine": 7, "project": 9}, maximum["layer_values"])
        self.assertEqual(["machine", "defaults"], [item["layer"] for item in maximum["overridden"]])
        self.assertEqual(str(self.machine), maximum["overridden"][0]["file"])
        self.assertEqual(4, maximum["overridden"][1]["value"])

    def test_env_wins_and_is_read_only(self):
        self.write(self.machine, "schema_version = 1\n\n[config-demo]\nmode = \"safe\"\n")
        env = {**self.env, "SKM_CONFIG_DEMO_MODE": "fast"}
        document = self.view(service=self.make(env))
        mode = self.entry(document, "mode")
        self.assertEqual("fast", mode["effective"]["value"])
        self.assertEqual("env", mode["effective"]["layer"])
        self.assertEqual("SKM_CONFIG_DEMO_MODE", mode["effective"]["source"])
        self.assertEqual("machine", mode["overridden"][0]["layer"])
        layers = {layer["name"]: layer for layer in document["layers"]}
        self.assertFalse(layers["env"]["writable"])
        self.assertTrue(layers["env"]["present"])

    def test_raw_is_redacted_and_large_raw_is_withheld(self):
        self.write(self.machine, f"# note {SECRET_VALUE_SENTINEL}\nschema_version = 1\n")
        document = self.view(project=False)
        raw = next(layer for layer in document["layers"] if layer["name"] == "machine")["raw"]
        self.assertNotIn(SECRET_VALUE_SENTINEL, raw)
        self.assertNotIn(SECRET_VALUE_SENTINEL, json.dumps(document))
        self.write(self.machine, "schema_version = 1\n# " + "x" * 262144 + "\n")
        layer = next(layer for layer in self.view(project=False)["layers"] if layer["name"] == "machine")
        self.assertIsNone(layer["raw"])
        self.assertTrue(layer["raw_truncated"])
        self.assertEqual(self.revision(self.machine), layer["revision"])

    def test_secret_key_shows_the_reference_only(self):
        self.write(self.machine, "schema_version = 1\n\n[config-demo]\ntoken = \"env://SKM_TEST_SECRET\"\n")
        token = self.entry(self.view(), "token")
        self.assertEqual("env://SKM_TEST_SECRET", token["effective"]["value"])
        self.assertEqual("env://SKM_TEST_SECRET", token["layer_values"]["machine"])

    def test_maps_list_their_entries(self):
        self.write(self.project, "schema_version = 1\n\n[config-demo.profiles.fast]\nlevel = 3\n\n"
                                 "[config-demo.profiles.slow]\nlabel = \"calm\"\n")
        document = self.view()
        self.assertEqual([{"key": "profiles", "entry_pattern": "^[a-z][a-z0-9-]*$", "entries": ["fast", "slow"]}],
                         document["maps"])
        keys = [entry["key"] for entry in document["entries"]]
        self.assertEqual(["profiles.fast.level", "profiles.fast.label", "profiles.slow.level", "profiles.slow.label"],
                         keys[9:])
        level = self.entry(document, "profiles.fast.level")
        self.assertEqual("project", level["effective"]["layer"])
        self.assertEqual(3, level["layer_values"]["project"])
        self.assertEqual(1, self.entry(document, "profiles.slow.level")["effective"]["value"])

    def test_unknown_module_and_broken_layer(self):
        with self.assertRaises(GuiError) as caught:
            self.service.view("nope", None)
        self.assertEqual("NOT_FOUND", caught.exception.code)
        self.write(self.machine, "this is = = not toml\n")
        with self.assertRaises(GuiError) as caught:
            self.view(project=False)
        self.assertEqual("INPUT_INVALID", caught.exception.code)


class TestPreview(ServiceCase):
    def test_preview_has_no_side_effects(self):
        before = self.tree()
        document = self.preview("project", [set_op("limits.max", 6)])
        self.assertEqual(before, self.tree())
        self.assertFalse(self.project.exists())
        self.assertFalse(Path(str(self.project) + ".lock").exists())
        self.assertEqual([], self.audits + self.project_events + self.machine_events)
        self.assertEqual(EMPTY, document["revision"])
        self.assertEqual([], document["issues"])
        self.assertFalse(document["confirm_required"])
        self.assertEqual([], document["confirm_reasons"])
        self.assertEqual([{"key": "limits.max", "before": None, "after": 6,
                           "effective_before": {"value": 4, "layer": "defaults"},
                           "effective_after": {"value": 6, "layer": "project"}}], document["diff"])
        self.assertEqual(self.revision(self.project), document["revision"])

    def test_preview_of_an_existing_file_leaves_its_bytes(self):
        self.write(self.project, "# keep\nschema_version = 1\n\n[config-demo.limits]\nmax = 5\n")
        bytes_before = self.project.read_bytes()
        document = self.preview("project", [set_op("limits.max", 6)])
        self.assertEqual(bytes_before, self.project.read_bytes())
        self.assertEqual(5, document["diff"][0]["before"])

    def test_preview_id_is_deterministic_and_bound_to_its_inputs(self):
        first = self.preview("project", [set_op("limits.max", 6)])
        again = self.preview("project", [set_op("limits.max", 6)])
        self.assertEqual(first["preview_id"], again["preview_id"])
        self.assertNotEqual(first["preview_id"], self.preview("project", [set_op("limits.max", 7)])["preview_id"])
        self.assertNotEqual(first["preview_id"], self.preview("machine", [set_op("limits.max", 6)])["preview_id"])
        other = self.service.preview("config-demo", str(self.root), "proj-2",
                                     request("project", [set_op("limits.max", 6)], EMPTY))
        self.assertNotEqual(first["preview_id"], other["preview_id"])
        schema_copy = self.tmp / "units" / "config-demo"
        shutil.copytree(FIXTURES / "config-demo", schema_copy)
        schema_file = schema_copy / "configs" / "config.schema.json"
        schema_file.write_text(schema_file.read_text(encoding="utf-8").replace("Largest count.", "Biggest count."),
                               encoding="utf-8")
        changed = self.make({**self.env, "SKM_UNITS_PATH": str(schema_copy)})
        self.assertNotEqual(first["preview_id"], self.preview("project", [set_op("limits.max", 6)],
                                                              service=changed)["preview_id"])

    def test_float_values_have_a_preview_id(self):
        document = self.preview("project", [set_op("limits.ratio", 0.25)])
        self.assertEqual(0.25, document["diff"][0]["after"])

    def test_confirm_reasons(self):
        machine = self.preview("machine", [set_op("limits.max", 6)])
        self.assertEqual(["machine_layer"], machine["confirm_reasons"])
        self.assertTrue(machine["confirm_required"])
        secret = self.preview("project", [set_op("token", "env://SKM_TEST_SECRET")])
        self.assertEqual(["secret_key"], secret["confirm_reasons"])
        self.write(self.project, "schema_version = 1\n\n[config-demo.limits]\nmax = 5\n")
        unset = self.preview("project", [unset_op("limits.max")])
        self.assertEqual(["unset"], unset["confirm_reasons"])
        self.assertEqual(5, unset["diff"][0]["before"])
        self.assertIsNone(unset["diff"][0]["after"])
        self.assertEqual({"value": 4, "layer": "defaults"}, unset["diff"][0]["effective_after"])
        self.project.unlink()
        everything = self.preview("machine", [set_op("token", "keyring://demo"), unset_op("limits.max")])
        self.assertEqual(["machine_layer", "secret_key", "unset"], everything["confirm_reasons"])

    def test_shadowed_by_a_higher_layer(self):
        env = {**self.env, "SKM_CONFIG_DEMO_MODE": "fast"}
        service = self.make(env)
        document = self.preview("project", [set_op("mode", "safe"), set_op("limits.max", 6)], service=service)
        self.assertEqual(["shadowed:env"], document["confirm_reasons"])
        self.assertTrue(document["confirm_required"])
        mode = next(item for item in document["diff"] if item["key"] == "mode")
        self.assertEqual({"value": "fast", "layer": "env"}, mode["effective_after"])

    def test_diff_names_keys_whose_effective_value_changed(self):
        self.write(self.machine, "schema_version = 1\n\n[config-demo.profiles.a]\nlevel = 2\n")
        document = self.preview("machine", [unset_op("profiles.a.level")])
        self.assertEqual(["profiles.a.level"], [item["key"] for item in document["diff"]])
        self.assertEqual({"value": None, "layer": None}, document["diff"][0]["effective_after"])

    def test_issues(self):
        cases = [
            (set_op("nothing.here", 1), "CONFIG_UNKNOWN_KEY", "nothing.here"),
            (set_op("limits.max", "many"), "CONFIG_TYPE", "limits.max"),
            (set_op("limits.max", 1000), None, "limits.max"),
            (set_op("mode", "turbo"), None, "mode"),
        ]
        for op, code, key in cases:
            with self.subTest(op=op):
                document = self.preview("project", [op])
                self.assertEqual(1, len(document["issues"]), document)
                self.assertEqual(key, document["issues"][0]["key"])
                if code:
                    self.assertEqual(code, document["issues"][0]["code"])
                self.assertEqual([], [item for item in document["diff"] if item["after"] is not None])

    def test_forbidden_layer_for_a_key_is_an_issue(self):
        document = self.preview("project", [set_op("cache_dir", "/tmp/x")])
        self.assertEqual(["CONFIG_LAYER_FORBIDDEN"], [issue["code"] for issue in document["issues"]])
        self.assertEqual([], self.preview("machine", [set_op("cache_dir", "/tmp/x")])["issues"])

    def test_secret_value_is_an_issue_without_the_value(self):
        for value in (SECRET_VALUE_SENTINEL, "plain://x", "vault://x"):
            with self.subTest(value=value):
                document = self.preview("machine", [set_op("token", value)])
                self.assertEqual(["SECRET_REF_INVALID"], [issue["code"] for issue in document["issues"]])
                self.assertNotIn(SECRET_VALUE_SENTINEL, json.dumps(document))
        for value in ("env://SKM_TEST_SECRET", "keyring://demo/token"):
            self.assertEqual([], self.preview("machine", [set_op("token", value)])["issues"])

    def test_one_good_and_one_bad_op_keep_both_visible(self):
        document = self.preview("project", [set_op("limits.max", 6), set_op("mode", "turbo")])
        self.assertEqual(["mode"], [issue["key"] for issue in document["issues"]])
        self.assertEqual(6, document["diff"][0]["after"])

    def test_stale_revision_is_a_conflict_with_the_current_one(self):
        self.write(self.project, "schema_version = 1\n")
        with self.assertRaises(GuiError) as caught:
            self.preview("project", [set_op("limits.max", 6)], revision=EMPTY)
        self.assertEqual("CONFIG_REVISION_CONFLICT", caught.exception.code)
        self.assertEqual(self.revision(self.project), caught.exception.details["current_revision"])

    def test_module_mismatch_layer_and_project(self):
        with self.assertRaises(GuiError) as caught:
            self.service.preview("config-demo", None, None, request("machine", [set_op("verbose", True)], EMPTY,
                                                                    module="other"))
        self.assertEqual("INPUT_INVALID", caught.exception.code)
        with self.assertRaises(GuiError) as caught:
            self.service.preview("config-demo", None, None, request("project", [set_op("verbose", True)], EMPTY))
        self.assertEqual("INPUT_INVALID", caught.exception.code)
        with self.assertRaises(GuiError) as caught:
            self.service.preview("config-demo", None, None, request("env", [set_op("verbose", True)], EMPTY))
        self.assertEqual("CONFIG_LAYER_FORBIDDEN", caught.exception.code)


class TestCommit(ServiceCase):
    def test_happy_path_keeps_comments_makes_a_backup_and_announces(self):
        self.write(self.project, "# my note\nschema_version = 1\n\n[config-demo.limits]\nmax = 5 # inline\n")
        preview = self.preview("project", [set_op("limits.max", 6), set_op("verbose", True)])
        result = self.commit(preview, "project")
        self.assertEqual([], contracts.validate(result, "config-mutation"))
        text = self.project.read_text(encoding="utf-8")
        self.assertIn("# my note", text)
        self.assertIn("# inline", text)
        self.assertIn("max = 6", text)
        self.assertIn("verbose = true", text)
        self.assertEqual(self.revision(self.project), result["revision"])
        self.assertEqual(str(self.project), result["file"])
        self.assertTrue(result["backup"] and Path(result["backup"]).read_text(encoding="utf-8").count("max = 5"))
        self.assertEqual([("config.commit", "config-demo:project", "applied")],
                         [audit[:3] for audit in self.audits])
        details = self.audits[0][3]
        self.assertEqual(preview["revision"], details["revision_before"])
        self.assertEqual(result["revision"], details["revision_after"])
        self.assertEqual(["limits.max", "verbose"], details["keys"])
        self.assertEqual({"file", "revision_before", "revision_after", "keys"}, set(details))
        self.assertEqual([("gui.config.changed", {"module": "config-demo", "layer": "project",
                                                  "keys": ["limits.max", "verbose"], "revision": result["revision"]},
                           "config-demo", str(self.root))], self.project_events)
        self.assertEqual([], self.machine_events)
        self.assertEqual(6, self.entry(self.view(), "limits.max")["effective"]["value"])

    def test_new_file_has_no_backup_and_machine_event_has_no_journal(self):
        preview = self.preview("machine", [set_op("limits.max", 8)], project=False)
        result = self.commit(preview, "machine", confirmed=True, project=False)
        self.assertIsNone(result["backup"])
        self.assertIn("max = 8", self.machine.read_text(encoding="utf-8"))
        self.assertEqual([], self.project_events)
        self.assertEqual(1, len(self.machine_events))
        self.assertEqual(("gui.config.changed", "config-demo"), (self.machine_events[0][0], self.machine_events[0][2]))

    def test_confirmation_is_required_and_audited(self):
        preview = self.preview("machine", [set_op("limits.max", 8)])
        with self.assertRaises(GuiError) as caught:
            self.commit(preview, "machine")
        self.assertEqual("CONFIRMATION_REQUIRED", caught.exception.code)
        self.assertEqual("machine_layer", caught.exception.details["confirm_reasons"])
        self.assertFalse(self.machine.exists())
        self.assertEqual("refused", self.audits[0][2])
        self.assertEqual("CONFIRMATION_REQUIRED", self.audits[0][3]["code"])
        self.commit(preview, "machine", confirmed=True)
        self.assertTrue(self.machine.exists())

    def test_stale_revision_conflicts_and_leaves_the_file(self):
        self.write(self.project, "schema_version = 1\n")
        preview = self.preview("project", [set_op("limits.max", 6)])
        self.write(self.project, "schema_version = 1\n# edited elsewhere\n")
        edited = self.project.read_bytes()
        with self.assertRaises(GuiError) as caught:
            self.commit(preview, "project")
        self.assertEqual("CONFIG_REVISION_CONFLICT", caught.exception.code)
        self.assertEqual(sha256_tagged(edited), caught.exception.details["current_revision"])
        self.assertEqual(edited, self.project.read_bytes())
        self.assertEqual(("config.commit", "config-demo:project", "refused"), self.audits[0][:3])
        self.assertEqual([], self.project_events)

    def test_the_cli_changes_the_layer_between_preview_and_commit(self):
        self.write(self.machine, "schema_version = 1\n")
        preview = self.preview("machine", [set_op("limits.max", 8)], project=False)
        aicore_lib = str(Path(__import__("aicore").__file__).resolve().parents[1])
        run = subprocess.run([sys.executable, "-m", "aicore", "config", "set", "--machine", "config-demo.limits.max",
                              "9"], env={**self.env, "PYTHONPATH": aicore_lib}, capture_output=True, text=True,
                             cwd=str(self.tmp))
        self.assertEqual(0, run.returncode, run.stderr)
        with self.assertRaises(GuiError) as caught:
            self.commit(preview, "machine", confirmed=True, project=False)
        self.assertEqual("CONFIG_REVISION_CONFLICT", caught.exception.code)
        self.assertEqual(self.revision(self.machine), caught.exception.details["current_revision"])
        self.assertIn("max = 9", self.machine.read_text(encoding="utf-8"))
        self.assertNotIn("max = 8", self.machine.read_text(encoding="utf-8"))

    def test_a_lock_held_by_another_process_is_locked(self):
        self.write(self.project, "schema_version = 1\n")
        preview = self.preview("project", [set_op("limits.max", 6)])
        before = self.project.read_bytes()
        holder = subprocess.Popen([sys.executable, "-c", (
            "import fcntl, os, sys, time\n"
            "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)\n"
            "fcntl.flock(fd, fcntl.LOCK_EX)\n"
            "print('held', flush=True)\n"
            "sys.stdin.readline()\n"), str(self.project) + ".lock"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True)

        def release():
            holder.stdin.close()
            holder.wait()
            holder.stdout.close()

        self.addCleanup(release)
        try:
            self.assertEqual("held", holder.stdout.readline().strip())
            self.timeout = 0.2
            with self.assertRaises(GuiError) as caught:
                self.commit(preview, "project")
            self.assertEqual("CONFIG_LOCKED", caught.exception.code)
        finally:
            holder.stdin.write("\n")
            holder.stdin.flush()
            holder.wait()
        self.assertEqual(before, self.project.read_bytes())
        self.assertEqual("refused", self.audits[0][2])
        self.commit(preview, "project")  # the preview is still valid after the lock is gone
        self.assertIn("max = 6", self.project.read_text(encoding="utf-8"))

    def test_unknown_repeated_and_mismatched_previews_are_stale(self):
        preview = self.preview("project", [set_op("limits.max", 6)])
        unknown = {**preview, "preview_id": "sha256:" + "0" * 64}
        with self.assertRaises(GuiError) as caught:
            self.commit(unknown, "project")
        self.assertEqual("PREVIEW_STALE", caught.exception.code)
        with self.assertRaises(GuiError) as caught:
            self.commit(preview, "machine", confirmed=True)
        self.assertEqual("PREVIEW_STALE", caught.exception.code)
        with self.assertRaises(GuiError) as caught:
            self.service.commit("config-demo", "project", str(self.root), "proj-other",
                                {"$schema": MUTATION, "kind": "commit_request", "preview_id": preview["preview_id"],
                                 "expected_revision": preview["revision"], "confirmed": True})
        self.assertEqual("PREVIEW_STALE", caught.exception.code)
        with self.assertRaises(GuiError) as caught:
            self.commit(preview, "project", revision="sha256:" + "1" * 64)
        self.assertEqual("PREVIEW_STALE", caught.exception.code)
        self.commit(preview, "project")
        with self.assertRaises(GuiError) as caught:
            self.commit(preview, "project")
        self.assertEqual("PREVIEW_STALE", caught.exception.code)

    def test_preview_expires_with_the_clock(self):
        preview = self.preview("project", [set_op("limits.max", 6)])
        self.clock.now += 601
        with self.assertRaises(GuiError) as caught:
            self.commit(preview, "project")
        self.assertEqual("PREVIEW_STALE", caught.exception.code)
        self.assertFalse(self.project.exists())

    def test_schema_change_makes_the_preview_stale(self):
        copy = self.tmp / "units" / "config-demo"
        shutil.copytree(FIXTURES / "config-demo", copy)
        service = self.make({**self.env, "SKM_UNITS_PATH": str(copy)})
        preview = self.preview("project", [set_op("limits.max", 6)], service=service)
        schema_file = copy / "configs" / "config.schema.json"
        schema_file.write_text(schema_file.read_text(encoding="utf-8").replace("Largest count.", "Biggest count."),
                               encoding="utf-8")
        body = {"$schema": MUTATION, "kind": "commit_request", "preview_id": preview["preview_id"],
                "expected_revision": preview["revision"], "confirmed": True}
        with self.assertRaises(GuiError) as caught:
            service.commit("config-demo", "project", str(self.root), "proj-1", body)
        self.assertEqual("PREVIEW_STALE", caught.exception.code)
        self.assertFalse(self.project.exists())

    def test_a_preview_with_issues_cannot_be_committed(self):
        preview = self.preview("project", [set_op("mode", "turbo")])
        with self.assertRaises(GuiError) as caught:
            self.commit(preview, "project")
        self.assertEqual("INPUT_INVALID", caught.exception.code)
        self.assertEqual("mode", caught.exception.issues[0]["pointer"].rsplit("/", 1)[1])
        self.assertFalse(self.project.exists())

    def test_the_layer_of_the_path_must_be_writable(self):
        preview = self.preview("project", [set_op("limits.max", 6)])
        with self.assertRaises(GuiError) as caught:
            self.service.commit("config-demo", "env", str(self.root), "proj-1", {})
        self.assertEqual("CONFIG_LAYER_FORBIDDEN", caught.exception.code)
        self.assertIsNotNone(self.service.store.get(preview["preview_id"]))

    def test_secret_reference_is_written_and_nothing_leaks(self):
        preview = self.preview("machine", [set_op("token", "env://SKM_TEST_SECRET")], project=False)
        result = self.commit(preview, "machine", confirmed=True, project=False)
        self.assertIn('token = "env://SKM_TEST_SECRET"', self.machine.read_text(encoding="utf-8"))
        everything = json.dumps([preview, result, self.audits, self.machine_events, self.view(project=False)])
        self.assertNotIn(SECRET_VALUE_SENTINEL, everything)


class TestPreviewStore(unittest.TestCase):
    def record(self, index):
        return PreviewRecord(preview_id=f"sha256:{index:064x}", module="m", layer="machine", project_id=None,
                             project_root=None, file="/f", revision="r", schema_digest="d", ops=(), issues=(),
                             confirm_required=False, confirm_reasons=(), keys=())

    def test_ttl_and_capacity(self):
        clock = Clock()
        store = PreviewStore(lambda: 10, max_items=3, clock=clock)
        for index in range(5):
            store.put(self.record(index))
        self.assertEqual(3, len(store))
        self.assertIsNone(store.get(self.record(0).preview_id))
        self.assertIsNotNone(store.get(self.record(4).preview_id))
        clock.now += 10
        self.assertIsNone(store.get(self.record(4).preview_id))
        self.assertEqual(0, len(store))

    def test_drop(self):
        store = PreviewStore(lambda: 10)
        store.put(self.record(1))
        store.drop(self.record(1).preview_id)
        self.assertIsNone(store.get(self.record(1).preview_id))


if __name__ == "__main__":
    unittest.main()
