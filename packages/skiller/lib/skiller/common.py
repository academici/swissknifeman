"""Общие утилиты: окружение, вывод, парсинг flag'ов и frontmatter.

Дословно общий с maind/brain код (die/warn/now_iso/confirm/sanitize + ядро Env)
вынесен в общий core; здесь — только специфика swissknifeman (path-property,
parse_flags, frontmatter, делегирование окружения в harness, константы реестра)."""
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Общий core (подключается через PYTHONPATH лаунчером/test.sh). Реэкспорт для
# модулей пакета, которые исторически берут эти имена из .common.
from core import (  # noqa: F401
    HOME, BaseEnv, confirm, die, find_monorepo_root, now_iso, parse_flags,
    run_cmd, safe_load_json, sanitize, warn,
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
    # Профиль каркаса агентов (данные для agent-packs/универсальности, не движок):
    # shape — backend|frontend|fullstack; stacks — напр. ["laravel","vue"];
    # skills_map — домен→скиллы для преднагрузки ролей под стек.
    "shape": str, "stacks": list, "skills_map": dict,
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


def harness_bin(env):
    """Путь к лаунчеру пакета `harness` (настройка окружения вынесена туда).
    Резолв: env-override `SKM_HARNESS_BIN` → `<монорепо>/packages/harness/bin/harness`.
    None, если пакет не найден (standalone-раскладка / harness не установлен)."""
    override = os.environ.get("SKM_HARNESS_BIN")
    if override:
        p = Path(os.path.expanduser(override))
        return p if p.exists() else None
    mono = find_monorepo_root(env.root)
    if not mono:
        return None
    p = mono / "packages" / "harness" / "bin" / "harness"
    return p if p.exists() else None


def apply_permissions(env, target, presets="", dry_run=False, settings_file=None):
    """Влить permissions-пресеты в .claude цели — делегируется пакету `harness`.
    Окружение Claude Code (permissions/MCP/хуки) вынесено в отдельный пакет; skiller
    зовёт `harness permissions` через subprocess. presets="" → автодетект стека.
    Возвращает True, если harness запущен; False (с warn) — если harness не установлен."""
    binp = harness_bin(env)
    if binp is None:
        warn("harness не установлен — пропуск permissions "
             "(установите: packages/harness/install.sh)")
        return False
    cmd = [str(binp), "permissions", "--target", str(target)]
    if presets:
        cmd += ["--preset", presets]
    if settings_file:
        cmd += ["--file", settings_file]
    if dry_run:
        cmd.append("--dry-run")
    sys.stdout.flush()
    # timeout: завис harness (NFS/сеть) не должен морозить `skiller sync` молча.
    # stderr ловим в warn; stdout оставляем живым (harness печатает прогресс сам).
    try:
        result = subprocess.run(cmd, check=False, timeout=30,
                                stderr=subprocess.PIPE, text=True)
    except subprocess.TimeoutExpired:
        warn("harness: превышен таймаут 30s — permissions могли не примениться")
        return True
    if result.returncode != 0 and result.stderr:
        warn(f"harness: {result.stderr.strip()}")
    return True


# parse_flags — из общего core (реэкспорт выше); раньше дублировался здесь.


# --- frontmatter --------------------------------------------------------------
def parse_frontmatter(path):
    """Keys from the first ----delimited block only (body lines ignored).

    Поддержаны YAML-блок-скаляры `key: |` / `key: >` (с опц. чомпом |-, >-, |+):
    последующие отступные строки собираются в значение (| — с переносами, > —
    через пробел). Иначе `description: |` молча терялся бы. Stdlib-only, без pyyaml."""
    # utf-8-sig: срезает BOM, если есть (иначе `﻿---` != `---` и весь
    # frontmatter молча игнорируется); без BOM ведёт себя как обычный utf-8.
    lines = Path(path).read_text(encoding="utf-8-sig").replace("\r\n", "\n").splitlines()
    fm = {}
    if not lines or lines[0].strip() != "---":
        return fm
    i = 1
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            break
        if ":" in line and not line.startswith((" ", "\t", "-")):
            key, value = line.split(":", 1)
            key, value = key.strip(), value.strip()
            # Блок-скаляр только если value — ровно заголовок |/> (+ опц. чомп/
            # индент-индикатор), а не описание, начинающееся с этих символов
            # ("description: > см. ниже" — обычный скаляр, не блок).
            if value[:1] in ("|", ">") and all(c in "+-0123456789"
                                               for c in value[1:]):
                block, i = _collect_block_scalar(lines, i + 1)
                fm[key] = (" " if value[0] == ">" else "\n").join(block)
                continue
            fm[key] = value.strip('"').strip("'")
        i += 1
    return fm


def _collect_block_scalar(lines, start):
    """Собрать отступные строки YAML-блок-скаляра начиная с lines[start].
    Возвращает (строки без общего отступа, индекс первой неотступной строки).
    Пустые строки сохраняются как переносы; хвостовые — обрезаются (clip-чомп)."""
    block = []
    i = start
    while i < len(lines):
        ln = lines[i]
        if ln.strip() == "---":
            break
        if ln.strip() == "":
            block.append("")
        elif ln.startswith((" ", "\t")):
            block.append(ln.strip())
        else:
            break
        i += 1
    while block and block[-1] == "":
        block.pop()
    return block, i


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
