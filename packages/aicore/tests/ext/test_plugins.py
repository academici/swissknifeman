"""aicore.ext.plugins: manifest before launch, handshake, point calls, subscriber plugins, CLI.

Plugins are copies of the folders in ``fixtures/plugins`` staged into a temporary directory. A plugin that
runs leaves lines in ``calls.jsonl`` (see ``fixtures/plugins/_serve.py``): through ``FIXTURE_MARKS`` for a trusted
plugin that asks for the variable, in ``marks/`` next to a ``bad-*`` plugin. No mark file means never started.
"""
import json
import os
import shutil
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

from aicore.ext import delivery, events, plugins, settings
from aicore.ext.environment import clean_environment
from aicore.ext.errors import CODES, ExtError
from aicore.ext.process import run_json
from aicore.util.digest import digest_json

from tests.ext.support import FIXTURES, UNITS, TempCase, run_cli

PLUGINS = FIXTURES / "plugins"
AICORE_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "s3cr3t-" + uuid.uuid4().hex


def merge(target, patch):
    for key, value in patch.items():
        if value is None:
            target.pop(key, None)
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            merge(target[key], value)
        else:
            target[key] = value
    return target


class PluginCase(TempCase):
    def setUp(self):
        super().setUp()
        self.env["AICORE_ROOT"] = str(AICORE_ROOT)
        self.marks_dir = self.tmp / "marks"
        self.env["FIXTURE_MARKS"] = str(self.marks_dir)
        self.staged = self.tmp / "staged"
        self.staged.mkdir()
        self.config = ""

    # staging -------------------------------------------------------------------------------------------------
    def machine(self, text):
        self.config += text
        path = self.tmp / "skm" / "config" / "config.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("schema_version = 1\n" + self.config, encoding="utf-8")

    def stage(self, fixture, *, name=None, patch=None, marks=False, describe=None, script=None):
        """Copy a fixture plugin and return the path of its manifest.

        ``marks`` lets a trusted plugin receive ``FIXTURE_MARKS``; ``describe`` replaces the ``describe_patch`` of
        the plugin; ``script`` is the body of a ``plugin.py`` that already imported ``serve`` and ``Path``.
        """
        target = self.staged / (name or fixture)
        shutil.copytree(PLUGINS / fixture, target, ignore=shutil.ignore_patterns("marks", "__pycache__"))
        manifest_path = target / "extension.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if marks:
            merge(manifest, {"permissions": {"env": sorted({"FIXTURE_MARKS"} | set(
                manifest.get("permissions", {}).get("env", [])))}})
        merge(manifest, patch or {})
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        head = ("import os\nimport sys\nfrom pathlib import Path\n\nsys.path.insert(0, os.environ['AICORE_ROOT'])\n"
                "from tests.ext.fixtures.plugins._serve import reply, serve  # noqa: E402,F401\n\n")
        if describe is not None:
            (target / "plugin.py").write_text(head + f"serve(Path(__file__).resolve().parent, "
                                              f"describe_patch={describe!r})\n", encoding="utf-8")
        if script is not None:
            (target / "plugin.py").write_text(head + script, encoding="utf-8")
        return str(manifest_path)

    def register(self, plugin_id, manifest, **keys):
        lines = [f"[aicore.plugins.{plugin_id}]", f"manifest = {json.dumps(manifest)}"]
        for key, value in keys.items():
            lines.append(f"{key} = {json.dumps(value)}")
        self.machine("\n".join(lines) + "\n")

    def plugin(self, fixture, *, plugin_id=None, trusted=False, marks=False, enabled=True, timeout=None, **kwargs):
        """Stage and register; ``marks`` implies ``trusted`` (only a trusted plugin gets the variable)."""
        name = plugin_id or fixture
        manifest = self.stage(fixture, name=name, marks=marks, **kwargs)
        keys = {}
        if trusted or marks:
            keys["trusted"] = True
        if not enabled:
            keys["enabled"] = False
        if timeout:
            keys["timeout_seconds"] = timeout
        self.register(plugin_id or json.loads(Path(manifest).read_text(encoding="utf-8"))["id"], manifest, **keys)
        return manifest

    # actions and observations --------------------------------------------------------------------------------
    def registrations(self):
        loaded = settings.load(self.project, env=self.env, home=self.home)
        return plugins.registered_plugins(loaded, env=self.env)

    def registration(self, plugin_id):
        return {item.id: item for item in self.registrations()[0]}[plugin_id]

    def invoke(self, point="demo:check", data=None):
        return plugins.invoke_point(point, data if data is not None else {"x": 1}, project=self.project,
                                    env=self.env, home=self.home)

    def ops(self, directory=None):
        path = Path(directory or self.marks_dir) / "calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def op_names(self, directory=None):
        return [item["op"] for item in self.ops(directory)]

    def local_ops(self, name):
        return self.op_names(self.staged / name / "marks")

    def cli(self, *argv):
        return run_cli(*argv, env=self.env, cwd=self.project)


