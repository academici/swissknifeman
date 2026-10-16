"""The built frontend works under the backend CSP: no inline script, no inline style, no eval-like code.

Skipped only when `frontend/dist` was not built (`npm --prefix packages/gui/frontend run build`).
"""
import re
import unittest
from pathlib import Path

DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


@unittest.skipUnless((DIST / "index.html").is_file(), "frontend/dist is not built")
class TestFrontendBuild(unittest.TestCase):
    def setUp(self):
        self.html = (DIST / "index.html").read_text(encoding="utf-8")

    def test_no_inline_script_or_style(self):
        for match in re.finditer(r"<script\b([^>]*)>(.*?)</script>", self.html, flags=re.S | re.I):
            self.assertIn("src=", match.group(1), "inline <script> without src")
            self.assertEqual("", match.group(2).strip())
        self.assertIsNone(re.search(r"<style\b", self.html, flags=re.I))
        self.assertIsNone(re.search(r"\sstyle\s*=", self.html, flags=re.I))
        self.assertIsNone(re.search(r"\son[a-z]+\s*=", self.html, flags=re.I))

    def test_assets_are_local_files(self):
        references = re.findall(r'(?:src|href)="([^"]+)"', self.html)
        self.assertTrue(references)
        for reference in references:
            self.assertTrue(reference.startswith("/assets/"), reference)
            self.assertTrue((DIST / reference.lstrip("/")).is_file(), reference)

    def test_scripts_have_no_eval(self):
        for script in (DIST / "assets").glob("*.js"):
            text = script.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"\beval\(", script.name)
            self.assertNotIn("new Function(", text, script.name)


if __name__ == "__main__":
    unittest.main()
