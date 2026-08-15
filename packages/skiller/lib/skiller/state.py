"""Registry project database and Git state."""
import json
import subprocess
from pathlib import Path

from core import atomic_write_text, load_json_db

from .common import DB_VERSION, now_iso


def load_db(env):
    """Load the project database with shared corrupt-file recovery."""
    return load_json_db(env.db_file, {"version": DB_VERSION, "projects": []},
                        max_version=DB_VERSION)


def save_db(env, db):
    atomic_write_text(env.db_file,
                      json.dumps(db, indent=2, ensure_ascii=False) + "\n")


def upsert_project(env, record):
    """Records keyed by (path, channel, provider); preserves first_connected_at.

    Old rows predate provider-aware delivery.  Their absent provider is the frozen
    legacy Claude default, so an ordinary Claude refresh updates that row instead
    of creating a duplicate record.
    """
    db = load_db(env)
    # Canonicalize paths to avoid duplicate records for one directory.
    record["path"] = str(Path(record["path"]).resolve())
    record["updated_at"] = now_iso()
    provider = record.get("provider", "claude-code")
    record["provider"] = provider
    for i, p in enumerate(db["projects"]):
        existing_provider = p.get("provider", "claude-code")
        if (p["path"] == record["path"] and p["channel"] == record["channel"]
                and existing_provider == provider):
            record["first_connected_at"] = p.get("first_connected_at",
                                                 record["updated_at"])
            db["projects"][i] = record
            break
    else:
        record["first_connected_at"] = record["updated_at"]
        db["projects"].append(record)
    save_db(env, db)


def db_records(env, path):
    target = str(Path(path).resolve())  # Match upsert_project canonicalization.
    return [p for p in load_db(env)["projects"] if p["path"] == target]


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