class TestManifest(PluginCase):
    def setUp(self):
        super().setUp()
        self.env["SKM_UNITS_PATH"] = str(UNITS)

    def test_valid_command_manifest(self):
        manifest = plugins.load_manifest(PLUGINS / "echo" / "extension.json")
        self.assertEqual((manifest.id, manifest.kind, manifest.version), ("echo", "command", "0.1.0"))
        self.assertEqual(manifest.points, ["demo:check"])
        self.assertEqual(manifest.protocol, (1, 1))
        self.assertEqual(manifest.example_input, {"x": 1})
        self.assertEqual(manifest.timeout_seconds, 20)
        self.assertEqual(manifest.entrypoint[0], "python3")
        script = Path(manifest.entrypoint[1])
        self.assertTrue(script.is_absolute() and script.is_file())
        self.assertEqual(script.parent, (PLUGINS / "echo").resolve())
        self.assertEqual(manifest.capabilities_digest, digest_json(manifest.provides))

    def test_max_stdout_limit_is_validated(self):
        cap = 64 * 1024 * 1024
        self.assertEqual(plugins.load_manifest(self.stage("echo")).max_stdout, 1048576)
        for value in (1048576, 33554432, cap):
            with self.subTest(value):
                manifest = plugins.load_manifest(self.stage("echo", name=f"ok{value}",
                                                            patch={"limits": {"max_stdout_bytes": value}}))
                self.assertEqual(manifest.max_stdout, value)
        for value in (0, -1, 1.5, "x", 1048575, cap + 1, True):
            with self.subTest(value):
                with self.assertRaises(ExtError) as caught:
                    plugins.load_manifest(self.stage("echo", name=f"bad{value}",
                                                     patch={"limits": {"max_stdout_bytes": value}}))
                self.assertEqual(caught.exception.code, "PLUGIN_MANIFEST_INVALID")

    def test_valid_subscriber_manifest(self):
        manifest = plugins.load_manifest(PLUGINS / "sub" / "extension.json")
        self.assertEqual((manifest.kind, manifest.events), ("subscriber", ["demo.*"]))

    def test_each_defect_is_refused_with_its_code(self):
        wanted = {"bad-schema": "PLUGIN_MANIFEST_INVALID", "bad-entrypoint-escape": "PLUGIN_MANIFEST_INVALID",
                  "bad-protocol": "PLUGIN_PROTOCOL_UNSUPPORTED", "bad-requires": "PLUGIN_REQUIRES_UNSATISFIED",
                  "bad-profile-readonly": "PLUGIN_PROFILE_UNAVAILABLE"}
        for fixture, code in wanted.items():
            with self.subTest(fixture):
                with self.assertRaises(ExtError) as caught:
                    plugins.load_manifest(self.stage(fixture))
                self.assertEqual(caught.exception.code, code)
                self.assertIn(code, CODES)

    def test_a_defective_plugin_is_never_started(self):
        """R14: manifest first, then launch; the bad fixtures leave a mark in ``marks/`` whenever they start."""
        for fixture in ("bad-schema", "bad-entrypoint-escape", "bad-protocol", "bad-requires",
                        "bad-profile-readonly"):
            self.plugin(fixture, plugin_id=fixture, trusted=True)
        registrations, problems = self.registrations()
        self.assertEqual(sorted(item["plugin"] for item in problems), sorted(item.id for item in registrations))
        for registration in registrations:
            with self.subTest(registration.id):
                self.assertFalse(registration.usable)
                with self.assertRaises(ExtError):
                    plugins.describe_plugin(registration, env=self.env, project=self.project)
                self.assertEqual(self.local_ops(registration.id), [])
                self.assertFalse((self.staged / registration.id / "marks").exists())
        self.assertEqual(self.invoke(), [])

    def test_unreadable_and_broken_json(self):
        with self.assertRaises(ExtError) as missing:
            plugins.load_manifest(self.tmp / "none.json")
        self.assertEqual(missing.exception.code, "PLUGIN_MANIFEST_INVALID")
        broken = self.tmp / "extension.json"
        broken.write_text("{not json", encoding="utf-8")
        with self.assertRaises(ExtError) as caught:
            plugins.load_manifest(broken)
        self.assertEqual(caught.exception.code, "PLUGIN_MANIFEST_INVALID")

    def test_kind_requirements(self):
        with self.assertRaises(ExtError) as command:
            plugins.load_manifest(self.stage("echo", name="no-points", patch={"provides": {"points": None}}))
        self.assertIn("provides.points", command.exception.message)
        with self.assertRaises(ExtError) as subscriber:
            plugins.load_manifest(self.stage("sub", name="no-events", patch={"provides": {"events": None}}))
        self.assertIn("provides.events", subscriber.exception.message)

    def test_entrypoint_rules(self):
        cases = {
            "absolute script": {"entrypoint": ["python3", str(PLUGINS / "echo" / "plugin.py")]},
            "missing script": {"entrypoint": ["python3", "nothing.py"]},
            "interpreter alone": {"entrypoint": ["python3"]},
            "escape by dots": {"entrypoint": ["python3", "sub/../../plugin.py"]},
            "direct but not executable": {"entrypoint": ["plugin.py"]},
        }
        for label, patch in cases.items():
            with self.subTest(label):
                with self.assertRaises(ExtError) as caught:
                    plugins.load_manifest(self.stage("echo", name=label.replace(" ", "-"), patch=patch))
                self.assertEqual(caught.exception.code, "PLUGIN_MANIFEST_INVALID")

    def test_direct_executable_entrypoint_is_accepted(self):
        path = self.stage("echo", name="direct", patch={"entrypoint": ["plugin.py"]})
        os.chmod(Path(path).parent / "plugin.py", 0o755)
        self.assertEqual(plugins.load_manifest(path).entrypoint, (str((Path(path).parent / "plugin.py").resolve()),))

    def test_symlink_out_of_the_folder_is_refused(self):
        outside = self.tmp / "outside.py"
        outside.write_text("print('x')\n", encoding="utf-8")
        path = self.stage("echo", name="linked")
        script = Path(path).parent / "plugin.py"
        script.unlink()
        script.symlink_to(outside)
        with self.assertRaises(ExtError) as caught:
            plugins.load_manifest(path)
        self.assertEqual(caught.exception.code, "PLUGIN_MANIFEST_INVALID")
        self.assertIn("inside", caught.exception.message)

    def test_entrypoint_symlink_loop_is_refused_also_when_resolve_does_not_raise(self):
        path = self.stage("echo", name="looped")
        script = Path(path).parent / "plugin.py"
        script.unlink()
        script.symlink_to("plugin.py")
        lenient = lambda self, strict=False: Path(os.path.realpath(os.fspath(self)))  # noqa: E731 (Python 3.13+)
        for patch in (mock.patch.object(Path, "resolve", lenient), mock.patch.object(os, "name", os.name)):
            with patch, self.assertRaises(ExtError) as caught:
                plugins.load_manifest(path)
            self.assertEqual(caught.exception.code, "PLUGIN_MANIFEST_INVALID")

    def test_protocol_range(self):
        wide = plugins.load_manifest(self.stage("echo", name="wide", patch={"protocol": {"min": "0", "max": "5"}}))
        self.assertEqual(wide.protocol, (0, 5))
        for label, rng in (("above", {"min": "2", "max": "2"}), ("below", {"min": "0", "max": "0"})):
            with self.subTest(label):
                with self.assertRaises(ExtError) as caught:
                    plugins.load_manifest(self.stage("echo", name=label, patch={"protocol": rng}))
                self.assertEqual(caught.exception.code, "PLUGIN_PROTOCOL_UNSUPPORTED")
        with self.assertRaises(ExtError) as inverted:
            plugins.load_manifest(self.stage("echo", name="inverted", patch={"protocol": {"min": "3", "max": "1"}}))
        self.assertEqual(inverted.exception.code, "PLUGIN_MANIFEST_INVALID")

    def test_requires_needs_a_provided_major(self):
        ok = {"requires": [{"contract": "urn:swissknifeman:aicore:event", "versions": ["v9", "v1"]},
                           {"contract": "urn:swissknifeman:aicore:digest", "versions": ["v1"]}]}
        plugins.load_manifest(self.stage("echo", name="needs-ok", patch=ok))
        for label, contract in (("unknown", "urn:swissknifeman:aicore:nothing"),):
            with self.subTest(label):
                bad = {"requires": [{"contract": contract, "versions": ["v1"]}]}
                with self.assertRaises(ExtError) as caught:
                    plugins.load_manifest(self.stage("echo", name=label, patch=bad))
                self.assertEqual(caught.exception.code, "PLUGIN_REQUIRES_UNSATISFIED")


