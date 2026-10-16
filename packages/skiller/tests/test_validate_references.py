"""scripts/validate.sh reference gates: a broken skill/bucket/preset reference in presets/, profiles/ or
budget-configs/ fails the validator and names the file and the token.

Isolated like test_validate_upstream_body_path.py: validate.sh is copied next to a synthetic registry (never the
real package, never the real HOME); the sections that need the rest of the registry report their own errors, so
the exit code is non-zero and the assertions look for the specific reference lines."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
VALIDATE_SCRIPT = PKG_ROOT / "scripts" / "validate.sh"
GOOD = {
    "presets/demo-set.json": {"name": "demo-set", "description": "d", "buckets": ["general"],
                              "include": ["general/foo", "bar"]},
    "profiles/standalone.json": {"name": "standalone", "buckets": ["general"]},
    "budget-configs/demo.json": {"buckets": ["general"], "include": ["foo", "general/bar"],
                                 "exclude": ["bar", "general"], "presets": ["demo-set"], "agent": "claude"},
}


class ValidateReferencesCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name) / "home"
        self.home.mkdir()
        self.root = Path(tmp.name) / "registry"
        for name in ("foo", "bar"):
            skill = self.root / "skills" / "general" / name
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: Demo skill {name}.\n---\n\nBody.\n", encoding="utf-8")
        (self.root / "scripts").mkdir()
        shutil.copy2(VALIDATE_SCRIPT, self.root / "scripts" / "validate.sh")
        for rel, data in GOOD.items():
            self.write(rel, data)

    def write(self, rel, data):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def validate(self):
        env = dict(os.environ, HOME=str(self.home), SKM_HOME=str(self.home), SKM_VALIDATE_SKIP_TESTS="1")
        env.setdefault("AICORE_ROOT", str(PKG_ROOT.parent / "aicore"))
        result = subprocess.run(["bash", str(self.root / "scripts" / "validate.sh")], env=env,
                                capture_output=True, text=True, timeout=120)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        return result

    def test_valid_references_raise_no_reference_error(self):
        out = self.validate().stdout
        for needle in ("unknown bucket", "does not resolve", "unknown preset", "extends unknown"):
            self.assertNotIn(needle, out)

    def test_broken_references_are_named_with_file_and_token(self):
        cases = (
            ("presets/demo-set.json", {"include": ["general/ghost"]},
             "presets/demo-set.json: include 'general/ghost' does not resolve"),
            ("presets/demo-set.json", {"buckets": ["ghostbucket"]},
             "presets/demo-set.json: unknown bucket 'ghostbucket'"),
            ("profiles/standalone.json", {"buckets": ["ghostbucket"]},
             "profiles/standalone.json: unknown bucket: ghostbucket"),
            ("budget-configs/demo.json", {"buckets": ["ghostbucket"]},
             "budget-configs/demo.json: unknown bucket 'ghostbucket'"),
            ("budget-configs/demo.json", {"include": ["general/ghost"]},
             "budget-configs/demo.json: include 'general/ghost' does not resolve"),
            ("budget-configs/demo.json", {"exclude": ["ghost-skill"]},
             "budget-configs/demo.json: exclude 'ghost-skill' does not resolve"),
            ("budget-configs/demo.json", {"presets": ["ghost-preset"]},
             "budget-configs/demo.json: unknown preset 'ghost-preset'"),
        )
        for rel, patch, expected in cases:
            with self.subTest(expected=expected):
                self.write(rel, {**GOOD[rel], **patch})
                result = self.validate()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stdout)
                self.write(rel, GOOD[rel])

    def test_budget_config_shape_errors(self):
        (self.root / "budget-configs" / "broken.json").write_text("{not json", encoding="utf-8")
        self.write("budget-configs/list.json", {"buckets": "general"})
        out = self.validate().stdout
        self.assertIn("budget-configs/broken.json: invalid JSON", out)
        self.assertIn("budget-configs/list.json: buckets must be a list", out)


if __name__ == "__main__":
    unittest.main()
