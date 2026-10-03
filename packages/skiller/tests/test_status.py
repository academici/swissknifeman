"""Tests status — read-only report and canal hygiene.

Key case: one bucket should not be distributed AT THE SAME TIME by the plugin (connect) and
vendor (vendor) — otherwise the skills are duplicated. Check lives in skiller (owner
skills) and is accessible from the umbrella via `swissknifeman skills status`."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.common import MANIFEST, MARKETPLACE
from skiller.status import (channel_overlap, cmd_status, detect_raw_vendor_path,
                            local_channel_entries, name_duplicates,
                            raw_vendor_overlap_dirs, registry_skill_names,
                            remove_raw_vendor_entries)
import tests.fixtures as fx


def run(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a, **kw)
    return buf.getvalue()


class TestChannelOverlapUnit(unittest.TestCase):
    def test_overlap_pure(self):
        self.assertEqual(
            channel_overlap(["php", "quality"], {"php", "devops"}), ["php"])
        self.assertEqual(channel_overlap(["php"], set()), [])
        self.assertEqual(channel_overlap([], {"php"}), [])


class TestStatusOverlapReport(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        self.proj = fx.make_laravel_project(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def _enable_plugins(self, buckets):
        """Write connect-artifact: marketplace + enabledPlugins for buckets."""
        d = self.proj / ".claude"
        d.mkdir(parents=True, exist_ok=True)
        (d / "settings.local.json").write_text(json.dumps({
            "extraKnownMarketplaces": {
                MARKETPLACE: {"source": {"source": "directory",
                                         "path": str(self.root)}}},
            "enabledPlugins": {f"{b}@{MARKETPLACE}": True for b in buckets},
        }), encoding="utf-8")

    def _vendor_manifest(self, buckets):
        """Write vendor-manifest with one skill per bucket."""
        d = self.proj / ".claude" / "skills"
        d.mkdir(parents=True, exist_ok=True)
        (d / MANIFEST).write_text(json.dumps({
            "version": 1, "layout": "flat", "agent": "claude", "profile": "",
            "installed_at": "2026-06-25T00:00:00Z",
            "skills": [{"flat_name": f"s-{b}",
                        "source_path": f"skills/{b}/s-{b}"} for b in buckets],
        }), encoding="utf-8")

    def test_warns_when_bucket_in_both_channels(self):
        self._enable_plugins(["php", "quality"])
        self._vendor_manifest(["php"])           # php in both channels
        out = run(cmd_status, self.env, ["--target", str(self.proj)])
        self.assertIn("DOUBLE CHANNELS", out)
        self.assertIn("php", out.split("DOUBLE CHANNELS")[1].splitlines()[0])

    def test_no_warning_when_channels_disjoint(self):
        self._enable_plugins(["quality"])
        self._vendor_manifest(["php"])           # no intersection
        out = run(cmd_status, self.env, ["--target", str(self.proj)])
        self.assertNotIn("DOUBLE CHANNELS", out)

    def test_no_warning_single_channel(self):
        self._vendor_manifest(["php"])           # only vendor
        out = run(cmd_status, self.env, ["--target", str(self.proj)])
        self.assertNotIn("DOUBLE CHANNELS", out)

    def test_json_exposes_dependency_closure_and_provider_measurements(self):
        data = json.loads(run(
            cmd_status, self.env, ["--target", str(self.proj), "--json"]))
        self.assertEqual(data["dependency_closure"], {
            "status": "green", "diagnostics": [],
        })
        rows = data["measurements"]["rows"]
        self.assertEqual({row["provider"] for row in rows},
                         {"claude-code", "codex", "cursor", "grok"})
        for row in rows:
            self.assertEqual(row["surface"], "listing")
            self.assertEqual(len({"model", "model_family"} & set(row)), 1)
            self.assertTrue({
                "value", "unit", "method", "uncertainty", "measurement_class",
                "observed_at", "expires_at", "source_id", "status", "threshold",
            } <= set(row))


class TestDetectRawVendorPath(unittest.TestCase):
    """P3.5 delta a: channel without manifest (repo fact flexcrm — symlinks from
    third-party .ai/skills, without skills-lock.json)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_none_when_no_skills_dir(self):
        self.assertIsNone(detect_raw_vendor_path(self.tmp, {}))

    def test_none_when_skills_dir_empty(self):
        (self.tmp / ".claude" / "skills").mkdir(parents=True)
        self.assertIsNone(detect_raw_vendor_path(self.tmp, {}))

    def test_found_without_manifest(self):
        d = self.tmp / ".claude" / "skills" / "foo"
        d.mkdir(parents=True)
        self.assertEqual(detect_raw_vendor_path(self.tmp, {}), ".claude/skills")

    def test_respects_configured_skills_path(self):
        d = self.tmp / "custom" / "skills" / "foo"
        d.mkdir(parents=True)
        self.assertEqual(
            detect_raw_vendor_path(self.tmp, {"skills_path": "custom/skills"}),
            "custom/skills")


