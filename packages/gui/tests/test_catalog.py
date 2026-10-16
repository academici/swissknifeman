"""Contribution catalog: sources, resolver rules (CONTRIB_* codes), conflicts, determinism, catalog/v1, gui check."""
import copy
import json
import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import aicore
from aicore.util import schema

from gui import contracts
from gui.catalog import resolve, sources
from gui.catalog.sources import Collected, Source

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "units"
CHECK_RESULT = schema.load_contract(Path(aicore.__file__).resolve().parents[2] / "schemas" / "check-result" / "v1")
CONTRIBUTION = "urn:swissknifeman:gui:contribution:v1"


def demo(owner="demo"):
    return json.loads((FIXTURES / "valid-one" / "demo" / "gui.json").read_text(encoding="utf-8").replace(
        '"demo', f'"{owner}').replace("demo.", f"{owner}."))


def resolved(*roots, problems=()):
    return resolve.resolve(Collected(sources=sources.unit_sources(list(roots)), problems=list(problems)))


class CatalogCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()

    def unit(self, folder, gui, *, uid=None, provides_gui="gui.json", files=True, root=None):
        """A unit folder with unit.json, gui.json and the files the demo contribution points to."""
        path = (root or self.tmp) / folder
        path.mkdir(parents=True, exist_ok=True)
        uid = uid or folder
        (path / "unit.json").write_text(json.dumps({"id": uid, "provides": {"gui": provides_gui}}), encoding="utf-8")
        if gui is not None:
            text = gui if isinstance(gui, str) else json.dumps(gui)
            (path / "gui.json").write_text(text, encoding="utf-8")
        if files:
            (path / "bin").mkdir(exist_ok=True)
            (path / "bin" / "greet").write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
            (path / "bin" / "greet").chmod(0o755)
            (path / "docs").mkdir(exist_ok=True)
            (path / "docs" / "index.md").write_text("# Guide\n", encoding="utf-8")
        return path

    def catalog(self, *roots, problems=()):
        doc = resolved(*roots, problems=problems)
        self.assertEqual([], contracts.validate(doc, "catalog"), doc)
        return doc

    def rejected_code(self, gui, **kw):
        kw.setdefault("uid", "demo")
        doc = self.catalog(self.unit(kw.pop("folder", "demo"), gui, **kw))
        self.assertEqual([], doc["contributions"])
        self.assertEqual(1, len(doc["rejected"]), doc["rejected"])
        return doc["rejected"][0]["code"], doc["rejected"][0]

    def assertRejected(self, code, gui, **kw):
        found, entry = self.rejected_code(gui, **kw)
        self.assertEqual(code, found, entry["message"])
        return entry


class TestFixtures(CatalogCase):
    def test_empty(self):
        doc = self.catalog(*sorted((FIXTURES / "empty").iterdir()))
        self.assertEqual(([], []), (doc["contributions"], doc["rejected"]))

    def test_valid_one(self):
        doc = self.catalog(FIXTURES / "valid-one" / "demo")
        self.assertEqual(["demo"], [entry["owner"] for entry in doc["contributions"]])
        entry = doc["contributions"][0]
        self.assertEqual("unit", entry["source"])
        self.assertEqual(str((FIXTURES / "valid-one" / "demo" / "gui.json").resolve()), entry["file"])
        self.assertTrue(entry["digest"].startswith("sha256:"))
        self.assertEqual({"min": "1", "max": "1"}, doc["host"]["gui_protocol"])

    def test_two_owners_without_conflict(self):
        doc = self.catalog(*sorted((FIXTURES / "two-owners").iterdir()))
        self.assertEqual(["alpha", "beta"], [entry["owner"] for entry in doc["contributions"]])
        self.assertEqual([], doc["rejected"])

    def test_conflict_rejects_every_participant(self):
        doc = self.catalog(*sorted((FIXTURES / "conflict-id").iterdir()))
        self.assertEqual([], doc["contributions"])
        self.assertEqual(["CONTRIB_CONFLICT", "CONTRIB_CONFLICT"], [entry["code"] for entry in doc["rejected"]])
        self.assertIn("routes 'demo.greet'", doc["rejected"][0]["message"])


