"""doctor — диагностика окружения."""
import json
import os
import sys
from pathlib import Path

from .common import DB_VERSION, parse_flags
from .state import registry_git_state


def cmd_doctor(env, argv):
    opts = parse_flags(argv, {})
    if opts["help"]:
        print("swissknifeman doctor")
        return
    root = env.root
    issues = 0

    def check(ok, label, hint=""):
        nonlocal issues
        mark = "ok " if ok else "FAIL"
        print(f"  [{mark}] {label}" + (f" — {hint}" if hint and not ok else ""))
        if not ok:
            issues += 1

    print(f"swissknifeman doctor (реестр: {root})")
    check(sys.version_info >= (3, 8), f"python3 {sys.version.split()[0]}")

    link = Path(os.path.expanduser("~/.local/bin/swissknifeman"))
    resolved = Path(os.path.realpath(link)) if link.exists() else None
    check(resolved is not None and str(resolved).startswith(str(root) + os.sep),
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
                  f"записи projects.json указывают на существующие каталоги",
                  f"{len(stale)} устаревших — swissknifeman list --prune")
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

    print(f"\n{'Все проверки пройдены.' if issues == 0 else f'Проблем: {issues}'}")
    if issues:
        sys.exit(1)
