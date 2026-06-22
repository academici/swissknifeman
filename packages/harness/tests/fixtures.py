"""Синтетические фикстуры для тестов harness (изоляция в tmpdir).

make_root — мини-«пакет» с пресетами MCP (как configs/claude-code/mcp/);
make_project — пустой целевой проект. real_root — настоящий корень пакета
(для e2e-проверки реального scripts/apply-permissions.sh в dry-run)."""
import json
from pathlib import Path

from harness.common import Env

PACKAGE_ROOT = Path(__file__).resolve().parents[1]  # packages/harness


def make_root(tmp):
    """Мини-root с пресетами MCP context7/playwright и tmp-home (изоляция ~/.claude)."""
    root = tmp / "harness"
    mcpd = root / "configs" / "claude-code" / "mcp"
    mcpd.mkdir(parents=True, exist_ok=True)
    (mcpd / "context7.json").write_text(json.dumps(
        {"type": "http", "url": "https://mcp.context7.com/mcp"}) + "\n")
    (mcpd / "playwright.json").write_text(json.dumps(
        {"command": "npx", "args": ["@playwright/mcp@latest", "--headless"]}) + "\n")
    home = tmp / "home"
    home.mkdir(exist_ok=True)
    return root, Env(root, "test", home=home)


def real_env(tmp):
    """Env с НАСТОЯЩИМ корнем пакета (реальные пресеты + apply-permissions.sh),
    но tmp-home — для e2e проверки скрипта без касания ~/.claude."""
    home = tmp / "home"
    home.mkdir(exist_ok=True)
    return Env(PACKAGE_ROOT, "test", home=home)


def make_project(tmp, name="proj"):
    p = tmp / name
    p.mkdir(parents=True, exist_ok=True)
    return p
