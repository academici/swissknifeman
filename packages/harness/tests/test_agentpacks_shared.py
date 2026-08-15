"""Internal documentation."""
import re
import unittest
from pathlib import Path

PACKS_DIR = Path(__file__).resolve().parents[1] / "configs" / "claude-code" / "agent-packs"


_SHARED_RE = re.compile(r"<!--\s*shared:(\w[\w-]*)\s*-->(.*?)<!--\s*/shared:\1\s*-->",
                        re.DOTALL)


def _collect_shared(pack):
    """Internal documentation."""
    blocks = {}
    pdir = PACKS_DIR / pack
    for sub in ("agents", "rules"):
        d = pdir / sub
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.md")):
            text = f.read_text(encoding="utf-8")
            for name, body in _SHARED_RE.findall(text):
                blocks.setdefault(name, []).append((f.relative_to(pdir).as_posix(), body))
    return blocks


class TestSharedBlocksParity(unittest.TestCase):
    """Internal documentation."""

    @classmethod
    def setUpClass(cls):
        cls.bl = _collect_shared("backend-laravel")
        cls.lp = _collect_shared("laravel-package")

    def test_packs_have_shared_blocks(self):


        self.assertTrue(self.bl, "backend-laravel: ни одного shared:NAME не найдено")
        self.assertTrue(self.lp, "laravel-package: ни одного shared:NAME не найдено")

    def test_shared_names_are_byte_identical_across_packs(self):
        common = set(self.bl) & set(self.lp)
        self.assertTrue(common, "ожидались общие shared:NAME между паками (напр. risk-adaptive)")
        for name in sorted(common):



            bl_bodies = {body for _f, body in self.bl[name]}
            lp_bodies = {body for _f, body in self.lp[name]}
            self.assertEqual(
                len(bl_bodies), 1,
                f"shared:{name} расходится ВНУТРИ backend-laravel: {[f for f, _ in self.bl[name]]}")
            self.assertEqual(
                len(lp_bodies), 1,
                f"shared:{name} расходится ВНУТРИ laravel-package: {[f for f, _ in self.lp[name]]}")
            self.assertEqual(
                bl_bodies, lp_bodies,
                f"shared:{name} разошёлся между паками (backend-laravel vs laravel-package) — "
                f"перенеси правку в оба места или заведи под другим NAME, если блок больше не общий")


class TestPackageReviewerHasNoAppCanon(unittest.TestCase):
    """Internal documentation."""

    _FORBIDDEN = re.compile(r"controller|FormRequest|app/Repositories", re.IGNORECASE)

    def test_no_backend_app_terms(self):
        f = PACKS_DIR / "laravel-package" / "agents" / "reviewer.md"
        text = f.read_text(encoding="utf-8")
        hits = self._FORBIDDEN.findall(text)
        self.assertFalse(hits, f"найдены app-канон термины в laravel-package/reviewer.md: {hits}")


if __name__ == "__main__":
    unittest.main()