class TestConflicts(CatalogCase):
    def test_same_route_path_of_one_owner(self):
        first, second = demo(), demo()
        second["routes"] = [dict(second["routes"][1], id="demo.other")]
        del second["commands"], second["docs"]
        second["routes"][0]["command"] = "demo.missing"
        doc = self.catalog(self.unit("a", first, uid="demo"), self.unit("b", second, uid="demo"))
        self.assertEqual(["CONTRIB_REF_UNKNOWN"], [entry["code"] for entry in doc["rejected"]])
        second["commands"] = copy.deepcopy(first["commands"])
        second["commands"][0]["id"] = second["routes"][0]["command"] = "demo.other"
        doc = self.catalog(self.unit("a", first, uid="demo"), self.unit("b", second, uid="demo"))
        self.assertEqual(2, len(doc["rejected"]))
        self.assertTrue(all("path '/x/demo/greet'" in entry["message"] for entry in doc["rejected"]))

    def test_one_owner_twice_without_shared_ids_still_conflicts(self):
        other = {"$schema": CONTRIBUTION, "owner": "demo", "version": "0.1.0", "gui_protocol": {"min": "1", "max": "1"}}
        doc = self.catalog(self.unit("a", demo(), uid="demo"), self.unit("b", other, uid="demo"))
        self.assertEqual(["CONTRIB_CONFLICT"] * 2, [entry["code"] for entry in doc["rejected"]])
        self.assertIn("owner 'demo'", doc["rejected"][0]["message"])

    def test_duplicates_inside_one_file(self):
        gui = demo()
        gui["routes"].append(dict(gui["routes"][0]))
        self.assertRejected("CONTRIB_CONFLICT", gui)
        gui = demo()
        gui["routes"][1]["path"] = gui["routes"][0]["path"]
        self.assertRejected("CONTRIB_CONFLICT", gui)
        gui = demo()
        gui["commands"][0]["input"].append(dict(gui["commands"][0]["input"][0]))
        self.assertRejected("CONTRIB_CONFLICT", gui)


class TestDeterminism(CatalogCase):
    def test_source_order_does_not_change_the_catalog(self):
        roots = [self.unit(name, demo(name)) for name in ("gamma", "alpha", "beta")]
        roots.append(self.unit("broken", "{not json"))
        roots += [self.unit("x1", demo("dup"), uid="dup"), self.unit("x2", demo("dup"), uid="dup")]
        first = self.catalog(*roots)
        for order in (list(reversed(roots)), roots[2:] + roots[:2]):
            self.assertEqual(first, self.catalog(*order))
        self.assertEqual(["alpha", "beta", "gamma"], [entry["owner"] for entry in first["contributions"]])

    def test_digest_ignores_paths_and_follows_content(self):
        one = self.catalog(self.unit("demo", demo()))
        other = self.catalog(self.unit("demo", demo(), root=self.tmp / "elsewhere"))
        self.assertEqual(one["digest"], other["digest"])
        changed = demo()
        changed["version"] = "0.2.0"
        self.assertNotEqual(one["digest"], self.catalog(self.unit("demo", changed, root=self.tmp / "third"))["digest"])


class TestPathRules(CatalogCase):
    def test_gui_json_outside_the_root(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "gui.json").write_text(json.dumps(demo()), encoding="utf-8")
        self.assertRejected("CONTRIB_PATH_ESCAPE", None, provides_gui="../outside/gui.json")
        self.assertRejected("CONTRIB_PATH_ESCAPE", None, folder="abs", provides_gui=str(outside / "gui.json"))

    def test_gui_json_symlink_leaving_the_root(self):
        outside = self.tmp / "outside.json"
        outside.write_text(json.dumps(demo()), encoding="utf-8")
        path = self.unit("demo", None)
        (path / "gui.json").symlink_to(outside)
        doc = self.catalog(path)
        self.assertEqual("CONTRIB_PATH_ESCAPE", doc["rejected"][0]["code"])

    def test_symlink_loop_fails_closed(self):
        path = self.unit("demo", None)
        (path / "gui.json").symlink_to(path / "gui.json")
        self.assertEqual("CONTRIB_PATH_ESCAPE", self.catalog(path)["rejected"][0]["code"])

    def test_symlink_inside_the_root_is_fine(self):
        path = self.unit("demo", None)
        (path / "real.json").write_text(json.dumps(demo()), encoding="utf-8")
        (path / "gui.json").symlink_to(path / "real.json")
        self.assertEqual(["demo"], [entry["owner"] for entry in self.catalog(path)["contributions"]])

    def test_argv0_and_docs_must_stay_inside(self):
        gui = demo()
        gui["commands"][0]["exec"]["argv"][0] = "../../bin/sh"
        self.assertRejected("CONTRIB_PATH_ESCAPE", gui)
        gui = demo()
        gui["commands"][0]["exec"]["argv"][0] = {"input": "name"}
        self.assertRejected("CONTRIB_PATH_ESCAPE", gui)
        gui = demo()
        gui["docs"][0]["index"] = "../../etc/passwd"
        self.assertRejected("CONTRIB_PATH_ESCAPE", gui)
        gui = demo()
        gui["docs"][0]["root"] = ".."
        self.assertRejected("CONTRIB_PATH_ESCAPE", gui)


