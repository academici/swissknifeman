"""Host configuration: discovery, closed validation, commands, plugin dirs and cache.

Fixtures use synthetic plugin names (`plugin-a`, `vendor/plugin-a`) so the test stays
inside the package boundary; the real host instance is checked by the plan item's
acceptance command, not here."""
import contextlib
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skiller import host as host_mod
from skiller.common import Env
from skiller.host import (
    HOST_CONFIG_ENV, HOST_CONFIG_INVALID, Host, host_command, host_plugin_dirs, load_host,
)

SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "host" / "v1" / "host.schema.json"

FULL = {
    "schema_version": 1,
    "plugin_dirs": ["vendor/*"],
    "bucket_aliases": {"env-skills": ["plugin-a"]},
    "default_command_plugins": ["plugin-a"],
    "version_files": [{"path": "vendor/plugin-a/configs/routing.json", "key": "plugin_version"}],
    "machine_plugins": {
        "grok": [{"name": "plugin-a", "path": "vendor/plugin-a",
                  "holds": ["vendor/plugin-a/adapters/grok/hold"]}],
    },
    "runtime_projection_plugins": ["plugin-a"],
    "codex_link_roots": ["vendor/plugin-a/adapters/codex/skills"],
    "legacy_runtime_links": [{"link": "vendor/plugin-a", "plugin": "plugin-a",
                              "source": "vendor/plugin-a"}],
    "commands": {
        "permissions": {"argv": ["vendor/tool-b/bin/tool-b", "permissions"],
                        "env_override": "SKILLER_TEST_TOOL_BIN",
                        "install_hint": "vendor/tool-b/install.sh"},
        "lookup": {"argv": ["tool-on-path", "doctor"]},
    },
    "mcp_servers": {"memory": {"tools": 11, "instructions_tokens": 0}},
    "bootstrap": "configs/bootstrap.json",
}


class HostCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name).resolve()
        (self.repo / ".git").mkdir()
        self.package = self.repo / "vendor" / "skills-tool"
        self.package.mkdir(parents=True)
        host_mod.clear_host_cache()
        self.addCleanup(host_mod.clear_host_cache)
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(HOST_CONFIG_ENV, None)
        os.environ.pop("SKILLER_TEST_TOOL_BIN", None)

    def write_config(self, data, path=None):
        path = path or self.repo / "configs" / "skiller-host.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data) if not isinstance(data, str) else data,
                        encoding="utf-8")
        return path

    def assert_invalid(self, data, field):
        self.write_config(data)
        host_mod.clear_host_cache()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            load_host(self.package)
        self.assertNotEqual(raised.exception.code, 0)
        self.assertIn(f"{HOST_CONFIG_INVALID}: {field}", stderr.getvalue())


