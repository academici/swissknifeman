"""Tests fleet.py — manifest (groups by common packages), parsing duplicates, feature-log."""
import json
import tempfile
import unittest
from pathlib import Path

from maind import derive
from maind.analysis import fleet
from maind import memory as memory_mod
from maind.config import load_config
from tests.fixtures import FakeMemoryServer, make_repo, write_maind_config


def _setup(tmp, url, namespaces=None, memory_namespaces=None):
    """flexcrm + azguard, both require axioma-studio/azguard-core (general package)."""
    root, env = make_repo(tmp)
    flex, az = Path(tmp) / "flexcrm", Path(tmp) / "azguard"
    for p, data in ((flex, {"name": "axioma-studio/flexcrm",
                            "require": {"axioma-studio/azguard-core": "@dev"}}),
                    (az, {"name": "axioma-studio/azguard",
                          "require": {"axioma-studio/azguard-core": "@dev"}})):
        p.mkdir(parents=True, exist_ok=True)
        (p / "composer.json").write_text(json.dumps(data), encoding="utf-8")
    (az / "packages" / "core").mkdir(parents=True, exist_ok=True)
    (az / "packages" / "core" / "composer.json").write_text(
        json.dumps({"name": "axioma-studio/azguard-core"}), encoding="utf-8")
    flexp = {"id": "flexcrm", "name": "FlexCRM", "type": "php-package", "status": "active",
             "enabled": True, "local_path": str(flex), "graphify": True}
    azp = {"id": "azguard", "name": "AzGuard", "type": "php-package", "status": "active",
           "enabled": True, "local_path": str(az)}
    if namespaces is not None:
        flexp["namespaces"] = azp["namespaces"] = namespaces
    if memory_namespaces is not None:
        flexp["memory_namespaces"] = azp["memory_namespaces"] = memory_namespaces
    write_maind_config(root, graph={"adapter": "federation"},
                       memory={"url": url}, projects=[flexp, azp])
    config, _ = load_config(env)
    derive.derive_all(env, config)
    return env, config


class TestManifest(unittest.TestCase):
    def test_shared_packages_and_entries(self):
        with tempfile.TemporaryDirectory() as tmp, FakeMemoryServer() as url:
            env, config = _setup(tmp, url)
            m = fleet.manifest(env, config)
            self.assertEqual(len(m["projects"]), 2)
            fx = next(p for p in m["projects"] if p["id"] == "flexcrm")
            self.assertTrue(fx["code"])
            self.assertTrue(fx["path"].endswith("flexcrm"))
            self.assertEqual(fx["scopes"]["private"], "project:flexcrm")
            sp = m["shared_packages"]
            core = next(s for s in sp if s["name"] == "azguard-core")
            self.assertEqual(core["consumers"], ["azguard", "flexcrm"])
            self.assertEqual(core["consumer_count"], 2)


class TestDuplicatesParsing(unittest.TestCase):
    def test_parse_marks_cross_project(self):
        pmap = {"/p/flexcrm": "flexcrm", "/p/azguard": "azguard"}
        report = {"duplicates": [
            {"lines": 12, "tokens": 80, "format": "php",
             "firstFile": {"name": "/p/flexcrm/app/A.php", "start": 1, "end": 13},
             "secondFile": {"name": "/p/azguard/src/B.php", "start": 5, "end": 17}},
            {"lines": 6, "tokens": 40, "format": "php",
             "firstFile": {"name": "/p/flexcrm/app/A.php"},
             "secondFile": {"name": "/p/flexcrm/app/C.php"}},
        ]}
        clones = fleet._parse_report(report, pmap)
        self.assertTrue(clones[0]["cross_project"])          # cross-project first
        self.assertEqual(clones[0]["projects"], ["azguard", "flexcrm"])
        self.assertFalse(clones[1]["cross_project"])         # within one project

    def test_jscpd_cmd_shape(self):
        cmd = fleet._jscpd_cmd(["/a", "/b"], "/out", min_tokens=50,
                               pattern="**/*.php", ignore="**/vendor/**")
        self.assertEqual(cmd[:3], ["npx", "--yes", "jscpd"])
        self.assertIn("--reporters", cmd)
        self.assertIn("/a", cmd)
        self.assertIn("/b", cmd)

    def test_resolve_targets_by_projects(self):
        with tempfile.TemporaryDirectory() as tmp, FakeMemoryServer() as url:
            env, config = _setup(tmp, url)
            pmap, paths = fleet._resolve_targets(env, config, {"projects": "flexcrm"})
            self.assertEqual(list(pmap.values()), ["flexcrm"])
            self.assertEqual(len(paths), 1)


