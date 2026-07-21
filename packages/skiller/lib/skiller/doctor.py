"""doctor — диагностика окружения."""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from .common import DB_VERSION, harness_bin, is_within, parse_flags, warn
from .state import registry_git_state


def _delegate_settings_doctor(env, opts):
    """Фасад `skiller doctor --settings` → `harness doctor --settings` (subprocess).
    Логики проверок здесь НЕТ (D10, единый источник истины в harness): только
    прокидываем stdout (наследуемый) и код возврата. harness не найден → warn и
    graceful skip (rc 0, как apply_permissions). Никакого разбора вывода harness."""
    binp = harness_bin(env)
    if binp is None:
        warn("harness не установлен — settings-doctor недоступен "
             "(установите: packages/harness/install.sh)")
        return
    cmd = [str(binp), "doctor", "--settings",
           "--target", opts.get("target") or os.getcwd()]
    try:
        result = subprocess.run(cmd, check=False, timeout=30)
    except (subprocess.SubprocessError, OSError) as e:
        warn(f"harness doctor --settings не запустился: {e}")
        return
    if result.returncode:
        sys.exit(result.returncode)


def _audit_downstream(env):
    """Гигиена publish-surface онбордженных проектов: always-loaded слой, который Claude Code
    читает в КАЖДОЙ сессии целевого проекта (CLAUDE.md ≤200, scoped/unscoped rules, deny-пресет).
    Это и есть основной runtime-расход токенов — он в ЦЕЛЕВОМ проекте, не в реестре."""
    print("\nDownstream publish-surface (always-loaded слой в проектах):")
    db_file = env.db_file
    projects = []
    if db_file.exists():
        try:
            projects = json.loads(db_file.read_text(encoding="utf-8")).get("projects", [])
        except json.JSONDecodeError:
            pass
    seen = 0
    for p in projects:
        pdir = Path(p.get("path", ""))
        if not pdir.is_dir():
            continue
        seen += 1
        name = p.get("id") or pdir.name
        cmd_md = pdir / "CLAUDE.md"
        if not cmd_md.is_file():
            cmd_md = pdir / ".claude" / "CLAUDE.md"
        lines = (len(cmd_md.read_text(encoding="utf-8", errors="ignore").splitlines())
                 if cmd_md.is_file() else 0)
        scoped = unscoped = 0
        rules_dir = pdir / ".claude" / "rules"
        if rules_dir.is_dir():
            for r in sorted(rules_dir.glob("*.md")):
                head = r.read_text(encoding="utf-8", errors="ignore")[:400]
                parts = head.split("---", 2)
                if head.lstrip().startswith("---") and len(parts) >= 3 and "paths:" in parts[1]:
                    scoped += 1
                else:
                    unscoped += 1
        deny = False
        for sf in (pdir / ".claude" / "settings.json",
                   pdir / ".claude" / "settings.local.json"):
            if sf.is_file():
                try:
                    s = json.loads(sf.read_text(encoding="utf-8"))
                    if (s.get("permissions") or {}).get("deny"):
                        deny = True
                except json.JSONDecodeError:
                    pass
        flags = []
        if lines > 200:
            flags.append(f"CLAUDE.md {lines}>200")
        if unscoped:
            flags.append(f"{unscoped} unscoped-rules (always-loaded)")
        if not deny:
            flags.append("нет deny-пресета шума")
        mark = "ok " if not flags else "warn"
        tail = (" — " + "; ".join(flags)) if flags else ""
        print(f"  [{mark}] {name}: CLAUDE.md={lines} строк, "
              f"rules={scoped} scoped/{unscoped} unscoped, "
              f"deny={'да' if deny else 'НЕТ'}{tail}")
    if seen == 0:
        print("  (нет онбордженных проектов на диске)")


def _vendor_drift(env):
    """Дрейф vendor-скиллов по флоту: зарегистрированные mode=vendor проекты, чей набор
    разошёлся с ТЕКУЩИМ реестром (add — новый скилл появился, update — sha256 сменился,
    remove — выпал из конфига). Сухой plan_sync, ничего не пишет. Connect-only проекты
    (без .swissknifeman/config.json) пропускаются — им обновление приходит из marketplace
    само. Возвращает [(project_name, plan), ...] только для тех, у кого есть дрейф."""
    from .skillset import load_skillset_config, plan_sync
    db_file = env.db_file
    if not db_file.exists():
        return []
    try:
        projects = json.loads(db_file.read_text(encoding="utf-8")).get("projects", [])
    except json.JSONDecodeError:
        return []
    drifted = []
    for p in projects:
        pdir = Path(p.get("path", ""))
        if not pdir.is_dir():
            continue
        try:
            cfg = load_skillset_config(pdir)
        except SystemExit:
            continue  # битый .swissknifeman/config.json — отдельная забота, не роняем скан
        if cfg is None:
            continue
        try:
            # include_core=True — тот же дефолт, что и у `skiller sync` (cmd_sync:
            # include_core=not opts["no_core"], по умолчанию no_core=False). Без
            # этого сравнение с реестром ложно считает CORE_SKILLS «add»/«remove».
            plan = plan_sync(env, pdir, cfg, include_core=True)
        except Exception:
            continue
        if plan["add"] or plan["update"] or plan["remove"] or plan["conflicts"]:
            drifted.append((p.get("id") or pdir.name, plan))
    return drifted


