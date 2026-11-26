"""frontend/scripts/check-budget.mjs on synthetic dist folders (needs node; skipped without it)."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "frontend" / "scripts" / "check-budget.mjs"
NODE = shutil.which("node")

HTML = ('<!doctype html><html><head><script type="module" crossorigin src="/assets/index-a.js"></script>'
        '<link rel="stylesheet" crossorigin href="/assets/index-a.css"></head><body></body></html>')


def noise(size):
    return os.urandom(size).hex()  # incompressible enough: gzip size ~ half of the characters


@unittest.skipUnless(NODE, "node is not installed")
class TestBudget(unittest.TestCase):
    def setUp(self):
        self.dist = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dist, True)
        (self.dist / "assets").mkdir()
        (self.dist / "index.html").write_text(HTML)
        (self.dist / "assets" / "index-a.css").write_text("body{margin:0}")
        (self.dist / "assets" / "index-a.js").write_text("console.log(1)")

    def run_budget(self):
        return subprocess.run([NODE, str(SCRIPT), "--dist", str(self.dist)], capture_output=True, text=True, timeout=60)

    def test_small_bundle_passes(self):
        done = self.run_budget()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("budget ok", done.stdout)

    def test_oversized_initial_js_fails(self):
        (self.dist / "assets" / "index-a.js").write_text("var a='" + noise(200_000) + "';")
        done = self.run_budget()
        self.assertEqual(1, done.returncode)
        self.assertIn("initial JS", done.stderr)

    def test_oversized_css_fails(self):
        (self.dist / "assets" / "index-a.css").write_text("a{content:'" + noise(30_000) + "'}")
        done = self.run_budget()
        self.assertEqual(1, done.returncode)
        self.assertIn("initial CSS", done.stderr)

    def test_oversized_lazy_chunk_fails_alone(self):
        (self.dist / "assets" / "lazy-b.js").write_text("var a='" + noise(450_000) + "';")
        done = self.run_budget()
        self.assertEqual(1, done.returncode)
        self.assertIn("lazy-b.js", done.stderr)
        self.assertNotIn("initial JS", done.stderr)

    def test_xterm_in_the_initial_script_fails(self):
        (self.dist / "assets" / "index-a.js").write_text("var t=new Terminal();/* xterm */")
        done = self.run_budget()
        self.assertEqual(1, done.returncode)
        self.assertIn("xterm", done.stderr)

    def test_dynamic_import_of_an_xterm_chunk_is_allowed(self):
        (self.dist / "assets" / "index-a.js").write_text('const load=()=>import("./xterm-9f.js");')
        (self.dist / "assets" / "xterm-9f.js").write_text("export const Terminal=class{}")
        self.assertEqual(0, self.run_budget().returncode)

    def test_static_import_of_an_xterm_chunk_fails(self):
        (self.dist / "assets" / "index-a.js").write_text('import{Terminal}from"./xterm-9f.js";')
        (self.dist / "assets" / "xterm-9f.js").write_text("export const Terminal=class{}")
        done = self.run_budget()
        self.assertEqual(1, done.returncode)
        self.assertIn("xterm", done.stderr)

    def test_a_static_import_counts_towards_the_initial_budget(self):
        (self.dist / "assets" / "index-a.js").write_text('import"./shared-c.js";')
        (self.dist / "assets" / "shared-c.js").write_text("var a='" + noise(200_000) + "';")
        done = self.run_budget()
        self.assertEqual(1, done.returncode)
        self.assertIn("initial JS", done.stderr)

    def test_missing_build_fails(self):
        (self.dist / "index.html").unlink()
        done = self.run_budget()
        self.assertEqual(1, done.returncode)
        self.assertIn("npm run build", done.stderr)


if __name__ == "__main__":
    unittest.main()
