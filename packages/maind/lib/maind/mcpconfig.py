"""Безопасное слияние MCP-конфигов проекта (.mcp.json / .cursor/mcp.json / .vscode/mcp.json).

Провижининг maind дописывает свои MCP-серверы в проект, НЕ затирая чужие (например
laravel-boost). Слияние идемпотентно (повторный запуск ничего не меняет), перед записью —
.bak. Это самый чувствительный к безопасности примитив — выделен и покрыт тестами."""
import json
from pathlib import Path

from .common import atomic_write_json, backup_file

# Куда какие агенты кладут MCP-серверы.
MCP_FILES = {
    "claude": ".mcp.json",
    "cursor": ".cursor/mcp.json",
    "vscode": ".vscode/mcp.json",
}


class MCPConfigError(Exception):
    """Битый/некорректный MCP-конфиг канала. load_mcp поднимает его вместо die, чтобы
    ВЫЗЫВАЮЩИЙ решал: уронить команду целиком или пропустить только этот канал (один
    битый sibling-файл вроде .cursor/mcp.json не должен валить весь фан-аут sync)."""


def mcp_path(project_path, channel):
    return Path(project_path) / MCP_FILES[channel]


def load_mcp(path):
    """(data, existed). Отсутствует → ({"mcpServers":{}}, False). Битый JSON / не-объект →
    MCPConfigError (файл НЕ трогаем; вызывающий решает фатальность)."""
    path = Path(path)
    if not path.exists():
        return {"mcpServers": {}}, False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise MCPConfigError(
            f"{path}: битый JSON MCP-конфига — не трогаю, исправьте вручную: {e}")
    if not isinstance(data, dict):
        raise MCPConfigError(f"{path}: ожидался объект MCP-конфига")
    data.setdefault("mcpServers", {})
    return data, True


def merge_server(data, name, entry):
    """Upsert mcpServers[name]=entry. Возвращает (data, changed). changed=False если идентично."""
    servers = data.setdefault("mcpServers", {})
    if servers.get(name) == entry:
        return data, False
    servers[name] = entry
    return data, True


def remove_server(data, name):
    """Удалить mcpServers[name], если есть. Возвращает (data, changed)."""
    servers = data.get("mcpServers")
    if isinstance(servers, dict) and name in servers:
        del servers[name]
        return data, True
    return data, False


def write_mcp(path, data, *, dry=False, backup=True):
    path = Path(path)
    if dry:
        print(f"[dry-run] {path}:\n"
              + json.dumps(data, ensure_ascii=False, indent=2))
        return
    if backup and path.exists():
        backup_file(path)
    atomic_write_json(path, data)


def has_server(path, name):
    """True, если в MCP-конфиге по path есть сервер name (read-only; битый/нет файла → False)."""
    path = Path(path)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return name in (data.get("mcpServers") or {})