class TestRules(CatalogCase):
    def test_unreadable_and_too_large(self):
        self.assertRejected("CONTRIB_UNREADABLE", "{not json")
        self.assertRejected("CONTRIB_UNREADABLE", None, folder="missing")
        big = demo()
        big["routes"][0]["title"] = "x" * (resolve.MAX_FILE_BYTES + 1)
        entry = self.assertRejected("CONTRIB_UNREADABLE", big, folder="big")
        self.assertIn("limit", entry["message"])

    def test_schema(self):
        gui = demo()
        gui["theme"] = "dark"
        entry = self.assertRejected("CONTRIB_INVALID", gui)
        self.assertEqual([{"pointer": "/theme", "code": "additional", "message": "/theme: unexpected property 'theme'"}],
                         entry["issues"])

    def test_limits(self):
        gui = demo()
        gui["routes"][0]["title"] = "x" * (resolve.MAX_TITLE + 1)
        entry = self.assertRejected("CONTRIB_INVALID", gui)
        self.assertEqual(["max_length"], [issue["code"] for issue in entry["issues"]])
        gui = demo()
        gui["commands"][0]["input"][0]["pattern"] = "^(["
        self.assertEqual("pattern", self.assertRejected("CONTRIB_INVALID", gui, folder="p")["issues"][0]["code"])
        gui = demo()
        gui["commands"][0]["exec"]["argv"] += ["x"] * resolve.MAX_ARGV
        self.assertEqual("max_items", self.assertRejected("CONTRIB_INVALID", gui, folder="a")["issues"][0]["code"])

    def test_owner_mismatch(self):
        self.assertRejected("CONTRIB_OWNER_MISMATCH", demo("other"), uid="demo")

    def test_id_prefix(self):
        gui = demo()
        gui["commands"][0]["id"] = "other.greet"
        self.assertRejected("CONTRIB_ID_PREFIX", gui)

    def test_protocol_and_contracts(self):
        gui = demo()
        gui["gui_protocol"] = {"min": "2", "max": "3"}
        self.assertRejected("CONTRIB_INCOMPATIBLE", gui)
        gui["gui_protocol"] = {"min": "3", "max": "2"}
        self.assertRejected("CONTRIB_INCOMPATIBLE", gui)
        gui = demo()
        gui["requires_contracts"] = [{"id": "urn:swissknifeman:gui:view-data", "version": "v9"}]
        self.assertRejected("CONTRIB_INCOMPATIBLE", gui)

    def test_host_supports_its_own_and_the_foundation_contracts(self):
        supported = resolve.host_contracts()
        self.assertIn(("urn:swissknifeman:gui:contribution", "v1"), supported)
        self.assertIn(("urn:swissknifeman:aicore:event", "v1"), supported)

    def test_refs(self):
        cases = []
        gui = demo()
        gui["routes"][1]["command"] = "demo.nope"
        cases.append(gui)
        gui = demo()
        del gui["routes"][1]["command"]
        cases.append(gui)
        gui = demo()
        gui["routes"][0]["actions"] = ["demo.nope"]
        cases.append(gui)
        gui = demo()
        gui["docs"][0]["index"] = "absent.md"
        cases.append(gui)
        gui = demo()
        gui["commands"][0]["input"][0]["enum"] = ["a"]
        cases.append(gui)
        gui = demo()
        gui["commands"][0]["dry_run"] = {"input": "name"}
        cases.append(gui)
        gui = demo()
        gui["commands"][0]["concurrency_key"] = "x:{user}"
        cases.append(gui)
        gui = demo()
        gui["config_sections"] = [{"id": "demo.cfg", "module": "demo", "title": "Demo", "form": "demo.nope"}]
        cases.append(gui)
        gui = demo()
        gui["routes"][0]["path"] = "guide/:topic"
        cases.append(gui)
        for index, case in enumerate(cases):
            with self.subTest(case=index):
                self.assertRejected("CONTRIB_REF_UNKNOWN", case, folder=f"c{index}")

    def test_route_and_widget_views_follow_their_query(self):
        gui = demo()
        gui["queries"] = [{"id": "demo.list", "title": "List", "scope": "fleet", "returns": "resource-list"}]
        gui["handler"] = {"extension": "extension.json"}
        path = self.unit("demo", gui)
        self.write_extension(path)
        gui["routes"].append({"id": "demo.list", "title": "List", "path": "list", "view": "board", "scope": "fleet",
                              "query": "demo.list"})
        self.assertRejected("CONTRIB_REF_UNKNOWN", gui, folder="demo")
        gui["routes"][-1]["view"] = "resource-list"
        gui["widgets"] = [{"id": "demo.w", "title": "W", "view": "metric-group", "query": "demo.list",
                           "scope": "fleet"}]
        self.assertRejected("CONTRIB_REF_UNKNOWN", gui, folder="demo")
        gui["widgets"][0]["view"] = "resource-list"
        self.assertEqual(["demo"], [e["owner"] for e in self.catalog(self.unit("demo", gui))["contributions"]])

    def test_argv_inputs(self):
        gui = demo()
        gui["commands"][0]["exec"]["argv"].append({"input": "nope"})
        self.assertRejected("CONTRIB_INPUT_UNKNOWN", gui)
        gui = demo()
        gui["commands"][0]["exec"]["argv"].append({"input": "loud"})
        self.assertRejected("CONTRIB_INPUT_UNKNOWN", gui)

    def test_argv0_must_be_an_executable(self):
        gui = demo()
        gui["commands"][0]["exec"]["argv"][0] = "docs/index.md"
        self.assertRejected("CONTRIB_REF_UNKNOWN", gui)
        gui["commands"][0]["exec"]["argv"][0] = "bin/absent"
        self.assertRejected("CONTRIB_REF_UNKNOWN", gui)

    def test_capabilities(self):
        gui = demo()
        gui["commands"][0]["effects"] = ["terminal"]
        self.assertRejected("CONTRIB_CAPABILITY_RESERVED", gui)
        gui = demo()
        del gui["commands"][0]["dry_run"]
        self.assertRejected("CONTRIB_CAPABILITY_RESERVED", gui)
        gui = demo()
        gui["commands"][0]["supports"] = ["cancel"]
        self.assertRejected("CONTRIB_CAPABILITY_RESERVED", gui)

    def write_extension(self, path, kind="command", points=("gui:query", "gui:command")):
        (path / "bin" / "handler").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (path / "bin" / "handler").chmod(0o755)
        provides = {"points": list(points)} if kind == "command" else {"events": ["demo.thing.done"]}
        (path / "extension.json").write_text(json.dumps({
            "$schema": "urn:swissknifeman:aicore:extension:v1", "id": "demo", "kind": kind, "version": "0.1.0",
            "description": "Demo handler.", "protocol": {"min": "1", "max": "1"}, "entrypoint": ["bin/handler"],
            "provides": provides}), encoding="utf-8")

    def handler_gui(self):
        gui = demo()
        gui["queries"] = [{"id": "demo.status", "title": "Status", "scope": "fleet", "returns": "metric-group"}]
        gui["widgets"] = [{"id": "demo.status", "title": "Status", "view": "metric-group", "query": "demo.status",
                           "scope": "fleet"}]
        return gui

    def test_handler(self):
        gui = self.handler_gui()
        self.assertRejected("CONTRIB_HANDLER_MISSING", gui)
        gui["handler"] = {"extension": "extension.json"}
        self.assertRejected("CONTRIB_HANDLER_MISSING", gui)  # the file does not exist
        path = self.unit("demo", gui)
        self.write_extension(path, points=("gui:command",))
        self.assertEqual("CONTRIB_HANDLER_MISSING", self.catalog(path)["rejected"][0]["code"])
        self.write_extension(path, kind="subscriber")
        self.assertEqual("CONTRIB_HANDLER_MISSING", self.catalog(path)["rejected"][0]["code"])
        self.write_extension(path)
        self.assertEqual(["demo"], [entry["owner"] for entry in self.catalog(path)["contributions"]])
        gui["handler"] = {"extension": "../extension.json"}
        self.assertRejected("CONTRIB_PATH_ESCAPE", gui, folder="demo")

    def test_invoke_command_needs_the_command_point(self):
        gui = demo()
        gui["commands"].append({"id": "demo.ping", "title": "Ping", "scope": "fleet", "effects": ["read"],
                                "risk": "low", "confirmation": "none", "timeout_s": 5, "exec": {"kind": "invoke"}})
        gui["handler"] = {"extension": "extension.json"}
        path = self.unit("demo", gui)
        self.write_extension(path, points=("gui:query",))
        self.assertEqual("CONTRIB_HANDLER_MISSING", self.catalog(path)["rejected"][0]["code"])

    def test_first_failing_rule_names_the_code(self):
        gui = demo("other")
        gui["commands"][0]["effects"] = ["terminal"]
        self.assertRejected("CONTRIB_OWNER_MISMATCH", gui, uid="demo")


