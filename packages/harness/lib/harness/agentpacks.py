"""agent-packs — детерминированный рендер/доставка паков субагентов в проект.

Пак (`configs/claude-code/agent-packs/<pack>/`) — версионируемый бандл артефактов
Claude Code (агенты/воркфлоу/хуки/фрагмент settings/rules/доки). Раньше его ставил
ТОЛЬКО агент по скиллу `system/agent-packs`. Здесь — детерминированный stdlib-рендер
БЕЗ агента в цикле: интервью резолвится из `detect:`-проб + дефолтов, плейсхолдеры
подставляются, lock пишется БАЙТ-СОВМЕСТИМО со скиллом (та же схема/`source`/
`base_sha256`=sha отрендеренного). Это позволяет `maind sync` раскатывать паки как
обычный провиженер. Агент-driven путь остаётся фолбэком для `needs-agent`/`conflict`.

Контракты: target-пути в pack.json — single-brace `{KEY}`; контент template-файлов —
double-brace `{{KEY}}`; интервью `default` интерполируется single-brace. Записи —
merge-only через settings.write_*, бэкап *.bak. stdlib-only, сообщения на русском.

Provenance-header: каждый сгенерированный файл (template И verbatim, кроме merge)
получает детерминированный блок «swissknifeman:generated» (без timestamp!) с паспортом
(пак@версия, шаблон, edit-policy, extension-points, команда upgrade). Header вшивается
ДО подсчёта sha → `base_sha256` в lock включает его, матрица решений
_decide/categorize_file_change не меняется. Lock schema=1, поле `user_owned` в
files[] — аддитивное (старые локи без него читаются через .get(..., False)).

files[]-запись может нести опциональное `src_pack` — контент берётся из каталога
ДРУГОГО пака (шаринг файлов между паками), владелец (Pack: в header, upgrade-команда)
остаётся текущий пак (см. `src_file`). `remove` — обратная операция к render/upgrade:
безопасно сносит только неправленные файлы (disk_sha == base_sha256), merge/user_owned
не трогает (warn), снимает запись пака из lock (пустой lock — удаляется целиком)."""
import hashlib
import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core import (ArtifactAdapterIdentity, ArtifactRenderRequest, ArtifactSource,
                  ArtifactTarget, ProviderId, plan_artifact_render, sha256_digest)

from .common import die, parse_flags, safe_load_json, sanitize, warn
from .settings import add_hook, load_settings, write_json, write_text

LOCK_REL = ".claude/agent-pack.lock.json"
PROBE_TIMEOUT = 5  # сек на одну shell-пробу

# Read-only префиксы сегментов, разрешённые при --allow-shell safe (дефолт maind).
# Проба, любой сегмент которой не отсюда, не исполняется (miss → default).
_SAFE_PROBE_PREFIXES = (
    "pwd", "command -v", "git symbolic-ref", "git rev-parse", "git config --get",
    "test ", "cat ", "ls ", "grep ", "echo ", "php ", "composer ",
    "dart ", "flutter ", "node ", "npm ", "npx ", "pnpm ", "yarn ",
    "python ", "python3 ", "uv ", "poetry ",
)
_FILE_HINT_RE = re.compile(r"^[\w./-]+\.(json|ya?ml|toml):")
_SINGLE_RE = re.compile(r"\{([A-Z_][A-Z0-9_]*)\}")
_DOUBLE_RE = re.compile(r"\{\{([A-Z_][A-Z0-9_]*)\}\}")
_IF_RE = re.compile(r"<!--\s*pack:if\s+(\w+)\s*-->(.*?)<!--\s*pack:endif\s*-->",
                    re.DOTALL)
_IFNOT_RE = re.compile(r"<!--\s*pack:ifnot\s+(\w+)\s*-->(.*?)<!--\s*pack:endif\s*-->",
                       re.DOTALL)


# ── discovery ────────────────────────────────────────────────────────────────
def pack_dir(env, pack):
    return env.agent_packs_dir / pack


def src_file(env, pack, f):
    """Путь исходника files[]-записи. Опциональное `src_pack` — контент берётся
    из каталога ДРУГОГО пака (шаринг файлов между паками без копий); владелец
    файла (Pack: в header, upgrade-команда) остаётся текущий `pack` — src_pack
    влияет только на резолв ИСТОЧНИКА, не на провенанс."""
    return pack_dir(env, f.get("src_pack") or pack) / f["src"]


def list_packs(env):
    d = env.agent_packs_dir
    return sorted(p.parent.name for p in d.glob("*/pack.json")) if d.is_dir() else []


def load_manifest(env, pack):
    f = pack_dir(env, pack) / "pack.json"
    if not f.exists():
        die(f"agent-pack не найден: {pack} (нет {f})")
    data = safe_load_json(f, default=None)
    if not isinstance(data, dict):
        die(f"{f}: невалидный JSON")
    if data.get("schema") != 1:
        die(f"{f}: schema должна быть 1")
    return data


