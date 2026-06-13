"""Общие утилиты: окружение, вывод, парсинг flag'ов и frontmatter."""
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
STATE_DIR = HOME / ".swissknifeman"
DB_FILE = STATE_DIR / "projects.json"
DB_VERSION = 1
MARKETPLACE = "swissknifeman"
MANIFEST = ".swissknifeman-manifest.json"
AGENT_DEFAULTS = {"claude": ".claude/skills", "cursor": ".cursor/skills",
                  "generic": ".ai/skills"}
CONFIG_KEYS = {
    "project_type": str, "buckets": list, "exclude": list,
    "skills_path": str, "agent": str,
}
HUB_MARKER = "<!-- swissknifeman:hub:start -->"


class Env:
    """Контекст запуска: корень реестра и текущая команда.

    Раньше эти значения были модульными глобалями (root/cmd/argv). Теперь
    передаются явно — функции становятся тестируемыми (можно подсунуть
    временный корень реестра, не трогая argv процесса)."""

    def __init__(self, root, cmd="", home=None):
        self.root = Path(root)
        self.cmd = cmd
        self.home = Path(home) if home else HOME

    @property
    def state_dir(self):
        return self.home / ".swissknifeman"

    @property
    def db_file(self):
        return self.state_dir / "projects.json"


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def warn(msg):
    print(f"WARN: {msg}", file=sys.stderr)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def confirm(prompt):
    if not sys.stdin.isatty():
        return False
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")


# --- flag parsing -------------------------------------------------------------
def parse_flags(args, spec):
    """spec: {'--flag': 'str'|'bool'}; returns dict keyed by flag name sans --."""
    out = {k.lstrip("-").replace("-", "_"): ("" if t == "str" else False)
           for k, t in spec.items()}
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-h", "--help"):
            out["help"] = True
            i += 1
            continue
        if a not in spec:
            die(f"неизвестный флаг: {a}")
        key = a.lstrip("-").replace("-", "_")
        if spec[a] == "bool":
            out[key] = True
            i += 1
        else:
            if i + 1 >= len(args):
                die(f"флаг {a} требует значение")
            out[key] = args[i + 1]
            i += 2
    out.setdefault("help", False)
    return out


# --- frontmatter --------------------------------------------------------------
def parse_frontmatter(path):
    """Keys from the first ----delimited block only (body lines ignored)."""
    lines = Path(path).read_text(encoding="utf-8").replace("\r\n", "\n").splitlines()
    fm = {}
    if not lines or lines[0].strip() != "---":
        return fm
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line and not line.startswith((" ", "\t", "-")):
            key, value = line.split(":", 1)
            fm[key.strip()] = value.strip().strip('"').strip("'")
    return fm


def parse_inline_list(value):
    value = (value or "").strip()
    if not (value.startswith("[") and value.endswith("]")):
        return []
    items = [i.strip().strip('"').strip("'") for i in value[1:-1].split(",")]
    return [i for i in items if i]


def parse_frontmatter_fields(skill_md):
    """name + requires from the first ----delimited block."""
    fm = parse_frontmatter(skill_md)
    return {"name": fm.get("name", ""),
            "requires": parse_inline_list(fm.get("requires", ""))}


def sanitize(name):
    name = name.lower().replace(" ", "-").replace("_", "-")
    name = re.sub(r"[^a-z0-9-]", "", name)
    return re.sub(r"-{2,}", "-", name).strip("-")