class TestFeatureLog(unittest.TestCase):
    def test_log_and_recall_cross_project(self):
        with tempfile.TemporaryDirectory() as tmp, FakeMemoryServer() as url:
            env, config = _setup(tmp, url, namespaces=["axioma"],
                                 memory_namespaces=["axioma"])
            flex = config["projects"][0]
            r = fleet.log_feature(env, config, flex, "added import CSV")
            self.assertEqual(r["status"], "ok")
            self.assertIn("ns:axioma", r["scopes"])
            # visible in the group bucket
            got = memory_mod.recall(url, "ns:axioma", fleet.FEATURE_MARKER)
            self.assertTrue(any("CSV" in m["text"] for m in got))
            feats = fleet.features(env, config, namespace="axioma")
            self.assertTrue(any("CSV" in f["text"] for f in feats))


class TestSimilar(unittest.TestCase):
    def test_extract_chunks_finds_declarations(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "pa"
            (a / "vendor").mkdir(parents=True)         # vendor is ignored
            (a / "src").mkdir(parents=True)
            (a / "src" / "X.php").write_text(
                "<?php\nclass Importer {\n  public function importCsv($f) {\n"
                "    $rows = read($f);\n    return map($rows);\n  }\n}\n", encoding="utf-8")
            (a / "vendor" / "Y.php").write_text("<?php\nfunction ignored(){}\n", encoding="utf-8")
            chunks = fleet.extract_chunks({str(a): "pa"}, min_chars=10)
            names = {c["name"] for c in chunks}
            self.assertIn("Importer", names)
            self.assertNotIn("ignored", names)         # from vendor we don’t take

    def test_cross_project_pairs_above_threshold(self):
        chunks = [{"project": "a", "name": "F", "file": "/a/F.php"},
                  {"project": "b", "name": "G", "file": "/b/G.php"},
                  {"project": "a", "name": "H", "file": "/a/H.php"}]
        vecs = [[1.0, 0.0], [0.99, 0.01], [0.0, 1.0]]   # F~G (various projects), H orthogonal
        pairs = fleet.cross_project_pairs(chunks, vecs, 0.9)
        self.assertEqual(len(pairs), 1)
        self.assertEqual({pairs[0]["a"]["project"], pairs[0]["b"]["project"]}, {"a", "b"})

    def test_embed_dies_without_backend(self):
        with self.assertRaises(SystemExit):
            fleet._embed(["x"], None)


class TestCosine(unittest.TestCase):
    def test_identical_vectors(self):
        self.assertAlmostEqual(fleet._cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]), 1.0)

    def test_orthogonal_is_zero(self):
        self.assertAlmostEqual(fleet._cosine([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_opposite_is_minus_one(self):
        self.assertAlmostEqual(fleet._cosine([1.0, 0.0], [-1.0, 0.0]), -1.0)

    def test_scale_invariant(self):
        self.assertAlmostEqual(fleet._cosine([1.0, 1.0], [3.0, 3.0]), 1.0)

    def test_zero_vector_no_div_by_zero(self):
        # zero norm is replaced by 1.0 - there is no division by zero, the result is 0.0
        self.assertEqual(fleet._cosine([0.0, 0.0], [1.0, 1.0]), 0.0)


if __name__ == "__main__":
    unittest.main()