def _audit_vendor_drift(env):
    """Детальный по-проектный отчёт дрейфа vendor-скиллов (--vendor-drift)."""
    print("\nДрейф vendor-скиллов от реестра (mode=vendor, сухой расчёт):")
    drifted = _vendor_drift(env)
    if not drifted:
        print("  (все vendor-проекты синхронизированы с реестром)")
        return
    for name, plan in drifted:
        parts = []
        if plan["add"]:
            parts.append(f"+{len(plan['add'])} новых")
        if plan["update"]:
            parts.append(f"~{len(plan['update'])} с новой версией")
        if plan["remove"]:
            parts.append(f"-{len(plan['remove'])} лишних")
        if plan["conflicts"]:
            parts.append(f"!{len(plan['conflicts'])} конфликтов (прерванный sync?)")
        print(f"  [warn] {name}: " + ", ".join(parts)
              + "  (применить: skiller sync — из каталога проекта)")


def _vendor_drift_summary(env):
    """Компактная summary-строка для дефолтного doctor: сколько vendor-проектов отстало
    от реестра (новые/изменившиеся managed-скиллы). Детали — --vendor-drift."""
    drifted = _vendor_drift(env)
    if drifted:
        print(f"  [warn] vendor-скиллы: {len(drifted)} проект(ов) отстали от реестра "
              "(детали: skiller doctor --vendor-drift)")
    else:
        print("  [ok ] vendor-скиллы: дрейфа от реестра нет")


def _downstream_claude_md_summary(env):
    """Компактная summary-строка для дефолтного doctor: сколько онбордженных проектов имеют
    CLAUDE.md > 200 строк (always-loaded → резидентный токен-расход). Детали — --downstream."""
    db_file = env.db_file
    if not db_file.exists():
        return
    try:
        projects = json.loads(db_file.read_text(encoding="utf-8")).get("projects", [])
    except json.JSONDecodeError:
        return
    seen = over = 0
    for p in projects:
        pdir = Path(p.get("path", ""))
        if not pdir.is_dir():
            continue
        seen += 1
        cmd_md = pdir / "CLAUDE.md"
        if not cmd_md.is_file():
            cmd_md = pdir / ".claude" / "CLAUDE.md"
        if (cmd_md.is_file()
                and len(cmd_md.read_text(encoding="utf-8", errors="ignore").splitlines()) > 200):
            over += 1
    if not seen:
        return
    if over:
        print(f"  [warn] downstream CLAUDE.md: {over}/{seen} проектов > 200 строк "
              "(always-loaded; детали: skiller doctor --downstream)")
    else:
        print(f"  [ok ] downstream CLAUDE.md: все {seen} ≤ 200 строк")


def _provider_distribution_doctor(env, target):
    """Read-only provider-aware delivery preflight; never invokes native Codex."""
    from .config import load_config
    from .publication import build_connect_distribution_plan, build_vendor_distribution_plan
    from .skillset import DEFAULT_SKILLS_PATH, load_skillset_config
    from core import find_repo_root
    config = load_config(env, target)
    repo_root = find_repo_root(env.root) or env.root
    print(f"Provider distribution (target: {target}):")
    try:
        connect = build_connect_distribution_plan(config, target, project_id=target.name,
                                                  repo_root=repo_root)
        print("  [ok ] marketplace plan: " + ", ".join(item.provider_id for item in connect))
    except SystemExit as exc:
        print(f"  [warn] marketplace plan blocked: {exc}")
    cfg = load_skillset_config(target)
    if cfg is None:
        print("  [ok ] vendor plan: no .swissknifeman/config.json")
        return
    try:
        vendor = build_vendor_distribution_plan(
            config, target, project_id=target.name,
            claude_path=cfg.get("skills_path") or DEFAULT_SKILLS_PATH,
            codex_path=".agents/skills")
        print("  [ok ] vendor plan: " + ", ".join(
            f"{item.provider_id}:{item.target.relative_to(target)}" for item in vendor))
    except SystemExit as exc:
        print(f"  [warn] vendor plan blocked: {exc}")


