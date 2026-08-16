"""Общие утилиты: окружение, вывод, парсинг flag'ов и frontmatter.

Дословно общий с maind/brain код (die/warn/now_iso/confirm/sanitize + ядро Env)
вынесен в общий core; здесь — только специфика swissknifeman (path-property,
parse_flags, frontmatter, делегирование окружения в harness, константы реестра)."""
import hashlib
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
    parse_inline_list, run_cmd, safe_load_json, sanitize, sibling_bin,
    state_dir, warn,
)
from core import parse_frontmatter as _core_parse_frontmatter

STATE_DIR = state_dir(HOME)
DB_FILE = STATE_DIR / "projects.json"
DB_VERSION = 1
MARKETPLACE = "swissknifeman"
MANIFEST = ".swissknifeman-manifest.json"
MANIFEST_VERSION = 1
AGENT_DEFAULTS = {"claude": ".claude/skills", "cursor": ".cursor/skills",
                  "generic": ".ai/skills"}
# Файлы каталога скилла, которые НЕ едут в потребляющий проект ни одним каналом
# физ.переноса (vendor/sync): upstream.json и .claude-plugin — служебные реестра;
# SKILL.*.md — неканонические localized/reference alternates ("SKILL.*.md" не
# матчит сам EN-only "SKILL.md"); evals/ — поведенческие тесты
# скилла; __pycache__/*.pyc — байткод-кэш, появляется локально при ручном запуске
# .py-сниппетов (напр. snippets/check.py) — найдено при расследовании нестабильного
# content_sha256 у скилла с .py-сниппетами (registry --check зеленел локально и
# дрейфовал в чистом чекауте/CI). ЕДИНЫЙ источник истины: vendor.copy_skill и
# skillset.sync копируют через него (раньше дублировали и skillset терял
# SKILL.*.md/evals → утечка RU-источника).
SKILL_IGNORE = ("upstream.json", ".claude-plugin", "SKILL.*.md", "evals",
                "__pycache__", "*.pyc", "*.provider-artifact.bak")
# CONFIG_KEYS живёт ЗДЕСЬ по имени (его берут оба гейта синхрона со схемой —
# doctor.py и tests/test_schema.py — и документация), но значение с 2026-08-02
# (P6.2) ВЫВОДИТСЯ из полей skiller.config.ProjectConfig: перечень ключей
# .swissknife.json имеет ровно один носитель — объект конфига. Там же — комментарии
# про мульти-тип memory_brain, зарезервированные shape/stacks/skills_map и
# policy_profile (D11). Импорт ленивый (PEP 562 module __getattr__): config
# импортирует common на module-level, поэтому обратная связь возможна только по
# требованию — иначе цикл импорта.
def __getattr__(name):
    if name == "CONFIG_KEYS":
        from .config import CONFIG_KEYS as derived
        globals()["CONFIG_KEYS"] = derived  # мемоизация: __getattr__ больше не зовётся
        return derived
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


HUB_MARKER = "<!-- swissknifeman:hub:start -->"
SKILL_MANAGED_MARKER = "<!-- swissknifeman:managed -->"


