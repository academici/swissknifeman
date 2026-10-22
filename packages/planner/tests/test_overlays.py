"""Overlay slots of the planner commands: ``plan.py overlays``, the slot set and the call line in every projection."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from . import fixtures  # noqa: F401 — package invocation
except ImportError:
    import fixtures  # noqa: F401 — direct discovery
from planner import integration
from planner.plan import cli

PLANNER = Path(__file__).resolve().parents[1]
SLOTS = ["design", "dev", "fix", "make-workflow", "plan-audit", "plan-close", "plan-design", "plan-run",
         "research", "review"]
LINE = ("Owner rules: run `plan.py overlays planner:%s` first and follow any "
        "rules it prints as additions to this command; they never override the plan, its checks or safety rules.")
CLI = ("Project CLI: `plan.py` means `python3 -I .swissknifeman/launcher.py planner`, run from the project root (the "
       "launcher binds the project; without one, run `swissknifeman project init` once). Never locate or run a Swiss "
       "Knife Man package script.")
needs_aicore = unittest.skipUnless(integration.available(), "aicore is not available")


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


def without_aicore():
    return mock.patch.dict(integration._PROBE, {"available": False, "root": None, "reason": "AICORE_NOT_FOUND"},
                           clear=True)


class SlotSetTests(unittest.TestCase):
    def test_declared_slots_equal_the_commands(self):
        unit = json.loads((PLANNER / "unit.json").read_text(encoding="utf-8"))
        commands = sorted(path.stem for path in (PLANNER / "commands").glob("*.md"))
        self.assertEqual(sorted(unit["provides"]["overlay_slots"]), commands)
        self.assertEqual(commands, SLOTS)

    def test_every_command_calls_its_own_slot_first(self):
        for name in SLOTS:
            with self.subTest(name):
                text = (PLANNER / "commands" / f"{name}.md").read_text(encoding="utf-8")
                body = text.split("\n---\n", 1)[1]
                # the project CLI is named first (the owner-rules line uses it), then the slot is called
                self.assertEqual(body.splitlines()[:2], [CLI, LINE % name])

    def test_every_projection_carries_the_line_of_its_slot(self):
        projections = {"claude golden": "tests/fixtures_data/claude-command-golden/commands/{}.md",
                       "codex": "adapters/codex/skills/planner-{}/command.md",
                       "cursor": "adapters/cursor/skills/planner-{}/command.md"}
        for label, pattern in projections.items():
            for name in SLOTS:
                with self.subTest(label=label, name=name):
                    path = PLANNER / pattern.format(name)
                    self.assertTrue(path.is_file(), path)
                    self.assertIn(f"plan.py overlays planner:{name}`", path.read_text(encoding="utf-8"))

    def test_no_projection_embeds_overlay_text(self):
        for path in PLANNER.glob("adapters/**/*.md"):
            self.assertNotIn("<!-- overlays:", path.read_text(encoding="utf-8"), path)


class WithoutAicoreTests(unittest.TestCase):
    def test_an_empty_block_and_exit_zero(self):
        with without_aicore():
            code, out, err = run("overlays", "planner:plan-run")
        self.assertEqual((code, out, err), (0, "", ""))

    def test_json_names_the_missing_foundation(self):
        with without_aicore():
            code, out, _ = run("overlays", "plan-run", "--json", "--strict")
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual((data["slot"], data["overlays"], data["warnings"]),
                         ("planner:plan-run", [], ["AICORE_UNAVAILABLE"]))
        self.assertEqual(data["aicore"]["aicore"], "unavailable")

    def test_an_unknown_slot_is_refused_without_the_foundation_too(self):
        with without_aicore():
            code, _, err = run("overlays", "planner:nope")
        self.assertEqual(code, 1)
        self.assertIn("OVERLAY_SLOT_UNKNOWN", err)


@needs_aicore
class OverlayCase(unittest.TestCase):
    def setUp(self):
        base = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(base, ignore_errors=True))
        self.home = base / "home"
        self.project = base / "project"
        (self.project / ".git").mkdir(parents=True)
        self.home.mkdir()
        env = {key: value for key, value in os.environ.items() if not key.startswith(("SKM_", "AICORE_CONFIG"))}
        env.update(HOME=str(self.home), SKM_HOME=str(self.home), SKM_AICORE_EVENTS__DELIVERY="off")
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.base = base

    def test_an_empty_project_without_a_project_around_is_no_root(self):
        outside = self.base / "outside"
        outside.mkdir()
        from planner.integration import overlays
        from aicore.state import locations
        marker_found = locations._marker_found
        # The synthetic filesystem ends at the fixture; a host checkout above it is not part of this case.
        with mock.patch.object(locations, "_marker_found", side_effect=lambda candidate, marker:
                               candidate not in self.base.parents and marker_found(candidate, marker)):
            self.assertIsNone(overlays.project_root(cwd=outside, project=""))

    def machine(self, text):
        from aicore.state import machine_config_file
        path = Path(machine_config_file())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("schema_version = 1\n" + text, encoding="utf-8")

    def project_config(self, text):
        path = self.project / ".swissknifeman" / "config.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("schema_version = 1\n" + text, encoding="utf-8")

    def file(self, where, text):
        where.parent.mkdir(parents=True, exist_ok=True)
        where.write_text(text, encoding="utf-8")
        return where

    def overlays(self, *argv):
        return run("overlays", *argv, "--project", self.project)


@needs_aicore
class ResolutionTests(OverlayCase):
    def test_a_slot_without_overlays_prints_nothing(self):
        self.assertEqual(self.overlays("planner:plan-run"), (0, "", ""))

    def test_the_short_and_the_full_slot_name_are_the_same(self):
        self.assertEqual(self.overlays("review"), self.overlays("planner:review"))

    def test_machine_overlay_block_is_exact(self):
        rules = self.file(self.home / "rules" / "machine.md", "Always cite the plan item.\n")
        self.machine(f'[aicore.overlays]\n"planner:plan-run" = [{json.dumps(str(rules))}]\n')
        code, out, err = self.overlays("planner:plan-run")
        shown = "~" + str(rules)[len(str(self.home)):]
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, "<!-- overlays: planner:plan-run -->\n"
                              f"<!-- overlay: {shown} (machine) -->\n"
                              "Always cite the plan item.\n"
                              "<!-- end overlays: planner:plan-run -->\n")

    def test_machine_comes_before_project_and_other_slots_are_untouched(self):
        machine = self.file(self.home / "m.md", "machine rule\n")
        self.file(self.project / ".swissknifeman" / "p.md", "project rule\n")
        self.machine(f'[aicore.overlays]\n"planner:plan-run" = [{json.dumps(str(machine))}]\n')
        self.project_config('[aicore]\n_append = {"overlays.planner:plan-run" = ["p.md"]}\n')
        code, out, _ = self.overlays("planner:plan-run")
        self.assertEqual(code, 0)
        self.assertLess(out.index("machine rule"), out.index("project rule"))
        self.assertIn("(project)", out)
        self.assertEqual(self.overlays("planner:fix"), (0, "", ""))

    def test_json_describes_the_files_and_the_foundation(self):
        rules = self.file(self.home / "a.md", "one\n")
        self.machine(f'[aicore.overlays]\n"planner:fix" = [{json.dumps(str(rules))}]\n')
        code, out, _ = self.overlays("fix", "--json")
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual((data["slot"], len(data["overlays"]), data["warnings"]), ("planner:fix", 1, []))
        self.assertEqual((data["overlays"][0]["layer"], data["overlays"][0]["bytes"]), ("machine", 4))
        self.assertEqual(data["aicore"]["aicore"], "available")

    def test_a_missing_file_warns_on_stderr_and_strict_makes_it_exit_one(self):
        self.machine(f'[aicore.overlays]\n"planner:dev" = [{json.dumps(str(self.home / "gone.md"))}]\n')
        code, out, err = self.overlays("planner:dev")
        self.assertEqual((code, out), (0, ""))
        self.assertIn("OVERLAY_MISSING", err)
        self.assertEqual(self.overlays("planner:dev", "--strict")[0], 1)

    def test_an_unknown_slot_is_refused(self):
        code, out, err = self.overlays("planner:nope")
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("OVERLAY_SLOT_UNKNOWN:"), err)

    def test_the_size_limit_is_refused(self):
        big = self.file(self.home / "big.md", "x" * 40000)
        self.machine(f'[aicore.overlays]\n"planner:dev" = [{json.dumps(str(big))}]\n')
        code, _, err = self.overlays("planner:dev")
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("OVERLAY_TOO_LARGE:"), err)

    def test_the_project_defaults_to_the_repository_of_the_working_directory(self):
        self.file(self.project / ".swissknifeman" / "p.md", "from project\n")
        self.project_config('[aicore.overlays]\n"planner:review" = ["p.md"]\n')
        nested = self.project / "src" / "deep"
        nested.mkdir(parents=True)
        previous = os.getcwd()
        os.chdir(nested)
        self.addCleanup(os.chdir, previous)
        code, out, err = run("overlays", "planner:review")
        self.assertEqual(code, 0)
        self.assertIn("from project", out, err)

    def test_the_catalog_lists_the_verb(self):
        code, out, _ = run("schema", "--verbs")
        row = next(verb for verb in json.loads(out)["data"]["verbs"] if verb["name"] == "overlays")
        self.assertEqual(code, 0)
        self.assertEqual(row["mode"], "read")
        self.assertIn("OVERLAY_SLOT_UNKNOWN", row["errors"])


if __name__ == "__main__":
    unittest.main()
