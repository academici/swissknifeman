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


def make_pack(root, name="demo-pack"):
    """Синтетический agent-pack под configs/claude-code/agent-packs/<name>/:
    шаблон-агент, verbatim-хук (chmod +x), merge-фрагмент SubagentStop, pack:if-блок,
    user_owned override-файл (точка расширения для provenance-header)."""
    import json
    pdir = root / "configs" / "claude-code" / "agent-packs" / name
    (pdir / "agents").mkdir(parents=True, exist_ok=True)
    (pdir / "hooks").mkdir(parents=True, exist_ok=True)
    (pdir / "settings").mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": 1, "pack": name, "version": "0.1.0", "description": "test pack",
        "stack": {"shape": "backend", "detect": {"project_type": "php-package"}},
        "requires": {"skills": ["x"], "harness_presets": ["base"]},
        "interview": [
            {"id": "PACK_PREFIX", "q": "?", "default": "{project_dirname}", "kind": "slug"},
            {"id": "RUNNER", "q": "?", "detect": "composer.json:scripts.test",
             "default": "phpunit"},
            {"id": "USE_X", "q": "?", "kind": "bool", "default": True},
        ],
        "files": [
            {"src": "agents/reviewer.md",
             "target": ".claude/agents/{PACK_PREFIX}-reviewer.md",
             "kind": "template", "role": "agent"},
            {"src": "hooks/gate.sh", "target": ".claude/hooks/gate.sh",
             "kind": "verbatim", "role": "hook", "chmod": "+x"},
            {"src": "settings/fragment.json", "target": ".claude/settings.json",
             "kind": "merge", "role": "settings",
             "merge": "hooks.SubagentStop[] append-if-absent"},
            {"src": "agents/overrides.md",
             "target": ".claude/agents/{PACK_PREFIX}-overrides.md",
             "kind": "template", "role": "override", "user_owned": True},
        ],
    }
    (pdir / "pack.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    (pdir / "agents" / "reviewer.md").write_text(
        "---\nname: {{PACK_PREFIX}}-reviewer\nrunner: {{RUNNER}}\n---\n"
        "<!-- pack:if USE_X -->X-on<!-- pack:endif -->\nbody\n")
    (pdir / "agents" / "overrides.md").write_text(
        "# Overrides для {{PACK_PREFIX}}\n\n(файл пользователя)\n")
    (pdir / "hooks" / "gate.sh").write_text("#!/usr/bin/env bash\necho gate\n")
    (pdir / "settings" / "fragment.json").write_text(json.dumps(
        {"hooks": {"SubagentStop": [{"hooks": [
            {"type": "command", "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/gate.sh"}]}]}}))
    return name


def make_src_pack_pair(root, name_a="demo-pack", name_b="demo-pack-b"):
    """Пак B без собственных файлов — единственная files[]-запись несёт
    `src_pack: name_a`, контент читается из каталога пака A (F-1 src_pack).
    Владелец файла (Pack: в header) при этом — B, не A."""
    pdir = root / "configs" / "claude-code" / "agent-packs" / name_b
    pdir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": 1, "pack": name_b, "version": "0.1.0", "description": "src_pack test",
        "interview": [
            {"id": "PACK_PREFIX", "q": "?", "default": "{project_dirname}", "kind": "slug"},
            {"id": "RUNNER", "q": "?", "default": "phpunit"},
            {"id": "USE_X", "q": "?", "kind": "bool", "default": True},
        ],
        "files": [
            {"src": "agents/reviewer.md", "src_pack": name_a,
             "target": ".claude/agents/{PACK_PREFIX}-shared.md",
             "kind": "template", "role": "agent"},
        ],
    }
    (pdir / "pack.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return name_b