def _split_bom(raw):
    """(bom, body) — срезать BOM-префикс (если есть) без нормализации остального."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[:3], raw[3:]
    return b"", raw


def _mark_skill_managed(dst):
    """Проставить SKILL_MANAGED_MARKER сразу после закрывающего `---` frontmatter'а
    в `dst/SKILL.md`, БАЙТ-РЕЖИМ (без text-mode чтения/нормализации `\\r\\n`→`\\n`) —
    старая версия читала файл через `.read_text()`, из-за чего у CRLF-скиллов
    записанные байты расходились с исходными и `hashlib.sha256(read_bytes())`
    реестра (registry.py) детектировал ложный дрейф на каждом sync. Идемпотентно
    (второй вызов — no-op); нет файла/нет frontmatter → тихий no-op (не крэш)."""
    path = Path(dst) / "SKILL.md"
    if not path.is_file():
        return
    raw = path.read_bytes()
    bom, body = _split_bom(raw)
    if body.startswith(b"---\r\n"):
        newline = b"\r\n"
    elif body.startswith(b"---\n"):
        newline = b"\n"
    else:
        return  # нет frontmatter — не наш файл, пропуск
    delim = b"---" + newline
    close_idx = body.find(delim, len(delim))
    if close_idx == -1:
        return  # frontmatter не закрыт — malformed, пропуск
    insert_at = close_idx + len(delim)
    marker_bytes = SKILL_MANAGED_MARKER.encode("utf-8")
    if body[insert_at:insert_at + len(marker_bytes)] == marker_bytes:
        return  # уже размечен — идемпотентный no-op
    new_body = body[:insert_at] + marker_bytes + newline + body[insert_at:]
    path.write_bytes(bom + new_body)


def strip_skill_managed_marker(data):
    """Обратное к `_mark_skill_managed` — убрать строку-маркер из байтов `data`
    (LF или CRLF), вернув исходное содержимое байт-в-байт. Отсутствие маркера —
    identity (не находка, а обычный невставленный файл)."""
    marker_bytes = SKILL_MANAGED_MARKER.encode("utf-8")
    for newline in (b"\r\n", b"\n"):
        pattern = marker_bytes + newline
        idx = data.find(pattern)
        if idx != -1:
            return data[:idx] + data[idx + len(pattern):]
    return data


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


def write_skill_manifest(manifest_file, *, profile, agent, layout, installed,
                         support_files=None):
    """ЕДИНЫЙ writer `.swissknifeman-manifest.json` — общий для vendor.do_vendor и
    skillset.sync_skillset (раньше два независимых писателя с разной схемой:
    date-only timestamp без `version` у vendor, `now_iso`+`version` у skillset —
    аудит V-4, update.detect_vendor_path читает оба и мог упереться в расхождение).
    Неизменившийся манифест сохраняет исходный installed_at и байты файла.
    Атомарно (tmp+os.replace), `version` первым ключом."""
    stable_data = {
        "profile": profile,
        "agent": agent,
        "layout": layout,
        "skills": installed,
    }
    if support_files is not None:
        stable_data["support_files"] = support_files
    existing = safe_load_json(manifest_file)
    if (isinstance(existing, dict)
            and existing.get("version") == MANIFEST_VERSION
            and isinstance(existing.get("installed_at"), str)
            and existing["installed_at"]
            and {key: value for key, value in existing.items()
                 if key not in {"version", "installed_at"}} == stable_data):
        return
    data = {"installed_at": now_iso(), **stable_data}
    atomic_write_json(manifest_file, data, version=MANIFEST_VERSION)


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
    Резолв — общий `core.sibling_bin`: env-override `SKM_HARNESS_BIN` → PATH →
    `<монорепо>/packages/harness/bin/harness`. None, если не найден (standalone /
    harness не установлен)."""
    return sibling_bin("harness", env_var="SKM_HARNESS_BIN", use_path=False,
                       monorepo_root=find_monorepo_root(env.root))


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
# Разбор перенесён в общий core.text (единый источник для skiller/harness/maind).
# Здесь остаётся только чтение файла: utf-8-sig срезает BOM, если есть (иначе
# `﻿---` != `---` и весь frontmatter молча игнорировался бы).
def parse_frontmatter(path):
    """Frontmatter скилла по пути (core.parse_frontmatter поверх utf-8-sig-чтения)."""
    return _core_parse_frontmatter(Path(path).read_text(encoding="utf-8-sig"))


def parse_frontmatter_fields(skill_md):
    """name + requires from the first ----delimited block."""
    fm = parse_frontmatter(skill_md)
    return {"name": fm.get("name", ""),
            "requires": parse_inline_list(fm.get("requires", ""))}


# --- requires (transitive dependency BFS) --------------------------------------
DEPENDENCY_DIAGNOSTIC_CODES = frozenset({
    "SKILL_REQUIRED_EXCLUDED",
    "SKILL_REQUIRED_UNKNOWN",
})


def aggregate_dependency_diagnostics(diagnostics):
    """Collapse dependency failures into stable machine-readable diagnostics.

    Human warnings remain owned by :func:`resolve_requires_bfs`; this projection is
    deliberately message-free so localization cannot change diagnostic identity.
    Repeated observations of the same ``code``/required skill are represented once,
    with the complete sorted requester set in ``affected_identities``.
    """
    grouped = {}
    for item in diagnostics:
        code = item.get("code")
        required = item.get("required_skill")
        requester = item.get("requester")
        if (code not in DEPENDENCY_DIAGNOSTIC_CODES
                or not isinstance(required, str) or not required
                or not isinstance(requester, str) or not requester):
            continue
        grouped.setdefault((code, required), set()).add(requester)
    return [
        {
            "code": code,
            "severity": "warning",
            "required_skill": required,
            "affected_identities": sorted(requesters),
        }
        for (code, required), requesters in sorted(grouped.items())
    ]