def cmd_doctor(env, argv):
    opts = parse_flags(argv, {"--downstream": "bool", "--vendor-drift": "bool",
                              "--settings": "bool", "--provider-distribution": "bool",
                              "--target": "str"})
    if opts["help"]:
        print("skiller doctor [--downstream] [--vendor-drift] [--settings [--target P]]\n"
              "  --downstream:   гигиена publish-surface онбордженных проектов "
              "(CLAUDE.md ≤200, scoped/unscoped rules, deny-пресет).\n"
              "  --vendor-drift: по-проектный дрейф vendor-скиллов от реестра "
              "(новые/изменившиеся managed-скиллы; сухой расчёт).\n"
              "  --provider-distribution: read-only preflight Claude/Codex delivery; "
              "не запускает native installer.\n"
              "  --settings:     аудит настроек Claude Code (фасад → harness "
              "doctor --settings).")
        return
    if opts.get("settings"):
        _delegate_settings_doctor(env, opts)
        return
    if opts.get("provider_distribution"):
        from .config import resolve_target
        target, _ = resolve_target(env, opts)
        _provider_distribution_doctor(env, target)
        return
    root = env.root
    issues = 0

    def check(ok, label, hint=""):
        nonlocal issues
        mark = "ok " if ok else "FAIL"
        print(f"  [{mark}] {label}" + (f" — {hint}" if hint and not ok else ""))
        if not ok:
            issues += 1

    print(f"skiller doctor (реестр: {root})")
    check(sys.version_info >= (3, 8), f"python3 {sys.version.split()[0]}")

    link = Path(os.path.expanduser("~/.local/bin/skiller"))
    resolved = Path(os.path.realpath(link)) if link.exists() else None
    check(resolved is not None and is_within(resolved, root),
          f"симлинк {link}",
          "перезапустите install.sh из репозитория реестра")
    on_path = any(Path(p or ".").resolve() == link.parent.resolve()
                  for p in os.environ.get("PATH", "").split(os.pathsep))
    check(on_path, f"{link.parent} в PATH",
          'добавьте: export PATH="$HOME/.local/bin:$PATH"')

    db_file = env.db_file
    if db_file.exists():
        try:
            db = json.loads(db_file.read_text(encoding="utf-8"))
            check(db.get("version", 1) <= DB_VERSION,
                  f"projects.json (записей: {len(db.get('projects', []))})",
                  "версия новее поддерживаемой — git pull в реестре")
            stale = [p for p in db.get("projects", [])
                     if not Path(p["path"]).is_dir()]
            check(not stale,
                  "записи projects.json указывают на существующие каталоги",
                  f"{len(stale)} устаревших — skiller list --prune")
        except json.JSONDecodeError:
            check(False, "projects.json парсится",
                  "битый JSON — следующая запись пересоздаст файл")
    else:
        check(True, "projects.json отсутствует (создастся при первом connect/vendor)")

    sha, dirty = registry_git_state(env)
    check(sha is not None, "реестр — git-репозиторий")
    if sha:
        check(not dirty, f"реестр чистый (HEAD {sha})",
              "есть незакоммиченные изменения скиллов — marketplace видит "
              "только коммиты")
    profiles = sorted((root / "profiles").glob("*.json"))
    bad = []
    for p in profiles:
        try:
            json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            bad.append(p.name)
    check(profiles and not bad, f"профили загружаются ({len(profiles)})",
          f"битые: {', '.join(bad)}")

    # harness (окружение Claude Code — permissions/MCP/хуки) — ОПЦИОНАЛЬНАЯ
    # зависимость: apply_permissions/_run_harness graceful-skip'ают, если её нет
    # (standalone-раскладка / не установлен). Раньше doctor вообще не смотрел на
    # harness — «не установлен» и «установлен, но сломан» (битый бинарь/венв/etc.)
    # были неотличимы: connect/integrate тихо теряли permissions-пресеты, а doctor
    # рапортовал «Все проверки пройдены» (аудит Doc-1). Отсутствие — НЕ FAIL (это
    # опциональный пакет); сломанность при наличии — FAIL.
    hbin = harness_bin(env)
    if hbin is None:
        print("  [ok ] harness не установлен — опционально (permissions/MCP/хуки "
              "не применяются; установка: packages/harness/install.sh)")
    else:
        try:
            r = subprocess.run([str(hbin), "--help"], capture_output=True,
                               text=True, timeout=10, check=False)
            check(r.returncode == 0, f"harness исполняется ({hbin})",
                  f"exit {r.returncode}: {(r.stderr or r.stdout).strip()[:200]}")
        except subprocess.TimeoutExpired:
            check(False, f"harness исполняется ({hbin})", "превышен таймаут 10s")
        except OSError as e:
            check(False, f"harness исполняется ({hbin})", str(e))

    # JSON-схемы конфигов (schema/*.json) — DX-артефакт (IntelliSense). Рантайм-
    # валидация ручная (CONFIG_KEYS/SKILLSET_KEYS); схема не должна расходиться с
    # кодом, иначе редактор подсказывает не то, что принимает skiller. Тот же гейт
    # держит tests/test_schema.py; doctor даёт его как интерактивную проверку.
    from .common import CONFIG_KEYS
    from .skillset import SKILLSET_KEYS
    for fname, keys, label in (
            ("swissknife.schema.json", CONFIG_KEYS, ".swissknife.json"),
            ("swissknifeman-config.schema.json", SKILLSET_KEYS,
             ".swissknifeman/config.json")):
        sf = root / "schema" / fname
        if not sf.is_file():
            check(False, f"схема {fname}", "нет файла в schema/")
            continue
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("корень схемы должен быть объектом")
            props = set(data.get("properties", {}))
        except (json.JSONDecodeError, ValueError) as e:
            check(False, f"схема {fname} парсится", str(e))
            continue
        check(props == set(keys), f"схема {fname} ⇄ ключи {label}",
              f"разошлись: лишние в схеме {sorted(props - set(keys))}, "
              f"нет в схеме {sorted(set(keys) - props)} — обнови schema/{fname}")
        # Doc-2: имена ключей — не единственное, что может разойтись. ТИП свойства
        # в схеме (string/array/…) — тоже контракт с CONFIG_KEYS/SKILLSET_KEYS; раньше
        # doctor сверял только имена ("⇄ ключи OK"), молчаливо пропуская расхождение
        # типа (тест test_schema.py::test_property_types_align_with_python это ловит,
        # но doctor ложно успокаивал интерактивным "OK").
        json_type = {str: "string", list: "array", int: "integer",
                    dict: "object", bool: "boolean"}
        props_data = data.get("properties", {})
        type_mismatches = []
        for k, t in keys.items():
            if k not in props_data:
                continue
            if isinstance(t, tuple):
                # Мульти-тип (memory_brain = (str, dict)) → в схеме oneOf; сверяем,
                # что члены покрывают ровно ожидаемые JSON-типы.
                members = {b.get("type") for b in props_data[k].get("oneOf", [])}
                want = {json_type.get(x) for x in t}
                if members != want:
                    type_mismatches.append(
                        f"{k}: схема oneOf={sorted(m for m in members if m)} код={sorted(want)}")
            elif props_data[k].get("type") != json_type.get(t):
                type_mismatches.append(
                    f"{k}: схема={props_data[k].get('type')} код={json_type.get(t)}")
        check(not type_mismatches, f"схема {fname} ⇄ типы {label}",
              f"разошлись типы: {'; '.join(type_mismatches)} — обнови schema/{fname}")

    # freshness хабов: штамп <!-- swissknifeman:registry sha=… --> в хабе проекта
    # сверяем с текущим sha реестра (тот же расчёт, что в generate-hub.sh). Проекты
    # без штампа (старый хаб) — пропускаем: получат штамп при следующей перегенерации.
    reg_skills = root / "skills.json"
    if reg_skills.is_file():
        reg_sha = hashlib.sha256(reg_skills.read_bytes()).hexdigest()[:12]
        pat = re.compile(r"swissknifeman:registry sha=([0-9a-f]+)")
        projects = []
        if db_file.exists():
            try:
                projects = json.loads(db_file.read_text(encoding="utf-8")).get("projects", [])
            except json.JSONDecodeError:
                projects = []
        stale_hubs = []
        for p in projects:
            pdir = Path(p["path"])
            if not pdir.is_dir():
                continue
            for cand in (pdir / ".ai/guidelines/swissknifeman-hub.md", pdir / "CLAUDE.md"):
                if not cand.is_file():
                    continue
                m = pat.search(cand.read_text(encoding="utf-8", errors="ignore"))
                if m:
                    if m.group(1) != reg_sha:
                        stale_hubs.append(pdir.name)
                    break
        check(not stale_hubs, f"хабы проектов свежие (реестр sha {reg_sha})",
              f"{len(stale_hubs)} устарел(и): {', '.join(stale_hubs)} — перегенерируй "
              "(skiller update / generate-hub.sh)")

    if opts.get("downstream"):
        _audit_downstream(env)
    else:
        _downstream_claude_md_summary(env)

    if opts.get("vendor_drift"):
        _audit_vendor_drift(env)
    else:
        _vendor_drift_summary(env)

    print(f"\n{'Все проверки пройдены.' if issues == 0 else f'Проблем: {issues}'}")
    if issues:
        sys.exit(1)
