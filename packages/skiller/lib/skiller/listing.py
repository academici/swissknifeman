"""list — registered projects (<state>/skiller/projects.json)."""
import json
from pathlib import Path

from aicore.util.cli import parse_flags
from .state import load_db, save_db


RECORD_FIELDS = ("path", "channel", "provider", "profile", "profile_source", "plugins",
                 "settings_file", "hub", "agent", "buckets", "exclude", "skills_path",
                 "target", "source_hash", "rendered_hash", "repair", "updated_at",
                 "first_connected_at")
SCHEMA_ID = "urn:swissknifeman:skiller:projects-list:v1"


def projects_document(db):
    """The `projects-list/v1` document: the declared registry fields plus `name` (directory
    name) and `connected_at`."""
    projects = []
    for rec in db["projects"]:
        item = {k: v for k, v in rec.items() if k in RECORD_FIELDS}
        item["name"] = Path(rec["path"]).name
        item["connected_at"] = rec.get("first_connected_at") or rec.get("updated_at") or ""
        projects.append(item)
    return {"$schema": SCHEMA_ID, "projects": projects}


def cmd_list(env, argv):
    opts = parse_flags(argv, {"--prune": "bool", "--json": "bool"})
    if opts["help"]:
        print("skiller list [--prune] [--json]")
        return
    db = load_db(env)
    if opts["json"] and not opts["prune"]:
        print(json.dumps(projects_document(db), indent=2, ensure_ascii=False))
        return
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
