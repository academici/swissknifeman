"""mcp — влить пресеты MCP-серверов в <project>/.mcp.json, merge-only.

Пресет сервера — configs/claude-code/mcp/<name>.json (голый объект конфига
сервера). Существующие записи mcpServers не затираются, бэкап *.bak."""
import json

from .common import die, parse_flags, warn
from .settings import write_json


def available_mcp(env):
    """Имена доступных MCP-пресетов (configs/claude-code/mcp/<name>.json)."""
    d = env.mcp_dir
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


def parse_mcp_flag(raw):
    """'a,b,c' → ['a','b','c'] (trim, без пустых)."""
    return [s.strip() for s in raw.split(",") if s.strip()] if raw else []


def block_mcp(env, target, servers, dry):
    """Влить пресеты MCP-серверов в <project>/.mcp.json, merge-only."""
    servers = servers or []
    print(f"MCP-серверы: {', '.join(servers) if servers else 'пропуск'}")
    if not servers:
        return
    f = target / ".mcp.json"
    data = {}
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            die(f"{f}: невалидный JSON: {e}")
    mcp = data.setdefault("mcpServers", {})
    added = []
    for name in servers:
        preset = env.mcp_dir / f"{name}.json"
        if not preset.exists():
            warn(f"  нет пресета MCP '{name}' ({preset}) — пропуск")
            continue
        if name in mcp:
            print(f"  MCP '{name}' уже в .mcp.json — пропуск")
            continue
        mcp[name] = json.loads(preset.read_text(encoding="utf-8"))
        added.append(name)
    if added:
        write_json(f, data, dry)
        print(f"  добавлены MCP: {', '.join(added)}")


def cmd_mcp(env, argv):
    opts = parse_flags(argv, {
        "--target": "str", "--mcp": "str", "--list": "bool", "--dry-run": "bool",
    })
    if opts["help"]:
        print("harness mcp [--target P] [--mcp name1,name2] [--list] [--dry-run]")
        return
    if opts["list"]:
        for name in available_mcp(env):
            print(name)
        return
    if not opts["target"]:
        die("нужен --target P (или --list)")
    from pathlib import Path
    block_mcp(env, Path(opts["target"]).expanduser(),
              parse_mcp_flag(opts["mcp"]), opts["dry_run"])
