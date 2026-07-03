"""Тесты BRAIN docs-sync (brain_sync.BrainSync).

Покрывают: pull копирует файлы из BRAIN в проект по glob-паттернам (mkdir + copy2,
сохраняя относительный путь); generate_sync_script пишет валидный bash (bash -n);
строковый конфиг нормализуется (back-compat: строка = путь без правил синка).
Всё во временных каталогах, без сети."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.brain_sync import BrainSync, normalize_brain_config


class NormalizeCase(unittest.TestCase):
    def test_string_config_becomes_path(self):
        # back-compat: строка = путь к волту, без правил синка.
        cfg = normalize_brain_config("/vaults/Brain")
        self.assertEqual(cfg, {"path": "/vaults/Brain"})

    def test_object_config_passthrough(self):
        obj = {"path": "/vaults/Brain", "sync": {"direction": "pull"}}
        self.assertEqual(normalize_brain_config(obj), obj)
        # НЕ мутируем вход (возвращаем копию).
        self.assertIsNot(normalize_brain_config(obj), obj)

    def test_empty_config(self):
        self.assertEqual(normalize_brain_config(None), {})
        self.assertEqual(normalize_brain_config(""), {})

    def test_string_config_defaults(self):
        # Строковый конфиг → direction по умолчанию pull, on_integrate False,
        # patterns — дефолтные.
        bs = BrainSync("/proj", "/vaults/Brain")
        self.assertEqual(bs.brain_path, Path("/vaults/Brain"))
        self.assertEqual(bs.direction, "pull")
        self.assertFalse(bs.on_integrate)
        self.assertTrue(bs.patterns)


class SyncPullCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.brain = self.tmp / "brain"
        self.proj = self.tmp / "proj"
        self.brain.mkdir()
        self.proj.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, base, rel, text):
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def test_pull_copies_by_patterns(self):
        # В BRAIN: docs/guide/a.md, README.md (матчатся) + secret.txt (не матчится).
        self._write(self.brain, "docs/guide/a.md", "# A")
        self._write(self.brain, "README.md", "# readme")
        self._write(self.brain, "secret.txt", "nope")
        cfg = {"path": str(self.brain),
               "sync": {"direction": "pull", "patterns": ["docs/**/*.md", "README.md"]}}
        bs = BrainSync(self.proj, cfg)
        copied = bs.sync_pull()
        # Скопированы только .md по паттернам, с сохранением относительного пути.
        self.assertEqual((self.proj / "docs/guide/a.md").read_text(encoding="utf-8"), "# A")
        self.assertEqual((self.proj / "README.md").read_text(encoding="utf-8"), "# readme")
        self.assertFalse((self.proj / "secret.txt").exists())
        self.assertEqual(len(copied), 2)

    def test_pull_missing_brain_is_soft(self):
        # Несуществующий BRAIN → [] без исключения.
        bs = BrainSync(self.proj, {"path": str(self.tmp / "nope")})
        self.assertEqual(bs.sync_pull(), [])

    def test_pull_idempotent_overwrites(self):
        self._write(self.brain, "README.md", "v1")
        bs = BrainSync(self.proj, {"path": str(self.brain),
                                   "sync": {"patterns": ["README.md"]}})
        bs.sync_pull()
        self._write(self.brain, "README.md", "v2")
        bs.sync_pull()
        self.assertEqual((self.proj / "README.md").read_text(encoding="utf-8"), "v2")


class GenerateScriptCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.proj = self.tmp / "proj"
        self.proj.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_generates_valid_bash(self):
        bs = BrainSync(self.proj, {"path": "/vaults/Brain",
                                   "sync": {"direction": "bidirectional",
                                            "patterns": ["docs/**/*.md"]}})
        script = bs.generate_sync_script()
        self.assertTrue(script.exists())
        self.assertEqual(script, self.proj / ".claude" / "sync-brain.sh")
        text = script.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("#!/usr/bin/env bash"))
        self.assertIn("/vaults/Brain", text)
        # Синтаксис валиден (bash -n не исполняет, только парсит).
        bash = shutil.which("bash")
        if bash:
            r = subprocess.run([bash, "-n", str(script)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_string_config_generates_script(self):
        # Строковый конфиг тоже даёт скрипт (BRAIN зашит, паттерны дефолтные).
        bs = BrainSync(self.proj, "/vaults/Brain")
        script = bs.generate_sync_script()
        text = script.read_text(encoding="utf-8")
        self.assertIn("/vaults/Brain", text)
        bash = shutil.which("bash")
        if bash:
            r = subprocess.run([bash, "-n", str(script)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
