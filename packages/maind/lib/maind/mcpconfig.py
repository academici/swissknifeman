"""Safe merge MCP-project configs (.mcp.json / .cursor/mcp.json / .vscode/mcp.json).

Provisioning maind adds his MCP-servers into the project, NOT overwriting others (for example
laravel-boost). Merge is idempotent (restarting does not change anything), before recording -
.bak. This is the most security-sensitive primitive - isolated and covered with tests."""
import json
import os
import subprocess
from pathlib import Path

from .common import atomic_write_json, backup_file, warn

EXAMPLE_SUFFIX = ".example"

# Where do they put which agents? MCP-servers.
MCP_FILES = {
    "claude": ".mcp.json",
    "cursor": ".cursor/mcp.json",
    "vscode": ".vscode/mcp.json",
}


class MCPConfigError(Exception):
    """Broken/incorrect MCP-channel config. load_mcp picks it up instead die, to
    The CALLER was deciding whether to drop the entire team or skip only this channel (one
    broken sibling-file like .cursor/mcp.json shouldn't blame the whole fan-out sync)."""


def mcp_path(project_path, channel):
    return Path(project_path) / MCP_FILES[channel]


def load_mcp(path):
    """(data, existed). Missing → ({"mcpServers":{}}, False). Broken JSON / non-object →
    MCPConfigError (DO NOT touch the file; the caller decides fatality)."""
    path = Path(path)
    if not path.exists():
        return {"mcpServers": {}}, False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise MCPConfigError(
            f"{path}: broken JSON MCP-config - I don’t touch it, fix it manually: {e}") from e
    if not isinstance(data, dict):
        raise MCPConfigError(f"{path}: object expected MCP-config")
    data.setdefault("mcpServers", {})
    return data, True


def merge_server(data, name, entry):
    """Upsert mcpServers[name]=entry. Returns (data, changed). changed=False if identical."""
    servers = data.setdefault("mcpServers", {})
    if servers.get(name) == entry:
        return data, False
    servers[name] = entry
    return data, True


def remove_server(data, name):
    """Delete mcpServers[name], if available. Returns (data, changed)."""
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
    """Recursively replace machine-specific absolute paths to placeholders (for .example):
    project path → <ABS_PATH_TO_PROJECT> (more specific, replace with the first), home prefix
    → <HOME> (catches the others home-based paths of other servers). Direction like
    ${MAIND_BIN:-maind} is not touched - it is already portable."""
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
    """Issue <real_path>.example with placeholders instead machine-specific abs. ways -
    portable map MCP-structures (is committed, unlike the real file). One
    generator → two outputs from one `data`: discrepancy real↔.example not possible by design.
    Idempotent: if there is a match with already written contents, the file is not overwritten (in `dry`
    nothing is printed). Returns `changed` (bool)."""
    home = os.path.expanduser("~")
    example = _placeholderize(data, str(project_root), home)
    ex_path = Path(str(real_path) + EXAMPLE_SUFFIX)
    if ex_path.is_file():
        try:
            existing = json.loads(ex_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = None
        if existing == example:
            return False
    if dry:
        print(f"[dry-run] {ex_path} (placeholders machine-specific paths)")
        return True
    atomic_write_json(ex_path, example)
    return True


def _is_tracked(project_root, rel):
    """True, if rel is already in the index git project (best-effort — no git/error → False)."""
    try:
        return subprocess.run(
            ["git", "-C", str(project_root), "ls-files", "--error-unmatch", rel],
            capture_output=True).returncode == 0
    except OSError:
        return False


def reconcile_gitignore(project_root, rel_real, *, dry=False):
    """Hygiene .gitignore for pair real↔.example: real MCP-config - B .gitignore
    (append-if-absent, he has machine-specific paths), him `.example` — NOT in .gitignore
    (remove-if-present, otherwise the template being ported will not be committed). Idempotent. If
    real file is already being tracked git — warn (we don't `git rm` silently). Returns changed."""
    gi = Path(project_root) / ".gitignore"
    rel_example = rel_real + EXAMPLE_SUFFIX
    lines = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    out, changed = [], False
    for ln in lines:
        if ln.strip() == rel_example:          # .example should NOT be ignored
            changed = True
            continue
        out.append(ln)
    if rel_real not in [ln.strip() for ln in out]:   # real - should
        out.append(rel_real)
        changed = True
    if not changed:
        return False
    if dry:
        print(f"[dry-run] {gi}: + {rel_real}, − {rel_example}")
        return True
    if _is_tracked(project_root, rel_real):
        warn(f"{rel_real} is already tracking git in {project_root} — added to .gitignore, "
             f"but `git rm --cached {rel_real}` do it yourself")
    gi.write_text("\n".join(out) + "\n", encoding="utf-8")
    return True


def check_hygiene(project_root):
    """Read-only snapshot real↔.example hygiene `.mcp.json` project (without network/writes to disk):
    is it trackable? git and is there `.example`. Only claude-channel - `.cursor`/`.vscode` not maind-
    default targets (project.mcp.targets) and often do not contain machine-specific paths at all
    (e.g. clean `php artisan boost:mcp`), testing them blindly produces noise without benefit.
    Source of hints `maind health`: tracked-in-git repaired manually (git rm --cached, hygiene
    above does not automate this), missing-example repairs `maind sync --only mcp`
    (default-on — config.mcp.emit_example=false turns off, see provision/deploy.py) — but
    only if the provider project plan is green: failed `unmanaged-target` emissions
    does not receive."""
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
    """True, if in MCP-config by path there is a server name (read-only; broken/no file → False)."""
    path = Path(path)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return name in (data.get("mcpServers") or {})