class TestRegistration(PluginCase):
    def setUp(self):
        super().setUp()
        self.env["SKM_UNITS_PATH"] = str(UNITS)

    def test_registration_fields_and_timeout_precedence(self):
        self.plugin("echo", timeout=7)
        self.plugin("probe", trusted=True)
        self.plugin("sub", patch={"timeout_seconds": None})
        registrations, problems = self.registrations()
        by_id = {item.id: item for item in registrations}
        self.assertEqual(problems, [])
        self.assertEqual([item.id for item in registrations], ["echo", "probe", "sub"])
        self.assertEqual((by_id["echo"].timeout_seconds, by_id["probe"].timeout_seconds,
                          by_id["sub"].timeout_seconds), (7, plugins.DEFAULT_TIMEOUT_S, plugins.DEFAULT_TIMEOUT_S))
        self.assertEqual((by_id["echo"].trusted, by_id["probe"].trusted), (False, True))
        self.assertTrue(all(item.usable for item in registrations))

    def test_manifest_timeout_is_used_when_the_config_has_none(self):
        self.plugin("echo")
        self.assertEqual(self.registration("echo").timeout_seconds, 20)

    def test_entry_name_must_equal_the_manifest_id(self):
        self.plugin("echo", plugin_id="other")
        registration = self.registration("other")
        self.assertEqual(registration.problem["code"], "PLUGIN_ID_MISMATCH")
        self.assertFalse(registration.usable)
        self.assertEqual([item["code"] for item in self.registrations()[1]], ["PLUGIN_ID_MISMATCH"])
        self.assertEqual(self.invoke()[0].code, "PLUGIN_ID_MISMATCH")

    def test_unknown_point_is_a_problem_but_the_known_one_still_works(self):
        self.plugin("echo", patch={"provides": {"points": ["demo:check", "ghost:point"]}})
        registration = self.registration("echo")
        self.assertEqual(registration.unknown_points, ("ghost:point",))
        self.assertEqual([(item["code"], item["plugin"]) for item in self.registrations()[1]],
                         [("PLUGIN_POINT_UNKNOWN", "echo")])
        self.assertTrue(registration.usable)
        self.assertEqual([item.status for item in self.invoke()], ["ok"])

    def test_missing_relative_and_absent_manifest_paths(self):
        self.machine('[aicore.plugins.nomanifest]\ntrusted = false\n'
                     '[aicore.plugins.relative]\nmanifest = "extension.json"\n'
                     '[aicore.plugins.gone]\nmanifest = "/nonexistent/extension.json"\n')
        registrations, problems = self.registrations()
        self.assertEqual({item.id: item.problem["code"] for item in registrations},
                         {"nomanifest": "PLUGIN_MANIFEST_INVALID", "relative": "PLUGIN_MANIFEST_INVALID",
                          "gone": "PLUGIN_MANIFEST_INVALID"})
        self.assertEqual(len(problems), 3)

    def test_a_disabled_plugin_is_listed_but_neither_reported_nor_called(self):
        self.plugin("echo", enabled=False, marks=True)
        self.plugin("bad-schema", plugin_id="bad-schema", enabled=False)
        registrations, problems = self.registrations()
        self.assertEqual(problems, [])
        self.assertEqual([(item.id, item.enabled) for item in registrations], [("bad-schema", False), ("echo", False)])
        self.assertEqual(self.invoke(), [])
        self.assertEqual(self.ops(), [])

    def test_tilde_in_the_manifest_path_is_expanded(self):
        target = self.home / "plugins"
        shutil.copytree(PLUGINS / "echo", target / "echo", ignore=shutil.ignore_patterns("marks", "__pycache__"))
        self.machine('[aicore.plugins.echo]\nmanifest = "~/plugins/echo/extension.json"\n')
        self.assertTrue(self.registration("echo").usable)
        self.assertEqual([item.status for item in self.invoke()], ["ok"])


