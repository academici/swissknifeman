"""aicore.delivery.claude: marketplace settings merge, dry-run redaction, plugin listing."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aicore.delivery import MARKETPLACE, claude
from aicore.delivery.claude import (MarketplaceEnableResult, enable_marketplace_plugins,
                                    redacted_settings_preview)

SOURCE = {"source": "directory", "path": "/repo"}


def enable(settings, plugins=("core",), *, root="/repo", fix=False):
    return enable_marketplace_plugins(settings, marketplace=MARKETPLACE, marketplace_root=root,
                                      plugins=list(plugins), fix_path_drift=fix)


class EnableMarketplacePluginsCase(unittest.TestCase):
    def test_new_marketplace_and_plugins_are_written(self):
        settings = {}
        result = enable(settings, ["core", "php"])
        self.assertIsInstance(result, MarketplaceEnableResult)
        self.assertEqual(settings["extraKnownMarketplaces"], {"swissknifeman": {"source": SOURCE}})
        self.assertEqual(settings["enabledPlugins"],
                         {"core@swissknifeman": True, "php@swissknifeman": True})
        self.assertEqual((result.added, result.skipped_false, result.drift, result.notes),
                         (("core", "php"), (), (), ()))

    def test_marketplace_name_is_a_parameter(self):
        settings = {}
        enable_marketplace_plugins(settings, marketplace="other", marketplace_root="/r",
                                   plugins=["x"], fix_path_drift=False)
        self.assertEqual(list(settings["extraKnownMarketplaces"]), ["other"])
        self.assertEqual(settings["enabledPlugins"], {"x@other": True})

    def test_same_source_is_left_alone_without_notes(self):
        settings = {"extraKnownMarketplaces": {"swissknifeman": {"source": dict(SOURCE)}}}
        result = enable(settings)
        self.assertEqual(result.notes, ())
        self.assertEqual(settings["extraKnownMarketplaces"]["swissknifeman"], {"source": SOURCE})

    def test_other_directory_is_reported_and_kept_without_fix(self):
        old = {"source": "directory", "path": "/old"}
        settings = {"extraKnownMarketplaces": {"swissknifeman": {"source": dict(old)}}}
        result = enable(settings)
        self.assertEqual(settings["extraKnownMarketplaces"]["swissknifeman"], {"source": old})
        self.assertEqual(len(result.notes), 1)
        self.assertTrue(result.notes[0].startswith("⚠ marketplace 'swissknifeman' points to ANOTHER directory: /old"))
        self.assertIn("registry is now here: /repo", result.notes[0])
        self.assertIn("skiller connect --fix-path", result.notes[0])

    def test_other_directory_is_updated_with_fix_path_drift(self):
        settings = {"extraKnownMarketplaces": {"swissknifeman": {"source": {"source": "directory", "path": "/old"}}}}
        result = enable(settings, fix=True)
        self.assertEqual(settings["extraKnownMarketplaces"]["swissknifeman"], {"source": SOURCE})
        self.assertEqual(result.notes, ("NOTE: path marketplace is deprecated (/old) — updating to /repo",))

    def test_non_directory_source_is_never_touched(self):
        github = {"source": "github", "repo": "owner/repo"}
        for fix in (False, True):
            with self.subTest(fix=fix):
                settings = {"extraKnownMarketplaces": {"swissknifeman": {"source": dict(github)}}}
                result = enable(settings, fix=fix)
                self.assertEqual(settings["extraKnownMarketplaces"]["swissknifeman"], {"source": github})
                self.assertEqual(result.notes, (
                    "NOTE: marketplace 'swissknifeman' declared with a different origin "
                    f"({json.dumps(github)}) — I leave it as is.",))

    def test_explicit_false_is_not_overwritten(self):
        settings = {"enabledPlugins": {"php@swissknifeman": False, "core@swissknifeman": True}}
        result = enable(settings, ["core", "php", "quality"])
        self.assertEqual(settings["enabledPlugins"], {
            "php@swissknifeman": False, "core@swissknifeman": True, "quality@swissknifeman": True})
        self.assertEqual((result.added, result.skipped_false), (("quality",), ("php",)))

    def test_drift_lists_enabled_keys_of_this_marketplace_outside_the_set(self):
        settings = {"enabledPlugins": {
            "old@swissknifeman": True, "off@swissknifeman": False,
            "foreign@elsewhere": True, "core@swissknifeman": True}}
        result = enable(settings, ["core"])
        self.assertEqual(result.drift, ("old@swissknifeman",))
        self.assertEqual(settings["enabledPlugins"]["old@swissknifeman"], True)

    def test_other_settings_keys_survive_and_the_function_does_not_print(self):
        settings = {"env": {"A": "1"}, "permissions": {"allow": ["x"]}}
        with mock.patch("builtins.print") as printed:
            enable(settings)
        printed.assert_not_called()
        self.assertEqual(settings["env"], {"A": "1"})
        self.assertEqual(settings["permissions"], {"allow": ["x"]})

    def test_path_object_root_is_accepted(self):
        settings = {}
        enable(settings, root=Path("/repo"))
        self.assertEqual(settings["extraKnownMarketplaces"]["swissknifeman"], {"source": SOURCE})


class RedactedSettingsPreviewCase(unittest.TestCase):
    def test_env_values_and_secret_like_keys_are_hidden(self):
        settings = {
            "env": {"ANYTHING": "visible?", "nested": {"x": 1}},
            "apiKeyHelper": "helper",
            "hooks": [{"command": "run", "authorization": "Bearer abc"}],
            "enabledPlugins": {"core@swissknifeman": True},
            "model": "m",
        }
        preview = redacted_settings_preview(settings)
        self.assertEqual(preview["env"], {"ANYTHING": "[REDACTED]", "nested": {"x": "[REDACTED]"}})
        self.assertEqual(preview["apiKeyHelper"], "[REDACTED]")
        self.assertEqual(preview["hooks"], [{"command": "run", "authorization": "[REDACTED]"}])
        self.assertEqual(preview["enabledPlugins"], {"core@swissknifeman": True})
        self.assertEqual(preview["model"], "m")

    def test_original_is_not_modified(self):
        settings = {"env": {"TOKEN": "t"}}
        redacted_settings_preview(settings)
        self.assertEqual(settings, {"env": {"TOKEN": "t"}})


class PluginListingCase(unittest.TestCase):
    def setUp(self):
        claude._details_cache.clear()
        self.addCleanup(claude._details_cache.clear)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cwd = Path(tmp.name)

    def test_run_claude_reports_a_missing_binary(self):
        with mock.patch.object(claude, "claude_bin", return_value=None) as lookup:
            ok, out, detail = claude.run_claude(["plugin", "list"])
        lookup.assert_called_once_with()
        self.assertEqual((ok, out), (False, None))
        self.assertIn(claude.CLAUDE_BIN_ENV, detail)

    def test_run_claude_reports_a_failing_exit_code(self):
        failed = subprocess.CompletedProcess([], 3, "", "boom")
        with mock.patch.object(claude, "claude_bin", return_value="claude"), \
                mock.patch.object(claude.subprocess, "run", return_value=failed) as run:
            ok, out, detail = claude.run_claude(["plugin", "list"], cwd="/x")
        self.assertEqual(run.call_args.args[0], ["claude", "plugin", "list"])
        self.assertEqual(run.call_args.kwargs["cwd"], "/x")
        self.assertEqual((ok, out), (False, None))
        self.assertIn("code 3", detail)

    def test_enabled_plugins_are_deduplicated_by_id(self):
        listing = json.dumps([
            {"id": "a@m", "enabled": True, "scope": "user"},
            {"id": "a@m", "enabled": True, "scope": "project"},
            {"id": "b@m", "enabled": False},
            {"enabled": True},
        ])
        with mock.patch.object(claude, "run_claude", return_value=(True, listing, None)) as run:
            entries, status, detail = claude.list_enabled_plugins(self.cwd)
        self.assertEqual(run.call_args.kwargs["cwd"], str(self.cwd))
        self.assertEqual(status, "ok")
        self.assertEqual([entry["id"] for entry in entries], ["a@m"])
        self.assertEqual(entries[0]["scope"], "user")
        self.assertEqual(detail, [])

    def test_invalid_listing_is_na_not_empty(self):
        with mock.patch.object(claude, "run_claude", return_value=(True, "not json", None)):
            entries, status, detail = claude.list_enabled_plugins(self.cwd)
        self.assertEqual((entries, status), ([], "n/a"))
        self.assertTrue(detail)

    def test_always_on_price_is_parsed_and_cached_only_on_success(self):
        details = "Projected token cost\n  Always-on:   ~1,275 tok   added to every session\n"
        with mock.patch.object(claude, "run_claude", return_value=(True, details, None)) as run:
            first = claude.plugin_always_on_tokens("a@m", self.cwd)
            second = claude.plugin_always_on_tokens("a@m", self.cwd)
        self.assertEqual((first, second), ((1275, None), (1275, None)))
        self.assertEqual(run.call_count, 1)
        claude._details_cache.clear()
        with mock.patch.object(claude, "run_claude", return_value=(True, "no price here", None)):
            tokens, error = claude.plugin_always_on_tokens("a@m", self.cwd)
        self.assertIsNone(tokens)
        self.assertIn("not recognized", error)
        self.assertNotIn("a@m", claude._details_cache)

    def test_summary_totals_recognised_prices_and_marks_the_rest_partial(self):
        listing = json.dumps([{"id": "a@m", "enabled": True, "scope": "user"},
                              {"id": "b@m", "enabled": True, "scope": "user"}])

        def fake(argv, *, cwd=None, timeout=claude.PLUGIN_CALL_TIMEOUT):
            if argv[:2] == ["plugin", "list"]:
                return True, listing, None
            if argv[2] == "a@m":
                return True, "Always-on: ~100 tok\n", None
            return False, None, "claude plugin details b@m — code 1"

        with mock.patch.object(claude, "run_claude", side_effect=fake):
            summary = claude.plugins_summary(self.cwd)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["total"], 100)
        self.assertTrue(summary["partial"])
        self.assertEqual([e["tokens"] for e in summary["entries"]], [100, None])
        self.assertEqual(len(summary["unparsed"]), 1)
