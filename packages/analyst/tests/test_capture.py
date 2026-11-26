import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from analyst.cli import main
from analyst.events import read_events


class CaptureTests(unittest.TestCase):
    def test_capture_and_migration_cli_keep_raw_source_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "legacy.json"
            source.write_text(json.dumps({"schema": 2, "session_id": "s", "generated_at": "2026-07-22T00:00:00Z", "tools": {"total": 1}, "bash": {}}), encoding="utf-8")
            before, cwd = source.read_bytes(), os.getcwd()
            try:
                os.chdir(root)
                with redirect_stdout(io.StringIO()):
                    main([str(root), "migrate", "--operation", "apply", "--source", str(source)])
            finally:
                os.chdir(cwd)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(len(read_events(root)), 1)


if __name__ == "__main__":
    unittest.main()
