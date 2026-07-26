"""Upgrade сверяет ФАКТ файлов, а не только номер версии пака.

Полевая раскатка 2026-07-11 (spec: удалённый `roadmap/agent-packs-upgrade-drift.md`,
текст в git-истории) дала два тихих отказа при РАВНЫХ версиях: (A) правка контента
источника без бампа `pack.json:version` не доехала ни в один из 11 проектов;
(B) снос соседнего пака с пересекающимися targets унёс файлы, а `upgrade` ответил
«уже актуален» и оставил проект с паком в локе и БЕЗ его файлов.

Здесь фиксируется поведение после фикса: план строится всегда из сверки хэшей,
локальные правки по-прежнему не затираются (conflict → `*.pack-new`), а совпадающее
состояние честно репортится как «нечего делать». Изоляция в tmpdir, без сети."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from harness import agentpacks as ap
from tests.fixtures import make_pack, make_project, make_root


class UpgradeFactBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root, self.env = make_root(self.tmp)
        self.pack = make_pack(self.root)
        self.proj = make_project(self.tmp, "p")
        (self.proj / "composer.json").write_text('{"scripts": {"test": "pest"}}')
        ap.do_render(self.env, self.pack, self.proj, auto=True,
                     overrides={"PACK_PREFIX": "acme"}, dry=False,
                     install_only=False, shell_policy="safe")
        self.pack_src = (self.root / "configs" / "claude-code" / "agent-packs"
                         / self.pack)
        self.reviewer = self.proj / ".claude/agents/acme-reviewer.md"
        self.gate = self.proj / ".claude/hooks/gate.sh"

    def upgrade(self):
        """upgrade без смены версии пака; возвращает (rc, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = ap.do_upgrade(self.env, self.pack, self.proj,
                               overrides={"PACK_PREFIX": "acme"}, dry=False,
                               shell_policy="safe")
        return rc, out.getvalue(), err.getvalue()

    def lock_entry(self):
        return json.loads((self.proj / ap.LOCK_REL).read_text())["packs"][self.pack]


class TestUpgradeByFact(UpgradeFactBase):
    def test_source_drift_without_version_bump_applied(self):
        """Кейс A: контент источника изменён, версия та же → изменение доезжает."""
        src = self.pack_src / "agents" / "reviewer.md"
        src.write_text(src.read_text() + "\nGlossary impact?\n")
        rc, out, err = self.upgrade()
        self.assertEqual(rc, 0)
        self.assertIn("Glossary impact?", self.reviewer.read_text())
        self.assertIn("[safe-apply]", out)
        self.assertIn("версия та же", out)
        self.assertIn("не менял версию", err)  # тихо игнорировать нельзя

    def test_deleted_target_restored_at_same_version(self):
        """Кейс B: target удалён (снос соседнего пака), версия та же → восстановление."""
        self.gate.unlink()
        rc, out, _err = self.upgrade()
        self.assertEqual(rc, 0)
        self.assertTrue(self.gate.exists())
        restored = self.gate.read_text()
        self.assertIn("echo gate", restored)              # контент источника
        self.assertIn("swissknifeman:generated", restored)  # с provenance-header'ом
        self.assertIn("[new]", out)

    def test_local_edit_plus_source_drift_is_conflict_not_overwrite(self):
        """Локальная правка + дрейф источника при равной версии → conflict, не затирание."""
        self.reviewer.write_text(self.reviewer.read_text() + "\nЛОКАЛЬНАЯ ПРАВКА\n")
        src = self.pack_src / "agents" / "reviewer.md"
        src.write_text(src.read_text() + "\nновая строка апстрима\n")
        rc, out, err = self.upgrade()
        self.assertEqual(rc, 0)
        self.assertIn("ЛОКАЛЬНАЯ ПРАВКА", self.reviewer.read_text())
        self.assertNotIn("новая строка апстрима", self.reviewer.read_text())
        pack_new = self.proj / ".claude/agents/acme-reviewer.md.pack-new"
        self.assertTrue(pack_new.exists())
        self.assertIn("новая строка апстрима", pack_new.read_text())
        self.assertIn("[conflict]", out)
        self.assertIn("conflict", err)

    def test_clean_state_reports_nothing_to_do(self):
        """Ничего не менялось → честное «нечего делать», без ложного «уже актуален»."""
        rc, out, err = self.upgrade()
        self.assertEqual(rc, 0)
        self.assertIn("нечего делать", out)
        self.assertNotIn("не менял версию", err)

    def test_user_owned_never_touched_at_same_version(self):
        """user_owned остаётся за пользователем и при сверке по факту."""
        overrides = self.proj / ".claude/agents/acme-overrides.md"
        overrides.write_text("моё содержимое\n")
        rc, _out, _err = self.upgrade()
        self.assertEqual(rc, 0)
        self.assertEqual(overrides.read_text(), "моё содержимое\n")

    def test_lock_base_sha_follows_applied_source(self):
        """После apply при равной версии lock хранит НОВЫЙ base_sha256 источника."""
        src = self.pack_src / "agents" / "reviewer.md"
        src.write_text(src.read_text() + "\nGlossary impact?\n")
        self.upgrade()
        entry = self.lock_entry()
        rec = next(f for f in entry["files"]
                   if f["target"] == ".claude/agents/acme-reviewer.md")
        self.assertEqual(rec["base_sha256"], ap.sha256_text(self.reviewer.read_text()))
        self.assertFalse(rec["local_modified"])

    def test_dry_run_does_not_write_at_same_version(self):
        self.gate.unlink()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            ap.do_upgrade(self.env, self.pack, self.proj,
                          overrides={"PACK_PREFIX": "acme"}, dry=True,
                          shell_policy="safe")
        self.assertFalse(self.gate.exists())
        self.assertIn("[new]", out.getvalue())


class TestDoctorSharedTargets(UpgradeFactBase):
    def test_two_packs_owning_one_target_warned(self):
        """Правило 6: два установленных пака владеют одним файлом → warn в doctor."""
        second = make_pack(self.root, name="demo-pack-2")
        ap.do_render(self.env, second, self.proj, auto=True,
                     overrides={"PACK_PREFIX": "acme"}, dry=False,
                     install_only=False, shell_policy="safe")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            ap.do_doctor(self.env, pack=None, target=self.proj)
        self.assertIn("пересечение targets", err.getvalue())
        self.assertIn(".claude/hooks/gate.sh", err.getvalue())

    def test_single_pack_no_shared_warning(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            ap.do_doctor(self.env, pack=None, target=self.proj)
        self.assertNotIn("пересечение targets", err.getvalue())


if __name__ == "__main__":
    unittest.main()