class TestHandshake(PluginCase):
    def setUp(self):
        super().setUp()
        self.env["SKM_UNITS_PATH"] = str(UNITS)

    def test_describe_of_a_good_plugin(self):
        self.plugin("echo", marks=True)
        described = plugins.describe_plugin(self.registration("echo"), env=self.env, project=self.project)
        manifest = self.registration("echo").manifest
        self.assertEqual((described.id, described.kind, described.version, described.protocol, described.transport),
                         ("echo", "command", "0.1.0", "1", "stdio-json"))
        self.assertEqual(described.capabilities_digest, digest_json(manifest.provides))
        self.assertEqual(self.op_names(), ["start", "describe"])

    def test_mismatching_digest_or_version_stops_before_invoke(self):
        for fixture, field in (("bad-digest", "capabilities_digest"), ("bad-version", "version")):
            with self.subTest(fixture):
                self.plugin(fixture, plugin_id=fixture, trusted=True)
                registration = self.registration(fixture)
                with self.assertRaises(ExtError) as caught:
                    plugins.describe_plugin(registration, env=self.env, project=self.project)
                self.assertEqual(caught.exception.code, "PLUGIN_HANDSHAKE_MISMATCH")
                self.assertIn(field, caught.exception.message)
                self.assertEqual(self.local_ops(fixture), ["start", "describe"])
                result = [item for item in self.invoke() if item.plugin == fixture][0]
                self.assertEqual((result.status, result.code), ("error", "PLUGIN_HANDSHAKE_MISMATCH"))
                self.assertNotIn("invoke", self.local_ops(fixture))

    def test_every_compared_field_is_checked(self):
        for field, value in (("id", "other-id"), ("kind", "subscriber"), ("transport", "http"),
                             ("protocol", "2"), ("capabilities_digest", "sha256:" + "0" * 64),
                             ("version", "0.1.1")):
            with self.subTest(field):
                name = "var-" + field.replace("_", "-")
                self.plugin("echo", plugin_id=name, patch={"id": name}, describe={field: value}, marks=True)
                with self.assertRaises(ExtError) as caught:
                    plugins.describe_plugin(self.registration(name), env=self.env, project=self.project)
                self.assertEqual(caught.exception.code, "PLUGIN_HANDSHAKE_MISMATCH")
        self.assertNotIn("invoke", self.op_names())

    def test_describe_is_repeated_before_every_use(self):
        self.plugin("echo", marks=True)
        self.invoke()
        self.invoke()
        self.assertEqual(self.op_names(), ["start", "describe", "start", "invoke"] * 2)

    def test_protocol_999_is_answered_with_protocol_unsupported_and_nothing_runs(self):
        self.plugin("echo", marks=True)
        manifest = self.registration("echo").manifest
        env, _ = clean_environment(self.env, permissions=manifest.permissions, trusted=True)
        request = {"$schema": plugins.REQUEST_SCHEMA, "protocol": "999", "op": "invoke",
                   "request_id": uuid.uuid4().hex, "deadline_ms": 5000, "point": "demo:check", "input": {}}
        result = run_json(list(manifest.entrypoint), request, deadline_s=10, env=env, cwd=str(self.tmp))
        self.assertTrue(result.ok, result)
        self.assertEqual(result.document["status"], "error")
        self.assertEqual(result.document["error"]["code"], "PROTOCOL_UNSUPPORTED")
        self.assertEqual(self.op_names(), ["start"])

    def test_wrong_answers_are_refused(self):
        scripts = {
            "other request id": ('import sys, json\nrequest = json.load(sys.stdin)\n'
                                 'reply("0" * 32)\n', "PLUGIN_RESPONSE_INVALID"),
            "extra field": ('import sys, json\nrequest = json.load(sys.stdin)\n'
                            'reply(request["request_id"], surprise=1)\n', "PLUGIN_RESPONSE_INVALID"),
            "error without error": ('import sys, json\nrequest = json.load(sys.stdin)\n'
                                    'reply(request["request_id"], "error")\n', "PLUGIN_RESPONSE_INVALID"),
            "too many diagnostics": ('import sys, json\nrequest = json.load(sys.stdin)\n'
                                     'reply(request["request_id"], diagnostics=["x"] * 21)\n',
                                     "PLUGIN_RESPONSE_INVALID"),
            "empty": ('import sys\nsys.stdin.read()\n', "PLUGIN_RESPONSE_INVALID"),
            "banner before json": ('import sys\nsys.stdin.read()\nprint("hello")\nprint("{}")\n', "PROTOCOL_STDOUT"),
            "exit 3": ('import sys\nsys.stdin.read()\nsys.exit(3)\n', "PROCESS_EXIT"),
            "describe is an error": ('import sys, json\nrequest = json.load(sys.stdin)\n'
                                     'reply(request["request_id"], "error", error={"code": "NO", "message": "m"})\n',
                                     "PLUGIN_HANDSHAKE_MISMATCH"),
        }
        for label, (script, code) in scripts.items():
            with self.subTest(label):
                name = label.replace(" ", "-")
                self.plugin("echo", plugin_id=name, patch={"id": name}, script=script)
                with self.assertRaises(ExtError) as caught:
                    plugins.describe_plugin(self.registration(name), env=self.env, project=self.project)
                self.assertEqual(caught.exception.code, code)

    def test_plugin_text_in_messages_is_escaped(self):
        script = 'import sys\nsys.stdin.read()\nsys.stderr.write("first\\n\\x1b[31mred\\n")\nsys.exit(1)\n'
        self.plugin("echo", plugin_id="noisy", patch={"id": "noisy"}, script=script)
        with self.assertRaises(ExtError) as caught:
            plugins.describe_plugin(self.registration("noisy"), env=self.env, project=self.project)
        self.assertEqual(caught.exception.code, "PROCESS_EXIT")
        self.assertNotIn("\x1b", caught.exception.message)
        self.assertIn("\\x1b", caught.exception.message)

    def test_safe_text(self):
        self.assertEqual(plugins.safe_text("a\u2028b\x85c\nd\x1b"), "a\\u2028b\\x85c\\nd\\x1b")
        self.assertEqual(plugins.safe_text("é ✓"), "é ✓")
        self.assertEqual(len(plugins.safe_text("x" * 500)), 200)