def resolve_requires_bfs(seed, lookup, selected_keys, exclude, *, diagnostics=None):
    """Транзитивный BFS резолва frontmatter `requires` — ЕДИНЫЙ источник для
    vendor.resolve_requires (FS-кортежи) и skillset._pull_requires (registry-entry):
    раньше это были два независимых, уже разошедшихся тела (RU/EN тексты warn,
    аудит V-1). Вызывающий адаптирует свою модель данных к узлу-словарю через `lookup`.

    seed: [(dep_name, requester_key), ...] — стартовая очередь (requires уже
        отобранных скиллов).
    lookup(dep_name) -> {"key", "requires": [str], "exclude_tokens": set[str], ...} | None
        — разрешить имя зависимости в узел; None — зависимость не найдена в реестре.
        Узел может нести любые доп. поля (напр. "_payload") — вызывающий сам их читает
        из возврата.
    selected_keys: изменяемое множество уже выбранных ключей — МУТИРУЕТСЯ (сюда
        добавляются ключи резолвнутых узлов), чтобы повторный вызов/рекурсия не
        задваивала уже выбранное.
    exclude: множество токенов, которые ПОБЕЖДАЮТ зависимость (safety-oriented) —
        зависимость с пересечением exclude_tokens пропускается с warning, даже если
        она нужна другому скиллу.

    diagnostics: optional mutable list populated with stable dependency records.
        It does not suppress or change the existing human warning text.

    Возвращает [(node, requester_key), ...] в порядке резолва — вызывающий сам
    решает, как класть узлы в свою структуру (список кортежей / dict по имени)."""
    queue = list(seed)
    resolved = []
    observed_diagnostics = []
    while queue:
        dep, requester = queue.pop(0)
        if dep in selected_keys:
            continue
        node = lookup(dep)
        if node is None:
            warn(f"'{requester}' requires неизвестный скилл '{dep}' — пропуск")
            observed_diagnostics.append({
                "code": "SKILL_REQUIRED_UNKNOWN",
                "required_skill": dep,
                "requester": requester,
            })
            continue
        if node["exclude_tokens"] & exclude:
            warn(f"'{requester}' requires '{dep}', но он в exclude — зависимость пропущена")
            observed_diagnostics.append({
                "code": "SKILL_REQUIRED_EXCLUDED",
                "required_skill": dep,
                "requester": requester,
            })
            continue
        selected_keys.add(node["key"])
        resolved.append((node, requester))
        queue.extend((d, node["key"]) for d in node["requires"])
    if diagnostics is not None:
        prior = [
            {
                "code": item.get("code"),
                "required_skill": item.get("required_skill"),
                "requester": requester,
            }
            for item in diagnostics
            for requester in item.get("affected_identities", [])
        ]
        diagnostics[:] = aggregate_dependency_diagnostics(
            prior + observed_diagnostics)
    return resolved


def skill_content_hash(skill_dir):
    """SHA-256 по содержимому ВСЕХ файлов каталога скилла — детект дрейфа sync шире,
    чем по одному SKILL.md: ловит правки в snippets/ и references/ (которые SKILL.md
    может не двигать). Игнорируем то же, что НЕ вендорится: upstream.json, языковые
    альтернаты SKILL.*.md (кроме SKILL.md), .claude-plugin/, __pycache__/*.pyc.
    Относительный путь файла входит в хеш (защита от переименований/перемещений).
    Порядок стабилен (sorted).

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
        # __pycache__/*.pyc — байткод-кэш при локальном запуске .py-сниппетов (напр.
        # snippets/check.py); без исключения content_sha256 нестабилен между машинами
        # (найдено при расследовании дрейфа skills.json — на диске разработчика был
        # __pycache__, в чистом чекауте/CI его нет, хеши расходились).
        if "__pycache__" in f.parts or name.endswith(".pyc"):
            continue
        # evals/ — поведенческие тесты (eval-first), НЕ вендорятся (см. vendor.copy_skill);
        # исключаем из хеша, чтобы правка теста не считалась дрейфом вендоренного скилла.
        if "evals" in f.relative_to(skill_dir).parts:
            continue
        h.update(str(f.relative_to(skill_dir)).encode("utf-8"))
        h.update(b"\0")
        h.update(f.read_bytes())
    return h.hexdigest()
