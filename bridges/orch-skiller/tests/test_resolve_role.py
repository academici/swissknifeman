"""``resolve_role.py``: closure of each role's skills and the delivery mode, offline against the partner's registry."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

BRIDGE = Path(__file__).resolve().parents[1]
if str(BRIDGE) not in sys.path:
    sys.path.insert(0, str(BRIDGE))

import partners  # noqa: E402

SCRIPT = BRIDGE / "resolve_role.py"
_ORCH = partners.find_orch_root()
# every role manifest of the partner: a new role needs no edit here (it used to be a hand-kept list that each new role broke)
ROLES = tuple(sorted(path.stem for path in (_ORCH / "roles").glob("*.json"))) if _ORCH else ()
PROVIDERS = ("claude-code", "codex", "grok")
SKILLER = partners.find_skiller()
ORCH = partners.find_orch_root()


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          encoding="utf-8", check=False)


def can_select() -> bool:
    if not SKILLER:
        return False
    probe = subprocess.run([str(SKILLER), "select", "--help"], capture_output=True, text=True, check=False)
    return probe.returncode == 0


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

    def test_every_skill_carries_the_digest_skiller_describes(self):
        out = self.resolve("reviewer", "codex")
        self.assertTrue(out["skills"])
        for skill in out["skills"]:
            with self.subTest(skill=skill["id"]):
                described = subprocess.run([str(SKILLER), "describe", skill["id"], "--json"], capture_output=True,
                                           text=True, encoding="utf-8", check=False)
                self.assertEqual(skill["digest"], json.loads(described.stdout)["digest"])
                self.assertRegex(skill["digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual([d for d in out["diagnostics"] if d["code"] == "SKILL_DIGEST_UNKNOWN"], [])

    def test_all_roles_prints_name_and_digest_per_role(self):
        done = run("--all-roles", "--provider", "codex", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        found = json.loads(done.stdout)
        self.assertEqual(sorted(found), sorted(ROLES))
        for role in ROLES:
            if role != "reviewer":
                self.assertEqual(found[role], [])
        reviewer = self.resolve("reviewer", "codex")["skills"]
        self.assertEqual(found["reviewer"], [{"name": s["name"], "digest": s["digest"]} for s in reviewer])
        self.assertEqual(done.stderr, "")

    def test_all_roles_excludes_a_manifest_and_a_role(self):
        for extra in (("--role", "reviewer"), ("--manifest", "x.json")):
            with self.subTest(extra=extra):
                done = run("--all-roles", "--provider", "codex", *extra)
                self.assertEqual(done.returncode, 2)

    def test_all_roles_output_is_the_prepare_skills_input(self):
        skills = json.loads(run("--all-roles", "--provider", "claude-code", "--json").stdout)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "skills.json"
            path.write_text(json.dumps(skills), encoding="utf-8")
            done = subprocess.run(
                [sys.executable, str(ORCH / "scripts" / "orch.py"), "prepare", "--provider", "claude-code",
                 "--input", str(ORCH / "fixtures" / "exec" / "v1" / "valid" / "execution-input" / "plan-bound.json"),
                 "--policy", str(ORCH / "configs" / "run-policies" / "review-only" / "policy.json"),
                 "--out", str(Path(tmp) / "out"), "--dry-run", "--skills", str(path)],
                capture_output=True, text=True, encoding="utf-8", check=False, cwd=tmp)
        self.assertEqual(done.returncode, 0, done.stderr)
        delivered = {stage["role"]: stage["delivery"].get("skills") for stage in json.loads(done.stdout)["stages"]}
        self.assertEqual(delivered["reviewer"], skills["reviewer"])

    def test_text_output_lists_skills(self):
        done = run("--role", "reviewer", "--provider", "claude-code")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("quality/code-review  required", done.stdout)


class DigestUnknown(unittest.TestCase):
    """The partner cannot describe a skill: the digest is absent and a warning says so."""

    def test_missing_digest_is_a_warning_not_a_failure(self):
        sys.path.insert(0, str(BRIDGE))
        import resolve_role
        manifest = {"contract_version": "exec/v1", "role_id": "reviewer"}
        with mock.patch.object(resolve_role, "run_describe", return_value=None):
            out, failed = resolve_role.resolve_role(manifest, "codex", "native")
        self.assertFalse(failed)
        self.assertTrue(out["skills"])
        self.assertTrue(all("digest" not in skill for skill in out["skills"]))
        unknown = [d for d in out["diagnostics"] if d["code"] == "SKILL_DIGEST_UNKNOWN"]
        self.assertEqual(sorted(d["skill"] for d in unknown), sorted(s["id"] for s in out["skills"]))
        self.assertEqual({d["severity"] for d in unknown}, {"warning"})

    def test_all_roles_leaves_a_skill_without_digest_out(self):
        import resolve_role
        with mock.patch.object(resolve_role, "run_describe", return_value=None):
            delivered, diagnostics, failed = resolve_role.all_roles("codex", "native")
        self.assertEqual((delivered["reviewer"], failed), ([], False))
        self.assertEqual({d["code"] for d in diagnostics}, {"SKILL_DIGEST_UNKNOWN"})
        self.assertEqual({d["role"] for d in diagnostics}, {"reviewer"})

    def test_describe_is_read_once_per_skill(self):
        import resolve_role
        with mock.patch.object(resolve_role, "run_describe", return_value="sha256:" + "0" * 64) as describe:
            resolve_role.all_roles("codex", "native")
        ids = [call.args[0] for call in describe.call_args_list]
        self.assertEqual(len(ids), len(set(ids)))

    def test_describe_rejects_an_unreadable_answer(self):
        import resolve_role
        for stdout in ("", "not json", json.dumps({"digest": "md5:1"}), json.dumps({"id": "x"}), json.dumps([])):
            with self.subTest(stdout=stdout):
                done = subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")
                with mock.patch.object(resolve_role.subprocess, "run", return_value=done), \
                        mock.patch.object(resolve_role, "require_skiller", return_value=Path("skiller")):
                    self.assertIsNone(resolve_role.run_describe("quality/code-review"))


class PartnerLookup(unittest.TestCase):
    def test_missing_partner_is_a_clear_error(self):
        import os
        env = {**os.environ, "SKM_SKILLER_ROOT": "/nonexistent"}
        done = subprocess.run([sys.executable, str(SCRIPT), "--role", "reviewer", "--provider", "codex"],
                              capture_output=True, text=True, env=env, check=False)
        self.assertEqual(done.returncode, 3)
        self.assertIn("BRIDGE_PARTNER_UNAVAILABLE", done.stderr)


class FakeSkillerSelect(unittest.TestCase):
    """Required --select coverage, with a fake PATH partner and no installed-partner skip."""

    def test_select_preserves_directory_digest_and_hashes_exact_skill_md_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            skill = root / "SKILL.md"
            data = b"---\r\nname: demo\r\n---\r\nExact skill bytes.\r\n"
            skill.write_bytes(data)
            directory_digest = "sha256:" + "c" * 64
            answer = {"included": [{"name": "demo", "id": "core/demo", "path": str(skill),
                                    "reason": "explicit", "tokens": 10, "digest": directory_digest}],
                      "excluded": [], "discoverable": [], "tokens": 10}
            launcher = root / "skiller"
            launcher.write_text(f"#!{sys.executable}\nprint({json.dumps(answer)!r})\n", encoding="utf-8")
            launcher.chmod(0o755)
            # A minimal role root keeps both partner lookups inside the fixture.
            orch = root / "orch"
            (orch / "scripts").mkdir(parents=True)
            (orch / "scripts/orch.py").touch()
            (orch / "roles").mkdir()
            (orch / "roles/executor.json").write_text(json.dumps({"contract_version": "exec/v1",
                                                                "role_id": "executor", "skills": []}))
            env = {**os.environ, "PATH": str(root), "SKM_SKILLER_ROOT": "", "SKM_ORCH_ROOT": str(orch),
                   "HOME": str(root / "home"), "CODEX_HOME": str(root / "codex"), "GROK_HOME": str(root / "grok")}
            done = subprocess.run([sys.executable, str(SCRIPT), "--select", "--role", "executor", "--provider", "codex"],
                                  capture_output=True, text=True, env=env, check=False)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            out = json.loads(done.stdout)
            self.assertEqual(out["skills"], [{**answer["included"][0], "skill_md_sha256": hashlib.sha256(data).hexdigest()}])
            # The consumer belongs to orch; exercise it as a process across this bridge, never import the bridge
            # into the neutral core's own tests. Both partner roots come from the explicit worktree environment.
            orch_root = partners.require_orch_root()
            foundation = partners.aicore_lib()
            self.assertIsNotNone(foundation, "AICORE_ROOT must name the worktree foundation")
            probe_env = {**env, "PYTHONPATH": os.pathsep.join((str(orch_root / "lib"), str(foundation)))}
            probe = '''\
import json, sys
from pathlib import Path
from types import SimpleNamespace
from orch.conductor import engine, options
chosen = json.load(sys.stdin)
path = Path(chosen["skills"][0]["path"])
eng = engine.Conductor.__new__(engine.Conductor)
eng.project = path.parent
eng.progress = SimpleNamespace(emit=lambda *args, **kwargs: None)
item = SimpleNamespace(ref="W1", state={"skills_auto": {"executor": chosen}}, routes={}, input_doc={},
                       options={"skills": {"executor": ["auto"]}, "instructions": {"isolate_roles": ["executor"]},
                                "limits": dict(options.DEFAULT_LIMITS)})
names = eng._skills(item, "executor")
assert names == ["demo"], names
assert eng._skill_texts(item, "executor") == {"demo": "Exact skill bytes."}
path.write_bytes(b"Changed after selection.\\n")
texts = eng._skill_texts(item, "executor")
assert texts == {}, texts
assert names == [], names
excluded = eng._skills_excluded(item, "executor")
assert excluded == [{"id": "core/demo", "reason": "digest_mismatch"}], excluded
print(json.dumps({"accepted": True, "excluded_after_change": excluded}))
'''
            consumed = subprocess.run([sys.executable, "-c", probe], input=json.dumps(out), capture_output=True,
                                      text=True, env=probe_env, check=False, cwd=root)
            self.assertEqual(consumed.returncode, 0, consumed.stdout + consumed.stderr)
            self.assertTrue(json.loads(consumed.stdout)["accepted"])

    def test_select_hash_does_not_open_oversized_or_symlink_files(self):
        import resolve_role
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            large = root / "SKILL.md"
            large.write_bytes(b"x" * (70 * 1024))
            with mock.patch.object(resolve_role.os, "open") as opened:
                self.assertIsNone(resolve_role.skill_md_sha256(large))
            opened.assert_not_called()
            (root / "alias").symlink_to(root, target_is_directory=True)
            large.write_text("Small.")
            with mock.patch.object(resolve_role.os, "open") as opened:
                self.assertIsNone(resolve_role.skill_md_sha256(root / "alias/SKILL.md"))
            opened.assert_not_called()


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(SKILLER and ORCH and can_select(), "skiller with `select` or orch partner not found")
class SelectRole(unittest.TestCase):
    def select(self, role: str, *args: str) -> dict:
        done = run("--select", "--role", role, "--provider", "claude-code", *args)
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        return json.loads(done.stdout)

    def test_migration_work_gets_the_triggered_skill_with_a_readable_path(self):
        out = self.select("executor", "--paths", "database/migrations/2026_01_01_create_users.php")
        ids = [skill["id"] for skill in out["skills"]]
        self.assertIn("php/database", ids)
        skill = next(s for s in out["skills"] if s["id"] == "php/database")
        self.assertEqual(skill["reason"], "trigger_path")
        self.assertTrue(Path(skill["path"]).is_file())
        self.assertEqual(out["tokens"], sum(s["tokens"] for s in out["skills"]))

    def test_no_signal_means_no_skills_for_a_role_without_a_list(self):
        out = self.select("executor", "--paths", "docs/guide.md")
        self.assertEqual(out["skills"], [])

    def test_the_role_list_is_included_explicitly(self):
        out = self.select("reviewer", "--paths", "docs/guide.md")
        by_id = {skill["id"]: skill["reason"] for skill in out["skills"]}
        self.assertEqual(by_id.get("quality/code-review"), "explicit")
        self.assertNotIn("quality/artifact-review", by_id)  # optional in the role list: not forced, same exclusive group

    def test_exclude_wins_over_include_and_budget_excludes_without_cutting(self):
        out = self.select("reviewer", "--exclude", "quality/code-review")
        self.assertNotIn("quality/code-review", [s["id"] for s in out["skills"]])
        self.assertIn({"id": "quality/code-review", "reason": "excluded"}, out["excluded"])
        over = self.select("executor", "--paths", "database/migrations/x.php", "--budget", "10")
        self.assertEqual(over["skills"], [])
        self.assertEqual({row["reason"] for row in over["excluded"]}, {"over_budget"})

    def test_select_needs_a_role(self):
        done = run("--select", "--manifest", "x.json", "--provider", "codex")
        self.assertEqual(done.returncode, 2)