class TestInvoke(PluginCase):
    def setUp(self):
        super().setUp()
        self.env["SKM_UNITS_PATH"] = str(UNITS)

    def test_echo_returns_its_input(self):
        self.plugin("echo", marks=True)
        results = self.invoke(data={"x": 1, "deep": {"y": [1, 2]}})
        self.assertEqual(len(results), 1)
        self.assertEqual((results[0].plugin, results[0].status, results[0].output, results[0].code, results[0].error),
                         ("echo", "ok", {"x": 1, "deep": {"y": [1, 2]}}, None, None))
        self.assertGreaterEqual(results[0].duration_ms, 0)
        self.assertEqual(self.op_names(), ["start", "describe", "start", "invoke"])
        context = self.ops()[-1]["context"]
        self.assertEqual(context, {"project_root": str(self.project), "attempt": 1, "trusted": True})

    def test_a_point_no_module_declares_is_refused(self):
        self.plugin("echo")
        with self.assertRaises(ExtError) as caught:
            plugins.invoke_point("ghost:point", {}, project=self.project, env=self.env, home=self.home)
        self.assertEqual(caught.exception.code, "PLUGIN_POINT_UNKNOWN")

    def test_only_plugins_of_the_point_and_kind_are_called(self):
        self.plugin("echo", marks=True)
        self.plugin("sub", plugin_id="sub")
        self.plugin("probe", patch={"provides": {"points": ["demo:other"]}})
        self.assertEqual([item.plugin for item in self.invoke()], ["echo"])
        with self.assertRaises(ExtError) as caught:  # no module declares demo:other, whoever provides it
            self.invoke(point="demo:other")
        self.assertEqual(caught.exception.code, "PLUGIN_POINT_UNKNOWN")

    def test_the_input_must_be_an_object(self):
        with self.assertRaises(ValueError):
            plugins.invoke_point("demo:check", [1], project=self.project, env=self.env, home=self.home)

    def test_one_failing_plugin_does_not_stop_the_others(self):
        self.plugin("bad-version", plugin_id="aaa-bad", patch={"id": "aaa-bad"}, describe={"version": "9.9.9"})
        self.plugin("echo", plugin_id="zzz-echo", patch={"id": "zzz-echo"})
        results = self.invoke()
        self.assertEqual([(item.plugin, item.status) for item in results],
                         [("aaa-bad", "error"), ("zzz-echo", "ok")])
        self.assertEqual(results[0].code, "PLUGIN_HANDSHAKE_MISMATCH")
        self.assertIsNone(results[0].output)

    def test_an_error_answer_keeps_the_plugin_code(self):
        script = ('def invoke(request):\n    reply(request["request_id"], "error", '
                  'error={"code": "BAD_INPUT", "message": "x is wrong"})\n    raise SystemExit(0)\n\n\n'
                  'serve(Path(__file__).resolve().parent, invoke=invoke)\n')
        self.plugin("echo", script=script)
        result = self.invoke()[0]
        self.assertEqual((result.status, result.code, result.error, result.output),
                         ("error", "BAD_INPUT", "x is wrong", None))

    def test_a_timeout_kills_the_plugin_and_is_reported(self):
        script = ('import time\n\n\ndef invoke(request):\n    time.sleep(60)\n\n\n'
                  'serve(Path(__file__).resolve().parent, invoke=invoke)\n')
        self.plugin("echo", script=script, timeout=1)
        started = time.monotonic()
        result = self.invoke()[0]
        self.assertEqual((result.status, result.code), ("error", "PROCESS_TIMEOUT"))
        self.assertLess(time.monotonic() - started, 30)

    def test_a_declared_stdout_limit_lets_a_large_answer_through(self):
        data = {"pad": "z" * (1536 * 1024)}
        self.plugin("echo", patch={"limits": {"max_stdout_bytes": 4 * 1024 * 1024}})
        result = self.invoke(data=data)[0]
        self.assertEqual((result.status, result.code), ("ok", None))
        self.assertEqual(result.output, data)

    def test_without_the_field_a_large_answer_is_too_large(self):
        self.plugin("echo")
        result = self.invoke(data={"pad": "z" * (1536 * 1024)})[0]
        self.assertEqual((result.status, result.code), ("error", "PROTOCOL_STDOUT_TOO_LARGE"))

    def test_skipped_status_is_passed_on(self):
        script = ('def invoke(request):\n    reply(request["request_id"], "skipped")\n'
                  '    raise SystemExit(0)\n\n\nserve(Path(__file__).resolve().parent, invoke=invoke)\n')
        self.plugin("echo", script=script)
        self.assertEqual([(item.status, item.output) for item in self.invoke()], [("skipped", None)])

    def test_the_plugin_runs_in_the_project_directory(self):
        script = ('import os\n\n\ndef invoke(request):\n    return {"cwd": os.getcwd()}\n\n\n'
                  'serve(Path(__file__).resolve().parent, invoke=invoke)\n')
        self.plugin("echo", script=script)
        self.assertEqual(self.invoke()[0].output["cwd"], os.path.realpath(self.project))


