"""permissions: graceful skip без скрипта; e2e реального apply-permissions.sh."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness.permissions import apply_permissions
import tests.fixtures as fx


def run(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        with contextlib.redirect_stderr(buf):
            out = fn(*a, **kw)
    return out, buf.getvalue()


class PermissionsCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_script_graceful(self):
        # мини-root без scripts/apply-permissions.sh → False + предупреждение, без падения
        _root, env = fx.make_root(self.tmp)
        proj = fx.make_project(self.tmp)
        ret, _out = run(apply_permissions, env, proj)
        self.assertFalse(ret)
        self.assertFalse((proj / ".claude").exists())

    def test_real_script_dry_run_writes_nothing(self):
        env = fx.real_env(self.tmp)
        proj = fx.make_project(self.tmp)
        ret, _out = run(apply_permissions, env, proj, dry_run=True)
        self.assertTrue(ret)
        self.assertFalse((proj / ".claude").exists())

    def test_real_script_writes_permissions(self):
        env = fx.real_env(self.tmp)
        proj = fx.make_project(self.tmp)
        ret, _out = run(apply_permissions, env, proj)
        self.assertTrue(ret)
        f = proj / ".claude" / "settings.local.json"
        self.assertTrue(f.exists())
        data = json.loads(f.read_text())
        self.assertIn("permissions", data)
        # base-пресет всегда вносит deny/allow — структура непустая
        self.assertTrue(data["permissions"])


if __name__ == "__main__":
    unittest.main()
