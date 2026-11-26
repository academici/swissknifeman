"""aicore.util.http opens http and https URLs only (a configured file:// URL must not be read)."""
import tempfile
import unittest
from pathlib import Path

from aicore.util import http


class SchemeTests(unittest.TestCase):
    def test_file_and_ftp_urls_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "secret.json"
            target.write_text('{"k": 1}', encoding="utf-8")
            for url in (target.as_uri(), "ftp://example.invalid/x", "gopher://x", "data:text/plain,hi", "/etc/passwd"):
                with self.subTest(url=url):
                    with self.assertRaises(RuntimeError) as caught:
                        http.http_get_json(url)
                    self.assertIn("unsupported URL scheme", str(caught.exception))
                    with self.assertRaises(RuntimeError):
                        http.http_post_json(url, {})
                    self.assertFalse(http.ping(url))

    def test_http_and_https_pass_the_scheme_check(self):
        http._check_scheme("http://127.0.0.1:1/x")
        http._check_scheme("HTTPS://example.invalid/")


if __name__ == "__main__":
    unittest.main()
