"""Fleet-аудит оптимизаций по зарегистрированным проектам (read-only, fail-soft).

Контрольная поверхность хаба: показывает, ГДЕ раздача оптимизаций неполна —
- mcp:    активные MCP-серверы проекта (+ кандидаты на ревизию: каждая схема
          грузится в КАЖДЫЙ запрос, см. context-economy §MCP-аудит);
- claude: размер CLAUDE.md (>200 строк — постоянный налог на контекст сессии);
- deny:   есть ли permissions.deny (блок мусора _ide_helper/*.lock из контекста);
- core:   доехали ли CORE-скиллы токен-экономии (раздаёт swissknifeman).

Ничего не пишет на диск — только читает файлы проектов. Источник списка —
projects.listing (та же модель, что projects/status)."""
import json
import os
from pathlib import Path

from . import codegraph
from .mcpconfig import MCP_FILES
from .projects import listing

DIMS = ("mcp", "claude", "deny", "core")
CLAUDE_MD_WARN = 200  # ориентир Anthropic (context-economy ось 1)
CORE_SKILLS = ("context-economy", "anti-drift", "compact-responses",
               "session-handoff", "gh-review")
# Серверы, которые maind раскатывает штатно — не кандидаты на ревизию.
HUB_MCP = {"agentmemory", "maind"}


def _mcp_servers(path):
    """Имена всех MCP-серверов проекта по всем конфигам (dedup, fail-soft)."""
    names = set()
    for rel in MCP_FILES.values():
        f = path / rel
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            names |= set((data.get("mcpServers") or {}).keys())
    return sorted(names)


def _claude_md_lines(path):
    f = path / "CLAUDE.md"
    if not f.is_file():
        return None
    try:
        return f.read_text(encoding="utf-8").count("\n") + 1
    except OSError:
        return None


def _deny_present(path):
    """permissions.deny непуст в любом из .claude/settings(.local).json."""
    for name in ("settings.json", "settings.local.json"):
        f = path / ".claude" / name
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict) and (data.get("permissions") or {}).get("deny"):
            return True
    return False


def _present_skills(path):
    """Имена установленных скиллов: skills-lock.json + каталоги .claude/.ai skills."""
    names = set()
    lock = path / "skills-lock.json"
    if lock.is_file():
        try:
            data = json.loads(lock.read_text(encoding="utf-8"))
            names |= set((data.get("skills") or {}).keys())
        except (json.JSONDecodeError, OSError):
            pass
    for base in (path / ".claude" / "skills", path / ".ai" / "skills"):
        if base.is_dir():
            names |= {d.name for d in base.iterdir() if d.is_dir()}
    return names


def audit_project(env, project, dims, code_st):
    pid = project["id"]
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    row = {"id": pid, "path": local}
    if not path or not path.is_dir():
        row["status"] = "missing-path"
        return row
    row["status"] = "ok"
    if "mcp" in dims:
        servers = _mcp_servers(path)
        known = HUB_MCP | {codegraph.server_name(project, code_st)}
        row["mcp"] = {"servers": servers,
                      "review": [s for s in servers if s not in known]}
    if "claude" in dims:
        row["claude_md_lines"] = _claude_md_lines(path)
    if "deny" in dims:
        row["deny"] = _deny_present(path)
    if "core" in dims:
        present = _present_skills(path)
        row["core"] = {"missing": [s for s in CORE_SKILLS if s not in present]}
    return row


def run_audit(env, config, dim, as_json=False):
    """dim ∈ mcp|claude|deny|core|all (или пусто → all). Печатает отчёт."""
    dims = DIMS if dim in (None, "", "all") else (dim,)
    bad = [d for d in dims if d not in DIMS]
    if bad:
        from .common import die
        die(f"--audit: {', '.join(bad)} (доступно: {', '.join(DIMS)}, all)")
    code_st = codegraph.settings(config)
    projs = listing(env, config)
    rows = [audit_project(env, p, dims, code_st) for p in projs]
    if as_json:
        print(json.dumps({"dims": list(dims), "projects": rows},
                         ensure_ascii=False, indent=2))
        return
    print(f"maind audit ({', '.join(dims)}) — проектов: {len(rows)}")
    if not rows:
        print("  проектов нет — .maind.json пуст или отсутствует")
        return
    for r in rows:
        if r.get("status") == "missing-path":
            print(f"  {r['id']:<18} [missing-path] {r.get('path')}")
            continue
        parts = []
        if "mcp" in dims:
            review = r["mcp"]["review"]
            seg = f"mcp={len(r['mcp']['servers'])}"
            if review:
                seg += f"⚠(ревизия: {', '.join(review)})"
            parts.append(seg)
        if "claude" in dims:
            n = r["claude_md_lines"]
            seg = "claude.md=" + ("—" if n is None else str(n))
            if n and n > CLAUDE_MD_WARN:
                seg += f"⚠>{CLAUDE_MD_WARN}"
            parts.append(seg)
        if "deny" in dims:
            parts.append("deny" + ("✓" if r["deny"] else "✗"))
        if "core" in dims:
            miss = r["core"]["missing"]
            parts.append("core✓" if not miss else f"core⚠(нет: {', '.join(miss)})")
        print(f"  {r['id']:<18} " + "  ".join(parts))
