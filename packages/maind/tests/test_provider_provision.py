"""P6.2 public temporary-root conformance for provider instruction provisioning."""
import tempfile
import unittest

from maind.doctor import provider_trust_report
from maind.health import health_report
from maind.provision import sync
from tests.fixtures import capture
from tests.test_sync import _setup


def _providers(config, selection):
    config["projects"][0]["providers"] = {
        "contract_version": "1.0.0", "selection": selection,
    }


class TestProviderProvisionConformance(unittest.TestCase):
    def test_sync_health_and_doctor_cover_legacy_codex_and_dual_targets(self):
        cases = (
            ("legacy-claude", None, ("CLAUDE.md",)),
            ("codex", {"claude-code": {"enabled": False}, "codex": {"enabled": True}},
             ("AGENTS.md",)),
            ("dual", {"claude-code": {"enabled": True}, "codex": {"enabled": True}},
             ("CLAUDE.md", "AGENTS.md")),
        )
        for _name, selection, names in cases:
            with self.subTest(case=_name), tempfile.TemporaryDirectory() as tmp:
                env, config, root = _setup(tmp)
                if selection is not None:
                    _providers(config, selection)
                first = sync.run_sync(env, config, config["projects"], only="instructions", mode="auto")[0]
                self.assertEqual(first["status"], "ok")
                self.assertEqual(len(first["providers"]), len(names))
                for scope in ("", "packages/skiller", "packages/harness", "packages/maind",
                              "packages/analyst", "packages/task"):
                    for name in names:
                        self.assertTrue((root / scope / name).is_file(), (scope, name))
                # P5 owns the blocks, so unrelated user bytes remain clean and untouched.
                target = root / names[0]
                target.write_text("user prefix\n" + target.read_text(encoding="utf-8")
                                  + "\nuser suffix\n", encoding="utf-8")
                second = sync.run_sync(env, config, config["projects"], only="instructions", mode="auto")[0]
                self.assertEqual(second["status"], "ok")
                self.assertFalse(second["changed"])
                self.assertTrue(target.read_text(encoding="utf-8").startswith("user prefix\n"))
                context = sync.contexts(env, config, config["projects"])[0]
                health = health_report(env, config, config["projects"][0], memory_reachable=False,
                                       provider_context=context)
                self.assertEqual(len(health["provider_trust"]), len(names))
                doctor = provider_trust_report(env, config)
                self.assertEqual(len(doctor), len(names))
                self.assertTrue(all(not row["green"] for row in doctor))  # untrusted is non-green

    def test_unknown_provider_fails_before_sync_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, root = _setup(tmp)
            _providers(config, {"unsupported-provider": {"enabled": True}})
            with self.assertRaises(ValueError):
                sync.run_sync(env, config, config["projects"], only="instructions")
            self.assertFalse((root / "CLAUDE.md").exists())

    def test_public_conformance_command_generates_the_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, _config, root = _setup(tmp)
            output = root / "provider-conformance.md"
            _result, text = capture(sync.cmd_sync, env, ["--conformance", str(output)])
            self.assertIn("provider provision conformance", text)
            generated = output.read_text(encoding="utf-8")
            self.assertIn("Dual-provider", generated)
            self.assertIn("harness semantic parity/extensions", generated)
            self.assertIn("managed drift and explicit repair", generated)
