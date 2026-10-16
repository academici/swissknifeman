"""Tests of aicore.util.digest against the language-neutral vectors of the digest/v1 contract."""
import json
import unittest
from hashlib import sha256
from pathlib import Path

from aicore.artifacts import artifact
from aicore.util import digest

VECTORS = Path(__file__).resolve().parent.parent / "schemas" / "digest" / "v1" / "vectors.json"


class TestVectors(unittest.TestCase):
    def setUp(self):
        self.vectors = json.loads(VECTORS.read_text(encoding="utf-8"))["vectors"]

    def test_vector_count_and_names(self):
        names = [vector["name"] for vector in self.vectors]
        self.assertGreaterEqual(len(names), 6)
        self.assertEqual(len(names), len(set(names)))

    def test_every_vector(self):
        for vector in self.vectors:
            with self.subTest(vector=vector["name"]):
                canonical = digest.canonical_json_bytes(vector["input"])
                self.assertEqual(canonical, vector["canonical"].encode("utf-8"))
                self.assertEqual(digest.sha256_tagged(canonical), vector["digest"])
                if isinstance(vector["input"], dict):
                    self.assertEqual(digest.digest_json(vector["input"]), vector["digest"])
                self.assertTrue(digest.is_tagged_digest(vector["digest"]))

    def test_empty_object_digest(self):
        self.assertEqual(digest.sha256_tagged(b"{}"),
                         "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a")


class TestRules(unittest.TestCase):
    def test_rejects_float_and_non_string_key(self):
        for value in (1.5, {"a": 1.0}, [0.1], {1: "x"}, {"a": {2: 1}}, {"a": object()}, {"a": {1, 2}}, b"x"):
            with self.subTest(value=repr(value)):
                with self.assertRaises(TypeError):
                    digest.canonical_json_bytes(value)

    def test_tuples_are_arrays_and_mappings_are_objects(self):
        self.assertEqual(digest.canonical_json_bytes({"a": (1, 2)}), digest.canonical_json_bytes({"a": [1, 2]}))
        self.assertEqual(digest.canonical_json_bytes(artifact.MappingProxyType({"b": 1, "a": 2})), b'{"a":2,"b":1}')

    def test_key_order_does_not_matter(self):
        self.assertEqual(digest.digest_json({"a": 1, "b": 2}), digest.digest_json({"b": 2, "a": 1}))

    def test_exclude_keys_is_top_level_only_and_pure(self):
        original = {"digest": "old", "z": "привет", "a": {"digest": "nested", "n": 1}}
        expected = "sha256:" + sha256('{"a":{"digest":"nested","n":1},"z":"привет"}'.encode()).hexdigest()
        self.assertEqual(digest.digest_json(original, exclude_keys=("digest",)), expected)
        self.assertEqual(original["digest"], "old")
        self.assertNotEqual(digest.digest_json(original), expected)

    def test_digest_json_needs_mapping(self):
        with self.assertRaises(TypeError):
            digest.digest_json([1])

    def test_bytes_only(self):
        for fn in (digest.sha256_tagged, digest.sha256_hex):
            with self.assertRaises(TypeError):
                fn("text")
        self.assertEqual(digest.sha256_hex(b""), sha256(b"").hexdigest())

    def test_is_tagged_digest(self):
        good = "sha256:" + "a" * 64
        self.assertTrue(digest.is_tagged_digest(good))
        for bad in (good + "\n", "sha256:" + "A" * 64, "a" * 64, "sha256:abc", None, 5, ["sha256:" + "a" * 64]):
            with self.subTest(bad=repr(bad)):
                self.assertFalse(digest.is_tagged_digest(bad))


class TestArtifactReexport(unittest.TestCase):
    def test_public_names_are_the_same_objects(self):
        self.assertIs(artifact.canonical_json_bytes, digest.canonical_json_bytes)
        self.assertIs(artifact.sha256_digest, digest.sha256_tagged)

    def test_sha256_digest_rejects_non_bytes(self):
        with self.assertRaises(TypeError):
            artifact.sha256_digest("text")


if __name__ == "__main__":
    unittest.main()
