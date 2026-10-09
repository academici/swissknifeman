"""list — registered projects (~/.swissknifeman/projects.json)."""
from pathlib import Path

from aicore.util.cli import parse_flags
from .state import load_db, save_db


def cmd_list(env, argv):
    opts = parse_flags(argv, {"--prune": "bool"})
    if opts["help"]:
        print("skiller list [--prune]")
        return
    db = load_db(env)
    if not db["projects"]:
        print("No projects registered - skiller connect/vendor "
              "in the project will add an entry.")
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
            print("\nNothing to clean.")
            return
        db["projects"] = [r for r in db["projects"] if Path(r["path"]).is_dir()]
        save_db(env, db)
        print(f"\nRecords deleted: {len(missing)}")
    elif missing:
        print(f"\n{len(missing)} entry(to her) indicate missing directories - "
              f"clean: skiller list --prune")
