import tempfile
import unittest
from pathlib import Path

from orch.conductor.infrastructure.roles import unused_attempt


class InterruptedStreamsTest(unittest.TestCase):
    def test_resume_preserves_interrupted_and_compressed_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            streams = Path(tmp)
            (streams / "review.1.jsonl").write_text("first")
            (streams / "review.1-a2.jsonl.gz").write_bytes(b"")
            self.assertEqual(unused_attempt(streams, "review.1", 2), 3)
            self.assertEqual((streams / "review.1.jsonl").read_text(), "first")
