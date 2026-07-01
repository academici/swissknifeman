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

    def test_conditional_if_and_ifnot(self):
        # pack:if держит блок при truthy, pack:ifnot — при falsy/отсутствующем.
        t = ("<!-- pack:if K -->yes<!-- pack:endif -->"
             "<!-- pack:ifnot K -->no<!-- pack:endif -->")
        self.assertEqual(ap._apply_conditionals(t, {"K": True}), "yes")
        self.assertEqual(ap._apply_conditionals(t, {"K": False}), "no")
        self.assertEqual(ap._apply_conditionals(t, {}), "no")   # отсутствует → falsy
        # соседние плоские блоки разных типов парятся независимо
        flat = ("A<!-- pack:if P -->-pkg<!-- pack:endif -->"
                "<!-- pack:ifnot P -->-app<!-- pack:endif -->B")
        self.assertEqual(ap._apply_conditionals(flat, {"P": True}), "A-pkgB")
        self.assertEqual(ap._apply_conditionals(flat, {"P": False}), "A-appB")

    def test_install_only_skips_installed(self):
        self._render(overrides={"PACK_PREFIX": "x"})
        rc = self._render(overrides={"PACK_PREFIX": "x"}, install_only=True)
        self.assertEqual(rc, 0)

    def test_doctor_clean_pack(self):
        self.assertEqual(ap.do_doctor(self.env, self.pack), 0)

    def test_upgrade_installs_new_file(self):
        # Файл, добавленный в новой версии пака (нет в прежнем lock), должен
        # ставиться на upgrade — не только render (иначе recon-агенты не доедут).
        self._render(overrides={"PACK_PREFIX": "x"})
        lock_path = self.proj / ".claude/agent-pack.lock.json"
        lock = json.loads(lock_path.read_text())
        entry = lock["packs"][self.pack]
        entry["version"] = "0.0.1"  # старее манифеста → upgrade сработает
        dropped = next(f["target"] for f in entry["files"]
                       if f["target"].endswith("-reviewer.md"))
        entry["files"] = [f for f in entry["files"] if f["target"] != dropped]
        lock_path.write_text(json.dumps(lock))
        (self.proj / dropped).unlink()  # как будто файл ещё не установлен
        self.assertFalse((self.proj / dropped).exists())
        ap.do_upgrade(self.env, self.pack, self.proj, overrides={},
                      dry=False, shell_policy="safe")
        self.assertTrue((self.proj / dropped).exists())  # новый файл поставлен


class TestCategorizeFileChange(unittest.TestCase):
    """Чистая логика категоризации (выделена из do_upgrade) — матрица случаев."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.tgt = self.tmp / "f.txt"

    def _pf(self, sha):
        return {"base_sha256": sha}

    def test_new_and_new_optional(self):
        self.assertEqual(ap.categorize_file_change({}, None, "sha", self.tgt), "new")
        self.assertEqual(
            ap.categorize_file_change({"optional": True}, None, "sha", self.tgt),
            "new-optional")

    def test_user_owned_short_circuits(self):
        self.assertEqual(
            ap.categorize_file_change({"user_owned": True}, self._pf("old"), "new", self.tgt),
            "user-owned")

    def test_nochange_when_base_same(self):
        self.assertEqual(
            ap.categorize_file_change({}, self._pf("same"), "same", self.tgt), "nochange")

    def test_safe_apply_base_changed_disk_untouched(self):
        # на диске = прежняя база (не правлена локально), база сменилась → safe-apply
        self.tgt.write_text("body", encoding="utf-8")
        disk = ap.sha256_text("body")
        self.assertEqual(
            ap.categorize_file_change({}, self._pf(disk), "newsha", self.tgt), "safe-apply")

    def test_conflict_base_and_local_both_changed(self):
        self.tgt.write_text("locally edited", encoding="utf-8")
        self.assertEqual(
            ap.categorize_file_change({}, self._pf("orig"), "newsha", self.tgt), "conflict")


if __name__ == "__main__":
    unittest.main()