# ── interview resolution (без агента) ────────────────────────────────────────
class _Defaulting(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def _interp(text, answers, target):
    """Интерполяция single-brace в строке default: {KEY} из answers + синтетические
    {project_dirname}/{pwd}. Неизвестные токены остаются литералами."""
    if not isinstance(text, str):
        return text
    m = _Defaulting({k: str(v) for k, v in answers.items()})
    m["project_dirname"] = target.name
    m["pwd"] = str(target)
    return text.format_map(m)


def _read_json(path):
    return safe_load_json(path, default=None)


def _file_hint(probe, target):
    """'composer.json:require-dev.pestphp/pest' → 'true' если ключ есть, иначе ''."""
    rel, _, dotted = probe.partition(":")
    if not rel.endswith(".json"):
        return ""  # v1: только JSON-манифесты (yaml/toml → miss)
    data = _read_json(target / rel)
    if not isinstance(data, dict):
        return ""
    cur = data
    for seg in dotted.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return ""
    return "true"


def _probe_allowed(probe):
    for seg in re.split(r"\|\||&&|;|\|", probe):
        seg = seg.strip()
        if not seg:
            continue
        if not any(seg.startswith(p) for p in _SAFE_PROBE_PREFIXES):
            return False
    return True


def _run_detect(probe, target, shell_policy, report):
    """Резолв одной detect-пробы → строка (или '' при промахе). Никогда не бросает."""
    probe = probe.strip()
    if not probe:
        return ""
    if probe == "pwd":
        return str(target)
    if _FILE_HINT_RE.match(probe):
        return _file_hint(probe, target)
    if shell_policy == "off":
        return ""
    if shell_policy == "safe" and not _probe_allowed(probe):
        report["skipped_probes"].append(probe)
        return ""
    try:
        r = subprocess.run(["bash", "-lc", probe], cwd=str(target),
                           capture_output=True, text=True, timeout=PROBE_TIMEOUT)
        return (r.stdout or "").strip() if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _coerce(value, kind):
    if kind == "slug":
        return sanitize(value) if value else value
    if kind == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() not in ("", "0", "false", "no")
    return value


def resolve_interview(manifest, target, overrides, shell_policy="safe"):
    """Резолв всех interview[]-ответов детерминированно. overrides (профиль/--answer)
    всегда побеждают. Возвращает (answers, report)."""
    answers, report = {}, {"assumed": [], "unresolved": [], "skipped_probes": []}
    for e in manifest.get("interview", []):
        key, kind = e["id"], e.get("kind", "str")
        enum = e.get("enum")
        if key in overrides:
            answers[key] = _coerce(overrides[key], kind)
            continue
        raw = ""
        if e.get("detect"):
            raw = _run_detect(e["detect"], target, shell_policy, report)
        if raw == "" and "default" in e:
            raw = e["default"]
        if isinstance(raw, str):
            raw = _interp(raw, answers, target)
        val = _coerce(raw, kind)
        if enum and val not in enum:
            dflt = e.get("default")
            val = dflt if dflt in enum else (enum[0] if enum else val)
            report["assumed"].append(f"{key}={val}")
        if val == "" and not enum and "default" not in e:
            report["unresolved"].append(key)
        answers[key] = val
    return answers, report


# ── provenance header ────────────────────────────────────────────────────────
# Синтаксис комментария по расширению target-файла. Расширения вне карты header
# не получают (не знаем безопасный синтаксис комментария — лучше ничего, чем
# сломать файл). kind=merge header не получает никогда (фрагмент вливается в
# чужой JSON, свой заголовок там неуместен и невалиден).
_COMMENT_STYLES = {".md": "html", ".js": "line//", ".mjs": "line//",
                   ".sh": "line#", ".ini": "line#"}


def provenance_header(pack, version, src_rel, target_rel, edit_policy,
                      extension_points):
    """Детерминированный provenance-блок для сгенерированного файла. НАМЕРЕННО без
    timestamp: header участвует в base_sha256, и любая недетерминированность
    ломала бы skip-nochange/idempotent re-render. Возвращает '' для расширений
    вне _COMMENT_STYLES."""
    style = _COMMENT_STYLES.get(os.path.splitext(target_rel)[1])
    if not style:
        return ""
    pts = ", ".join(extension_points) if extension_points else "—"
    lines = [
        "swissknifeman:generated",
        "Generated-by: harness agent-packs",
        f"Pack: {pack}@{version}",
        f"Template: {src_rel}",
        f"Edit-policy: {edit_policy}",
        f"Extension-points: {pts}",
        f"Upgrade: harness agent-packs upgrade --pack {pack} --target .",
    ]
    if style == "html":
        return "<!-- " + lines[0] + "\n" + "\n".join(lines[1:]) + "\n-->\n"
    prefix = "//" if style == "line//" else "#"
    return "\n".join(f"{prefix} {ln}" for ln in lines) + "\n"


def inject_header(rendered, header, target_rel):
    """Вставить header в отрендеренный текст, не ломая машинно-значимые прологи:
    .md — ПОСЛЕ закрывающего '---' YAML-frontmatter (иначе Claude Code перестал бы
    парсить метаданные агента), shebang-файлы — после первой строки (иначе ядро
    не увидит интерпретатор). Пустой header → текст без изменений."""
    if not header:
        return rendered
    ext = os.path.splitext(target_rel)[1]
    if ext == ".md" and rendered.startswith("---"):
        lines = rendered.splitlines(keepends=True)
        if lines[0].rstrip("\n") == "---":
            for i, ln in enumerate(lines[1:], start=1):
                if ln.rstrip("\n") == "---":  # закрывающий разделитель frontmatter
                    return "".join(lines[:i + 1]) + header + "".join(lines[i + 1:])
        return header + rendered  # frontmatter не закрыт/нет — в начало
    if rendered.startswith("#!"):
        nl = rendered.find("\n")
        if nl != -1:
            return rendered[:nl + 1] + header + rendered[nl + 1:]
        return rendered + "\n" + header
    return header + rendered


def _edit_policy(f):
    """Текст Edit-policy для header: user_owned-файлы отданы пользователю навсегда,
    остальные перезаписываются паком при upgrade — редактировать их бессмысленно."""
    return ("user-owned — файл ваш, пак его не перезапишет" if f.get("user_owned")
            else "generated-core — НЕ редактируй; расширяй через extension-point")


def _extension_points(manifest, answers):
    """Точки расширения пака — target'ы файлов с role=override (новое поле формата,
    может отсутствовать). Их и предлагаем править вместо generated-core."""
    return [_subst_single(x["target"], answers)
            for x in manifest.get("files", []) if x.get("role") == "override"]


# ── render engine ────────────────────────────────────────────────────────────
def sha256_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _subst_single(text, answers):
    return _SINGLE_RE.sub(lambda m: str(answers.get(m.group(1), m.group(0))), text)


def _subst_double(text, answers):
    return _DOUBLE_RE.sub(lambda m: str(answers.get(m.group(1), m.group(0))), text)


def _apply_conditionals(text, answers):
    """Условные блоки. <!-- pack:if KEY -->...<!-- pack:endif --> — оставить при truthy
    answer; <!-- pack:ifnot KEY -->...<!-- pack:endif --> — при falsy/отсутствующем
    (движок без логических операторов — «иначе»-ветка). Пары if/ifnot держи ПЛОСКО
    (последовательно, не вложенно) — non-greedy парит каждый open с ближайшим endif."""
    for _ in range(10):  # вложенность/множественность: повторяем, пока есть изменения
        new = _IF_RE.sub(lambda m: m.group(2) if answers.get(m.group(1)) else "", text)
        new = _IFNOT_RE.sub(
            lambda m: m.group(2) if not answers.get(m.group(1)) else "", new)
        if new == text:
            return new
        text = new
    return text


def _render_template_text(src_text, answers):
    return _subst_double(_apply_conditionals(src_text, answers), answers)


def validate_expect_globs(manifest, target, answers):
    """Пост-рендер проверка: критичные пути пака (`expect_globs`, single-brace-глобы,
    интерполируются `answers`) реально существуют в проекте. Возвращает список
    не-совпавших глобов (пусто = ок). Детерминированно ловит layout-mismatch —
    напр. хардкод `app/`-путей в монорепо (`packages/*/src`) → 0 совпадений →
    иначе молчаливый ложно-зелёный access-layer. Сеть безопасности НЕЗАВИСИМО от
    корректности detect-проб."""
    misses = []
    for pattern in manifest.get("expect_globs", []):
        pat = _subst_single(pattern, answers).strip()
        if not pat:
            continue
        try:
            hit = any(True for _ in target.glob(pat))
        except (ValueError, OSError):
            hit = False
        if not hit:
            misses.append(pat)
    return misses


def _chmod_x(path):
    cur = os.stat(path).st_mode
    os.chmod(path, cur | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _decide(target_path, new_sha, owned, base_sha):
    """Решение по одному файлу. owned — записан ли он прошлым lock этого пака."""
    if not target_path.exists():
        return "write"
    disk_sha = sha256_text(target_path.read_text(encoding="utf-8"))
    if not owned:
        return "skip-identical" if disk_sha == new_sha else "skip-foreign"
    if disk_sha != base_sha:
        return "skip-local-modified"
    return "skip-nochange" if disk_sha == new_sha else "write"


def render_pack(env, pack, target, answers, *, dry=False, prior=None):
    """Отрендерить и записать все files[] пака. Возвращает report c lock-структурой
    файлов (src/target/kind/base_sha256/local_modified/user_owned) и changed-флагом.
    Provenance-header вшивается ДО вычисления sha — база в lock включает header,
    поэтому матрица _decide/categorize_file_change не меняется вообще."""
    manifest = load_manifest(env, pack)
    prior_files = {f["src"]: f for f in (prior or {}).get("files", [])}
    ext_points = _extension_points(manifest, answers)
    out_files, changed, notes = [], False, []
    for f in manifest.get("files", []):
        src, kind = f["src"], f.get("kind", "template")
        sfile = src_file(env, pack, f)
        if not sfile.exists():
            if f.get("optional"):
                continue
            die(f"{f.get('src_pack') or pack}: нет файла пака {src}")
        tgt_rel = _subst_single(f["target"], answers)
        tgt = target / tgt_rel
        prior_f = prior_files.get(src)
        base_sha = (prior_f or {}).get("base_sha256", "")
        owned = prior_f is not None

        if kind == "merge":
            ch = _merge_fragment(target, sfile, f.get("merge", ""), answers, dry)
            changed = changed or ch
            out_files.append({"src": src, "target": tgt_rel, "kind": kind,
                              "base_sha256": sha256_text(sfile.read_text(encoding="utf-8")),
                              "local_modified": False,
                              "user_owned": bool(f.get("user_owned", False))})
            continue

        rendered = (_render_template_text(sfile.read_text(encoding="utf-8"), answers)
                    if kind == "template" else sfile.read_text(encoding="utf-8"))
        rendered = inject_header(
            rendered,
            provenance_header(pack, manifest["version"], src, tgt_rel,
                              _edit_policy(f), ext_points),
            tgt_rel)
        new_sha = sha256_text(rendered)
        decision = _decide(tgt, new_sha, owned, base_sha)
        local_mod = decision == "skip-local-modified"
        if decision == "write":
            tgt.parent.mkdir(parents=True, exist_ok=True)
            write_text(tgt, rendered, dry)
            if not dry and f.get("chmod") == "+x":
                _chmod_x(tgt)
            changed = True
        elif decision == "skip-foreign":
            warn(f"  коллизия: {tgt_rel} уже существует и не принадлежит паку — пропуск")
            notes.append(f"collision:{tgt_rel}")
        elif decision == "skip-local-modified":
            warn(f"  {tgt_rel} правлен локально — не затираю (см. upgrade)")
        out_files.append({"src": src, "target": tgt_rel, "kind": kind,
                          "base_sha256": new_sha, "local_modified": local_mod,
                          "user_owned": bool(f.get("user_owned", False))})
    report = {"files": out_files, "changed": changed, "notes": notes}
    return report


def _merge_fragment(target, sfile, directive, answers, dry):
    """JSON-фрагмент append-if-absent в .claude/settings.json (хуки по событиям)."""
    raw = _subst_double(sfile.read_text(encoding="utf-8"), answers)
    frag = json.loads(raw)
    settings, f = load_settings(target, "settings.json")
    added = False
    events = [seg.split("[")[0].split(".")[-1]
              for seg in directive.replace("append-if-absent", "").split("+")
              if seg.strip()]
    for event in events or list(frag.get("hooks", {})):
        for entry in frag.get("hooks", {}).get(event, []):
            matcher = entry.get("matcher")
            for h in entry.get("hooks", []):
                if add_hook(settings, event, matcher, h.get("command")):
                    added = True
    if added:
        write_json(f, settings, dry)
    else:
        print("  settings.json: хуки фрагмента уже на месте — пропуск")
    return added


# ── lock ─────────────────────────────────────────────────────────────────────
def lock_path(target):
    return target / LOCK_REL


def load_lock(target):
    return safe_load_json(lock_path(target), default={"schema": 1, "packs": {}})


def write_lock(target, lock, dry):
    lp = lock_path(target)
    if dry:
        print(f"  [dry-run] обновил бы {lp}")
        return
    lp.parent.mkdir(parents=True, exist_ok=True)
    from core import atomic_write_json
    atomic_write_json(lp, lock)
    print(f"  lock: {lp}")


def _pack_lock_entry(env, pack, answers, report):
    return {
        "version": load_manifest(env, pack)["version"],
        "source": f"harness:configs/claude-code/agent-packs/{pack}",
        "answers": answers,
        "files": report["files"],
        "removed_optional": [],
    }


# ── operations ───────────────────────────────────────────────────────────────
def do_render(env, pack, target, *, auto, overrides, dry, install_only, shell_policy):
    manifest = load_manifest(env, pack)
    lock = load_lock(target)
    prior = lock.get("packs", {}).get(pack)
    if install_only and prior is not None:
        print(f"agent-pack '{pack}' уже установлен (v{prior.get('version')}) — пропуск")
        return 0
    # ре-ролл предпочитает зафиксированные answers (стабильность), detect добивает новые
    base_overrides = dict((prior or {}).get("answers", {}))
    base_overrides.update(overrides)
    answers, rep = resolve_interview(manifest, target, base_overrides, shell_policy)
    print(f"=== agent-pack render: {pack} v{manifest['version']} → {target} ===")
    if rep["assumed"]:
        warn(f"  допущения (проверь): {', '.join(rep['assumed'])}")
    if rep["skipped_probes"]:
        warn(f"  пропущены небезопасные пробы: {len(rep['skipped_probes'])}")
    report = render_pack(env, pack, target, answers, dry=dry, prior=prior)
    new_entry = _pack_lock_entry(env, pack, answers, report)
    lock.setdefault("packs", {})[pack] = new_entry
    # report["changed"] отражает ТОЛЬКО запись на диск (write/merge) — но местное
    # состояние lock'а (напр. local_modified per-file) может стать неактуальным и
    # БЕЗ единой записи на диск: файл, который был skip-foreign/skip-local-modified,
    # мог быть вручную приведён к базе между прогонами (см. F-7: разруливание
    # коллизии после смены пака) — тогда decision внутри render_pack тихо перешёл в
    # skip-nochange, а лежащий на диске lock всё ещё врёт "local_modified": true.
    # Сравниваем entry целиком (не только changed), чтобы такой дрейф lock'а не
    # застревал молча — иначе `doctor` (без --drift) годами репортил бы ложный modified.
    if report["changed"] or prior is None or new_entry != prior:
        write_lock(target, lock, dry)
    for pat in validate_expect_globs(manifest, target, answers):
        warn(f"  ожидаемый путь '{pat}' матчит 0 файлов — проверь layout/answers "
             f"(риск ложно-зелёного access-layer)")
    status = "needs-agent" if rep["unresolved"] else "ok"
    print(f"=== {status} (changed={report['changed']}) ===")
    return 0 if status == "ok" else 0  # needs-agent не фейл: ставим что смогли


def categorize_file_change(f, pf, new_sha, tgt):
    """Категория файла при upgrade agent-pack'а. Чистая логика решения (без записи на
    диск) — выделена из do_upgrade ради юнит-тестов матрицы случаев.

    f — описание файла из манифеста (флаги optional/user_owned); pf — запись файла из
    прежнего lock (None, если файл новый); new_sha — sha отрендеренного нового содержимого;
    tgt — путь файла на диске (для детекта локальной правки). Возврат:
      new / new-optional — файла не было; user-owned — отдан пользователю, не трогаем;
      conflict — изменились и база, и локальная копия; safe-apply — изменилась только
      база (в т.ч. пропавший с диска файл при смене версии, см. ниже); nochange —
      база не менялась (пропавший файл без смены версии — тоже nochange, это забота
      doctor --drift, не upgrade)."""
    if pf is None:
        return "new-optional" if f.get("optional") else "new"
    if f.get("user_owned"):
        return "user-owned"
    missing = not tgt.exists()
    disk_sha = "" if missing else sha256_text(tgt.read_text(encoding="utf-8"))
    local_mod = disk_sha != pf.get("base_sha256")
    base_changed = new_sha != pf.get("base_sha256")
    if base_changed and local_mod:
        # Файл пропал с диска (lock_drift: 'missing') — мержить нечего: это не
        # конфликт локальной правки, а установка отсутствующего файла (ровно то,
        # что советует doctor --drift: "восстанови render"). Иначе missing-файл
        # при смене версии пака ложно давал бы *.pack-new вместо восстановления.
        return ("new-optional" if f.get("optional") else "new") if missing else "conflict"
    if base_changed:
        return "safe-apply"
    return "nochange"


def do_upgrade(env, pack, target, *, overrides, dry, shell_policy):
    manifest = load_manifest(env, pack)
    lock = load_lock(target)
    prior = lock.get("packs", {}).get(pack)
    if prior is None:
        die(f"agent-pack '{pack}' не установлен — сначала render")
    v_old, v_new = prior.get("version"), manifest["version"]
    if v_old == v_new:
        print(f"agent-pack '{pack}' уже актуален (v{v_new})")
        return 0
    base_overrides = dict(prior.get("answers", {}))
    base_overrides.update(overrides)
    answers, _ = resolve_interview(manifest, target, base_overrides, shell_policy)
    prior_files = {f["src"]: f for f in prior.get("files", [])}
    ext_points = _extension_points(manifest, answers)
    plan, out_files = [], []
    for f in manifest.get("files", []):
        src, kind = f["src"], f.get("kind", "template")
        sfile = src_file(env, pack, f)
        if not sfile.exists():
            continue
        tgt_rel = _subst_single(f["target"], answers)
        tgt = target / tgt_rel
        if kind == "merge":
            _merge_fragment(target, sfile, f.get("merge", ""), answers, dry)
            out_files.append({"src": src, "target": tgt_rel, "kind": kind,
                              "base_sha256": sha256_text(sfile.read_text(encoding="utf-8")),
                              "local_modified": False,
                              "user_owned": bool(f.get("user_owned", False))})
            continue
        rendered = (_render_template_text(sfile.read_text(encoding="utf-8"), answers)
                    if kind == "template" else sfile.read_text(encoding="utf-8"))
        # header — ДО sha: база сравнивается с прежней базой, тоже включавшей header
        # (изменение только header'а, напр. bump версии пака, = обычный safe-apply)
        rendered = inject_header(
            rendered,
            provenance_header(pack, manifest["version"], src, tgt_rel,
                              _edit_policy(f), ext_points),
            tgt_rel)
        new_sha = sha256_text(rendered)
        cat = categorize_file_change(f, prior_files.get(src), new_sha, tgt)
        plan.append((cat, src, tgt_rel))
        # Новые файлы версии (напр. recon-агенты) ставим на upgrade так же, как render:
        # цель не существует → запись безопасна (нечего затирать). Опциональные, которые
        # пользователь ЯВНО удалил (removed_optional), не возвращаем.
        install_new = cat == "new" or (
            cat == "new-optional" and src not in prior.get("removed_optional", []))
        if (cat == "safe-apply" or install_new) and not dry:
            tgt.parent.mkdir(parents=True, exist_ok=True)
            write_text(tgt, rendered, dry)
            if f.get("chmod") == "+x":
                _chmod_x(tgt)
        elif cat == "conflict" and not dry:
            write_text(target / (tgt_rel + ".pack-new"), rendered, dry)
            warn(f"  conflict: {tgt_rel} — новый вариант в {tgt_rel}.pack-new (смержи вручную)")
        out_files.append({"src": src, "target": tgt_rel, "kind": kind,
                          "base_sha256": new_sha,
                          "local_modified": cat == "conflict",
                          "user_owned": bool(f.get("user_owned", False))})
    print(f"=== upgrade {pack}: {v_old} → {v_new} ===")
    for cat, _src, tgt_rel in plan:
        print(f"  [{cat}] {tgt_rel}")
    conflicts = [t for c, _s, t in plan if c == "conflict"]
    if conflicts:
        warn(f"  ⚠ {len(conflicts)} conflict → ручной мерж из .pack-new: "
             + ", ".join(t + ".pack-new" for t in conflicts))
    for pat in validate_expect_globs(manifest, target, answers):
        warn(f"  ожидаемый путь '{pat}' матчит 0 файлов — проверь layout/answers "
             f"(риск ложно-зелёного access-layer)")
    removed = sorted(set(prior_files) - {f["src"] for f in manifest.get("files", [])})
    for src in removed:
        warn(f"  removed в {v_new}: {src} — не удаляю авто (удали вручную при желании)")
    entry = _pack_lock_entry(env, pack, answers, {"files": out_files})
    entry["removed_optional"] = prior.get("removed_optional", [])
    lock.setdefault("packs", {})[pack] = entry
    write_lock(target, lock, dry)
    return 0


def do_remove(env, pack, target, *, dry):
    """Удалить установленный agent-pack из target. Безопасно — удаляются только
    файлы, которые не были локально изменены (disk_sha == base_sha256 из lock);
    kind=merge (вливается фрагментом в чужой settings.json) и user_owned (отдан
    пользователю навсегда) не трогаем никогда — только предупреждаем. Запись
    пака в lock снимается в любом случае (даже если ни один файл не удалён —
    иначе повторный remove видел бы призрак); опустевший lock удаляется целиком."""
    lock = load_lock(target)
    entry = lock.get("packs", {}).get(pack)
    if entry is None:
        print(f"agent-pack '{pack}' не установлен в {target} — нечего удалять")
        return 0
    tag = " [dry-run]" if dry else ""
    print(f"=== agent-pack remove: {pack} v{entry.get('version')} ← {target} ==={tag}")
    merge_kept = []
    for f in entry.get("files", []):
        tgt_rel = f.get("target", "")
        tgt = target / tgt_rel
        if f.get("kind", "template") == "merge":
            merge_kept.append(tgt_rel)
            continue
        if f.get("user_owned"):
            warn(f"  {tgt_rel}: user-owned — оставлен, удали вручную при желании")
            continue
        if not tgt.exists():
            continue  # уже отсутствует — тихо пропускаем
        try:
            disk_sha = sha256_text(tgt.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            warn(f"  {tgt_rel}: не читается — оставлен на всякий случай")
            continue
        if disk_sha != f.get("base_sha256"):
            warn(f"  {tgt_rel}: локально правлен — оставлен")
            continue
        print(f"  [{'dry-run' if dry else 'remove'}] {tgt_rel}")
        if not dry:
            tgt.unlink()
    if merge_kept:
        warn("  хуки в settings.json остаются — удали вручную при необходимости: "
             + ", ".join(merge_kept))
    if dry:
        print(f"  [dry-run] lock: запись '{pack}' была бы удалена")
        return 0
    lock.get("packs", {}).pop(pack, None)
    if lock.get("packs"):
        write_lock(target, lock, dry=False)
    else:
        lp = lock_path(target)
        if lp.exists():
            lp.unlink()
        print(f"  lock: {lp} удалён (пуст)")
    return 0


def lock_drift(target):
    """Детект дрейфа generated-файлов lock'а против диска (E-2). Для каждой
    files[]-записи каждого установленного пака — кроме kind=merge (вливается в
    чужой JSON, свой sha не отслеживаем) и user_owned (файл отдан пользователю
    навсегда, «дрейф» там ожидаем и не проблема) — sha256 файла на диске
    сравнивается с base_sha256 из lock. Защитная функция: lock читается через
    load_lock (несуществующий/битый → {schema:1, packs:{}} → пустой дрейф),
    отсутствующий/нечитаемый файл на диске — 'missing', а не исключение.

    Возвращает список {pack, target, status: 'modified'|'missing'} — чистая,
    без побочных эффектов и печати (тестируема напрямую)."""
    lock = load_lock(target)
    drift = []
    for pack, entry in (lock.get("packs") or {}).items():
        for f in entry.get("files") or []:
            if f.get("kind") == "merge" or f.get("user_owned"):
                continue
            tgt_rel = f.get("target", "")
            tgt = target / tgt_rel
            if not tgt.exists():
                drift.append({"pack": pack, "target": tgt_rel, "status": "missing"})
                continue
            try:
                disk_sha = sha256_text(tgt.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                drift.append({"pack": pack, "target": tgt_rel, "status": "missing"})
                continue
            if disk_sha != f.get("base_sha256"):
                drift.append({"pack": pack, "target": tgt_rel, "status": "modified"})
    return drift


def do_doctor_drift(target, *, strict=False):
    """Печать таблицы дрейфа generated-файлов (lock vs диск). rc=0 информативно
    (для обычного doctor-прогона), но --strict превращает найденный дрейф в
    негромкий провал (rc=1) — годится как CI-гейт «никто не правил generated
    руками мимо override»."""
    drift = lock_drift(target)
    if not drift:
        print("[OK] дрейф generated-файлов не найден")
        return 0
    for d in drift:
        if d["status"] == "modified":
            warn(f"[{d['pack']}] generated-файл правлен локально: {d['target']} — "
                 f"перенеси правку в override и восстанови render")
        else:
            warn(f"[{d['pack']}] generated-файл отсутствует: {d['target']} — "
                 f"восстанови render (harness agent-packs render --pack {d['pack']} "
                 f"--target .)")
    return 1 if strict else 0


def do_doctor(env, pack=None, target=None, json_out=False):
    packs = [pack] if pack else list_packs(env)
    rc = 0
    catalog = []
    for pk in packs:
        manifest = load_manifest(env, pk)
        problems = []
        ids = {e["id"] for e in manifest.get("interview", [])}
        for f in manifest.get("files", []):
            if not src_file(env, pk, f).exists() and not f.get("optional"):
                problems.append(f"нет {f['src']}")
        # проверка: каждый {{TOKEN}} в template-исходниках имеет interview-id
        for f in manifest.get("files", []):
            if f.get("kind", "template") != "template":
                continue
            sfile = src_file(env, pk, f)
            if not sfile.exists():
                continue
            for tok in set(_DOUBLE_RE.findall(sfile.read_text(encoding="utf-8"))):
                if tok not in ids:
                    problems.append(f"{f['src']}: {{{{{tok}}}}} нет в interview")
        # сухой рендер с дефолтами: не должно остаться {{...}}
        defaults = {e["id"]: e.get("default", "") for e in manifest.get("interview", [])}
        for f in manifest.get("files", []):
            if f.get("kind", "template") != "template":
                continue
            sfile = src_file(env, pk, f)
            if not sfile.exists():
                continue
            left = _DOUBLE_RE.findall(_render_template_text(
                sfile.read_text(encoding="utf-8"), defaults))
            if left:
                problems.append(f"{f['src']}: остаточные {{{{{','.join(sorted(set(left)))}}}}}")
        if problems:
            rc = 1
        catalog.append({"pack": pk, "version": manifest["version"],
                        "ok": not problems, "problems": problems})
        if not json_out:
            print(f"[{'OK ' if not problems else 'BAD'}] {pk} v{manifest['version']}")
            for p in problems:
                print(f"      - {p}")
    installed = None
    if target:
        lock = load_lock(target)
        lock_ok = lock.get("schema") == 1
        installed = {name: {"version": pk.get("version"),
                            "files": len(pk.get("files") or []),
                            "modified": any(f.get("local_modified")
                                            for f in (pk.get("files") or []))}
                     for name, pk in (lock.get("packs") or {}).items()}
        if not lock_ok:
            rc = 1
            if not json_out:
                print("[BAD] lock: schema != 1")
        elif installed and not json_out:
            print(f"Установлено в {target.name}: {', '.join(sorted(installed))}")
        # .bak-гигиена: локальные *.bak в .claude/agents/ — легальны (бэкап merge-only
        # записи), но копятся мусором (прецедент: agelto — 9 файлов) — только warn, не error.
        bak_files = sorted(f.name for f in (target / ".claude" / "agents").glob("*.bak"))
        if bak_files and not json_out:
            warn(f".claude/agents: {len(bak_files)} .bak-файл(ов) — "
                 f"проверь и удали лишнее ({', '.join(bak_files)})")
    if json_out:
        print(json.dumps({"catalog": catalog, "installed": installed, "rc": rc},
                         ensure_ascii=False, indent=2))
    return rc


# ── CLI ──────────────────────────────────────────────────────────────────────
def _pop_answers(argv):
    """Вытащить все повторяющиеся --answer K=V (parse_flags хранит лишь последний)."""
    rest, answers = [], {}
    it = iter(argv)
    for a in it:
        if a == "--answer":
            kv = next(it, "")
            k, _, v = kv.partition("=")
            if k:
                answers[k] = v
        else:
            rest.append(a)
    return rest, answers


def cmd_agent_packs(env, argv):
    if not argv:
        die("usage: harness agent-packs <list|render|upgrade|remove|doctor> [...]")
    sub, rest = argv[0], argv[1:]
    rest, answers = _pop_answers(rest)
    opts = parse_flags(rest, {
        "--pack": "str", "--target": "str", "--auto": "bool", "--dry-run": "bool",
        "--install-only": "bool", "--allow-shell": "str", "--list": "bool", "--json": "bool",
        "--drift": "bool", "--strict": "bool",
    })
    if opts.get("help"):
        print("harness agent-packs <list|render|upgrade|remove|doctor> "
              "[--pack P] [--target DIR] [--auto] [--answer K=V] "
              "[--install-only] [--allow-shell off|safe|full] [--dry-run] [--json] "
              "[--drift [--strict]]")
        return
    shell_policy = opts.get("allow_shell") or "safe"

    if sub == "list":
        for pk in list_packs(env):
            m = load_manifest(env, pk)
            print(f"{pk}\tv{m['version']}\t{m.get('stack', {}).get('shape', '-')}\t"
                  f"{m.get('description', '')[:70]}")
        return

    if sub == "doctor":
        from pathlib import Path
        target = Path(opts["target"]).resolve() if opts.get("target") else None
        if opts.get("drift"):
            if target is None:
                die("--drift требует --target DIR")
            raise SystemExit(do_doctor_drift(target, strict=bool(opts.get("strict"))))
        raise SystemExit(do_doctor(env, opts.get("pack"), target, json_out=opts.get("json")))

    if sub in ("render", "install", "upgrade", "remove"):
        if not opts.get("pack") or not opts.get("target"):
            die(f"нужны --pack P и --target DIR для {sub}")
        from pathlib import Path
        target = Path(os.path.expanduser(opts["target"])).resolve()
        if not target.is_dir():
            die(f"target не каталог: {target}")
        pack = opts["pack"]
        dry = bool(opts.get("dry_run"))
        if sub == "upgrade":
            raise SystemExit(do_upgrade(env, pack, target, overrides=answers,
                                        dry=dry, shell_policy=shell_policy))
        if sub == "remove":
            raise SystemExit(do_remove(env, pack, target, dry=dry))
        raise SystemExit(do_render(env, pack, target, auto=bool(opts.get("auto")),
                                   overrides=answers, dry=dry,
                                   install_only=bool(opts.get("install_only")),
                                   shell_policy=shell_policy))

    die(f"неизвестная подкоманда agent-packs: {sub}")


# P5.4 provider projection seam. The role catalog is the semantic source; the
# established Claude lifecycle and templates above are compatibility consumers.
@dataclass(frozen=True)
class AgentRole:
    pack_id: str
    role_id: str
    description_lines: tuple[str, ...]
    content: str
    skills: tuple[str, ...]
    tool_requirements: tuple[str, ...]
    command_ids: tuple[str, ...]
    model_class: str
    activation_requirements: tuple[str, ...]


@dataclass(frozen=True)
class AgentProjection:
    provider_id: str
    target_path: str
    rendered: bytes
    diagnostic: str | None = None


_ROLE_FIELDS = {"pack_id", "role_id", "description_lines", "content", "skills",
                "tool_requirements", "command_ids", "model_class", "activation_requirements"}
_COMMON_FORBIDDEN = re.compile(
    r"\.claude(?:/|\b)|(?<![\w-])/(?:task:[a-z-]+|effort|clear)\b|"
    r"\bWorkflow\b|\bSubagentStop\b|(?<![\w-])(?:Read|Grep|Glob|Bash|Edit|Write|"
    r"Haiku|Sonnet|Opus)(?![\w-])")
_TOKEN = re.compile(r"\{\{token:([a-z-]+)\}\}")
_MODEL_SELECTORS = {"economy": "gpt-5.6-luna", "implementation": "gpt-5.6-terra",
                    "frontier": "gpt-5.6-sol"}
_CLAUDE_TOKENS = {
    "agent-roster": "`.claude/agents/{{PACK_PREFIX}}-*.md` (Glob/Read)",
    "managed-role-override-pattern": "`.claude/rules/*-overrides.md`",
    "managed-role-override": "`.claude/rules/{{PACK_PREFIX}}-reviewer-overrides.md`",
    "background-orchestration": "**фоновый** Workflow `{{PACK_PREFIX}}-dev-loop` (не пошагово\nв основном контексте)",
    "tool-read": "Read", "tool-grep": "Grep", "tool-glob": "Glob",
    "tool-shell": "Bash", "tool-edit": "Edit", "tool-write": "Write",
    "model-economy": "Haiku", "model-implementation": "Sonnet", "model-frontier": "Opus",
}
_CODEX_TOKENS = {
    "agent-roster": "`.codex/agents/{{PACK_PREFIX}}-*.toml`",
    "managed-role-override-pattern": "`.codex/agents/*-overrides.toml`",
    "managed-role-override": "`.codex/agents/{{PACK_PREFIX}}-reviewer-overrides.toml`",
    "tool-read": "filesystem-read capability", "tool-grep": "filesystem-search capability",
    "tool-glob": "filesystem-search capability", "tool-shell": "shell-execute capability",
    "tool-edit": "file-edit capability", "tool-write": "filesystem-write capability",
    "model-economy": "economy model class", "model-implementation": "implementation model class",
    "model-frontier": "frontier model class",
}
_CLAUDE_TOOLS = {
    "command.filesystem-read": "Read", "agent.tool.search": "Grep, Glob",
    "agent.tool.edit": "Edit", "command.filesystem-write": "Write",
    "agent.tool.shell-execute": "Bash",
}


def load_agentpack_catalog(path):
    """Load the common role source without reading any provider consumer."""
    value = safe_load_json(Path(path), default=None)
    if not isinstance(value, dict) or set(value) != {"catalog_version", "roles"}:
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    rows = value["roles"]
    if value["catalog_version"] != "1.0.0" or not isinstance(rows, list):
        raise ValueError("HARNESS_VERSION_UNSUPPORTED")
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != _ROLE_FIELDS:
            raise ValueError("HARNESS_CATALOG_MISMATCH")
        key = (row["pack_id"], row["role_id"])
        list_fields = ("skills", "tool_requirements", "command_ids", "activation_requirements")
        if (key in seen or row["model_class"] not in _MODEL_SELECTORS
                or not all(isinstance(row.get(field), str) and row[field] for field in
                           ("pack_id", "role_id", "content"))
                or not isinstance(row["description_lines"], list)
                or not row["description_lines"]
                or not all(isinstance(item, str) for item in row["description_lines"])
                or not all(isinstance(row[field], list)
                           and all(isinstance(item, str) and item for item in row[field])
                           for field in list_fields)
                or _COMMON_FORBIDDEN.search(row["content"])):
            raise ValueError("HARNESS_CATALOG_MISMATCH")
        if set(_TOKEN.findall(row["content"])) - set(_CLAUDE_TOKENS):
            raise ValueError("HARNESS_MAPPING_MISSING")
        seen.add(key)
        result.append(AgentRole(row["pack_id"], row["role_id"], tuple(row["description_lines"]),
                                row["content"], tuple(row["skills"]),
                                tuple(row["tool_requirements"]), tuple(row["command_ids"]),
                                row["model_class"], tuple(row["activation_requirements"])))
    if not result:
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    return tuple(result)


def semantic_agent_roles(catalog_path):
    return load_agentpack_catalog(catalog_path)


def expected_agent_inventory(env):
    """Manifest-derived independent expected set; renderer output cannot define it."""
    result = []
    for pack in list_packs(env):
        for entry in load_manifest(env, pack).get("files", []):
            if entry.get("role") == "agent":
                result.append((pack, Path(entry["src"]).stem))
    if len(result) != len(set(result)):
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    return tuple(sorted(result))


def compare_agent_inventory(roles, expected):
    observed = [(role.pack_id, role.role_id) for role in roles]
    return {"missing": tuple(sorted(set(expected) - set(observed))),
            "extra": tuple(sorted(set(observed) - set(expected))),
            "duplicates": tuple(sorted({item for item in observed if observed.count(item) > 1}))}


def _resolve_tokens(role, provider_id):
    mapping = _CLAUDE_TOKENS if provider_id == "claude-code" else _CODEX_TOKENS
    def replace(match):
        try:
            return mapping[match.group(1)]
        except KeyError as error:
            raise ValueError("HARNESS_ACTIVATION_UNSUPPORTED") from error
    return _TOKEN.sub(replace, role.content)


def load_claude_role_bindings(path, roles):
    value = safe_load_json(Path(path), default=None)
    if not isinstance(value, dict) or set(value) != {"binding_version", "roles"}:
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    if value["binding_version"] != "1.0.0" or not isinstance(value["roles"], list):
        raise ValueError("HARNESS_VERSION_UNSUPPORTED")
    result = {}
    for row in value["roles"]:
        if not isinstance(row, dict) or set(row) != {"pack_id", "role_id", "model_selector", "color"}:
            raise ValueError("HARNESS_CATALOG_MISMATCH")
        key = (row["pack_id"], row["role_id"])
        if (key in result or not all(isinstance(row[field], str) and row[field]
                                     for field in row)):
            raise ValueError("HARNESS_CATALOG_MISMATCH")
        result[key] = (row["model_selector"], row["color"])
    expected = {(role.pack_id, role.role_id) for role in roles}
    if set(result) != expected:
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    return result


def agent_model_trace(roles, bindings_path, env):
    """Independently trace common classes to Claude selectors and pack defaults."""
    value = safe_load_json(Path(bindings_path), default=None)
    if not isinstance(value, dict) or value.get("binding_version") != "1.0.0":
        raise ValueError("HARNESS_VERSION_UNSUPPORTED")
    rows = value.get("roles")
    if not isinstance(rows, list):
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    bound, duplicates = {}, set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"pack_id", "role_id", "model_selector", "color"}:
            raise ValueError("HARNESS_CATALOG_MISMATCH")
        key = (row["pack_id"], row["role_id"])
        if key in bound:
            duplicates.add(key)
        bound[key] = row["model_selector"]
    expected = {(role.pack_id, role.role_id): role for role in roles}
    report = {"missing": tuple(sorted(set(expected) - set(bound))),
              "extra": tuple(sorted(set(bound) - set(expected))),
              "duplicates": tuple(sorted(duplicates)), "unknown_selector": (),
              "model_class_mismatch": ()}
    unknown, mismatch = [], []
    classes = {"haiku": "economy", "sonnet": "implementation", "inherit": "implementation",
               "opus": "frontier"}
    for key in sorted(set(expected) & set(bound)):
        selector = bound[key]
        match = re.fullmatch(r"\{\{([A-Z0-9_]+)\}\}", selector)
        if match:
            defaults = {row["id"]: row.get("default")
                        for row in load_manifest(env, key[0]).get("interview", [])}
            selector = defaults.get(match.group(1))
        if selector not in classes:
            unknown.append((key[0], key[1], selector))
            continue
        if expected[key].model_class != classes[selector]:
            mismatch.append((key[0], key[1], expected[key].model_class, classes[selector]))
    return {**report, "unknown_selector": tuple(unknown),
            "model_class_mismatch": tuple(mismatch)}


def _claude_frontmatter(role, binding):
    """Map semantic requirements to Claude syntax; no legacy template is consulted."""
    try:
        tools = ", ".join(_CLAUDE_TOOLS[item] for item in role.tool_requirements)
    except KeyError as error:
        raise ValueError("HARNESS_MAPPING_MISSING") from error
    model_selector, color = binding[(role.pack_id, role.role_id)]
    lines = ["---", f"name: {{{{PACK_PREFIX}}}}-{role.role_id}", "description: >-"]
    lines.extend("  " + line if line else "" for line in role.description_lines)
    lines.append(f"tools: {tools}")
    if role.skills:
        lines.append("skills:")
        lines.extend(f"  - {skill}" for skill in role.skills)
    lines.extend((f"model: {model_selector}", f"color: {color}", "---", ""))
    return "\n".join(lines)


def project_agent_role(role, provider_id, *, claude_bindings=None, pack_prefix=None):
    """Render named consumers from the semantic record, never from a provider output."""
    if provider_id == "claude-code":
        if claude_bindings is None:
            raise ValueError("HARNESS_MAPPING_MISSING")
        target = f".claude/agents/{{{{PACK_PREFIX}}}}-{role.role_id}.md"
        rendered = (_claude_frontmatter(role, claude_bindings) + _resolve_tokens(role, provider_id)).encode("utf-8")
    elif provider_id == "codex":
        if "command.workflow-carrier" in role.activation_requirements:
            raise ValueError("HARNESS_ACTIVATION_UNSUPPORTED:codex:command.workflow-carrier:P4")
        target = f".codex/agents/{{{{PACK_PREFIX}}}}-{role.role_id}.toml"
        model = _MODEL_SELECTORS[role.model_class]
        skills = ", ".join(json.dumps(item, ensure_ascii=False) for item in role.skills)
        commands = ", ".join(json.dumps(item, ensure_ascii=False) for item in role.command_ids)
        rendered = (f'name = {json.dumps(role.pack_id + "-" + role.role_id)}\n'
                    f'model = {json.dumps(model)}\n'
                    f'skills = [{skills}]\n'
                    f'command_requirements = [{commands}]\n'
                    f'developer_instructions = {json.dumps(_resolve_tokens(role, provider_id), ensure_ascii=False)}\n').encode("utf-8")
    else:
        raise ValueError("HARNESS_MAPPING_MISSING")
    if pack_prefix is not None:
        target = target.replace("{{PACK_PREFIX}}", pack_prefix)
        rendered = rendered.replace(b"{{PACK_PREFIX}}", pack_prefix.encode("utf-8"))
    return AgentProjection(provider_id, target, rendered)


_ARTIFACT_ID_SEGMENT = re.compile(r"^[a-z][a-z0-9-]*$")


def _artifact_identity_component(value):
    """Preserve valid segments; encode only semantic values P2 cannot represent."""
    if _ARTIFACT_ID_SEGMENT.fullmatch(value):
        return value
    return "encoded-" + value.encode("utf-8").hex()


def _agent_artifact_id(role, provider_id):
    return (f"harness.{provider_id}.agent.{_artifact_identity_component(role.pack_id)}."
            f"{_artifact_identity_component(role.role_id)}")


def _validate_agent_artifact_ids(roles, provider_id):
    artifact_ids = tuple(_agent_artifact_id(role, provider_id) for role in roles)
    if len(artifact_ids) != len(set(artifact_ids)):
        raise ValueError("HARNESS_CATALOG_MISMATCH:agent-artifact-id-collision")


def plan_agent_artifact(role, *, provider_id, catalog_path, claude_bindings_path=None,
                        claude_bindings=None, pack_prefix=None):
    catalog_roles = semantic_agent_roles(catalog_path)
    catalog_role = next((candidate for candidate in catalog_roles
                         if (candidate.pack_id, candidate.role_id)
                         == (role.pack_id, role.role_id)), None)
    if catalog_role != role:
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    _validate_agent_artifact_ids(catalog_roles, provider_id)
    if provider_id == "claude-code" and claude_bindings is None:
        claude_bindings = load_claude_role_bindings(claude_bindings_path, catalog_roles)
    projection = project_agent_role(role, provider_id, claude_bindings=claude_bindings,
                                    pack_prefix=pack_prefix)
    source = ArtifactSource("harness.agent-role.catalog",
                            "packages/harness/configs/common/agent-packs/roles.json",
                            sha256_digest(Path(catalog_path).read_bytes()))
    sources = (source,)
    if provider_id == "claude-code":
        sources += (ArtifactSource("harness.claude.agent-bindings",
                                   "packages/harness/configs/claude-code/agent-packs/role-bindings.json",
                                   sha256_digest(Path(claude_bindings_path).read_bytes())),)
    identity = ArtifactAdapterIdentity(f"harness.{provider_id}.agent", "1.0.1",
                                       ProviderId(provider_id), "1.0.0", ())
    return plan_artifact_render(ArtifactRenderRequest(
        _agent_artifact_id(role, provider_id), sources,
        ArtifactTarget(projection.target_path, ("whole-file", ())), identity, (),
        {"pack_id": role.pack_id, "role_id": role.role_id, "model_class": role.model_class,
         "command_ids": list(role.command_ids), "pack_prefix": pack_prefix or "template"},
        lambda _request: projection.rendered, contract_version="1.1.0"))


def classify_agent_projection(*, managed: bool, observed: bytes | None, expected: bytes,
                              user_owned: bool = False):
    """Keep P2-style no-adoption and managed-drift states visible for both targets."""
    if user_owned:
        return "ownership-conflict"
    if observed is None:
        return "missing"
    if not managed:
        return "ownership-conflict"
    return "clean" if observed == expected else "managed-drift"
