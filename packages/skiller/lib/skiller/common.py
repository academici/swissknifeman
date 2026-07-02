"""Общие утилиты: окружение, вывод, парсинг flag'ов и frontmatter.

Дословно общий с maind/brain код (die/warn/now_iso/confirm/sanitize + ядро Env)
вынесен в общий core; здесь — только специфика swissknifeman (path-property,
parse_flags, frontmatter, делегирование окружения в harness, константы реестра)."""
import hashlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Общий core (подключается через PYTHONPATH лаунчером/test.sh). Реэкспорт для
# модулей пакета, которые исторически берут эти имена из .common.
from core import (  # noqa: F401
    HOME, BaseEnv, atomic_write_json, atomic_write_text, confirm, die,
    find_monorepo_root, is_within, is_within_lexical, now_iso, parse_flags,
    run_cmd, safe_load_json, sanitize, state_dir, warn,
)

STATE_DIR = state_dir(HOME)
DB_FILE = STATE_DIR / "projects.json"
DB_VERSION = 1
MARKETPLACE = "swissknifeman"
MANIFEST = ".swissknifeman-manifest.json"
AGENT_DEFAULTS = {"claude": ".claude/skills", "cursor": ".cursor/skills",
                  "generic": ".ai/skills"}
# Файлы каталога скилла, которые НЕ едут в потребляющий проект ни одним каналом
# физ.переноса (vendor/sync): upstream.json и .claude-plugin — служебные реестра;
# SKILL.*.md (SKILL.ru.md и пр.) — человеческий ИСТОЧНИК (агент грузит лишь EN
# SKILL.md, "SKILL.*.md" не матчит сам "SKILL.md"); evals/ — поведенческие тесты
# скилла. ЕДИНЫЙ источник истины: vendor.copy_skill и skillset.sync копируют через
# него (раньше дублировали и skillset терял SKILL.*.md/evals → утечка RU-источника).
SKILL_IGNORE = ("upstream.json", ".claude-plugin", "SKILL.*.md", "evals")
CONFIG_KEYS = {
    "project_type": str, "buckets": list, "exclude": list, "presets": list,
    "skills_path": str, "agent": str,
    "memory_brain": str, "coordinator_ignore": list,
    # Профиль каркаса агентов (данные для agent-packs/универсальности, не движок):
    # shape — backend|frontend|fullstack; stacks — напр. ["laravel","vue"];
    # skills_map — домен→скиллы для преднагрузки ролей под стек.
    "shape": str, "stacks": list, "skills_map": dict,
}
HUB_MARKER = "<!-- swissknifeman:hub:start -->"


def safe_copy_skill(src, dst, dest_root):
    """Безопасно скопировать каталог скилла src→dst внутри dest_root. ЕДИНЫЙ путь копии
    для vendor.do_vendor и skillset.sync_skillset (раньше дублировались, расходясь в
    деталях безопасности). Шаги: лексич. containment (traversal через '../' в имени → стоп),
    снять существующий dst (symlink/файл/dir, symlink НЕ разыменовываем), пере-проверка
    против гонки (TOCTOU: чужой процесс мог пересоздать dst симлинком наружу), copytree с
    SKILL_IGNORE. Возврат True при копировании, False при пропуске (с warn). is_within/
    is_within_lexical — теперь из core (реэкспорт выше)."""
    if not is_within_lexical(dst, dest_root):
        warn(f"пропуск: путь вне каталога назначения: {dst}")
        return False
    if dst.is_symlink() or dst.is_file():
        dst.unlink()
    elif dst.is_dir():
        shutil.rmtree(dst)
    if dst.is_symlink() or dst.exists():
        warn(f"пропуск '{dst.name}': путь пересоздан между удалением и копированием (гонка)")
        return False
    shutil.copytree(src, dst, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(*SKILL_IGNORE))
    return True


@dataclass(frozen=True)
class Env(BaseEnv):
    """Контекст запуска swissknifeman: ядро (root/cmd/home) — из BaseEnv;
    здесь только path-property реестра (state ~/.swissknifeman)."""

    @property
    def state_dir(self):
        return state_dir(self.home)

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
    if result.returncode != 0:
        # Раньше warn был только при непустом stderr → молчаливый ненулевой rc прятал, что
        # permissions-пресеты (deny мусора/allow стека) НЕ легли. Сообщаем всегда.
        detail = result.stderr.strip() if result.stderr else f"exit {result.returncode}"
        warn(f"harness permissions не применились ({detail}) — пресеты deny/allow могли не лечь; "
             f"перезапустите: harness permissions --target {target}")
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


def skill_content_hash(skill_dir):
    """SHA-256 по содержимому ВСЕХ файлов каталога скилла — детект дрейфа sync шире,
    чем по одному SKILL.md: ловит правки в snippets/ и references/ (которые SKILL.md
    может не двигать). Игнорируем то же, что НЕ вендорится: upstream.json, языковые
    альтернаты SKILL.*.md (кроме SKILL.md), .claude-plugin/. Относительный путь файла
    входит в хеш (защита от переименований/перемещений). Порядок стабилен (sorted).

    Полный hexdigest, как у остальных sha256 в реестре/локе. Дополняет, а НЕ заменяет
    поле sha256 (по SKILL.md) — старые локи без content_sha256 деградируют корректно."""
    h = hashlib.sha256()
    skill_dir = Path(skill_dir)
    for f in sorted(skill_dir.rglob("*")):
        if not f.is_file():
            continue
        name = f.name
        if name == "upstream.json":
            continue
        if name.startswith("SKILL.") and name.endswith(".md") and name != "SKILL.md":
            continue
        if ".claude-plugin" in f.parts:
            continue
        # evals/ — поведенческие тесты (eval-first), НЕ вендорятся (см. vendor.copy_skill);
        # исключаем из хеша, чтобы правка теста не считалась дрейфом вендоренного скилла.
        if "evals" in f.relative_to(skill_dir).parts:
            continue
        h.update(str(f.relative_to(skill_dir)).encode("utf-8"))
        h.update(b"\0")
        h.update(f.read_bytes())
    return h.hexdigest()
