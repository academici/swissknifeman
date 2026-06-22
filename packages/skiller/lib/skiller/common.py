"""Общие утилиты: окружение, вывод, парсинг flag'ов и frontmatter.

Дословно общий с maind/brain код (die/warn/now_iso/confirm/sanitize + ядро Env)
вынесен в общий core; здесь — только специфика swissknifeman (path-property,
parse_flags, frontmatter, apply_permissions, константы реестра)."""
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Общий core (подключается через PYTHONPATH лаунчером/test.sh). Реэкспорт для
# модулей пакета, которые исторически берут эти имена из .common.
from core import (  # noqa: F401
    HOME, BaseEnv, confirm, die, now_iso, sanitize, warn,
)

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
    "memory_brain": str, "coordinator_ignore": list,
}
HUB_MARKER = "<!-- swissknifeman:hub:start -->"


@dataclass(frozen=True)
class Env(BaseEnv):
    """Контекст запуска swissknifeman: ядро (root/cmd/home) — из BaseEnv;
    здесь только path-property реестра (state ~/.swissknifeman)."""

    @property
    def state_dir(self):
        return self.home / ".swissknifeman"

    @property
    def db_file(self):
        return self.state_dir / "projects.json"

    @property
    def topology_file(self):
        return self.state_dir / "topology.json"


def apply_permissions(env, target, presets="", dry_run=False, settings_file=None):
    """Влить permissions-пресеты в .claude цели через scripts/apply-permissions.sh.
    presets="" → автодетект стека внутри скрипта. settings_file=None → дефолт
    скрипта (settings.local.json). Возвращает True, если скрипт запущен."""
    script = env.root / "scripts" / "apply-permissions.sh"
    if not script.exists():
        warn("scripts/apply-permissions.sh не найден — пропуск permissions")
        return False
    cmd = ["bash", str(script), "--target", str(target)]
    if presets:
        cmd += ["--preset", presets]
    if settings_file:
        cmd += ["--file", settings_file]
    if dry_run:
        cmd.append("--dry-run")
    sys.stdout.flush()
    subprocess.run(cmd, check=False)
    return True


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