class TestLocalChannelEntries(unittest.TestCase):
    """P3.5 delta in: dead records - broken symlinks And directories without SKILL.md."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.skills_dir = self.tmp / "skills"
        self.skills_dir.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_live_dead_and_empty_dir_classified(self):
        live = self.skills_dir / "live-skill"
        fx.write_skill(live, "live-skill", description="A live one")
        (self.skills_dir / "no-skill-md").mkdir()
        (self.skills_dir / "broken-link").symlink_to(
            self.skills_dir / "nonexistent-target")
        entries = local_channel_entries(self.skills_dir)
        by_dir = {e["dir"]: e for e in entries}
        self.assertEqual(by_dir["live-skill"],
                         {"dir": "live-skill", "dead": False, "name": "live-skill"})
        self.assertTrue(by_dir["no-skill-md"]["dead"])
        self.assertTrue(by_dir["broken-link"]["dead"])

    def test_empty_dir_returns_no_entries(self):
        self.assertEqual(local_channel_entries(self.skills_dir), [])

    def test_missing_dir_returns_no_entries(self):
        self.assertEqual(local_channel_entries(self.skills_dir / "gone"), [])


class TestNameDuplicatesAgainstRegistry(unittest.TestCase):
    """P3.5 delta b: double is counted according to frontmatter `name`, across the ENTIRE registry
    (not only included buckets) — second physical copy of the registry skill."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_duplicate_and_unique_names(self):
        names = registry_skill_names(self.env)
        self.assertIn("code-style", names)
        self.assertEqual(names["code-style"], ["php"])
        local = [
            {"dir": "code-style", "dead": False, "name": "code-style"},
            {"dir": "my-own-thing", "dead": False, "name": "my-own-thing"},
            {"dir": "broken", "dead": True, "name": None},
        ]
        dup = name_duplicates(local, names)
        self.assertEqual(dup, [("code-style", "code-style", ("php",))])

    def test_dead_entries_ignored_by_dup_detector(self):
        names = registry_skill_names(self.env)
        local = [{"dir": "code-style", "dead": True, "name": None}]
        self.assertEqual(name_duplicates(local, names), [])

    def test_maind_managed_skills_excluded_from_duplicates(self):
        names = registry_skill_names(self.env)
        names["ecosystem-mcp"] = ["repository-bootstrap"]
        local = [{"dir": "ecosystem-mcp", "dead": False, "name": "ecosystem-mcp"}]
        self.assertEqual(name_duplicates(local, names), [])

    def test_raw_vendor_overlap_dirs_respects_enabled_buckets(self):
        names = {"code-style": ["php"], "my-own-thing": ["quality"]}
        local = [
            {"dir": "code-style", "dead": False, "name": "code-style"},
            {"dir": "my-own-thing", "dead": False, "name": "my-own-thing"},
        ]
        self.assertEqual(raw_vendor_overlap_dirs(local, names, {"php"}), ["code-style"])
        self.assertEqual(raw_vendor_overlap_dirs(local, names, {"quality"}), ["my-own-thing"])
        self.assertEqual(raw_vendor_overlap_dirs(local, names, set()), [])

    def test_remove_raw_vendor_entries_unlinks_symlink(self):
        skills_dir = self.tmp / "skills"
        skills_dir.mkdir()
        link = skills_dir / "code-style"
        target = self.tmp / "source"
        target.mkdir()
        link.symlink_to(target, target_is_directory=True)
        removed = remove_raw_vendor_entries(skills_dir, ["code-style"])
        self.assertEqual(removed, ["code-style"])
        self.assertFalse(link.exists())


class TestStatusRawVendorReport(unittest.TestCase):
    """Integration run cmd_status on a channel without a manifest - the same class,
    what flexcrm (Code Guidance item'a requires running on a living tree; here -
    reproducible equivalent in tmpdir)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        self.proj = fx.make_laravel_project(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_reports_duplicates_and_dead_entries(self):
        skills_dir = self.proj / ".claude" / "skills"
        # double name with registry php/code-style
        fx.write_skill(skills_dir / "code-style", "code-style")
        # unique local skill - not a duplicate
        fx.write_skill(skills_dir / "my-own-thing", "my-own-thing")
        # broken symlink
        (skills_dir / "broken").symlink_to(skills_dir / "nowhere")
        out = run(cmd_status, self.env, ["--target", str(self.proj)])
        self.assertIn("WITHOUT manifest", out)
        self.assertIn("DUPLICATE NAMES", out)
        self.assertIn("code-style", out)
        self.assertIn("DEAD POSTS", out)
        self.assertIn("broken", out)
        js = json.loads(run(cmd_status, self.env,
                            ["--target", str(self.proj), "--json"]))
        self.assertEqual(js["dead_entries"], ["broken"])
        self.assertEqual([d["dir"] for d in js["name_duplicates"]], ["code-style"])

    def test_maind_managed_not_reported_as_duplicate(self):
        skills_dir = self.proj / ".claude" / "skills"
        fx.write_skill(skills_dir / "ecosystem-mcp", "ecosystem-mcp")
        js = json.loads(run(cmd_status, self.env,
                            ["--target", str(self.proj), "--json"]))
        self.assertEqual(js["name_duplicates"], [])

    def test_silent_when_no_local_skills_dir(self):
        out = run(cmd_status, self.env, ["--target", str(self.proj)])
        self.assertNotIn("DUPLICATE NAMES", out)
        self.assertNotIn("DEAD POSTS", out)
        self.assertNotIn("Channel vendor", out)


if __name__ == "__main__":
    unittest.main()