class TestSources(CatalogCase):
    def umbrella(self, body, code=0):
        script = self.tmp / f"swissknifeman-{len(list(self.tmp.glob('swissknifeman-*')))}"
        script.write_text(f"#!/bin/sh\ncat <<'EOF'\n{body}\nEOF\nexit {code}\n", encoding="utf-8")
        script.chmod(0o755)
        return {"PATH": os.environ.get("PATH", ""), "SKM_UMBRELLA": str(script), "HOME": str(self.tmp)}

    def test_units_path_wins(self):
        roots, problem = sources.unit_roots({"SKM_UNITS_PATH": str(FIXTURES / "two-owners")})
        self.assertIsNone(problem)
        self.assertEqual(["alpha", "beta"], [root.name for root in roots])

    def test_registry_roots_resolve_against_hub_root(self):
        hub = self.tmp / "hub"
        self.unit("demo", demo(), root=hub / "bridges")
        env = self.umbrella(json.dumps({"schema": "umbrella-units/v1", "hub_root": str(hub),
                                        "units": [{"id": "demo", "root": "bridges/demo"},
                                                  {"id": "abs", "root": str(self.tmp / "abs")}]}))
        roots, problem = sources.unit_roots(env)
        self.assertIsNone(problem)
        self.assertEqual([hub / "bridges" / "demo", self.tmp / "abs"], roots)

    def test_registry_problems_are_codes(self):
        cases = {
            "relative roots without hub_root": self.umbrella(json.dumps({"schema": "umbrella-units/v1",
                                                                         "units": [{"id": "a", "root": "a"}]})),
            "exited with 3": self.umbrella("{}", code=3),
            "did not print": self.umbrella("not json"),
            "not found": {"PATH": str(self.tmp / "empty")},
        }
        for needle, env in cases.items():
            with self.subTest(case=needle):
                roots, problem = sources.unit_roots(env)
                self.assertEqual([], roots)
                self.assertEqual("CATALOG_SOURCE_UNAVAILABLE", problem["code"])
                self.assertIn(needle, problem["message"])

    def test_source_problem_is_a_rejected_entry_and_others_still_count(self):
        problem = {"owner": None, "file": "swissknifeman units list", "code": "CATALOG_SOURCE_UNAVAILABLE",
                   "message": "swissknifeman not found"}
        doc = self.catalog(FIXTURES / "valid-one" / "demo", problems=[problem])
        self.assertEqual(["demo"], [entry["owner"] for entry in doc["contributions"]])
        self.assertEqual([problem], doc["rejected"])

    def test_units_without_gui_or_with_a_broken_manifest_are_not_sources(self):
        (self.tmp / "broken").mkdir()
        (self.tmp / "broken" / "unit.json").write_text("{", encoding="utf-8")
        plain = self.tmp / "plain"
        plain.mkdir()
        (plain / "unit.json").write_text(json.dumps({"id": "plain", "provides": {}}), encoding="utf-8")
        self.assertEqual([], sources.unit_sources([self.tmp / "broken", plain, self.tmp / "absent"]))

    def test_extensions_declaring_gui(self):
        path = self.unit("ext", demo("ext"), files=True)
        (path / "extension.json").write_text(json.dumps({"id": "ext", "provides": {"gui": "gui.json"}}),
                                             encoding="utf-8")
        manifest = mock.Mock(path=path / "extension.json")
        usable = mock.Mock(usable=True, manifest=manifest)
        unusable = mock.Mock(usable=False, manifest=manifest)
        with mock.patch.object(sources.ext_settings, "load"), \
                mock.patch.object(sources, "registered_plugins", return_value=([usable, unusable], [])):
            found, problem = sources.extension_sources(None, {})
        self.assertIsNone(problem)
        self.assertEqual([Source("extension", "ext", path, path / "extension.json", "gui.json")], found)
        doc = resolve.resolve(Collected(found, []))
        self.assertEqual([("ext", "extension")], [(e["owner"], e["source"]) for e in doc["contributions"]])

    def test_broken_plugin_configuration_is_a_code(self):
        from aicore.ext.errors import ExtError

        with mock.patch.object(sources.ext_settings, "load", side_effect=ExtError("CONFIG_INVALID", "bad")):
            found, problem = sources.extension_sources(None, {})
        self.assertEqual(([], "CATALOG_SOURCE_UNAVAILABLE"), (found, problem["code"]))

    def test_collect_joins_units_and_extensions(self):
        with mock.patch.object(sources, "extension_sources", return_value=([], None)):
            collected = sources.collect(None, {"SKM_UNITS_PATH": str(FIXTURES / "two-owners")})
        self.assertEqual(["alpha", "beta"], sorted(source.owner for source in collected.sources))
        self.assertEqual([], collected.problems)


