"""Тесты projects.py: синк из brain (маппинг, идемпотентность, сохранение полей)."""
import tempfile
import unittest

from maind.config import load_config
from maind.projects import get, listing, sync_from_brain, write_config
from tests.fixtures import make_repo, write_brain_projects, write_maind_config


class TestSync(unittest.TestCase):
    def test_adds_and_preserves_maind_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            write_maind_config(root, projects=[
                {"id": "brain", "name": "OldName", "skills": ["arch"],
                 "dependencies": ["maind"], "type": "obsidian-vault"}])
            bpath = write_brain_projects(root)
            cfg, source = load_config(env)
            self.assertEqual(source, ".maind.json")
            cfg, stats = sync_from_brain(env, cfg, bpath)
            self.assertEqual(stats["added"], 1)    # swiss-knife-man — новый
            self.assertEqual(stats["updated"], 1)  # brain — обновлён
            brain = get(cfg, "brain")
            self.assertEqual(brain["name"], "Brain")       # обновлено из brain
            self.assertEqual(brain["skills"], ["arch"])    # maind-only сохранено
            self.assertEqual(brain["dependencies"], ["maind"])
            # идемпотентность: второй синк ничего не добавляет
            cfg, stats2 = sync_from_brain(env, cfg, bpath)
            self.assertEqual(stats2["added"], 0)

    def test_write_config_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            cfg, source = load_config(env)        # пусто
            self.assertEqual(source, "empty")
            cfg, _ = sync_from_brain(env, cfg, write_brain_projects(root))
            write_config(env, cfg)
            cfg2, source2 = load_config(env)
            self.assertEqual(source2, ".maind.json")  # .maind.json приоритетнее
            self.assertTrue(get(cfg2, "brain"))
            self.assertEqual(len(listing(env, cfg2)), 2)


if __name__ == "__main__":
    unittest.main()
