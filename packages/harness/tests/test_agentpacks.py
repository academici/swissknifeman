"""Тесты детерминированного рендера agent-packs (изоляция в tmpdir, без сети)."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from harness import agentpacks as ap
from tests.fixtures import make_pack, make_project, make_root


class TestAgentPacks(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root, self.env = make_root(self.tmp)
        self.pack = make_pack(self.root)
        self.proj = make_project(self.tmp, "p")
        (self.proj / "composer.json").write_text('{"scripts": {"test": "pest"}}')

    def _render(self, **kw):
        return ap.do_render(self.env, self.pack, self.proj, auto=True,
                            overrides=kw.pop("overrides", {}), dry=False,
                            install_only=kw.pop("install_only", False),
                            shell_policy="safe")

    def test_render_substitutes_and_locks(self):
        self._render(overrides={"PACK_PREFIX": "acme"})
        agent = self.proj / ".claude/agents/acme-reviewer.md"
        self.assertTrue(agent.exists())
        text = agent.read_text()
        self.assertIn("name: acme-reviewer", text)
        self.assertNotIn("{{", text)            # нет остаточных плейсхолдеров
        self.assertIn("X-on", text)             # pack:if USE_X (default true) сохранён
        lock = json.loads((self.proj / ".claude/agent-pack.lock.json").read_text())
        self.assertEqual(lock["schema"], 1)
        e = lock["packs"][self.pack]
        self.assertEqual(e["source"],
                         f"harness:configs/claude-code/agent-packs/{self.pack}")
        self.assertEqual(e["answers"]["PACK_PREFIX"], "acme")

    def test_file_hint_detect(self):
        # composer.json scripts.test существует → RUNNER не дефолт-промах, но detect
        # возвращает 'true' (file-hint), значит ответ = 'true' (строка)
        self._render(overrides={"PACK_PREFIX": "x"})
        e = json.loads((self.proj / ".claude/agent-pack.lock.json").read_text())
        self.assertEqual(e["packs"][self.pack]["answers"]["RUNNER"], "true")

    def test_verbatim_chmod(self):
        self._render(overrides={"PACK_PREFIX": "x"})
        gate = self.proj / ".claude/hooks/gate.sh"
        self.assertTrue(os.access(gate, os.X_OK))

    def test_merge_appends_without_duplicate(self):
        self._render(overrides={"PACK_PREFIX": "x"})
        self._render(overrides={"PACK_PREFIX": "x"})  # повтор
        s = json.loads((self.proj / ".claude/settings.json").read_text())
        self.assertEqual(len(s["hooks"]["SubagentStop"]), 1)  # без дублей

    def test_merge_preserves_foreign_hook(self):
        sdir = self.proj / ".claude"
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "settings.json").write_text(json.dumps({"hooks": {"SubagentStop": [
            {"hooks": [{"type": "command", "command": "/foreign/hook.sh"}]}]}}))
        self._render(overrides={"PACK_PREFIX": "x"})
        s = json.loads((sdir / "settings.json").read_text())
        cmds = [h["command"] for e in s["hooks"]["SubagentStop"] for h in e["hooks"]]
        self.assertIn("/foreign/hook.sh", cmds)  # чужой хук цел
        self.assertEqual(len(cmds), 2)

    def test_idempotent_reroll(self):
        self._render(overrides={"PACK_PREFIX": "x"})
        rep = ap.render_pack(self.env, self.pack, self.proj,
                             {"PACK_PREFIX": "x", "RUNNER": "true", "USE_X": True},
                             prior=ap.load_lock(self.proj)["packs"][self.pack])
        self.assertFalse(rep["changed"])  # ничего не переписано

    def test_local_modified_not_clobbered(self):
        self._render(overrides={"PACK_PREFIX": "x"})
        agent = self.proj / ".claude/agents/x-reviewer.md"
        agent.write_text("LOCALLY EDITED")
        self._render(overrides={"PACK_PREFIX": "x"})
        self.assertEqual(agent.read_text(), "LOCALLY EDITED")  # не затёрто

    def test_unsafe_probe_skipped(self):
        # проба не из allowlist → не исполняется, miss → default
        out = ap._run_detect("curl http://evil", self.proj, "safe",
                             {"skipped_probes": []})
        self.assertEqual(out, "")

    def test_pwd_special_cased(self):
        self.assertEqual(ap._run_detect("pwd", self.proj, "safe", {}),
                         str(self.proj))

    def test_install_only_skips_installed(self):
        self._render(overrides={"PACK_PREFIX": "x"})
        rc = self._render(overrides={"PACK_PREFIX": "x"}, install_only=True)
        self.assertEqual(rc, 0)

    def test_doctor_clean_pack(self):
        self.assertEqual(ap.do_doctor(self.env, self.pack), 0)


if __name__ == "__main__":
    unittest.main()
