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
merge-only через settings.write_*, бэкап *.bak. stdlib-only, сообщения на русском."""
import hashlib
import json
import os
import re
import stat
import subprocess

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


# ── render engine ────────────────────────────────────────────────────────────
def sha256_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _subst_single(text, answers):
    return _SINGLE_RE.sub(lambda m: str(answers.get(m.group(1), m.group(0))), text)


def _subst_double(text, answers):
    return _DOUBLE_RE.sub(lambda m: str(answers.get(m.group(1), m.group(0))), text)


def _apply_conditionals(text, answers):
    """Условные блоки. <!-- pack:if KEY -->...<!-- pack:endif --> — оставить при truthy
    answer; <!-- pack:ifnot KEY -->...<!-- pack:endif --> — при falsy/отсутствующем.
    Движок без логических операторов: пары if/ifnot держи ПЛОСКО (последовательно, не
    вложенно) — non-greedy парит каждый open с ближайшим endif."""
    for _ in range(10):  # вложенность: повторяем, пока есть изменения
        new = _IF_RE.sub(lambda m: m.group(2) if answers.get(m.group(1)) else "", text)
        new = _IFNOT_RE.sub(lambda m: m.group(2) if not answers.get(m.group(1)) else "",
                            new)
        if new == text:
            return new
        text = new
    return text


def _render_template_text(src_text, answers):
    return _subst_double(_apply_conditionals(src_text, answers), answers)


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
    файлов (src/target/kind/base_sha256/local_modified) и changed-флагом."""
    manifest = load_manifest(env, pack)
    pdir = pack_dir(env, pack)
    prior_files = {f["src"]: f for f in (prior or {}).get("files", [])}
    out_files, changed, notes = [], False, []
    for f in manifest.get("files", []):
        src, kind = f["src"], f.get("kind", "template")
        sfile = pdir / src
        if not sfile.exists():
            if f.get("optional"):
                continue
            die(f"{pack}: нет файла пака {src}")
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
                              "local_modified": False})
            continue

        rendered = (_render_template_text(sfile.read_text(encoding="utf-8"), answers)
                    if kind == "template" else sfile.read_text(encoding="utf-8"))
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
                          "base_sha256": new_sha, "local_modified": local_mod})
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
    lock.setdefault("packs", {})[pack] = _pack_lock_entry(env, pack, answers, report)
    if report["changed"] or prior is None:
        write_lock(target, lock, dry)
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
      conflict — изменились и база, и локальная копия; safe-apply — изменилась только база;
      nochange — база не менялась."""
    if pf is None:
        return "new-optional" if f.get("optional") else "new"
    if f.get("user_owned"):
        return "user-owned"
    disk_sha = sha256_text(tgt.read_text(encoding="utf-8")) if tgt.exists() else ""
    local_mod = disk_sha != pf.get("base_sha256")
    base_changed = new_sha != pf.get("base_sha256")
    if base_changed and local_mod:
        return "conflict"
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
    pdir = pack_dir(env, pack)
    plan, out_files = [], []
    for f in manifest.get("files", []):
        src, kind = f["src"], f.get("kind", "template")
        sfile = pdir / src
        if not sfile.exists():
            continue
        tgt_rel = _subst_single(f["target"], answers)
        tgt = target / tgt_rel
        if kind == "merge":
            _merge_fragment(target, sfile, f.get("merge", ""), answers, dry)
            out_files.append({"src": src, "target": tgt_rel, "kind": kind,
                              "base_sha256": sha256_text(sfile.read_text(encoding="utf-8")),
                              "local_modified": False})
            continue
        rendered = (_render_template_text(sfile.read_text(encoding="utf-8"), answers)
                    if kind == "template" else sfile.read_text(encoding="utf-8"))
        new_sha = sha256_text(rendered)
        cat = categorize_file_change(f, prior_files.get(src), new_sha, tgt)
        plan.append((cat, src, tgt_rel))
        if cat == "safe-apply" and not dry:
            tgt.parent.mkdir(parents=True, exist_ok=True)
            write_text(tgt, rendered, dry)
            if f.get("chmod") == "+x":
                _chmod_x(tgt)
        elif cat == "conflict" and not dry:
            write_text(target / (tgt_rel + ".pack-new"), rendered, dry)
            warn(f"  conflict: {tgt_rel} — новый вариант в {tgt_rel}.pack-new (смержи вручную)")
        out_files.append({"src": src, "target": tgt_rel, "kind": kind,
                          "base_sha256": new_sha,
                          "local_modified": cat == "conflict"})
    print(f"=== upgrade {pack}: {v_old} → {v_new} ===")
    for cat, _src, tgt_rel in plan:
        print(f"  [{cat}] {tgt_rel}")
    removed = sorted(set(prior_files) - {f["src"] for f in manifest.get("files", [])})
    for src in removed:
        warn(f"  removed в {v_new}: {src} — не удаляю авто (удали вручную при желании)")
    entry = _pack_lock_entry(env, pack, answers, {"files": out_files})
    entry["removed_optional"] = prior.get("removed_optional", [])
    lock.setdefault("packs", {})[pack] = entry
    write_lock(target, lock, dry)
    return 0


def do_doctor(env, pack=None, target=None, json_out=False):
    packs = [pack] if pack else list_packs(env)
    rc = 0
    catalog = []
    for pk in packs:
        manifest = load_manifest(env, pk)
        pdir = pack_dir(env, pk)
        problems = []
        ids = {e["id"] for e in manifest.get("interview", [])}
        for f in manifest.get("files", []):
            if not (pdir / f["src"]).exists() and not f.get("optional"):
                problems.append(f"нет {f['src']}")
        # проверка: каждый {{TOKEN}} в template-исходниках имеет interview-id
        for f in manifest.get("files", []):
            if f.get("kind", "template") != "template":
                continue
            sfile = pdir / f["src"]
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
            sfile = pdir / f["src"]
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
        die("usage: harness agent-packs <list|render|upgrade|doctor> [...]")
    sub, rest = argv[0], argv[1:]
    rest, answers = _pop_answers(rest)
    opts = parse_flags(rest, {
        "--pack": "str", "--target": "str", "--auto": "bool", "--dry-run": "bool",
        "--install-only": "bool", "--allow-shell": "str", "--list": "bool", "--json": "bool",
    })
    if opts.get("help"):
        print("harness agent-packs <list|render|upgrade|doctor> "
              "[--pack P] [--target DIR] [--auto] [--answer K=V] "
              "[--install-only] [--allow-shell off|safe|full] [--dry-run] [--json]")
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
        raise SystemExit(do_doctor(env, opts.get("pack"), target, json_out=opts.get("json")))

    if sub in ("render", "install", "upgrade"):
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
        raise SystemExit(do_render(env, pack, target, auto=bool(opts.get("auto")),
                                   overrides=answers, dry=dry,
                                   install_only=bool(opts.get("install_only")),
                                   shell_policy=shell_policy))

    die(f"неизвестная подкоманда agent-packs: {sub}")
