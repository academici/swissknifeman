"""Tests lock — composition skills-lock.json (swissknifeman wins + Laravel Boost)."""
import json
import tempfile
import unittest
from pathlib import Path

from skiller.common import Env
from skiller.lock import compose_lock


def _setup(tmp):
    """Synthetic registry + project with boost.json and vendor skills."""
    root = Path(tmp) / "registry"
    root.mkdir()
    (root / "skills.json").write_text(json.dumps({"skills": [
        {"name": "laravel-best-practices", "bucket": "php"},
        {"name": "writing-style", "bucket": "general"},
        {"name": "ci-cd", "bucket": "devops"},
    ]}), encoding="utf-8")

    target = Path(tmp) / "proj"
    (target / ".claude/skills/laravel-best-practices").mkdir(parents=True)
    (target / ".claude/skills/database").mkdir(parents=True)  # boost-native, not in the registry
    (target / "boost.json").write_text(json.dumps({
        "skills": ["laravel-best-practices", "database", "pest-testing"]}),
        encoding="utf-8")
    return Env(root, "lock"), target


class TestComposeLock(unittest.TestCase):
    def test_swissknifeman_wins_and_boost_complements(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, target = _setup(tmp)
            skills = compose_lock(env, target)["skills"]
            # in the registry + in boost → swissknifeman wins, conflict visible in also_in
            self.assertEqual(skills["laravel-best-practices"]["source"], "swissknifeman")
            self.assertEqual(skills["laravel-best-practices"]["bucket"], "php")
            self.assertEqual(skills["laravel-best-practices"]["also_in"], ["laravel-boost"])
            # is not in the registry, it is in boost/installed → laravel-boost
            self.assertEqual(skills["database"]["source"], "laravel-boost")
            self.assertEqual(skills["pest-testing"]["source"], "laravel-boost")
            self.assertNotIn("also_in", skills["database"])

    def test_universe_is_installed_union_boost(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, target = _setup(tmp)
            skills = compose_lock(env, target)["skills"]
            # writing-style/ci-cd is in the registry, but not installed and not in boost → not in lock
            self.assertNotIn("writing-style", skills)
            self.assertNotIn("ci-cd", skills)
            self.assertEqual(set(skills), {"laravel-best-practices", "database", "pest-testing"})

    def test_no_boost_only_swissknifeman(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, target = _setup(tmp)
            (target / "boost.json").unlink()  # project without Laravel Boost
            lock = compose_lock(env, target)
            self.assertNotIn("laravel-boost", lock["sources"])
            self.assertEqual(set(lock["skills"]), {"laravel-best-practices", "database"})
            self.assertEqual(lock["skills"]["laravel-best-practices"]["source"], "swissknifeman")
            self.assertNotIn("also_in", lock["skills"]["laravel-best-practices"])
            # installed, not in the registry, without boost → local (not laravel-boost)
            self.assertEqual(lock["skills"]["database"]["source"], "local")

    def test_local_skill_not_attributed_to_boost(self):
        # Skill installed, not in the registry, Boost CONNECTED, but the skill is not in
        # boost.json::skills (e.g. ecosystem-mcp from the hub's memory tool) → local, not boost.
        with tempfile.TemporaryDirectory() as tmp:
            env, target = _setup(tmp)
            (target / ".claude/skills/ecosystem-mcp").mkdir(parents=True)
            skills = compose_lock(env, target)["skills"]
            self.assertEqual(skills["ecosystem-mcp"]["source"], "local")
            # boost-declared skill still applies to boost
            self.assertEqual(skills["database"]["source"], "laravel-boost")


if __name__ == "__main__":
    unittest.main()
