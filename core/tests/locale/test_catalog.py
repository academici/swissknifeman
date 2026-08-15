import unittest
from core.locale.catalog import Catalog, Overlay, resolve_catalog


class CatalogTests(unittest.TestCase):
    def test_missing_russian_key_uses_english(self):
        result = resolve_catalog(Catalog("en", {"message.test": "Run `task`"}), None, "message.test", immutable_tokens=("task",))
        self.assertTrue(result["fallback"])

    def test_token_drift_refuses(self):
        catalog = Catalog("en", {"message.test": "Run `task`"})
        digest = "sha256:" + __import__("hashlib").sha256(b'{"message.test":"Run `task`"}').hexdigest()
        with self.assertRaisesRegex(ValueError, "TOKEN"):
            resolve_catalog(catalog, Overlay("ru", digest, {"message.test": {"text": "Запуск"}}), "message.test", immutable_tokens=("task",))
