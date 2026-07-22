"""Регрессионный cap-тест description'ов агентов всех agent-packs (P4.2): анти-реблоат
после диеты P4.1 (reviewer.md рос 0b7fca8→4e3af7b без контроля размера). Парсер
frontmatter — единый `core.parse_frontmatter` (тот же, что использует `router.py`),
дубль не заводим."""
import tempfile
import unittest
from pathlib import Path

from core import parse_frontmatter

from tests import fixtures as fx

CAP_BYTES = 600


def _agent_files(env):
    return sorted((env.agent_packs_dir).glob("*/agents/*.md"))


def _description_len(path):
    fm = parse_frontmatter(path.read_text(encoding="utf-8"))
    return len(fm.get("description", "").encode("utf-8"))


class TestPackDescCap(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.env = fx.real_env(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_all_agent_descriptions_within_cap(self):
        files = _agent_files(self.env)
        self.assertGreater(len(files), 0, "не нашлись agents/*.md паков — сломан путь?")
        offenders = [(f, _description_len(f)) for f in files if _description_len(f) > CAP_BYTES]
        self.assertEqual(offenders, [],
                          f"description превышает cap {CAP_BYTES}B: "
                          + ", ".join(f"{f.relative_to(self.env.agent_packs_dir)}={n}B"
                                      for f, n in offenders))

    def test_cap_catches_bloated_description(self):
        """Негативная проверка: раздутый description ловится (тест не тавтологичен)."""
        bloated = "x" * (CAP_BYTES + 1)
        text = f"---\nname: fake\ndescription: {bloated}\n---\nbody\n"
        tmp = Path(self._tmp.name) / "fake-agent.md"
        tmp.write_text(text, encoding="utf-8")
        self.assertGreater(_description_len(tmp), CAP_BYTES)


if __name__ == "__main__":
    unittest.main()
