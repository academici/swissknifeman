"""Internal documentation."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from harness import agentpacks as ap
from tests.fixtures import make_pack, make_project, make_root


class TestExpectGlobs(unittest.TestCase):
    """Internal documentation."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.proj = make_project(self.tmp, "p")

    def test_miss_when_absent(self):
        m = {"expect_globs": ["app/Http/Controllers"]}
        self.assertEqual(ap.validate_expect_globs(m, self.proj, {}), ["app/Http/Controllers"])

    def test_hit_when_present(self):
        (self.proj / "app/Http/Controllers").mkdir(parents=True)
        m = {"expect_globs": ["app/Http/Controllers"]}
        self.assertEqual(ap.validate_expect_globs(m, self.proj, {}), [])

    def test_single_brace_interpolation(self):
        (self.proj / "src/Http/Controllers").mkdir(parents=True)
        m = {"expect_globs": ["{ACCESS_ROOT}/Http/Controllers"]}
        self.assertEqual(ap.validate_expect_globs(m, self.proj, {"ACCESS_ROOT": "src"}), [])

    def test_monorepo_star_glob(self):
        (self.proj / "packages/core/src/Http/Controllers").mkdir(parents=True)
        m = {"expect_globs": ["{ACCESS_ROOT}/Http/Controllers"]}

        self.assertEqual(
            ap.validate_expect_globs(m, self.proj, {"ACCESS_ROOT": "packages/*/src"}), [])

    def test_no_expect_globs_is_ok(self):
        self.assertEqual(ap.validate_expect_globs({}, self.proj, {}), [])


class TestAccessRootDetect(unittest.TestCase):
    """Internal documentation."""

    PROBE = ("test -d app/Http && echo app ; "
             "test ! -d app/Http && test -d src/Http && echo src ; "
             "test ! -d app/Http && test ! -d src/Http && "
             "ls -d packages/*/src/Http >/dev/null 2>&1 && echo 'packages/*/src' ; echo ''")

    def test_app_priority_with_local_packages(self):

        proj = make_project(Path(tempfile.mkdtemp()), "applocal")
        (proj / "app/Http").mkdir(parents=True)
        (proj / "packages/x/src/Http").mkdir(parents=True)
        self.assertEqual(self._resolve(proj), "app")

    def _resolve(self, proj):
        manifest = {"interview": [
            {"id": "ACCESS_ROOT", "q": "?", "detect": self.PROBE, "default": "app"}]}
        answers, _ = ap.resolve_interview(manifest, proj, {}, shell_policy="safe")
        return answers["ACCESS_ROOT"]

    def test_app_layout(self):
        proj = make_project(Path(tempfile.mkdtemp()), "app")
        (proj / "app/Http").mkdir(parents=True)
        self.assertEqual(self._resolve(proj), "app")

    def test_monorepo_layout(self):
        proj = make_project(Path(tempfile.mkdtemp()), "mono")
        (proj / "packages/core/src/Http").mkdir(parents=True)
        self.assertEqual(self._resolve(proj), "packages/*/src")

    def test_single_package_layout(self):
        proj = make_project(Path(tempfile.mkdtemp()), "pkg")
        (proj / "src/Http").mkdir(parents=True)
        self.assertEqual(self._resolve(proj), "src")

    def test_default_when_none(self):
        proj = make_project(Path(tempfile.mkdtemp()), "empty")
        self.assertEqual(self._resolve(proj), "app")


class TestConflictSummary(unittest.TestCase):
    """Internal documentation."""

    def test_conflict_summary_and_pack_new(self):
        tmp = Path(tempfile.mkdtemp())
        root, env = make_root(tmp)
        pack = make_pack(root)
        proj = make_project(tmp, "p")
        (proj / "composer.json").write_text('{"scripts": {"test": "pest"}}')
        ap.do_render(env, pack, proj, auto=True, overrides={"PACK_PREFIX": "acme"},
                     dry=False, install_only=False, shell_policy="safe")

        rendered = proj / ".claude/agents/acme-reviewer.md"
        rendered.write_text(rendered.read_text() + "\nЛОКАЛЬНАЯ ПРАВКА\n")

        pdir = root / "configs/claude-code/agent-packs" / pack
        src = pdir / "agents/reviewer.md"
        src.write_text(src.read_text() + "\nНОВОЕ В ПАКЕ\n")
        mf = pdir / "pack.json"
        m = json.loads(mf.read_text())
        m["version"] = "0.2.0"
        mf.write_text(json.dumps(m, ensure_ascii=False, indent=2))

        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            ap.do_upgrade(env, pack, proj, overrides={}, dry=False, shell_policy="safe")
        err = buf.getvalue()
        self.assertIn("conflict", err)
        self.assertIn(".pack-new", err)
        self.assertTrue((proj / ".claude/agents/acme-reviewer.md.pack-new").exists())


if __name__ == "__main__":
    unittest.main()
