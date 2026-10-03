"""Internal documentation."""
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
        self.assertTrue(data["permissions"])
        self.assertNotIn("Read(**/CHANGELOG.md)", data["permissions"].get("deny", []))

    def test_global_preset_merges_enabled_mcpjson_servers(self):



        env = fx.real_env(self.tmp)
        proj = fx.make_project(self.tmp)

        settings_path = proj / ".claude" / "settings.local.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps({"enabledMcpjsonServers": ["github"]}))
        ret, _out = run(apply_permissions, env, proj, presets="global")
        self.assertTrue(ret)
        data = json.loads(settings_path.read_text())
        self.assertEqual(sorted(data["enabledMcpjsonServers"]), ["github", "perplexity-web"])


if __name__ == "__main__":
    unittest.main()
