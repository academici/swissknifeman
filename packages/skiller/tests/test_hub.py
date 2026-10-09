"""Hub generator tests (`lib/skiller/hub.py`, launcher `scripts/generate-hub.sh`).

Before P2.5 generator lived in heredoc'e bash-had no script or tests at all. Here
block form contract is checked (D20): short form for a channel with a native listing,
full - to a channel without it, return flag, reconciliation before reduction, idempotency,
safety of contents OUTSIDE markers and freshness-stamp.
"""
import io
import json
import unittest
from unittest import mock
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from skiller import hub
from skiller.common import Env

INDEX_TITLE = "## Installed skills"
RESIDUAL_TITLE = "## Skills outside the native listing"


def _skill_md(name, description):
    return f"---\nname: {name}\nversion: 0.1.0\ndescription: {description}\n---\n\nBody.\n"


def make_monorepo(tmp):
    """Mini monorepo: <mono>/core, <mono>/vendor/skiller (roster of 3 skills),
    <mono>/.claude-plugin/marketplace.json with curated and bucket plugin."""
    mono = Path(tmp) / "mono"
    (mono / "core").mkdir(parents=True)
    (mono / ".git").mkdir()
    root = mono / "vendor" / "skiller"
    skills = root / "skills"
    entries = [("php", "code-style", "PHP code style"),
               ("php", "laravel-conventions", "Laravel conventions"),
               ("quality", "test-writer", "Test writer")]
    for bucket, name, desc in entries:
        d = skills / bucket / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(_skill_md(name, desc), encoding="utf-8")
    (root / "skills.json").write_text(json.dumps({"skills": [
        {"name": name, "bucket": bucket, "path": f"skills/{bucket}/{name}/SKILL.md",
         "version": "0.1.0", "description": desc}
        for bucket, name, desc in entries]}), encoding="utf-8")
    (root / "buckets.json").write_text(json.dumps({
        "php": {"description": "PHP"}, "quality": {"description": "Quality"}}),
        encoding="utf-8")
    (mono / ".claude-plugin").mkdir()
    (mono / ".claude-plugin" / "marketplace.json").write_text(json.dumps({
        "name": "swissknifeman", "plugins": [
            {"name": "php", "source": "./vendor/skiller/skills/php"},
            {"name": "quality", "source": "./vendor/skiller/skills/quality"},
            {"name": "curated", "source": "./",
             "skills": ["./vendor/skiller/skills/php/code-style"]},
        ]}), encoding="utf-8")
    home = mono / "home"
    home.mkdir()
    hub._REGISTRY_CACHE.pop(str(root), None)
    return Env(root, "generate-hub", home=home)