class TestCheck(CatalogCase):
    def assertCheckResults(self, results):
        registry, kind = CHECK_RESULT
        for result in results:
            self.assertEqual([], schema.validate(result, kind, registry), result)

    def test_valid_unit_folder(self):
        results = resolve.check(FIXTURES / "valid-one" / "demo")
        self.assertCheckResults(results)
        self.assertEqual([f"gui.contribution.{rule}" for rule in resolve.RULES], [r["check_id"] for r in results])
        self.assertEqual({"ok"}, {result["status"] for result in results})

    def test_failing_rule_and_skips(self):
        gui = demo()
        gui["theme"] = "x"
        results = resolve.check(self.unit("demo", gui))
        self.assertCheckResults(results)
        statuses = {result["check_id"].rpartition(".")[2]: result["status"] for result in results}
        self.assertEqual(("ok", "ok", "fail"), (statuses["path"], statuses["read"], statuses["schema"]))
        self.assertEqual({"skip"}, {statuses[rule] for rule in resolve.RULES[3:]})
        failed = next(result for result in results if result["status"] == "fail")
        self.assertTrue(failed["observed"].startswith("CONTRIB_INVALID"))
        self.assertIn("remediation", failed)

    def test_gui_json_file_with_and_without_a_manifest(self):
        results = resolve.check(FIXTURES / "valid-one" / "demo" / "gui.json")
        self.assertEqual("ok", next(r for r in results if r["check_id"] == "gui.contribution.owner")["status"])
        bare = self.tmp / "bare"
        bare.mkdir()
        shutil.copytree(FIXTURES / "valid-one" / "demo" / "bin", bare / "bin")
        shutil.copytree(FIXTURES / "valid-one" / "demo" / "docs", bare / "docs")
        (bare / "gui.json").write_text(json.dumps(demo()), encoding="utf-8")
        results = resolve.check(bare / "gui.json")
        self.assertCheckResults(results)
        self.assertEqual("skip", next(r for r in results if r["check_id"] == "gui.contribution.owner")["status"])
        self.assertNotIn("fail", {result["status"] for result in results})

    def test_folder_without_a_declaring_manifest(self):
        results = resolve.check(self.tmp)
        self.assertCheckResults(results)
        self.assertEqual(["fail"], [result["status"] for result in results])

    def test_handler_conformance_is_appended(self):
        gui = TestRules.handler_gui(self)
        gui["handler"] = {"extension": "extension.json"}
        path = self.unit("demo", gui)
        TestRules.write_extension(self, path)
        extra = {"$schema": "urn:swissknifeman:aicore:check-result:v1", "check_id": "ext.conformance.describe",
                 "status": "ok", "category": "integration", "observed": "fine"}
        with mock.patch.object(resolve, "run_conformance", return_value=[extra]) as conformance:
            results = resolve.check(path)
        conformance.assert_called_once_with((path / "extension.json").resolve(), env=None)
        self.assertEqual(extra, results[-1])
        with mock.patch.object(resolve, "run_conformance") as conformance:
            resolve.check(path, conformance=False)
        conformance.assert_not_called()


class TestCatalogContract(unittest.TestCase):
    def test_rejection_codes_are_the_registered_ones(self):
        from gui import errors

        registry, kind = contracts.load("catalog")
        enum = registry.for_kind(kind)[0]["properties"]["rejected"]["items"]["properties"]["code"]["enum"]
        self.assertEqual({code for code in errors.CODES if code.startswith(("CONTRIB_", "CATALOG_"))}, set(enum))
        self.assertLessEqual({value for name, value in vars(resolve).items()
                              if isinstance(value, str) and value.startswith("CONTRIB_")}, set(enum))


if __name__ == "__main__":
    unittest.main()