class TestSecretsAndEnvironment(PluginCase):
    def setUp(self):
        super().setUp()
        self.env["SKM_UNITS_PATH"] = str(UNITS)
        self.env["FIXTURE_SECRET"] = SENTINEL
        self.env["FIXTURE_PLAIN"] = "plain"
        self.env["AWS_SECRET_ACCESS_KEY"] = SENTINEL

    NAMES = {"names": ["FIXTURE_SECRET", "FIXTURE_PLAIN", "AWS_SECRET_ACCESS_KEY", "SKM_EXT_TRUSTED"]}

    def test_untrusted_plugin_gets_neither_the_variable_nor_the_secret(self):
        self.plugin("probe")
        result = self.invoke(data=self.NAMES)[0]
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["present"], {"FIXTURE_SECRET": False, "FIXTURE_PLAIN": False,
                                                    "AWS_SECRET_ACCESS_KEY": False, "SKM_EXT_TRUSTED": True})
        self.assertEqual(result.output["trusted"], "0")
        self.assertNotIn(SENTINEL, repr(result))

    def test_trusted_plugin_gets_what_it_asks_for_and_nothing_else(self):
        self.plugin("probe", trusted=True)
        result = self.invoke(data=self.NAMES)[0]
        self.assertEqual(result.output["present"], {"FIXTURE_SECRET": True, "FIXTURE_PLAIN": True,
                                                    "AWS_SECRET_ACCESS_KEY": False, "SKM_EXT_TRUSTED": True})
        self.assertEqual(result.output["trusted"], "1")
        self.assertNotIn(SENTINEL, repr(result))

    def test_a_secret_echoed_to_stderr_is_redacted_in_the_failure(self):
        script = ('import os, sys\n\n\ndef invoke(request):\n    sys.stderr.write("token=" + '
                  'os.environ["FIXTURE_SECRET"] + "\\n")\n    sys.exit(2)\n\n\n'
                  'serve(Path(__file__).resolve().parent, invoke=invoke)\n')
        self.plugin("probe", trusted=True, script=script)
        result = self.invoke()[0]
        self.assertEqual((result.status, result.code), ("error", "PROCESS_EXIT"))
        self.assertIn("token=***", result.error)
        self.assertNotIn(SENTINEL, repr(result))

    def test_unsupported_and_unresolvable_secrets_refuse_the_launch(self):
        self.plugin("probe", plugin_id="keyring", trusted=True,
                    patch={"id": "keyring", "permissions": {"secrets": ["keyring://token"]}})
        self.plugin("probe", plugin_id="missing", trusted=True,
                    patch={"id": "missing", "permissions": {"secrets": ["env://NOT_SET_ANYWHERE"]}})
        results = {item.plugin: item for item in self.invoke()}
        self.assertEqual(results["keyring"].code, "PLUGIN_SECRET_UNSUPPORTED")
        self.assertEqual(results["missing"].code, "PLUGIN_SECRET_UNRESOLVED")
        self.assertNotIn(SENTINEL, repr(results))
        self.assertIn("PLUGIN_SECRET_UNRESOLVED", CODES)

    def test_status_names_what_an_untrusted_plugin_did_not_get(self):
        self.plugin("probe")
        code, out, _err = self.cli("ext", "status")
        self.assertEqual(code, 0)
        self.assertIn("untrusted", out)
        self.assertIn("FIXTURE_PLAIN", out)
        self.assertIn("env://FIXTURE_SECRET", out)
        self.assertNotIn(SENTINEL, out)


