"""Тесты lock — композиция skills-lock.json (swissknifeman wins + Laravel Boost)."""
import json
import tempfile
import unittest
from pathlib import Path

from swissknifeman.common import Env
from swissknifeman.lock import compose_lock


def _setup(tmp):
    """Синтетический реестр + проект с boost.json и вендоренными скиллами."""
    root = Path(tmp) / "registry"
    root.mkdir()
    (root / "skills.json").write_text(json.dumps({"skills": [
        {"name": "laravel-best-practices", "bucket": "php"},
        {"name": "writing-style", "bucket": "general"},
        {"name": "ci-cd", "bucket": "devops"},
    ]}), encoding="utf-8")

    target = Path(tmp) / "proj"
    (target / ".claude/skills/laravel-best-practices").mkdir(parents=True)
    (target / ".claude/skills/database").mkdir(parents=True)  # boost-native, не в реестре
    (target / "boost.json").write_text(json.dumps({
        "skills": ["laravel-best-practices", "database", "pest-testing"]}),
        encoding="utf-8")
    return Env(root, "lock"), target


class TestComposeLock(unittest.TestCase):
    def test_swissknifeman_wins_and_boost_complements(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, target = _setup(tmp)
            skills = compose_lock(env, target)["skills"]
            # в реестре + в boost → swissknifeman wins, конфликт виден в also_in
            self.assertEqual(skills["laravel-best-practices"]["source"], "swissknifeman")
            self.assertEqual(skills["laravel-best-practices"]["bucket"], "php")
            self.assertEqual(skills["laravel-best-practices"]["also_in"], ["laravel-boost"])
            # не в реестре, есть в boost/установлен → laravel-boost
            self.assertEqual(skills["database"]["source"], "laravel-boost")
            self.assertEqual(skills["pest-testing"]["source"], "laravel-boost")
            self.assertNotIn("also_in", skills["database"])

    def test_universe_is_installed_union_boost(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, target = _setup(tmp)
            skills = compose_lock(env, target)["skills"]
            # writing-style/ci-cd есть в реестре, но не установлены и не в boost → не в lock
            self.assertNotIn("writing-style", skills)
            self.assertNotIn("ci-cd", skills)
            self.assertEqual(set(skills), {"laravel-best-practices", "database", "pest-testing"})

    def test_no_boost_only_swissknifeman(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, target = _setup(tmp)
            (target / "boost.json").unlink()  # проект без Laravel Boost
            lock = compose_lock(env, target)
            self.assertNotIn("laravel-boost", lock["sources"])
            self.assertEqual(set(lock["skills"]), {"laravel-best-practices", "database"})
            self.assertEqual(lock["skills"]["laravel-best-practices"]["source"], "swissknifeman")
            self.assertNotIn("also_in", lock["skills"]["laravel-best-practices"])
            # установлен, не в реестре, без boost → local (не laravel-boost)
            self.assertEqual(lock["skills"]["database"]["source"], "local")

    def test_local_skill_not_attributed_to_boost(self):
        # Скилл установлен, не в реестре, Boost ПОДКЛЮЧЁН, но скилла нет в
        # boost.json::skills (напр. ecosystem-mcp из хаба maind) → local, не boost.
        with tempfile.TemporaryDirectory() as tmp:
            env, target = _setup(tmp)
            (target / ".claude/skills/ecosystem-mcp").mkdir(parents=True)
            skills = compose_lock(env, target)["skills"]
            self.assertEqual(skills["ecosystem-mcp"]["source"], "local")
            # boost-объявленный скилл по-прежнему относится к boost
            self.assertEqual(skills["database"]["source"], "laravel-boost")


if __name__ == "__main__":
    unittest.main()