def make_project(tmp, *, plugins=("php", "quality"), claude_md=None, boost=False,
                 config=None):
    proj = Path(tmp) / "project"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "settings.local.json").write_text(json.dumps(
        {"enabledPlugins": {f"{p}@swissknifeman": True for p in plugins}}),
        encoding="utf-8")
    if claude_md is not None:
        (proj / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
    if boost:
        (proj / "boost.json").write_text("{}\n", encoding="utf-8")
    if config is not None:
        (proj / ".swissknife.json").write_text(json.dumps(config), encoding="utf-8")
    return proj


def run_hub(env, proj, **kw):
    buf = io.StringIO()
    inventory = kw.pop("codex_inventory", {"ok": False, "names": set(), "notes": []})
    with redirect_stdout(buf), mock.patch("aicore.delivery.codex.native_inventory", return_value=inventory), \
            mock.patch("aicore.delivery.codex.codex_home", return_value=env.home / ".codex"):
        result = hub.run(env, proj, **kw)
    result["stdout"] = buf.getvalue()
    return result


class HubFormTests(unittest.TestCase):
    """Block shape is determined by the target channel, not the project (D20)."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = make_monorepo(self.tmp.name)

    def test_claude_md_gets_stub_form_by_default(self):
        proj = make_project(self.tmp.name, config={"buckets": ["php", "quality"]})
        result = run_hub(self.env, proj)
        text = (proj / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertEqual(result["forms"]["CLAUDE.md"], hub.FORM_STUB)
        self.assertNotIn(INDEX_TITLE, text)
        self.assertNotIn("- **code-style**", text)
        self.assertNotIn("NATIVE listing", text)
        self.assertIn("hub: stub", text)
        self.assertIn("--full-index", text)

    def test_claude_md_legacy_short_restores_priority_prose(self):
        proj = make_project(self.tmp.name, config={"buckets": ["php", "quality"]})
        result = run_hub(self.env, proj, legacy_short=True)
        text = (proj / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertEqual(result["forms"]["CLAUDE.md"], hub.FORM_SHORT)
        self.assertIn("NATIVE listing", text)

    def test_generator_wrapper_forwards_requested_root_files(self):
        proj = make_project(self.tmp.name)
        with mock.patch("skiller.hub.run_cmd") as run:
            hub.generate_hub(self.env, proj, root_files=("AGENTS.md",), full_index=True)
        run.assert_called_once_with([str(self.env.root / "scripts/generate-hub.sh"),
                                     "--target", str(proj), "--full-index", "--root-files", "AGENTS.md"])

    def test_codex_uses_native_discovery_while_gemini_keeps_full_index(self):
        proj = make_project(self.tmp.name, config={"buckets": ["php", "quality"]})
        result = run_hub(self.env, proj, root_files=["AGENTS.md", "GEMINI.md"],
                         codex_inventory={"ok": True, "names": {"code-style"},
                                          "enabled": ["php", "quality"], "notes": []})
        self.assertEqual(result["forms"]["AGENTS.md"], hub.FORM_STUB)
        self.assertEqual(result["forms"]["GEMINI.md"], hub.FORM_FULL)
        agents_md = (proj / "AGENTS.md").read_text(encoding="utf-8")
        claude_md = (proj / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertNotIn(INDEX_TITLE, agents_md)
        self.assertNotIn("- **code-style**", agents_md)
        self.assertNotIn("- **test-writer**", agents_md)
        self.assertIn(INDEX_TITLE, (proj / "GEMINI.md").read_text())
        self.assertNotIn(INDEX_TITLE, claude_md)

    def test_codex_failure_keeps_every_unconfirmed_skill_with_legacy_short(self):
        proj = make_project(self.tmp.name, config={"buckets": ["php", "quality"]})
        run_hub(self.env, proj, root_files=["AGENTS.md"], legacy_short=True)
        text = (proj / "AGENTS.md").read_text()
        for name in ("code-style", "laravel-conventions", "test-writer"):
            self.assertIn("- **" + name + "**", text)

    def test_codex_does_not_repeat_disabled_claude_only_plugin_skills(self):
        proj = make_project(self.tmp.name, config={"buckets": ["php", "quality"]})
        run_hub(self.env, proj, root_files=["AGENTS.md", "GEMINI.md"], legacy_short=True,
                codex_inventory={"ok": True, "names": {"code-style", "laravel-conventions"},
                                 "enabled": ["php"], "notes": []})
        agents = (proj / "AGENTS.md").read_text()
        self.assertNotIn("- **test-writer**", agents)
        self.assertNotIn(RESIDUAL_TITLE, agents)
        self.assertIn("- **test-writer**", (proj / "GEMINI.md").read_text())

    def test_codex_retains_explicit_selected_plugin_without_native_cache(self):
        proj = make_project(self.tmp.name, plugins=["php"], config={"buckets": ["php"]})
        (proj / ".codex").mkdir()
        (proj / ".codex/config.toml").write_text('[plugins."quality@swissknifeman"]\nenabled = true\n')
        run_hub(self.env, proj, root_files=["AGENTS.md"], legacy_short=True,
                codex_inventory={"ok": True, "names": {"code-style", "laravel-conventions"},
                                 "enabled": ["php"], "notes": []})
        self.assertIn("- **test-writer**", (proj / "AGENTS.md").read_text())

    def test_codex_curated_selection_does_not_expand_entire_donor_bucket(self):
        proj = make_project(self.tmp.name, config={"buckets": ["php", "quality"]})
        run_hub(self.env, proj, root_files=["AGENTS.md"], legacy_short=True,
                codex_inventory={"ok": True, "names": set(), "enabled": ["curated"], "notes": []})
        text = (proj / "AGENTS.md").read_text()
        self.assertIn("- **code-style**", text)
        self.assertNotIn("- **laravel-conventions**", text)
        self.assertNotIn("- **test-writer**", text)

    def test_codex_retains_manifest_declared_local_skill_when_plugin_is_disabled(self):
        proj = make_project(self.tmp.name, plugins=["php"], config={"buckets": ["php"]})
        folder = proj / ".ai/skills"
        folder.mkdir(parents=True)
        (folder / hub.MANIFEST).write_text(json.dumps({"skills": [
            {"source_path": "skills/quality/test-writer"}]}))
        run_hub(self.env, proj, root_files=["AGENTS.md"], legacy_short=True,
                codex_inventory={"ok": True, "names": {"code-style", "laravel-conventions"},
                                 "enabled": ["php"], "notes": []})
        self.assertIn("- **test-writer**", (proj / "AGENTS.md").read_text())

    def test_full_index_bypasses_native_codex_discovery(self):
        proj = make_project(self.tmp.name, config={"buckets": ["php", "quality"]})
        with mock.patch("aicore.delivery.codex.native_inventory", side_effect=AssertionError("native probe")):
            result = hub.run(self.env, proj, root_files=["AGENTS.md"], full_index=True)
        self.assertEqual(result["forms"]["AGENTS.md"], hub.FORM_FULL)

    def test_full_index_flag_returns_index_to_claude_md(self):
        proj = make_project(self.tmp.name, config={"buckets": ["php", "quality"]})
        result = run_hub(self.env, proj, full_index=True)
        self.assertEqual(result["forms"]["CLAUDE.md"], hub.FORM_FULL)
        text = (proj / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(INDEX_TITLE, text)
        self.assertIn("- **test-writer** — Test writer", text)

    def test_boost_target_is_claude_channel(self):
        """Boost inserts a fragment into CLAUDE.md — residency is the same, the form is short."""
        proj = make_project(self.tmp.name, boost=True,
                            config={"buckets": ["php", "quality"]})
        result = run_hub(self.env, proj)
        out = proj / ".ai" / "guidelines" / "swissknifeman-hub.md"
        self.assertTrue(out.is_file())
        self.assertEqual(list(result["forms"].values()), [hub.FORM_STUB])
        self.assertNotIn(INDEX_TITLE, out.read_text(encoding="utf-8"))

    def test_stamp_present_in_both_forms(self):
        """freshness-stamp checks skiller doctor — it must be in both forms."""
        proj = make_project(self.tmp.name, config={"buckets": ["php", "quality"]})
        run_hub(self.env, proj, root_files=["AGENTS.md"])
        for name in ("CLAUDE.md", "AGENTS.md"):
            text = (proj / name).read_text(encoding="utf-8")
            self.assertIn("<!-- swissknifeman:registry sha=", text)
            self.assertIn("skills=3 -->", text)


class HubNativeCheckTests(unittest.TestCase):
    """Reconciliation before reduction: without confirmation, the skill remains listed."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = make_monorepo(self.tmp.name)

    def test_unconfirmed_skill_stays_listed(self):
        """Bucket quality is not included by the plugin, but came with the vendor manifest in
        .ai/skills — native listing Claude Code it is not covered, which means it remains."""
        proj = make_project(self.tmp.name, plugins=["php"],
                            config={"buckets": ["php", "quality"]})
        manifest_dir = proj / ".ai" / "skills"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / ".swissknifeman-manifest.json").write_text(json.dumps(
            {"skills": [{"source_path": "skills/quality/test-writer"}]}),
            encoding="utf-8")
        result = run_hub(self.env, proj, legacy_short=True)
        self.assertEqual(result["check"]["unconfirmed"], ["test-writer"])
        text = (proj / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(RESIDUAL_TITLE, text)
        self.assertIn("- **test-writer**", text)
        self.assertNotIn("- **code-style**", text)  # confirmed - left the block

    def test_confirmed_set_is_intersection_with_measurer(self):
        """A skill that is not in the meter set is not reduced, even if
        delivered by plugin (conjunction of two sources)."""
        proj = make_project(self.tmp.name, plugins=["php", "quality"],
                            config={"buckets": ["php"]})
        result = run_hub(self.env, proj, legacy_short=True)
        self.assertNotIn("test-writer", result["check"]["confirmed"])
        self.assertIn("test-writer", result["check"]["unconfirmed"])
        self.assertIn("code-style", result["check"]["confirmed"])

    def test_no_delivery_channel_is_an_error(self):
        proj = Path(self.tmp.name) / "bare"
        (proj / ".claude").mkdir(parents=True)
        with self.assertRaises(SystemExit):
            run_hub(self.env, proj)


class HubWriteTests(unittest.TestCase):
    """Write: only between markers, idempotent, file created if missing."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = make_monorepo(self.tmp.name)

    def test_content_outside_markers_is_preserved(self):
        head = "# Project\n\nAuthor's text.\n\n"
        tail = "\n## Below the block\n\nMore original text.\n"
        existing = (head + hub.HUB_START + "\nold block\n" + hub.HUB_END + tail)
        proj = make_project(self.tmp.name, claude_md=existing,
                            config={"buckets": ["php", "quality"]})
        run_hub(self.env, proj)
        text = (proj / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith(head))
        self.assertTrue(text.endswith(tail))
        self.assertNotIn("old block", text)

    def test_repeat_run_is_idempotent(self):
        proj = make_project(self.tmp.name, claude_md="# Project\n\nText.\n",
                            config={"buckets": ["php", "quality"]})
        run_hub(self.env, proj, root_files=["AGENTS.md"])
        first = {n: (proj / n).read_text(encoding="utf-8")
                 for n in ("CLAUDE.md", "AGENTS.md")}
        run_hub(self.env, proj, root_files=["AGENTS.md"])
        second = {n: (proj / n).read_text(encoding="utf-8")
                  for n in ("CLAUDE.md", "AGENTS.md")}
        self.assertEqual(first, second)

    def test_missing_claude_md_is_created(self):
        proj = make_project(self.tmp.name, config={"buckets": ["php", "quality"]})
        self.assertFalse((proj / "CLAUDE.md").exists())
        run_hub(self.env, proj)
        text = (proj / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith(hub.HUB_START))
        self.assertIn(hub.HUB_END, text)

    def test_dry_run_writes_nothing(self):
        proj = make_project(self.tmp.name, config={"buckets": ["php", "quality"]})
        result = run_hub(self.env, proj, dry_run=True)
        self.assertFalse((proj / "CLAUDE.md").exists())
        self.assertIn("[dry-run]", result["stdout"])


if __name__ == "__main__":
    unittest.main()