class TestSubscribers(PluginCase):
    def setUp(self):
        super().setUp()
        empty = self.tmp / "no-units"
        empty.mkdir()
        self.env["SKM_UNITS_PATH"] = str(empty)

    def subscribe(self, name="tap", plugin="sub", on=("demo.*",), **extra):
        lines = [f"[aicore.subscriptions.{name}]", f"on = {json.dumps(list(on))}", f"plugin = {json.dumps(plugin)}"]
        lines += [f"{key} = {json.dumps(value)}" for key, value in extra.items()]
        self.machine("\n".join(lines) + "\n")

    def emit(self, type="demo.thing.happened", mode="off"):
        """``mode="sync"`` delivers at once: a new subscription starts at the event that triggered the delivery."""
        return events.emit(type, source=type.split(".")[0], project=self.project, delivery=mode, env=self.env,
                           home=self.home)

    def log(self):
        return delivery._read_records(delivery.deliveries_path(self.journal))

    def deliver(self):
        return delivery.deliver(self.journal, project=self.project, env=self.env, home=self.home)

    def status(self):
        return delivery.delivery_status(self.journal, project=self.project, env=self.env, home=self.home)

    def test_a_subscriber_plugin_receives_the_event_once(self):
        self.plugin("sub", marks=True)
        self.subscribe()
        first = self.emit(mode="sync")
        self.assertEqual([(item["op"], item.get("id"), item.get("type")) for item in self.ops()],
                         [("start", None, None), ("describe", None, None), ("start", None, None),
                          ("event", first.id, "demo.thing.happened")])
        self.assertEqual(self.ops()[-1]["attempt"], 1)
        report = self.deliver()
        self.assertEqual((report.delivered, report.failed, report.problems), (0, 0, []))
        second = self.emit("demo.other.done")
        report = self.deliver()
        self.assertEqual((report.delivered, report.failed, report.problems), (1, 0, []))
        self.assertEqual(self.ops()[-1]["id"], second.id)
        self.assertEqual([(item["subscription"], item["outcome"], item["code"]) for item in self.log()],
                         [("tap", "ok", None)] * 2)

    def test_status_row_names_the_plugin(self):
        self.plugin("sub", marks=True)
        self.subscribe()
        self.emit()
        row = self.status()["subscriptions"][0]
        self.assertEqual((row["id"], row["plugin"], row["active"]), ("tap", "sub", True))
        self.assertEqual(self.status()["problems"], [])

    def test_patterns_must_be_covered_by_the_manifest(self):
        self.plugin("sub", marks=True)
        self.subscribe(on=("plan.*",))
        self.emit("plan.item.closed")
        report = self.deliver()
        self.assertEqual([item["code"] for item in report.problems], ["SUBSCRIPTION_INVALID"])
        self.assertEqual(report.delivered, 0)
        self.assertEqual(self.ops(), [])
        self.assertIn("SUBSCRIPTION_INVALID", [item["code"] for item in self.status()["problems"]])

    def test_a_narrower_pattern_is_covered(self):
        self.plugin("sub", marks=True)
        self.subscribe(on=("demo.thing.*",))
        event = self.emit(mode="sync")
        self.assertEqual([item["id"] for item in self.ops() if item["op"] == "event"], [event.id])

    def test_a_command_plugin_cannot_subscribe(self):
        self.plugin("echo", marks=True)
        self.subscribe(plugin="echo")
        self.emit()
        self.assertEqual([item["code"] for item in self.deliver().problems], ["SUBSCRIPTION_INVALID"])
        self.assertEqual(self.ops(), [])

    def test_unknown_and_disabled_plugins_are_unavailable(self):
        self.plugin("sub", enabled=False)
        self.subscribe(name="off", plugin="sub")
        self.subscribe(name="ghost", plugin="nobody")
        self.emit()
        report = self.deliver()
        self.assertEqual(sorted((item["subscription"], item["code"]) for item in report.problems),
                         [("ghost", "PLUGIN_UNAVAILABLE"), ("off", "PLUGIN_UNAVAILABLE")])
        self.assertFalse(delivery.cursors_path(self.journal).exists())

    def test_a_broken_manifest_makes_the_subscription_unavailable(self):
        self.plugin("sub", patch={"kind": "library"})
        self.subscribe()
        self.emit()
        report = self.deliver()
        self.assertEqual([item["code"] for item in report.problems], ["PLUGIN_UNAVAILABLE"])
        self.assertIn("PLUGIN_MANIFEST_INVALID", report.problems[0]["message"])

    def test_a_handshake_failure_is_a_failed_attempt_and_ends_in_the_dead_letters(self):
        self.plugin("sub", describe={"version": "9.9.9"})
        self.machine("[aicore.events]\nmax_attempts = 2\n")
        self.subscribe()
        self.emit(mode="sync")
        self.assertEqual([(item["outcome"], item["code"]) for item in self.log()],
                         [("failed", "PLUGIN_HANDSHAKE_MISMATCH")])
        report = self.deliver()
        self.assertEqual((report.delivered, report.failed, report.dead_lettered), (0, 0, 1))
        self.assertEqual(self.deliver().dead_lettered, 0)

    def test_replay_of_one_event_goes_through_the_plugin(self):
        self.plugin("sub", marks=True)
        self.subscribe()
        event = self.emit(mode="sync")
        report = delivery.replay(self.journal, "tap", event_id=event.id, project=self.project, env=self.env,
                                 home=self.home)
        self.assertEqual((report.delivered, report.failed), (1, 0))
        self.assertEqual([item["id"] for item in self.ops() if item["op"] == "event"], [event.id, event.id])

    def test_replay_refuses_a_plugin_that_cannot_receive(self):
        self.subscribe(plugin="nobody")
        event = self.emit()
        with self.assertRaises(ExtError) as caught:
            delivery.replay(self.journal, "tap", event_id=event.id, project=self.project, env=self.env, home=self.home)
        self.assertEqual(caught.exception.code, "PLUGIN_UNAVAILABLE")

    def test_a_failed_attempt_is_retried_with_the_next_attempt_number(self):
        script = ('def event(request):\n    if request["context"]["attempt"] == 1:\n'
                  '        reply(request["request_id"], "error", error={"code": "TRY_AGAIN", "message": "later"})\n'
                  '        raise SystemExit(0)\n    return "ok"\n\n\n'
                  'serve(Path(__file__).resolve().parent, event=event)\n')
        self.plugin("sub", marks=True, script=script)
        self.subscribe()
        self.emit(mode="sync")
        self.assertEqual([(item["outcome"], item["code"]) for item in self.log()], [("failed", "TRY_AGAIN")])
        self.assertEqual(self.deliver().delivered, 1)
        self.assertEqual([item["attempt"] for item in self.ops() if item["op"] == "event"], [1, 2])


