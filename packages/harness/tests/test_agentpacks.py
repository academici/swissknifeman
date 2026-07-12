"""Тесты детерминированного рендера agent-packs (изоляция в tmpdir, без сети)."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from harness import agentpacks as ap
from tests.fixtures import make_pack, make_project, make_root, make_src_pack_pair


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

    def test_lock_local_modified_flag_stays_honest(self):
        # F-7 field-feedback (chatom): report["changed"] отражает только запись НА
        # ДИСК — если единственное, что изменилось между прогонами, это флаг
        # local_modified (файл стал/перестал быть локально правленным, а писать на
        # диск было нечего — см. test_local_modified_not_clobbered выше), раньше
        # write_lock() пропускался и lock годами врал. Отдельно от "не затирает
        # содержимое" (тест выше) — здесь проверяем именно ЧЕСТНОСТЬ lock'а.
        self._render(overrides={"PACK_PREFIX": "x"})
        lock_path = self.proj / ".claude/agent-pack.lock.json"
        agent = self.proj / ".claude/agents/x-reviewer.md"
        original = agent.read_text()

        agent.write_text("LOCALLY EDITED")
        self._render(overrides={"PACK_PREFIX": "x"})
        lock = json.loads(lock_path.read_text())
        f = next(f for f in lock["packs"][self.pack]["files"]
                if f["target"].endswith("-reviewer.md"))
        self.assertTrue(f["local_modified"])  # lock ловит правку немедленно

        agent.write_text(original)  # вручную привели к базе (как в F-7)
        self._render(overrides={"PACK_PREFIX": "x"})
        lock = json.loads(lock_path.read_text())
        f = next(f for f in lock["packs"][self.pack]["files"]
                if f["target"].endswith("-reviewer.md"))
        self.assertFalse(f["local_modified"])  # и честно снимает флаг обратно

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

    def test_doctor_warns_on_bak_files_but_stays_ok(self):
        # .bak в .claude/agents/ — легальный бэкап merge-only записи (не ошибка):
        # doctor должен warn'ить, но rc остаётся 0 (P4.2 — гигиена, не гейт).
        self._render(overrides={"PACK_PREFIX": "acme"})
        (self.proj / ".claude/agents/acme-reviewer.md.bak").write_text("old")
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            rc = ap.do_doctor(self.env, self.pack, self.proj)
        self.assertEqual(rc, 0)
        self.assertIn("acme-reviewer.md.bak", buf.getvalue())

    def test_doctor_no_warn_without_bak_files(self):
        self._render(overrides={"PACK_PREFIX": "acme"})
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            rc = ap.do_doctor(self.env, self.pack, self.proj)
        self.assertEqual(rc, 0)
        self.assertNotIn(".bak", buf.getvalue())

    # ── src_pack (F-1) ────────────────────────────────────────────────────────
    def test_src_pack_renders_from_other_pack_with_own_header(self):
        # пак B без собственных файлов — src_pack указывает на A: контент читается
        # из каталога A, но provenance-header несёт владельца — B@его версия.
        pack_b = make_src_pack_pair(self.root, self.pack)
        rc = ap.do_render(self.env, pack_b, self.proj, auto=True, overrides={},
                          dry=False, install_only=False, shell_policy="safe")
        self.assertEqual(rc, 0)
        shared = self.proj / f".claude/agents/{self.proj.name}-shared.md"
        self.assertTrue(shared.exists())
        text = shared.read_text()
        self.assertIn(f"Pack: {pack_b}@0.1.0", text)   # владелец — B, не A
        self.assertIn("Template: agents/reviewer.md", text)
        self.assertNotIn("{{", text)

    def test_src_pack_doctor_checks_existence_in_other_pack(self):
        pack_b = make_src_pack_pair(self.root, self.pack)
        self.assertEqual(ap.do_doctor(self.env, pack_b), 0)

    def test_src_pack_missing_source_is_bad_in_doctor(self):
        pack_b = make_src_pack_pair(self.root, self.pack, name_b="demo-pack-c")
        pdir = self.root / "configs" / "claude-code" / "agent-packs" / "demo-pack-c"
        manifest = json.loads((pdir / "pack.json").read_text())
        manifest["files"][0]["src_pack"] = "no-such-pack"
        (pdir / "pack.json").write_text(json.dumps(manifest))
        rc = ap.do_doctor(self.env, "demo-pack-c")
        self.assertEqual(rc, 1)

    # ── provenance-header (E-1) ──────────────────────────────────────────────
    def test_header_in_md_after_frontmatter(self):
        # header в .md строго ПОСЛЕ закрывающего '---' — иначе сломался бы
        # парсинг YAML-метаданных агента Claude Code'ом
        self._render(overrides={"PACK_PREFIX": "acme"})
        text = (self.proj / ".claude/agents/acme-reviewer.md").read_text()
        fm_end = text.index("\n---\n") + len("\n---\n")
        self.assertTrue(text[fm_end:].startswith("<!-- swissknifeman:generated"))
        self.assertIn(f"Pack: {self.pack}@0.1.0", text)
        self.assertIn("Template: agents/reviewer.md", text)
        self.assertIn("Edit-policy: generated-core", text)
        # точка расширения из role=override с интерполированным target
        self.assertIn("Extension-points: .claude/agents/acme-overrides.md", text)
        self.assertIn(f"Upgrade: harness agent-packs upgrade --pack {self.pack} "
                      "--target .", text)

    def test_header_in_sh_after_shebang(self):
        # verbatim-файл тоже получает header; shebang остаётся первой строкой
        self._render(overrides={"PACK_PREFIX": "x"})
        lines = (self.proj / ".claude/hooks/gate.sh").read_text().splitlines()
        self.assertTrue(lines[0].startswith("#!"))
        self.assertEqual(lines[1], "# swissknifeman:generated")

    def test_header_user_owned_policy(self):
        self._render(overrides={"PACK_PREFIX": "x"})
        text = (self.proj / ".claude/agents/x-overrides.md").read_text()
        self.assertIn("Edit-policy: user-owned — файл ваш", text)
        # .md без frontmatter → header в самом начале
        self.assertTrue(text.startswith("<!-- swissknifeman:generated"))

    def test_merge_fragment_without_header(self):
        # kind=merge вливается в чужой settings.json — header там невалиден
        self._render(overrides={"PACK_PREFIX": "x"})
        s = (self.proj / ".claude/settings.json").read_text()
        self.assertNotIn("swissknifeman:generated", s)

    def test_header_deterministic_rerender_nochange(self):
        # header без timestamp → sha стабилен → повторный render = skip-nochange
        self._render(overrides={"PACK_PREFIX": "x"})
        before = (self.proj / ".claude/agents/x-reviewer.md").read_text()
        rep = ap.render_pack(self.env, self.pack, self.proj,
                             {"PACK_PREFIX": "x", "RUNNER": "true", "USE_X": True},
                             prior=ap.load_lock(self.proj)["packs"][self.pack])
        self.assertFalse(rep["changed"])
        self.assertEqual((self.proj / ".claude/agents/x-reviewer.md").read_text(),
                         before)

    def test_header_deterministic_skip_identical_without_lock(self):
        # без lock (owned=False), диск байт-в-байт совпадает → skip-identical, не write
        self._render(overrides={"PACK_PREFIX": "x"})
        rep = ap.render_pack(self.env, self.pack, self.proj,
                             {"PACK_PREFIX": "x", "RUNNER": "true", "USE_X": True},
                             prior=None)
        self.assertFalse(rep["changed"])
        self.assertEqual(rep["notes"], [])  # ни одной collision-жалобы

    def test_user_owned_flag_in_lock(self):
        self._render(overrides={"PACK_PREFIX": "x"})
        lock = json.loads((self.proj / ".claude/agent-pack.lock.json").read_text())
        by_src = {f["src"]: f for f in lock["packs"][self.pack]["files"]}
        self.assertTrue(all("user_owned" in f for f in by_src.values()))
        self.assertTrue(by_src["agents/overrides.md"]["user_owned"])
        self.assertFalse(by_src["agents/reviewer.md"]["user_owned"])

    def test_old_lock_without_user_owned_still_reads(self):
        # старый lock (до E-1) без поля user_owned читается без миграции
        self._render(overrides={"PACK_PREFIX": "x"})
        lp = self.proj / ".claude/agent-pack.lock.json"
        lock = json.loads(lp.read_text())
        for f in lock["packs"][self.pack]["files"]:
            f.pop("user_owned", None)
        lp.write_text(json.dumps(lock))
        prior = ap.load_lock(self.proj)["packs"][self.pack]
        self.assertFalse(any(f.get("user_owned", False) for f in prior["files"]))
        rep = ap.render_pack(self.env, self.pack, self.proj,
                             {"PACK_PREFIX": "x", "RUNNER": "true", "USE_X": True},
                             prior=prior)
        self.assertFalse(rep["changed"])  # base_sha256 те же — nochange
        lock2 = json.loads(lp.read_text())  # lock не переписан (changed=False)…
        # …но render-репорт уже несёт поле аддитивно
        self.assertTrue(all("user_owned" in f for f in rep["files"]))
        self.assertEqual(lock2["schema"], 1)

    def test_provenance_header_unknown_extension_empty(self):
        self.assertEqual(ap.provenance_header("p", "1.0", "a.json", "b.json",
                                              "x", []), "")
        # пустой header → inject_header не трогает текст
        self.assertEqual(ap.inject_header("body", "", "b.json"), "body")

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


class TestAgentPacksRemove(unittest.TestCase):
    """Тесты do_remove (F-2): удаление установленного пака из target."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root, self.env = make_root(self.tmp)
        self.pack = make_pack(self.root)
        self.proj = make_project(self.tmp, "p")
        (self.proj / "composer.json").write_text('{"scripts": {"test": "pest"}}')
        ap.do_render(self.env, self.pack, self.proj, auto=True,
                    overrides={"PACK_PREFIX": "x"}, dry=False,
                    install_only=False, shell_policy="safe")
        self.reviewer = self.proj / ".claude/agents/x-reviewer.md"
        self.overrides = self.proj / ".claude/agents/x-overrides.md"
        self.gate = self.proj / ".claude/hooks/gate.sh"
        self.settings = self.proj / ".claude/settings.json"
        self.lock_path = self.proj / ".claude/agent-pack.lock.json"

    def test_remove_deletes_clean_files_lock_removed(self):
        # единственный установленный пак → после remove lock целиком удалён
        rc = ap.do_remove(self.env, self.pack, self.proj, dry=False)
        self.assertEqual(rc, 0)
        self.assertFalse(self.reviewer.exists())     # чистый template-файл снесён
        self.assertFalse(self.gate.exists())          # чистый verbatim-файл снесён
        self.assertTrue(self.overrides.exists())       # user_owned остался
        self.assertTrue(self.settings.exists())         # merge — settings.json не трогаем
        self.assertFalse(self.lock_path.exists())        # lock опустел → удалён целиком

    def test_remove_keeps_locally_modified_file(self):
        self.reviewer.write_text("LOCALLY EDITED")
        ap.do_remove(self.env, self.pack, self.proj, dry=False)
        self.assertTrue(self.reviewer.exists())
        self.assertEqual(self.reviewer.read_text(), "LOCALLY EDITED")

    def test_remove_drops_only_this_pack_entry_from_lock(self):
        pack_b = make_src_pack_pair(self.root, self.pack)
        ap.do_render(self.env, pack_b, self.proj, auto=True, overrides={},
                    dry=False, install_only=False, shell_policy="safe")
        ap.do_remove(self.env, self.pack, self.proj, dry=False)
        self.assertTrue(self.lock_path.exists())  # второй пак ещё установлен
        lock = json.loads(self.lock_path.read_text())
        self.assertNotIn(self.pack, lock["packs"])
        self.assertIn(pack_b, lock["packs"])

    def test_remove_dry_run_changes_nothing(self):
        before_lock = self.lock_path.read_text()
        rc = ap.do_remove(self.env, self.pack, self.proj, dry=True)
        self.assertEqual(rc, 0)
        self.assertTrue(self.reviewer.exists())
        self.assertTrue(self.gate.exists())
        self.assertEqual(self.lock_path.read_text(), before_lock)

    def test_remove_not_installed_is_noop(self):
        rc = ap.do_remove(self.env, "no-such-pack", self.proj, dry=False)
        self.assertEqual(rc, 0)
        self.assertTrue(self.reviewer.exists())  # ничего не тронуто

    def test_remove_missing_file_silently_skipped(self):
        self.reviewer.unlink()
        rc = ap.do_remove(self.env, self.pack, self.proj, dry=False)
        self.assertEqual(rc, 0)
        self.assertFalse(self.lock_path.exists())


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

    def test_missing_file_with_base_changed_is_new_not_conflict(self):
        # F-7 field-feedback (chatom, upgrade _common 0.3.0→0.4.0): файл установлен
        # паком (pf есть в lock) и база сменилась (напр. version-bump в header), но
        # файл пропал с диска (тот же случай ловит lock_drift: 'missing'). Раньше
        # несуществующий disk_sha="" всегда != base → ложный "conflict" → бесполезный
        # *.pack-new вместо простого восстановления. self.tgt НЕ создаётся — файла нет.
        self.assertEqual(
            ap.categorize_file_change({}, self._pf("orig"), "newsha", self.tgt), "new")
        self.assertEqual(
            ap.categorize_file_change({"optional": True}, self._pf("orig"), "newsha", self.tgt),
            "new-optional")

    def test_missing_file_with_base_unchanged_stays_nochange(self):
        # Пропавший файл БЕЗ смены версии пака — не дело upgrade его восстанавливать
        # (это забота doctor --drift); upgrade просто нечего делать для этой записи.
        self.assertEqual(
            ap.categorize_file_change({}, self._pf("samesha"), "samesha", self.tgt), "nochange")


if __name__ == "__main__":
    unittest.main()
