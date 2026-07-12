"""P1.3: гайдлайн межпроектной памяти (D10 — digest project-only, shared по запросу).

Проверяет ДВЕ вещи из Validation фазы P1 (плана 2026.07.12-CONTEXT-ECONOMY):
1) обновлённые скиллы/доки не утверждают «digest несёт namespace/global» без оговорки
   on-demand — грепом по канонической фразе, которая обязана присутствовать рядом;
2) все команды, упомянутые в новом гайдлайне (`maind memory digest|recall|remember --help`,
   `maind graph --help`) реально существуют на HEAD — прогоняются без исключений; плюс
   MCP-имена инструментов (`maind_graph_path`, `maind_memory_recall`, `maind_memory_store`)
   сверены со списком TOOLS в mcp.py, а не взяты по памяти.
"""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from maind.memory import cmd_memory
from maind.graph import cmd_graph
from maind.mcp import TOOLS
from tests.fixtures import make_repo, write_maind_config

_REPO_ROOT = Path(__file__).resolve().parents[3]  # .../packages/maind/tests → repo root

_ECOSYSTEM_MCP_TEMPLATE = (_REPO_ROOT / "packages" / "maind" / "templates" / "skills"
                           / "ecosystem-mcp" / "SKILL.md")
_LOCAL_SKILLS = {
    "maind-overview": _REPO_ROOT / ".claude" / "skills" / "maind-overview" / "SKILL.md",
    "cross-project-optimizer": _REPO_ROOT / ".claude" / "skills" / "cross-project-optimizer"
                                / "SKILL.md",
    "ecosystem-integration": _REPO_ROOT / ".claude" / "skills" / "ecosystem-integration"
                              / "SKILL.md",
}
_MEMORY_DOC = _REPO_ROOT / "packages" / "maind" / "docs" / "guide" / "memory.md"


def _run(fn, env, argv):
    """Прогон CLI-функции в изолированном stdout; исключение — провал теста (команда не работает)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(env, argv)
    return buf.getvalue()


def _env():
    tmp = tempfile.mkdtemp()
    root, env = make_repo(tmp)
    write_maind_config(root)
    return env


class TestGuidelineDocsExist(unittest.TestCase):
    """Файлы из Scope Included P1.3 реально обновлены и на месте."""

    def test_files_present(self):
        for path in [_ECOSYSTEM_MCP_TEMPLATE, *_LOCAL_SKILLS.values(), _MEMORY_DOC]:
            self.assertTrue(path.is_file(), f"нет файла: {path}")


class TestDigestOnDemandCaveat(unittest.TestCase):
    """Нет утверждения «digest общий/несёт shared» без оговорки project-only/on-demand."""

    def test_ecosystem_mcp_template_has_project_only_caveat(self):
        text = _ECOSYSTEM_MCP_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("shared_max=0", text)
        self.assertIn("Межпроектная задача", text)
        # оговорка должна идти сразу после утверждения «память общая внутри namespace»
        idx_shared = text.index("Память **общая внутри namespace**")
        idx_caveat = text.index("Дайджест на старте сессии — только свой проект")
        self.assertGreater(idx_caveat, idx_shared)
        self.assertLess(idx_caveat - idx_shared, 400, "оговорка про digest должна идти сразу рядом")

    def test_memory_doc_states_project_only_default(self):
        text = _MEMORY_DOC.read_text(encoding="utf-8")
        self.assertIn("project-only по умолчанию", text)
        self.assertIn("shared_max=0", text)
        self.assertIn("Межпроектная задача", text)

    def test_local_skills_reference_on_demand_model(self):
        for name, path in _LOCAL_SKILLS.items():
            text = path.read_text(encoding="utf-8")
            has_caveat = ("shared_max=0" in text or "project-only" in text
                          or "дайджест" in text.lower())
            self.assertTrue(has_caveat, f"{name}: нет оговорки project-only/on-demand про digest")


class TestGuidelineCommandsExist(unittest.TestCase):
    """Каждая команда, упомянутая в гайдлайне, реально прогоняется на HEAD (--help, без исключений)."""

    def test_memory_digest_help(self):
        env = _env()
        out = _run(cmd_memory, env, ["digest", "--help"])
        self.assertIn("digest", out)

    def test_memory_recall_help(self):
        env = _env()
        out = _run(cmd_memory, env, ["recall", "--help"])
        self.assertIn("recall", out)
        self.assertIn("--scope", out)

    def test_memory_remember_help(self):
        env = _env()
        out = _run(cmd_memory, env, ["remember", "--help"])
        self.assertIn("remember", out)
        self.assertIn("--scope", out)

    def test_graph_help_documents_project_shortform(self):
        env = _env()
        out = _run(cmd_graph, env, ["--help"])
        self.assertIn("--project", out)


class TestMcpToolNamesMatchGuideline(unittest.TestCase):
    """Имена MCP-инструментов из гайдлайна сверены с реальным списком TOOLS (mcp.py), не по памяти."""

    def test_referenced_tool_names_exist(self):
        names = {t["name"] for t in TOOLS}
        for tool in ("maind_graph_path", "maind_graph_neighbors",
                     "maind_memory_recall", "maind_memory_store"):
            self.assertIn(tool, names)
            self.assertIn(tool, _ECOSYSTEM_MCP_TEMPLATE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