class TestCli(PluginCase):
    def setUp(self):
        super().setUp()
        self.env["SKM_UNITS_PATH"] = str(UNITS)

    def test_ext_is_a_group(self):
        code, out, _err = run_cli("--help")
        self.assertEqual(code, 0)
        self.assertIn("ext", [line.split()[0] for line in out.splitlines() if line.startswith("  ")])
        self.assertEqual(run_cli("ext")[0], 2)

    def test_plugins_list(self):
        self.plugin("echo")
        self.plugin("sub", trusted=True)
        code, out, _err = self.cli("ext", "plugins", "list")
        self.assertEqual(code, 0)
        self.assertIn("echo command 0.1.0 untrusted enabled", out)
        self.assertIn("sub subscriber 0.1.0 trusted enabled", out)
        code, out, _err = self.cli("ext", "plugins", "list", "--json")
        rows = {row["id"]: row for row in json.loads(out)["plugins"]}
        self.assertEqual((rows["echo"]["trusted"], rows["sub"]["trusted"]), (False, True))
        self.assertEqual(rows["echo"]["points"], ["demo:check"])
        self.assertEqual(rows["echo"]["profile"], {"profile": "trusted-local", "enforced": False})
        self.assertEqual(rows["sub"]["events"], ["demo.*"])

    def test_list_starts_nothing(self):
        self.plugin("echo", marks=True)
        self.cli("ext", "plugins", "list")
        self.cli("ext", "status")
        self.assertEqual(self.ops(), [])

    def test_the_manifest_path_is_shown_with_a_tilde(self):
        target = self.home / "p" / "echo"
        shutil.copytree(PLUGINS / "echo", target, ignore=shutil.ignore_patterns("marks", "__pycache__"))
        self.machine(f'[aicore.plugins.echo]\nmanifest = "{target}/extension.json"\n')
        code, out, _err = self.cli("ext", "plugins", "list")
        self.assertIn("manifest: ~/p/echo/extension.json", out)

    def test_describe(self):
        self.plugin("echo")
        code, out, err = self.cli("ext", "plugins", "describe", "echo")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("echo command 0.1.0 protocol 1 stdio-json sha256:", out)
        code, out, _err = self.cli("ext", "plugins", "describe", "echo", "--json")
        self.assertEqual(json.loads(out)["id"], "echo")
        code, _out, err = self.cli("ext", "plugins", "describe", "nobody")
        self.assertEqual(code, 1)
        self.assertIn("PLUGIN_NOT_FOUND", err)

    def test_describe_reports_a_mismatch(self):
        self.plugin("bad-version", trusted=True)
        code, _out, err = self.cli("ext", "plugins", "describe", "bad-version")
        self.assertEqual(code, 1)
        self.assertIn("PLUGIN_HANDSHAKE_MISMATCH", err)

    def test_invoke_json(self):
        self.plugin("echo")
        code, out, err = self.cli("ext", "plugins", "invoke", "demo:check", "--input", '{"x": 1}', "--json")
        self.assertEqual((code, err), (0, ""))
        document = json.loads(out)
        self.assertEqual(document["point"], "demo:check")
        self.assertEqual(len(document["results"]), 1)
        result = document["results"][0]
        self.assertEqual((result["plugin"], result["status"], result["output"], result["error"], result["code"]),
                         ("echo", "ok", {"x": 1}, None, None))
        self.assertIsInstance(result["duration_ms"], int)

    def test_invoke_text_input_file_and_failures(self):
        self.plugin("echo")
        data = self.tmp / "input.json"
        data.write_text('{"y": 2}', encoding="utf-8")
        code, out, _err = self.cli("ext", "plugins", "invoke", "demo:check", "--input-file", str(data))
        self.assertEqual(code, 0)
        self.assertIn("echo ok", out)
        self.assertIn('{"y": 2}', out)
        self.assertEqual(self.cli("ext", "plugins", "invoke", "demo:check", "--input", "[1]")[0], 1)
        self.assertEqual(self.cli("ext", "plugins", "invoke", "demo:check", "--input", "{bad")[0], 1)
        self.assertEqual(self.cli("ext", "plugins", "invoke", "demo:check", "--input", "{}", "--input-file",
                                  str(data))[0], 2)
        code, _out, err = self.cli("ext", "plugins", "invoke", "ghost:point")
        self.assertEqual(code, 1)
        self.assertIn("PLUGIN_POINT_UNKNOWN", err)

    def test_invoke_exits_1_when_a_plugin_failed_and_0_without_plugins(self):
        code, out, _err = self.cli("ext", "plugins", "invoke", "demo:check")
        self.assertEqual(code, 0)
        self.assertIn("no plugin handles demo:check", out)
        self.plugin("bad-version", trusted=True, describe={"version": "9.9.9"})
        code, out, _err = self.cli("ext", "plugins", "invoke", "demo:check")
        self.assertEqual(code, 1)
        self.assertIn("error PLUGIN_HANDSHAKE_MISMATCH", out)

    def test_status_text(self):
        self.plugin("echo")
        self.plugin("probe", trusted=True)
        code, out, err = self.cli("ext", "status")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("echo command 0.1.0 untrusted enabled", out)
        self.assertIn("probe command 0.1.0 trusted enabled", out)
        self.assertIn("profile: trusted-local, enforced: false", out)
        self.assertIn("points: demo:check", out)
        self.assertIn("subscriptions:", out)
        self.assertIn("demo:log unit on lag 0", out)

    def test_status_lists_plugin_subscriptions_and_exits_0_with_problems(self):
        self.plugin("sub", plugin_id="sub")
        self.plugin("bad-schema", plugin_id="bad-schema")
        self.machine('[aicore.subscriptions.tap]\non = ["demo.*"]\nplugin = "sub"\n'
                     '[aicore.subscriptions.lost]\non = ["demo.*"]\nplugin = "nobody"\n')
        code, out, err = self.cli("ext", "status")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("tap config plugin sub on", out)
        self.assertIn("problem: PLUGIN_MANIFEST_INVALID", out)
        self.assertIn("problem: PLUGIN_UNAVAILABLE", out)
        code, out, _err = self.cli("ext", "status", "--json")
        document = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual({item["code"] for item in document["problems"]}, {"PLUGIN_MANIFEST_INVALID",
                                                                           "PLUGIN_UNAVAILABLE"})
        self.assertEqual({item["id"] for item in document["plugins"]}, {"sub", "bad-schema"})

    def test_status_survives_a_broken_configuration(self):
        self.machine('[aicore.plugins.x]\nunknown_key = 1\n')
        code, out, _err = self.cli("ext", "status")
        self.assertEqual(code, 0)
        self.assertIn("problem: CONFIG_INVALID", out)
        self.assertEqual(out.count("CONFIG_INVALID"), 1)

    def test_status_without_anything(self):
        code, out, _err = self.cli("ext", "status")
        self.assertEqual(code, 0)
        self.assertIn("plugins: none", out)


class TestUnit(unittest.TestCase):
    def test_doctor_probe_is_declared(self):
        doc = json.loads((AICORE_ROOT / "unit.json").read_text(encoding="utf-8"))
        checks = {item["id"]: item for item in doc["provides"]["doctor"]}
        self.assertEqual(checks["aicore.ext"], {"id": "aicore.ext", "category": "integration",
                                                "probe": ["bin/aicore", "ext", "status"], "output": "text"})

    def test_codes_are_registered(self):
        for code in ("PLUGIN_MANIFEST_INVALID", "PLUGIN_PROTOCOL_UNSUPPORTED", "PLUGIN_REQUIRES_UNSATISFIED",
                     "PLUGIN_ID_MISMATCH", "PLUGIN_POINT_UNKNOWN", "PLUGIN_HANDSHAKE_MISMATCH",
                     "PLUGIN_RESPONSE_INVALID", "PLUGIN_NOT_FOUND", "PLUGIN_SECRET_UNRESOLVED"):
            self.assertIn(code, CODES)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
