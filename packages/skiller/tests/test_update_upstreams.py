"""P7.3 (thin-navigator): scripts/update-upstreams.sh with body_path — end-to-end,
without network.

scripts/update-upstreams.sh — bash-wrap around python-heredoc'a (not a module
lib/skiller/), so the only fair way to test it is to actually
run (as already doing test_registry_state.py::test_broken_upstream_json_dies_
with_path for another script). REPO_ROOT script resolves from its own
locations (dirname(BASH_SOURCE)/..), so we copy the script itself next to
synthetic skills/ in tmp — real packages/skiller cannot be touched or read
to write. No network needed: source="file" + url=Path.as_uri() (file://) — exactly for
this in schema/upstream.schema.json "source" contains file ("local only
fixtures/tests"), and urllib.request supports file:// out of the box."""
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
UPDATE_SCRIPT = PKG_ROOT / "scripts" / "update-upstreams.sh"


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class UpdateUpstreamsBodyPathCase(unittest.TestCase):
    """Synthetic external-skill: SKILL.md — thin navigator (not tracked
    like upstream-mirror), upstream body - references/full.md, monitored software
    body_path (files[]-entry with the same path)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root = self.tmp / "registry"
        self.skill_dir = self.root / "skills" / "external" / "thin-monolith"
        self.skill_dir.mkdir(parents=True)
        (self.skill_dir / "SKILL.md").write_text(
            "---\nname: thin-monolith\n"
            "description: Navigator only, body lives in references/full.md.\n"
            "---\n\nSee references/full.md for the full content.\n",
            encoding="utf-8")
        refs = self.skill_dir / "references"
        refs.mkdir()
        self.body_text = "Full upstream body.\nSection two.\n"
        self.body_file = refs / "full.md"
        self.body_file.write_text(self.body_text, encoding="utf-8")
        self._write_upstream_json(url=self.body_file.as_uri(),
                                  sha256=_sha256(self.body_text))
        scripts_dir = self.root / "scripts"
        scripts_dir.mkdir()
        shutil.copy2(UPDATE_SCRIPT, scripts_dir / "update-upstreams.sh")

    def tearDown(self):
        self._tmp.cleanup()

    def _write_upstream_json(self, **file_overrides):
        entry = {"path": "references/full.md", "url": "file:///unused",
                 "sha256": "unused", "fetched_at": "2026-07-01", **file_overrides}
        data = {"schema_version": 1, "source": "file", "strategy": "notify",
                "body_path": "references/full.md", "files": [entry],
                # P5.11: bundle with the verdict read - otherwise --check would add to
                # subject of these cases (body_path) also a find AUDIT_MISSING.
                # Anchor at a given body_path — sha EXACTLY named body.
                "audit": {"verdict": "clean", "at": "2026-08-01",
                          "by": "test P0.0", "upstream_sha": entry["sha256"]}}
        (self.skill_dir / "upstream.json").write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def _run(self, *args):
        return subprocess.run(
            ["bash", str(self.root / "scripts" / "update-upstreams.sh"), *args],
            capture_output=True, text=True, timeout=30)

    def test_check_in_sync_tracks_body_path_not_skill_md(self):
        # sha already matches upstream → --check green; reconciliation is in progress
        # references/full.md — files[] does not contain an entry SKILL.md at all (navigator
        # is not tracked as upstream-mirror).
        result = self._run("--check", "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["checked"], 1)
        self.assertEqual(data["failures"], [])
        self.assertEqual(data["notify"], [])
        self.assertEqual(data["updates"], [])

    def test_check_reports_drift_via_body_path_file(self):
        # Upstream has gone ahead (new sha) → --check sees drift EXACTLY at
        # references/full.md (file from body_path), not at SKILL.md.
        self.body_file.write_text(self.body_text + "New section.\n", encoding="utf-8")
        result = self._run("--check", "--json")
        self.assertEqual(result.returncode, 10, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(len(data["notify"]), 1)
        self.assertEqual(data["notify"][0]["file"], "references/full.md")

    def test_check_rejects_body_path_not_tracked_in_files(self):
        # Structure gate (P7.3): body_path, not tracked by ANY files[]-
        # entry, - malformed upstream.json, and not a silent tracking hole.
        cfg = self.skill_dir / "upstream.json"
        data = json.loads(cfg.read_text(encoding="utf-8"))
        data["body_path"] = "references/missing.md"
        cfg.write_text(json.dumps(data), encoding="utf-8")
        result = self._run("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("body_path", result.stderr)
        self.assertIn("not in files[].path", result.stderr)


if __name__ == "__main__":
    unittest.main()
