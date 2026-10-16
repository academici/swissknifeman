"""The content-addressed blob store behind artifact-ref/v1."""
import hashlib
import os
import stat
import tempfile
import unittest
from pathlib import Path

from aicore import state
from aicore.state import blobs
from aicore.util import schema

CONTRACT = Path(__file__).resolve().parents[2] / "schemas" / "artifact-ref" / "v1"


class BlobCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = self.root / "proj"
        self.project.mkdir()
        self.env = {"SKM_HOME": str(self.root / "skm")}

    def put(self, data=b"hello", **kwargs):
        kwargs.setdefault("media_type", "text/plain")
        kwargs.setdefault("project", self.project)
        return blobs.put_bytes(data, env=self.env, **kwargs)


class TestPutAndRead(BlobCase):
    def test_round_trip_in_the_project_store(self):
        ref = self.put(b"hello", name="greeting")
        digest = "sha256:" + hashlib.sha256(b"hello").hexdigest()
        self.assertEqual({"$schema": "urn:swissknifeman:aicore:artifact-ref:v1", "digest": digest, "size": 5,
                          "media_type": "text/plain", "sensitivity": "normal", "name": "greeting",
                          "location": "project"}, ref)
        path = blobs.blob_path(ref, project=self.project)
        self.assertEqual(self.project / ".swissknifeman" / "state" / "artifacts" / "sha256" / digest[7:], path)
        self.assertEqual(b"hello", path.read_bytes())
        self.assertEqual(b"hello", blobs.read_bytes(ref, project=self.project))
        self.assertEqual(b"hello", blobs.read_bytes(digest, project=self.project))  # a bare digest also works

    def test_reference_is_a_valid_artifact_ref(self):
        registry, kind = schema.load_contract(CONTRACT)
        for kwargs in ({}, {"name": "n", "sensitivity": "sensitive"}):
            ref = self.put(b"x", **kwargs)
            self.assertEqual([], schema.validate(ref, kind, registry))
        self.assertEqual([], schema.validate(blobs.put_json({"a": 1}, env=self.env), kind, registry))

    def test_machine_store_without_a_project_follows_skm_home(self):
        ref = blobs.put_bytes(b"data", media_type="application/octet-stream", env=self.env)
        self.assertEqual("machine", ref["location"])
        path = blobs.blob_path(ref, env=self.env)
        self.assertEqual(self.root / "skm" / "state" / "artifacts" / "sha256" / ref["digest"][7:], path)
        self.assertEqual(b"data", blobs.read_bytes(ref, env=self.env))
        self.assertFalse((self.project / ".swissknifeman").exists())

    def test_files_are_private(self):
        path = blobs.blob_path(self.put(b"secret", sensitivity="sensitive"), project=self.project)
        self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))
        self.assertEqual([], [p.name for p in path.parent.iterdir() if p.name.startswith(".blob-")])

    def test_writing_the_same_bytes_again_changes_nothing(self):
        first = self.put(b"same")
        path = blobs.blob_path(first, project=self.project)
        before = (path.stat().st_ino, path.stat().st_mtime_ns)
        second = self.put(b"same", media_type="text/markdown", name="other")
        self.assertEqual(first["digest"], second["digest"])
        self.assertEqual("text/markdown", second["media_type"])  # the reference differs, the blob does not
        self.assertEqual(before, (path.stat().st_ino, path.stat().st_mtime_ns))
        self.assertEqual(1, len(list(path.parent.iterdir())))

    def test_a_damaged_blob_is_rewritten_by_the_next_put(self):
        ref = self.put(b"good bytes")
        path = blobs.blob_path(ref, project=self.project)
        path.write_bytes(b"evil bytes!")  # same size, other content
        self.put(b"good bytes")
        self.assertEqual(b"good bytes", blobs.read_bytes(ref, project=self.project))

    def test_empty_content(self):
        ref = self.put(b"")
        self.assertEqual(0, ref["size"])
        self.assertEqual(b"", blobs.read_bytes(ref, project=self.project))

    def test_put_json_is_canonical(self):
        first = blobs.put_json({"b": 1, "a": [True, None]}, project=self.project, env=self.env)
        second = blobs.put_json({"a": [True, None], "b": 1}, project=self.project, env=self.env)
        self.assertEqual(first, second)
        self.assertEqual("application/json", first["media_type"])
        self.assertEqual(b'{"a":[true,null],"b":1}', blobs.read_bytes(first, project=self.project))
        with self.assertRaises(TypeError):
            blobs.put_json({"x": 1.5}, project=self.project, env=self.env)

    def test_reexported_from_the_state_package(self):
        for name in ("put_bytes", "put_json", "read_bytes", "blob_path"):
            self.assertIs(getattr(blobs, name), getattr(state, name))


