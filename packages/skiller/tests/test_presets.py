"""Resolve presets in connect-channel (.swissknife.json) — task #3.

presets[] in .swissknife.json no longer no-op: resolve_selection expands them to
buckets via skillset.resolve_presets (single extends/cycle-detection, without take) by
formula buckets = (resolve_presets(presets) ∪ buckets) − exclude — symmetrical vendor
sync (resolve_skillset), but at the bucket level (channels .swissknife.json bucket-granular).

Synthetic registry (fixtures.make_registry) carries buckets php/quality/devops."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from skiller.config import resolve_selection, validate_config

import tests.fixtures as fx


def _write_preset(root, name, **body):
    """Put presets/<name>.json to the synthetic registry."""
    d = root / "presets"
    d.mkdir(parents=True, exist_ok=True)
    obj = {"name": name, "description": f"test preset {name}", **body}
    (d / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False),
                                    encoding="utf-8")


class TestConnectPresetResolution(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        self.proj = fx.make_laravel_project(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def _resolve(self, config):
        # presets can warn' (skill-only preset) — muted stderr in tests.
        with contextlib.redirect_stderr(io.StringIO()):
            return resolve_selection(self.env, self.proj, config, "", [])

    def test_preset_buckets_expand(self):
        _write_preset(self.root, "p-web", buckets=["php", "quality"])
        items, _name, src, _label, _meta = self._resolve({"presets": ["p-web"]})
        self.assertEqual(set(items), {"php", "quality"})
        self.assertEqual(src, "config")

    def test_preset_union_with_explicit_buckets(self):
        # (presets ∪ buckets): p-web gives php, config adds devops
        _write_preset(self.root, "p-web", buckets=["php"])
        items, _n, _s, label, _m = self._resolve(
            {"presets": ["p-web"], "buckets": ["devops"]})
        self.assertEqual(set(items), {"php", "devops"})
        self.assertIn("presets", label)  # source marks presets+buckets

    def test_exclude_subtracts_bucket(self):
        # − exclude: preset gives php+quality, exclude subtracts quality (by bucket name)
        _write_preset(self.root, "p-web", buckets=["php", "quality"])
        items, *_ = self._resolve(
            {"presets": ["p-web"], "exclude": ["quality"]})
        self.assertEqual(set(items), {"php"})

    def test_extends_recursive_buckets(self):
        _write_preset(self.root, "p-base", buckets=["php"])
        _write_preset(self.root, "p-ext", extends=["p-base"], buckets=["quality"])
        items, *_ = self._resolve({"presets": ["p-ext"]})
        self.assertEqual(set(items), {"php", "quality"})

    def test_dedup_preserves_order_parents_first(self):
        # parent before child, duplicates collapsed, order stable
        _write_preset(self.root, "p-base", buckets=["php", "quality"])
        _write_preset(self.root, "p-ext", extends=["p-base"], buckets=["php", "devops"])
        items, *_ = self._resolve({"presets": ["p-ext"], "buckets": ["quality"]})
        self.assertEqual(items, ["php", "quality", "devops"])

    def test_unknown_preset_skipped_no_effect(self):
        # unknown preset → warn+skip in resolve_presets; in the absence buckets
        # thread presets is empty → fall into autodetect (laravel-project), not in config.
        items, _n, src, *_ = self._resolve({"presets": ["ghost"]})
        self.assertEqual(src, "autodetect")
        self.assertEqual(set(items), {"php", "quality"})

    def test_skill_only_preset_warns_and_no_buckets(self):
        # preset only with include (skill-granular) — in bucket-granular connect effect
        # no: warn is printed, buckets are empty → thread presets is not activated.
        _write_preset(self.root, "p-skills", include=["php/code-style"])
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            items, _n, src, *_ = resolve_selection(
                self.env, self.proj, {"presets": ["p-skills"]}, "", [])
        self.assertIn("skill-granular", err.getvalue())
        self.assertEqual(src, "autodetect")  # presets-thread didn't work (no buckets)

    def test_extends_cycle_dies(self):
        _write_preset(self.root, "p-a", extends=["p-b"], buckets=["php"])
        _write_preset(self.root, "p-b", extends=["p-a"], buckets=["quality"])
        with self.assertRaises(SystemExit):
            self._resolve({"presets": ["p-a"]})

    def test_flags_still_win_over_presets(self):
        # precedence: explicit --plugins/items interrupt .swissknife.json presets
        _write_preset(self.root, "p-web", buckets=["php", "quality"])
        with contextlib.redirect_stderr(io.StringIO()):
            items, _n, src, *_ = resolve_selection(
                self.env, self.proj, {"presets": ["p-web"]}, "", ["devops"])
        self.assertEqual(items, ["devops"])
        self.assertEqual(src, "items")

    def test_profile_flag_wins_over_presets(self):
        _write_preset(self.root, "p-web", buckets=["php"])
        with contextlib.redirect_stderr(io.StringIO()):
            items, _n, src, *_ = resolve_selection(
                self.env, self.proj, {"presets": ["p-web"]}, "php-package", [])
        self.assertEqual(set(items), {"php", "devops"})  # profile php-package
        self.assertEqual(src, "flag")


class TestPresetsNoLongerReserved(unittest.TestCase):
    """presets in .swissknife.json is no longer marked _RESERVED — validate_config not warn'etc."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_presets_key_does_not_warn_as_reserved(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            validate_config(self.env, {"presets": ["p-web"]},
                            self.tmp / ".swissknife.json")
        self.assertNotIn("presets", err.getvalue())


if __name__ == "__main__":
    unittest.main()
