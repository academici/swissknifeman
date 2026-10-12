"""Hook modes of a project: read through harness, the committed carrier and the legacy files; written through harness."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from maind import health
from maind.provision import onboard as onb
from tests.fixtures import make_repo
from tests.harness_partner import FakeHarnessCase, NoHarnessCase, RealHarnessCase


class Project:
    """A registered project with a local path."""

    def __init__(self, test):
        temporary = tempfile.TemporaryDirectory()
        test.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.record = {"id": "demo", "local_path": str(self.root)}

    def carrier(self, *lines):
        path = self.root / ".swissknifeman" / "hooks.env"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Generated\n" + "".join(line + "\n" for line in lines), encoding="utf-8")

    def legacy(self, name, text):
        path = self.root / ".claude" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


class WithoutHarnessCase(NoHarnessCase):
    def test_reads_fall_back_to_the_carrier_then_the_legacy_files(self):
        project = Project(self)
        self.assertIsNone(health.hook_memory_mode(project.record))
        project.legacy("memory.env.ini", "# note\nMODE=maind  # why\n")
        self.assertEqual(health.hook_memory_mode(project.record), "maind")
        project.carrier("MEMORY_MODE=off", "MEMORY_MODE__CURSOR=maind")
        self.assertEqual(health.hook_memory_mode(project.record), "off")
        project.carrier("MEMORY_MODE=off", "MEMORY_MODE__CLAUDE_CODE=manual")
        self.assertEqual(health.hook_memory_mode(project.record), "manual")

    def test_a_project_without_a_path_has_no_modes(self):
        self.assertIsNone(health.hook_memory_mode({"id": "x"}))
        self.assertIsNone(health.hook_router_policy({"id": "x"}))

    def test_router_policy_from_the_carrier_or_the_legacy_file(self):
        project = Project(self)
        self.assertIsNone(health.hook_router_policy(project.record))
        project.legacy("agent-router.env.ini", "THRESHOLD=3\n")
        self.assertEqual(health.hook_router_policy(project.record), "")  # file without POLICY: enabled
        project.legacy("agent-router.env.ini", "POLICY=off\n")
        self.assertEqual(health.hook_router_policy(project.record), "off")
        project.carrier("AGENT_ROUTER_POLICY=propose")
        self.assertEqual(health.hook_router_policy(project.record), "propose")

    def test_the_write_is_skipped_with_partner_unavailable(self):
        project = Project(self)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            status, detail = health.set_hook_memory_mode(project.record, "maind")
        self.assertEqual(status, "skip")
        self.assertIn("PARTNER_UNAVAILABLE: harness not found", detail)
        self.assertIn("PARTNER_UNAVAILABLE", err.getvalue())
        self.assertFalse((project.root / ".claude").exists())
        self.assertFalse((project.root / ".swissknifeman").exists())

    def test_onboarding_memory_reports_the_skip_and_writes_no_ini(self):
        project = Project(self)
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                report = onb._wire_memory(env, {"projects": []}, dict(project.record, namespaces=["a"]),
                                          mechanism="manual", dry=False)
        self.assertFalse(report["memory_env_written"])
        self.assertIn("PARTNER_UNAVAILABLE", report["memory_env_skipped"])
        self.assertEqual(sorted(project.root.rglob("*.env.ini")), [])


class ThroughHarnessCase(FakeHarnessCase):
    def test_memory_mode_is_asked_from_harness_first(self):
        project = Project(self)
        project.carrier("MEMORY_MODE=maind")
        project.legacy("memory.env.ini", "MODE=off\n")
        self.assertEqual(health.hook_memory_mode(project.record), "maind")
        shown = [call for call in self.fake_calls() if call[:2] == ["hooks", "show"]]
        self.assertEqual(shown, [["hooks", "show", "--target", str(project.root), "--json"]])

    def test_legacy_file_still_counts_when_harness_knows_nothing(self):
        project = Project(self)
        project.legacy("memory.env.ini", "MODE=maind\n")
        self.assertEqual(health.hook_memory_mode(project.record), "maind")

    def test_set_memory_mode_runs_the_harness_flag(self):
        project = Project(self)
        self.assertEqual(health.set_hook_memory_mode(project.record, "manual"), ("ok", "manual"))
        self.assertIn(["hooks", "--target", str(project.root), "--memory", "manual"], self.fake_calls())
        self.assertEqual(health.hook_memory_mode(project.record), "manual")

    def test_onboarding_memory_asks_harness_once_and_is_idempotent(self):
        project = Project(self)
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            proj = dict(project.record, namespaces=["a"])
            first = onb._wire_memory(env, {"projects": []}, proj, mechanism="manual", dry=False)
            second = onb._wire_memory(env, {"projects": []}, proj, mechanism="manual", dry=False)
        self.assertTrue(first["memory_env_written"])
        self.assertFalse(second["memory_env_written"])
        self.assertIsNone(first["memory_env_skipped"])
        flags = [call for call in self.fake_calls() if "--memory" in call]
        self.assertEqual(len(flags), 1)
        self.assertEqual(sorted(project.root.rglob("*.env.ini")), [])

    def test_dry_onboarding_writes_nothing(self):
        project = Project(self)
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            onb._wire_memory(env, {"projects": []}, dict(project.record, namespaces=["a"]),
                             mechanism="off", dry=True)
        self.assertFalse((project.root / ".swissknifeman").exists())
        self.assertEqual([call for call in self.fake_calls() if "--memory" in call], [])


class RealHarnessModesCase(RealHarnessCase):
    """The real harness: onboarding writes the project configuration and carrier; maind reads them back."""

    def test_round_trip_through_the_project_configuration(self):
        project = Project(self)
        self.assertEqual(health.set_hook_memory_mode(project.record, "maind"), ("ok", "maind"))
        config = (project.root / ".swissknifeman" / "config.toml").read_text(encoding="utf-8")
        self.assertIn("[harness.hooks.memory]", config)
        self.assertIn('mode = "maind"', config)
        carrier = (project.root / ".swissknifeman" / "hooks.env").read_text(encoding="utf-8")
        self.assertIn("MEMORY_MODE=maind", carrier.splitlines())
        self.assertEqual(health.hook_memory_mode(project.record), "maind")
        self.assertEqual(sorted(project.root.rglob("*.env.ini")), [])
        self.assertFalse((project.root / ".swissknife.json").exists())
        state = health.hooks_state(project.root)
        self.assertEqual(state["settings"]["hooks"]["memory"]["mode"], "maind")
        self.assertFalse(state["stale"])

    def test_a_legacy_only_project_is_still_read(self):
        project = Project(self)
        project.legacy("memory.env.ini", "MODE=manual\n")
        self.assertEqual(health.hook_memory_mode(project.record), "manual")
        self.assertEqual(health.hooks_state(project.root)["legacy"], [str(project.root / ".claude" / "memory.env.ini")])


if __name__ == "__main__":
    unittest.main()
