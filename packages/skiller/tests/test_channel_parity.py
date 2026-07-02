"""Паритет каналов vendor vs sync (skillset) — golden-тест.

vendor.collect_skills сканирует бакеты живым FS-rglob; skillset.resolve_skillset
разворачивает их через registry-индекс (skills.json). Это два независимых
исполнения одной формулы «бакеты ∪ include − exclude» (аудит V-5) — если бы они
разошлись (напр. кто-то поправил один путь и забыл другой), обычные тесты каждого
канала по отдельности этого не поймали бы. Здесь сверяем результат ОБОИХ каналов
на одном синтетическом реестре."""
import json
import tempfile
import unittest
from pathlib import Path

from skiller.registry import build_registry
from skiller.skillset import resolve_skillset
from skiller.vendor import collect_skills

from tests.fixtures import make_registry


def _materialize_registry(env):
    reg, *_ = build_registry(env)
    (env.root / "skills.json").write_text(
        json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


class TestChannelParity(unittest.TestCase):
    def test_bucket_selection_matches_across_channels(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)

            vendor_skills, _all_rels = collect_skills(env, ["php", "devops"], set())
            vendor_names = {fm_name for _b, _r, _d, fm_name in vendor_skills}

            entries, skipped = resolve_skillset(env, {"buckets": ["php", "devops"]})
            sync_names = {e["name"] for e in entries}

            self.assertEqual(vendor_names, sync_names)
            self.assertEqual(skipped, [])

    def test_exclude_matches_across_channels(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root, env = make_registry(tmp)
            _materialize_registry(env)
            exclude = {"code-style"}

            vendor_skills, _ = collect_skills(env, ["php"], exclude)
            vendor_names = {fm_name for _b, _r, _d, fm_name in vendor_skills}

            entries, _skipped = resolve_skillset(
                env, {"buckets": ["php"], "exclude": sorted(exclude)})
            sync_names = {e["name"] for e in entries}

            # laravel-conventions requires code-style — исключён, оба канала
            # пропускают зависимость (warning), сам бакет отдаёт laravel-conventions.
            self.assertEqual(vendor_names, {"laravel-conventions"})
            self.assertEqual(sync_names, {"laravel-conventions"})
            self.assertEqual(vendor_names, sync_names)