class DiscoveryTests(HostCase):
    def test_repo_root_config_is_loaded_with_all_fields(self):
        config = self.write_config(FULL)
        loaded = load_host(self.package)
        self.assertEqual(loaded.root, self.repo)
        self.assertEqual(loaded.source, config)
        self.assertEqual(loaded.plugin_dirs, ("vendor/*",))
        self.assertEqual(loaded.default_command_plugins, ("plugin-a",))
        self.assertEqual(loaded.version_files[0].path, "vendor/plugin-a/configs/routing.json")
        self.assertEqual(loaded.version_files[0].key, "plugin_version")
        grok = loaded.machine_plugins["grok"][0]
        self.assertEqual((grok.name, grok.path, grok.holds),
                         ("plugin-a", "vendor/plugin-a", ("vendor/plugin-a/adapters/grok/hold",)))
        self.assertEqual(loaded.runtime_projection_plugins, ("plugin-a",))
        self.assertEqual(loaded.codex_link_roots, ("vendor/plugin-a/adapters/codex/skills",))
        link = loaded.legacy_runtime_links[0]
        self.assertEqual((link.link, link.plugin, link.source),
                         ("vendor/plugin-a", "plugin-a", "vendor/plugin-a"))
        command = loaded.commands["permissions"]
        self.assertEqual(command.argv, ("vendor/tool-b/bin/tool-b", "permissions"))
        self.assertEqual(command.env_override, "SKILLER_TEST_TOOL_BIN")
        self.assertEqual(command.install_hint, "vendor/tool-b/install.sh")
        self.assertIsNone(loaded.commands["lookup"].env_override)
        self.assertEqual(loaded.mcp_servers["memory"].tools, 11)
        self.assertEqual(loaded.mcp_servers["memory"].instructions_tokens, 0)
        self.assertEqual(loaded.bootstrap, "configs/bootstrap.json")

    def test_minimal_config_has_empty_defaults(self):
        self.write_config({"schema_version": 1})
        loaded = load_host(self.package)
        self.assertEqual(loaded.root, self.repo)
        self.assertEqual(loaded.plugin_dirs, ())
        self.assertEqual(dict(loaded.commands), {})
        self.assertIsNone(loaded.bootstrap)

    def test_env_override_wins_over_repo_root(self):
        self.write_config({"schema_version": 1, "default_command_plugins": ["repo"]})
        other = self.write_config({"schema_version": 1, "default_command_plugins": ["env"]},
                                  self.repo / "elsewhere" / "host.json")
        os.environ[HOST_CONFIG_ENV] = str(other)
        loaded = load_host(self.package)
        self.assertEqual(loaded.default_command_plugins, ("env",))
        self.assertEqual(loaded.source, other)
        self.assertEqual(loaded.root, self.repo)

    def test_env_override_must_exist_and_be_absolute(self):
        for value, text in ((str(self.repo / "missing.json"), "not found"),
                            ("relative/host.json", "absolute")):
            with self.subTest(value=value):
                os.environ[HOST_CONFIG_ENV] = value
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
                    load_host(self.package)
                self.assertIn(HOST_CONFIG_ENV, stderr.getvalue())
                self.assertIn(text, stderr.getvalue())

    def test_missing_config_is_a_silent_empty_host(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            loaded = load_host(self.package)
        self.assertEqual(loaded, Host.empty())
        self.assertIsNone(loaded.root)
        self.assertEqual(stderr.getvalue(), "")

    def test_standalone_package_ignores_its_own_configs_dir(self):
        (self.package / ".git").mkdir()
        self.write_config(FULL, self.package / "configs" / "skiller-host.json")
        self.assertEqual(load_host(self.package), Host.empty())

    def test_no_repository_is_an_empty_host(self):
        with tempfile.TemporaryDirectory() as bare:
            self.assertEqual(load_host(Path(bare)), Host.empty())

    def test_host_follows_package_root_not_working_directory(self):
        consumer = self.repo / "consumer"
        (consumer / ".git").mkdir(parents=True)
        self.write_config(FULL, consumer / "configs" / "skiller-host.json")
        previous = Path.cwd()
        os.chdir(consumer)
        self.addCleanup(os.chdir, previous)
        self.assertEqual(load_host(self.package), Host.empty())
        self.write_config({"schema_version": 1, "default_command_plugins": ["hub"]})
        self.assertEqual(load_host(self.package).default_command_plugins, ("hub",))

    def test_empty_host_is_immutable(self):
        empty = Host.empty()
        with self.assertRaises(AttributeError):
            empty.plugin_dirs = ("x",)
        with self.assertRaises(TypeError):
            empty.commands["x"] = None


class ValidationTests(HostCase):
    def test_invalid_documents(self):
        cases = [
            ("not json", "json"),
            ([], "root"),
            ({}, "schema_version"),
            ({"schema_version": 2}, "schema_version"),
            ({"schema_version": True}, "schema_version"),
            ({"schema_version": 1, "unknown": 1}, "unknown"),
            ({"schema_version": 1, "plugin_dirs": "vendor/*"}, "plugin_dirs"),
            ({"schema_version": 1, "plugin_dirs": ["/abs/*"]}, "plugin_dirs[0]"),
            ({"schema_version": 1, "plugin_dirs": ["vendor/../x"]}, "plugin_dirs[0]"),
            ({"schema_version": 1, "plugin_dirs": [""]}, "plugin_dirs[0]"),
            ({"schema_version": 1, "plugin_dirs": ["vendor\\x"]}, "plugin_dirs[0]"),
            ({"schema_version": 1, "default_command_plugins": [1]}, "default_command_plugins[0]"),
            ({"schema_version": 1, "default_command_plugins": ["a b"]},
             "default_command_plugins[0]"),
            ({"schema_version": 1, "version_files": [{"path": "a.json"}]}, "version_files[0].key"),
            ({"schema_version": 1, "version_files": [{"path": "../a.json", "key": "v"}]},
             "version_files[0].path"),
            ({"schema_version": 1, "version_files": [{"path": "a", "key": "v", "x": 1}]},
             "version_files[0].x"),
            ({"schema_version": 1, "machine_plugins": {"grok": [{"name": "a", "path": "/a"}]}},
             "machine_plugins.grok[0].path"),
            ({"schema_version": 1, "machine_plugins": {"grok": [
                {"name": "a", "path": "a", "holds": ["../h"]}]}},
             "machine_plugins.grok[0].holds[0]"),
            ({"schema_version": 1, "machine_plugins": []}, "machine_plugins"),
            ({"schema_version": 1, "codex_link_roots": ["/abs"]}, "codex_link_roots[0]"),
            ({"schema_version": 1, "legacy_runtime_links": [{"link": "a", "plugin": "a"}]},
             "legacy_runtime_links[0].source"),
            ({"schema_version": 1, "commands": {"c": {"argv": []}}}, "commands.c.argv"),
            ({"schema_version": 1, "commands": {"c": {"argv": ["/usr/bin/x"]}}},
             "commands.c.argv[0]"),
            ({"schema_version": 1, "commands": {"c": {"argv": ["../bin/x"]}}},
             "commands.c.argv[0]"),
            ({"schema_version": 1, "commands": {"c": {"argv": ["x", 1]}}}, "commands.c.argv[1]"),
            ({"schema_version": 1, "commands": {"c": {"argv": ["x"], "env_override": "1-X"}}},
             "commands.c.env_override"),
            ({"schema_version": 1, "commands": {"c": {"argv": ["x"], "shell": True}}},
             "commands.c.shell"),
            ({"schema_version": 1, "mcp_servers": {"m": {"tools": -1}}}, "mcp_servers.m.tools"),
            ({"schema_version": 1, "mcp_servers": {"m": {"tools": True}}}, "mcp_servers.m.tools"),
            ({"schema_version": 1, "bootstrap": "/etc/boot.json"}, "bootstrap"),
            ({"schema_version": 1, "bootstrap": 3}, "bootstrap"),
        ]
        for data, field in cases:
            with self.subTest(field=field, data=data):
                self.assert_invalid(data, field)

    def test_schema_and_validator_key_sets_match(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(schema["$id"], "urn:swissknifeman:skiller:host:v1")
        props = schema["properties"]

        def entry(node):
            return next(iter(node["patternProperties"].values()))

        objects = {
            "": schema,
            "version_files": props["version_files"]["items"],
            "machine_plugins": entry(props["machine_plugins"])["items"],
            "legacy_runtime_links": props["legacy_runtime_links"]["items"],
            "commands": entry(props["commands"]),
            "mcp_servers": entry(props["mcp_servers"]),
        }
        self.assertEqual(set(objects), set(host_mod.OBJECT_KEYS))
        for name, node in objects.items():
            with self.subTest(object=name or "root"):
                self.assertIs(node["additionalProperties"], False)
                self.assertEqual(set(node["properties"]), set(host_mod.OBJECT_KEYS[name]))
                self.assertEqual(set(node.get("required", [])),
                                 set(host_mod.REQUIRED_KEYS.get(name, ())))
                for key, prop in node["properties"].items():
                    self.assertTrue(prop.get("description"), f"{name}.{key}: description")

    def test_full_example_matches_schema_types(self):
        self.write_config(FULL)
        self.assertEqual(set(FULL), set(host_mod.OBJECT_KEYS[""]))
        load_host(self.package)


class CommandTests(HostCase):
    def make_executable(self, relative):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def test_relative_argv_resolves_against_repo_root(self):
        self.write_config(FULL)
        binary = self.make_executable("vendor/tool-b/bin/tool-b")
        self.assertEqual(host_command(self.package, "permissions"),
                         [str(binary), "permissions"])
        self.assertEqual(host_command(Env(root=self.package), "permissions"),
                         [str(binary), "permissions"])

    def test_env_override_replaces_argv0(self):
        self.write_config(FULL)
        self.make_executable("vendor/tool-b/bin/tool-b")
        override = self.make_executable("custom/tool")
        os.environ["SKILLER_TEST_TOOL_BIN"] = str(override)
        self.assertEqual(host_command(self.package, "permissions"),
                         [str(override), "permissions"])
        os.environ["SKILLER_TEST_TOOL_BIN"] = str(self.repo / "custom" / "missing")
        self.assertIsNone(host_command(self.package, "permissions"))

    def test_bare_name_is_looked_up_on_path(self):
        self.write_config(FULL)
        found = self.make_executable("path-bin/tool-on-path")
        os.environ["PATH"] = str(found.parent)
        self.assertEqual(host_command(self.package, "lookup"), [str(found), "doctor"])
        os.environ["PATH"] = str(self.repo / "nothing")
        self.assertIsNone(host_command(self.package, "lookup"))

    def test_missing_binary_command_or_host_is_none(self):
        self.write_config(FULL)
        self.assertIsNone(host_command(self.package, "permissions"))
        self.assertIsNone(host_command(self.package, "absent"))
        (self.repo / "configs" / "skiller-host.json").unlink()
        host_mod.clear_host_cache()
        self.assertIsNone(host_command(self.package, "permissions"))


class PluginDirTests(HostCase):
    def plugin(self, relative):
        path = self.repo / relative
        (path / ".claude-plugin").mkdir(parents=True)
        (path / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
        return path

    def test_glob_candidates_with_manifest_except_self(self):
        (self.package / ".claude-plugin").mkdir()
        (self.package / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
        second = self.plugin("vendor/plugin-b")
        first = self.plugin("vendor/plugin-a")
        extra = self.plugin("extra/plugin-c")
        (self.repo / "vendor" / "no-manifest").mkdir()
        (self.repo / "vendor" / "file.txt").write_text("x", encoding="utf-8")
        self.write_config({"schema_version": 1,
                           "plugin_dirs": ["vendor/*", "extra/*", "vendor/plugin-a"]})
        loaded = load_host(self.package)
        self.assertEqual(host_plugin_dirs(self.repo, self.package, loaded),
                         [first, second, extra])

    def test_empty_host_has_no_plugin_dirs(self):
        self.plugin("vendor/plugin-a")
        self.assertEqual(host_plugin_dirs(self.repo, self.package, Host.empty()), [])


class CacheTests(HostCase):
    def test_loaded_host_is_cached_per_resolved_path(self):
        config = self.write_config({"schema_version": 1, "default_command_plugins": ["one"]})
        first = load_host(self.package)
        config.write_text(json.dumps({"schema_version": 1,
                                      "default_command_plugins": ["two"]}), encoding="utf-8")
        self.assertIs(load_host(self.package), first)
        self.assertIs(load_host(self.package / "." / ".." / self.package.name), first)
        host_mod.clear_host_cache()
        self.assertEqual(load_host(self.package).default_command_plugins, ("two",))


if __name__ == "__main__":
    unittest.main()
