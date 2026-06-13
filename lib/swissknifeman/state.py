"""~/.swissknifeman/projects.json и git-состояние реестра."""
import json
import os
import subprocess
from datetime import date

from .common import DB_VERSION, die, now_iso, warn


def load_db(env):
    db_file = env.db_file
    if not db_file.exists():
        return {"version": DB_VERSION, "projects": []}
    try:
        db = json.loads(db_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup = db_file.with_name(
            f"projects.json.corrupt.{date.today().isoformat()}")
        db_file.rename(backup)
        warn(f"{db_file} повреждён — переименован в {backup.name}, начинаю заново "
             f"(записи восстановятся при swissknifeman update в проектах)")
        return {"version": DB_VERSION, "projects": []}
    if db.get("version", 1) > DB_VERSION:
        die(f"{db_file} записан более новой версией swissknifeman — обновите "
            f"репозиторий реестра (git pull) и перезапустите install.sh")
    return db


def save_db(env, db):
    env.state_dir.mkdir(parents=True, exist_ok=True)
    db_file = env.db_file
    tmp = db_file.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(db, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    os.replace(tmp, db_file)


def upsert_project(env, record):
    """Records keyed by (path, channel); preserves first_connected_at."""
    db = load_db(env)
    record["updated_at"] = now_iso()
    for i, p in enumerate(db["projects"]):
        if p["path"] == record["path"] and p["channel"] == record["channel"]:
            record["first_connected_at"] = p.get("first_connected_at",
                                                 record["updated_at"])
            db["projects"][i] = record
            break
    else:
        record["first_connected_at"] = record["updated_at"]
        db["projects"].append(record)
    save_db(env, db)


def db_records(env, path):
    return [p for p in load_db(env)["projects"] if p["path"] == str(path)]


# --- registry git state ---------------------------------------------------------
def registry_git_state(env):
    """(short sha | None, dirty: bool) — dirty considers skills/ + manifests."""
    root = env.root
    try:
        sha = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()
        porcelain = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain",
             "skills", "generate-skill", "skills.json", ".claude-plugin"],
            capture_output=True, text=True, check=True).stdout.strip()
        return sha, bool(porcelain)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None, False


def print_registry_state(env):
    sha, dirty = registry_git_state(env)
    if sha:
        print(f"Реестр:   HEAD {sha}" + (" (есть незакоммиченные изменения "
              "скиллов — marketplace видит только коммиты)" if dirty else ""))