class TestCorruption(BlobCase):
    def test_changed_content_is_reported(self):
        ref = self.put(b"abcdef")
        path = blobs.blob_path(ref, project=self.project)
        path.write_bytes(b"abcdeX")
        with self.assertRaisesRegex(ValueError, "^BLOB_CORRUPT sha256:"):
            blobs.read_bytes(ref, project=self.project)

    def test_a_wrong_size_is_reported_before_the_hash(self):
        ref = self.put(b"abcdef")
        with self.assertRaisesRegex(ValueError, "BLOB_CORRUPT .*reference says 99"):
            blobs.read_bytes(dict(ref, size=99), project=self.project)
        blobs.blob_path(ref, project=self.project).write_bytes(b"abc")
        with self.assertRaisesRegex(ValueError, "the file has 3 bytes"):
            blobs.read_bytes(ref, project=self.project)

    def test_the_message_never_holds_the_content(self):
        ref = self.put(b"TOP-SECRET-VALUE", sensitivity="sensitive")
        blobs.blob_path(ref, project=self.project).write_bytes(b"TOP-SECRET-VALUX")
        with self.assertRaises(ValueError) as caught:
            blobs.read_bytes(ref, project=self.project)
        self.assertNotIn("SECRET", str(caught.exception))

    def test_a_missing_blob_is_file_not_found(self):
        ref = dict(self.put(b"here"), digest="sha256:" + "0" * 64)
        with self.assertRaises(FileNotFoundError):
            blobs.read_bytes(ref, project=self.project)

    def test_references_that_could_leave_the_store_are_refused(self):
        for digest in ("sha256:../../etc/passwd", "../x", "sha256:" + "A" * 64, "sha256:abc", "", None):
            with self.subTest(digest=digest), self.assertRaisesRegex(ValueError, "BLOB_REF_INVALID"):
                blobs.blob_path({"digest": digest}, project=self.project)
        with self.assertRaisesRegex(ValueError, "BLOB_REF_INVALID"):
            blobs.read_bytes({}, project=self.project)


class TestArguments(BlobCase):
    def test_bad_arguments_are_refused(self):
        for kwargs in ({"media_type": "text"}, {"media_type": "Text/Plain"}, {"media_type": ""},
                       {"sensitivity": "secret"}, {"name": ""}, {"name": "a\nb"}, {"name": "x" * 256}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, "BLOB_ARGUMENT"):
                self.put(b"x", **kwargs)
        with self.assertRaises(TypeError):
            self.put("text")
        self.assertFalse((self.project / ".swissknifeman").exists())

    def test_a_failed_write_leaves_no_temporary_file(self):
        real = os.replace

        def broken(*args, **kwargs):
            raise OSError("disk full")

        os.replace = broken
        try:
            with self.assertRaises(OSError):
                self.put(b"data")
        finally:
            os.replace = real
        store = self.project / ".swissknifeman" / "state" / "artifacts" / "sha256"
        self.assertEqual([], list(store.iterdir()))


if __name__ == "__main__":
    unittest.main()
