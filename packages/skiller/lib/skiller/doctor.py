"""doctor — диагностика окружения."""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from .common import DB_VERSION, is_within, parse_flags
from .state import registry_git_state


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


def cmd_doctor(env, argv):
    opts = parse_flags(argv, {"--downstream": "bool"})
    if opts["help"]:
        print("skiller doctor [--downstream]\n"
              "  --downstream: гигиена publish-surface онбордженных проектов "
              "(CLAUDE.md ≤200, scoped/unscoped rules, deny-пресет).")
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

    print(f"\n{'Все проверки пройдены.' if issues == 0 else f'Проблем: {issues}'}")
    if issues:
        sys.exit(1)
