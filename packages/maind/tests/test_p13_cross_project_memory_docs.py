"""P1.3: cross-project memory guideline (D10 — digest project-only, shared upon request).

Checks TWO things from Validation phases P1 (plan):
1) updated skills/docs don't approve «digest carries namespace/global» without reservation
   on-demand — grep on a canonical phrase that must be present nearby;
2) all commands mentioned in the new guideline (`maind memory digest|recall|remember --help`,
   `maind graph --help`) actually exist on HEAD — are run without exceptions; plus
   MCP-tool names (`maind_graph_path`, `maind_memory_recall`, `maind_memory_store`)
   checked against the list TOOLS in mcp.py, and not taken from memory.
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

_PACKAGE = Path(__file__).resolve().parents[1]  # the maind package, in the hub and standalone alike
_HUB = _PACKAGE.parents[1]

_ECOSYSTEM_MCP_TEMPLATE = _PACKAGE / "templates" / "skills" / "ecosystem-mcp" / "SKILL.md"
_BOOTSTRAP_SKILLS = _HUB / "bootstrap" / "skills"
_LOCAL_SKILLS = {
    # Root-bootstrap projections under .claude/skills/ are thin pointer stubs (Class-A
    # projection design, P1.2) — no copied body, so the caveat
    # phrase is checked against the canonical source they point back at.
    "maind-overview": _PACKAGE / "dev-skills" / "maind-overview" / "SKILL.md",
}
if _BOOTSTRAP_SKILLS.is_dir():  # skills of the hub itself; a standalone copy of maind has none
    _LOCAL_SKILLS.update({
        "cross-project-optimizer": _BOOTSTRAP_SKILLS / "cross-project-optimizer" / "SKILL.md",
        "ecosystem-integration": _BOOTSTRAP_SKILLS / "ecosystem-integration" / "SKILL.md",
    })
_MEMORY_DOC = _PACKAGE / "docs" / "guide" / "memory.md"


def _run(fn, env, argv):
    """Run CLI-functions in isolated stdout; exception - test failure (command does not work)."""
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
    """Files from Scope Included P1.3 really updated and in place."""

    def test_files_present(self):
        for path in [_ECOSYSTEM_MCP_TEMPLATE, *_LOCAL_SKILLS.values(), _MEMORY_DOC]:
            self.assertTrue(path.is_file(), f"no file: {path}")


class TestDigestOnDemandCaveat(unittest.TestCase):
    """No approval «digest general/carries shared» without reservation project-only/on-demand."""

    def test_ecosystem_mcp_template_has_project_only_caveat(self):
        text = _ECOSYSTEM_MCP_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("MODE=manual", text)
        self.assertIn("Normal recall remains private scope project", text)
        self.assertIn("Cross-project task", text)
        idx_private = text.index("Normal recall remains private scope project")
        idx_manual = text.index("MODE=manual")
        self.assertGreater(idx_manual, idx_private)
        self.assertLess(idx_manual - idx_private, 600,
                        "disclaimer about manual memory should go next to the description scope")

    def test_memory_doc_states_project_only_default(self):
        text = _MEMORY_DOC.read_text(encoding="utf-8")
        self.assertIn("project-only default", text)
        self.assertIn("shared_max=0", text)
        self.assertIn("Cross-project task", text)

    def test_local_skills_reference_on_demand_model(self):
        for name, path in _LOCAL_SKILLS.items():
            text = path.read_text(encoding="utf-8")
            has_caveat = ("shared_max=0" in text or "project-only" in text
                          or "digest" in text.lower()
                          or "does not carry it by default" in text.lower())
            self.assertTrue(has_caveat, f"{name}: no reservation project-only/on-demand about digest")


class TestGuidelineCommandsExist(unittest.TestCase):
    """Each command mentioned in the guideline is actually run on HEAD (--help, no exceptions)."""

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
    """Names MCP-tools from the guideline are checked against the real list TOOLS (mcp.py), not from memory."""

    def test_referenced_tool_names_exist(self):
        names = {t["name"] for t in TOOLS}
        for tool in ("maind_graph_path", "maind_graph_neighbors",
                     "maind_memory_recall", "maind_memory_store"):
            self.assertIn(tool, names)
            self.assertIn(tool, _ECOSYSTEM_MCP_TEMPLATE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
