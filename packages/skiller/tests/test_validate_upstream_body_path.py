"""P7.3 (thin-navigator): scripts/validate.sh body_path-gates - isolated, without
touching the present packages/skiller.

scripts/validate.sh — bash-wrap around python-heredoc'a (same reason as
test_update_upstreams.py: not lib/skiller-module, honestly tested only by real
launch). REPO_ROOT resolves from the location of the script, so copy
validate.sh next to MINIMUM synthetic skills/. Such a root is intentionally NOT
contains buckets.json/skills.json/marketplace.json etc. - sections validate.sh,
who need them, in their absence they gently hoard ERROR (do not fall exception), a
python-heredoc does almost immediately sys.exit(1) due to non-empty errors[] — bash-sections
11+ (registry --check, full test.sh, budget --check-core) to real
packages/skiller are NOT received at all (and therefore cannot recursively restart
the same test suite). Checking for non-general exit-code (it is expectedly non-zero due to
missing registry environment), and SPECIFIC lines about body_path in stdout."""
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
VALIDATE_SCRIPT = PKG_ROOT / "scripts" / "validate.sh"


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ValidateBodyPathCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "registry"
        self.skill_dir = self.root / "skills" / "external" / "thin-monolith"
        self.skill_dir.mkdir(parents=True)
        (self.skill_dir / "SKILL.md").write_text(
            "---\nname: thin-monolith\n"
            "description: Navigator only, body lives in references/full.md.\n"
            "---\n\nSee references/full.md for the full content.\n",
            encoding="utf-8")
        refs = self.skill_dir / "references"
        refs.mkdir()
        self.body_text = "Full upstream body.\n"
        (refs / "full.md").write_text(self.body_text, encoding="utf-8")
        scripts_dir = self.root / "scripts"
        scripts_dir.mkdir()
        shutil.copy2(VALIDATE_SCRIPT, scripts_dir / "validate.sh")

    def tearDown(self):
        self._tmp.cleanup()

    def _write_upstream(self, **overrides):
        data = {
            "schema_version": 1, "source": "file", "strategy": "notify",
            "body_path": "references/full.md",
            "files": [{"path": "references/full.md", "url": "file:///unused",
                      "sha256": _sha256(self.body_text), "fetched_at": "2026-07-01"}],
        }
        data.update(overrides)
        (self.skill_dir / "upstream.json").write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def _run(self):
        return subprocess.run(
            ["bash", str(self.root / "scripts" / "validate.sh")],
            capture_output=True, text=True, timeout=60)

    def test_valid_body_path_no_related_errors(self):
        self._write_upstream()
        result = self._run()
        out = result.stdout
        self.assertNotIn("Traceback", out + result.stderr)
        self.assertNotIn("body_path", out,
                         "well-formed body_path must not raise any body_path error")

    def test_body_path_not_tracked_in_files(self):
        self._write_upstream(body_path="references/missing.md")
        result = self._run()
        self.assertIn(
            "body_path 'references/missing.md' is not tracked in files[]",
            result.stdout)

    def test_body_path_escaping_skill_dir(self):
        self._write_upstream(body_path="../../etc/passwd")
        result = self._run()
        self.assertIn("body_path escapes skill dir", result.stdout)

    def test_replace_strategy_with_skill_md_still_tracked_is_rejected(self):
        # Otherwise update-upstreams.sh --apply would silently overwrite the navigator.
        self._write_upstream(strategy="replace", files=[
            {"path": "references/full.md", "url": "file:///unused",
             "sha256": _sha256(self.body_text), "fetched_at": "2026-07-01"},
            {"path": "SKILL.md", "url": "file:///unused2",
             "sha256": "deadbeef", "fetched_at": "2026-07-01"},
        ])
        result = self._run()
        self.assertIn(
            "body_path set (thin-navigator) but files[] also tracks SKILL.md "
            "under strategy=replace", result.stdout)


if __name__ == "__main__":
    unittest.main()
