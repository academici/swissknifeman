"""Безопасное слияние MCP-конфигов проекта (.mcp.json / .cursor/mcp.json / .vscode/mcp.json).

Провижининг maind дописывает свои MCP-серверы в проект, НЕ затирая чужие (например
laravel-boost). Слияние идемпотентно (повторный запуск ничего не меняет), перед записью —
.bak. Это самый чувствительный к безопасности примитив — выделен и покрыт тестами."""
import json
import os
import subprocess
from pathlib import Path

from .common import atomic_write_json, backup_file, warn

EXAMPLE_SUFFIX = ".example"

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
            f"{path}: битый JSON MCP-конфига — не трогаю, исправьте вручную: {e}") from e
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


def _placeholderize(obj, project_root, home):
    """Рекурсивно заменить machine-specific абсолютные пути на плейсхолдеры (для .example):
    путь проекта → <ABS_PATH_TO_PROJECT> (специфичнее, заменяем первым), домашний префикс
    → <HOME> (ловит остальные home-based пути чужих серверов). Индирекция вроде
    ${MAIND_BIN:-maind} не трогается — она и так портируема."""
    if isinstance(obj, str):
        s = obj
        if project_root:
            s = s.replace(project_root, "<ABS_PATH_TO_PROJECT>")
        if home:
            s = s.replace(home, "<HOME>")
        return s
    if isinstance(obj, list):
        return [_placeholderize(x, project_root, home) for x in obj]
    if isinstance(obj, dict):
        return {k: _placeholderize(v, project_root, home) for k, v in obj.items()}
    return obj


def write_example(real_path, data, project_root, *, dry=False):
    """Эмитит <real_path>.example с плейсхолдерами вместо machine-specific абс. путей —
    портируемая карта MCP-структуры (коммитится, в отличие от реального файла). Один
    генератор → два выхода из одного `data`: расхождение real↔.example невозможно by design."""
    home = os.path.expanduser("~")
    example = _placeholderize(data, str(project_root), home)
    ex_path = Path(str(real_path) + EXAMPLE_SUFFIX)
    if dry:
        print(f"[dry-run] {ex_path} (плейсхолдеры machine-specific путей)")
        return
    atomic_write_json(ex_path, example)


def _is_tracked(project_root, rel):
    """True, если rel уже в индексе git проекта (best-effort — нет git/ошибка → False)."""
    try:
        return subprocess.run(
            ["git", "-C", str(project_root), "ls-files", "--error-unmatch", rel],
            capture_output=True).returncode == 0
    except OSError:
        return False


def reconcile_gitignore(project_root, rel_real, *, dry=False):
    """Гигиена .gitignore для пары real↔.example: реальный MCP-конфиг — В .gitignore
    (append-if-absent, у него machine-specific пути), его `.example` — НЕ в .gitignore
    (remove-if-present, иначе портируемый шаблон не закоммитится). Идемпотентно. Если
    реальный файл уже трекается git — warn (не делаем `git rm` молча). Возвращает changed."""
    gi = Path(project_root) / ".gitignore"
    rel_example = rel_real + EXAMPLE_SUFFIX
    lines = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    out, changed = [], False
    for ln in lines:
        if ln.strip() == rel_example:          # .example НЕ должен игнориться
            changed = True
            continue
        out.append(ln)
    if rel_real not in [ln.strip() for ln in out]:   # реальный — должен
        out.append(rel_real)
        changed = True
    if not changed:
        return False
    if dry:
        print(f"[dry-run] {gi}: + {rel_real}, − {rel_example}")
        return True
    if _is_tracked(project_root, rel_real):
        warn(f"{rel_real} уже трекается git в {project_root} — добавил в .gitignore, "
             f"но `git rm --cached {rel_real}` сделай сам")
    gi.write_text("\n".join(out) + "\n", encoding="utf-8")
    return True


def check_hygiene(project_root):
    """Read-only снимок real↔.example гигиены `.mcp.json` проекта (без сети/записи на диск):
    трекается ли git и есть ли `.example`. Только claude-канал — `.cursor`/`.vscode` не maind-
    таргеты по умолчанию (project.mcp.targets) и часто не содержат machine-specific путей вовсе
    (напр. чистый `php artisan boost:mcp`), проверка их вслепую даёт шум без пользы.
    Источник хинтов `maind health`: tracked-in-git чинится вручную (git rm --cached, гигиена
    выше это не автоматизирует), missing-example чинит `maind sync --only mcp`
    (default-on — config.mcp.emit_example=false выключает, см. provision/deploy.py)."""
    rel = MCP_FILES["claude"]
    path = Path(project_root) / rel
    if not path.is_file():
        return []
    problems = []
    if _is_tracked(project_root, rel):
        problems.append("tracked-in-git")
    if not Path(str(path) + EXAMPLE_SUFFIX).is_file():
        problems.append("missing-example")
    return [{"channel": "claude", "file": rel, "problems": problems}] if problems else []


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
