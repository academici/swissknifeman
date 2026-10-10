"""``resolve_role.py``: closure of each role's skills and the delivery mode, offline against the partner's registry."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BRIDGE = Path(__file__).resolve().parents[1]
if str(BRIDGE) not in sys.path:
    sys.path.insert(0, str(BRIDGE))

import partners  # noqa: E402

SCRIPT = BRIDGE / "resolve_role.py"
ROLES = ("context-scout", "executor", "bounded-implementer", "reviewer", "registrar")
PROVIDERS = ("claude-code", "codex", "grok")
SKILLER = partners.find_skiller()
ORCH = partners.find_orch_root()


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          encoding="utf-8", check=False)


@unittest.skipUnless(SKILLER and ORCH, "skiller or orch partner not found")
class ResolveRole(unittest.TestCase):
    def resolve(self, role: str, provider: str) -> dict:
        done = run("--role", role, "--provider", provider, "--json")
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        return json.loads(done.stdout)

    def test_every_role_resolves_on_every_provider(self):
        for role in ROLES:
            for provider in PROVIDERS:
                with self.subTest(role=role, provider=provider):
                    out = self.resolve(role, provider)
                    self.assertEqual((out["role"], out["provider"]), (role, provider))
                    self.assertLessEqual(len(out["skills"]), 5)
                    self.assertEqual([d for d in out["diagnostics"] if d["severity"] == "error"], [])

    def test_roles_without_skills_have_empty_closure(self):
        for role in ("context-scout", "executor", "bounded-implementer", "registrar"):
            with self.subTest(role=role):
                self.assertEqual(self.resolve(role, "claude-code")["skills"], [])

    def test_reviewer_has_code_review_and_no_plan_protocol(self):
        out = self.resolve("reviewer", "codex")
        by_name = {s["name"]: s for s in out["skills"]}
        self.assertTrue(by_name["code-review"]["required"])
        self.assertFalse(by_name["artifact-review"]["required"])
        self.assertFalse([s for s in out["skills"] if "plan-protocol" in s["id"]])

    def test_delivery_mode_comes_from_the_capability_seed(self):
        modes = {p: self.resolve("executor", p)["delivery"] for p in PROVIDERS}
        self.assertEqual(modes["claude-code"]["mode"], "native_plugin_dir")
        self.assertEqual(modes["codex"]["mode"], "isolated_home")
        self.assertTrue(modes["claude-code"]["source"].endswith("native--claude-code.json"))
        cao = json.loads(run("--role", "executor", "--provider", "codex", "--binding", "cao", "--json").stdout)
        self.assertTrue(cao["delivery"]["source"].endswith("cao--codex.json"))

    def test_missing_seed_is_unknown_with_a_diagnostic(self):
        done = run("--role", "executor", "--provider", "grok", "--binding", "claude-only", "--json")
        out = json.loads(done.stdout)
        self.assertEqual(out["delivery"]["mode"], "unknown")
        self.assertEqual([d["code"] for d in out["diagnostics"]], ["DELIVERY_UNKNOWN"])

    def test_required_follows_requires_of_a_required_skill(self):
        found = [{"id": "a/x", "required_by": []}, {"id": "a/y", "required_by": ["a/x"]},
                 {"id": "a/z", "required_by": []}]
        import resolve_role
        self.assertEqual(resolve_role.required_closure({"a/x": True, "a/z": False}, found), {"a/x", "a/y"})

    def test_unknown_skill_exits_1_with_error_diagnostic(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "role.json"
            manifest.write_text(json.dumps({
                "contract_version": "exec/v1", "role_id": "ghost",
                "skills": [{"name": "quality:no-such-skill", "required": True, "why": "test"}]}), encoding="utf-8")
            done = run("--manifest", str(manifest), "--provider", "claude-code", "--json")
        self.assertEqual(done.returncode, 1)
        self.assertIn("SKILL_UNKNOWN", [d["code"] for d in json.loads(done.stdout)["diagnostics"]])

    def test_foreign_contract_version_and_unknown_role_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "role.json"
            manifest.write_text(json.dumps({"contract_version": "exec/v9", "role_id": "x"}), encoding="utf-8")
            done = run("--manifest", str(manifest), "--provider", "codex")
        self.assertEqual(done.returncode, 1)
        self.assertIn("CONTRACT_VERSION", done.stderr)
        done = run("--role", "no-such-role", "--provider", "codex")
        self.assertEqual((done.returncode, done.stderr.split(":")[0]), (1, "ROLE_UNKNOWN"))

    def test_text_output_lists_skills(self):
        done = run("--role", "reviewer", "--provider", "claude-code")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("quality/code-review  required", done.stdout)


class PartnerLookup(unittest.TestCase):
    def test_missing_partner_is_a_clear_error(self):
        import os
        env = {**os.environ, "SKM_SKILLER_ROOT": "/nonexistent"}
        done = subprocess.run([sys.executable, str(SCRIPT), "--role", "reviewer", "--provider", "codex"],
                              capture_output=True, text=True, env=env, check=False)
        self.assertEqual(done.returncode, 3)
        self.assertIn("BRIDGE_PARTNER_UNAVAILABLE", done.stderr)


if __name__ == "__main__":
    unittest.main()
