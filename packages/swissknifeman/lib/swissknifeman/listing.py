"""list — зарегистрированные проекты (~/.swissknifeman/projects.json)."""
from pathlib import Path

from .common import parse_flags
from .state import load_db, save_db


def cmd_list(env, argv):
    opts = parse_flags(argv, {"--prune": "bool"})
    if opts["help"]:
        print("swissknifeman list [--prune]")
        return
    db = load_db(env)
    if not db["projects"]:
        print("Нет зарегистрированных проектов — swissknifeman connect/vendor "
              "в проекте добавит запись.")
        return
    rows, missing = [], []
    for rec in db["projects"]:
        state = "ok" if Path(rec["path"]).is_dir() else "missing"
        if state == "missing":
            missing.append(rec)
        rows.append((state, rec["channel"], rec.get("profile") or "-",
                     rec.get("updated_at", "-"), rec["path"]))
    print(f"{'STATE':8} {'CHANNEL':12} {'PROFILE':18} {'UPDATED':22} PATH")
    for state, channel, profile, updated, path in rows:
        print(f"{state:8} {channel:12} {profile:18} {updated:22} {path}")
    if opts["prune"]:
        if not missing:
            print("\nНечего чистить.")
            return
        db["projects"] = [r for r in db["projects"] if Path(r["path"]).is_dir()]
        save_db(env, db)
        print(f"\nУдалено записей: {len(missing)}")
    elif missing:
        print(f"\n{len(missing)} запис(ей) указывают на отсутствующие каталоги — "
              f"почистить: swissknifeman list --prune")
