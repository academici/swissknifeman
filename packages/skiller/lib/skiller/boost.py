"""Sync boost.json::skills for Laravel Boost."""
import json
import sys

from aicore.util.io import atomic_write_text


def sync_boost_json(target, skill_names, dry_run=False):
    """If in target yes boost.json — idempotently add vendor ones
    skills in boost.json::skills (by frontmatter-name), to be picked up
    `php artisan boost:update`. Returns True, if boost.json detected."""
    boost_file = target / "boost.json"
    if not boost_file.is_file():
        return False
    try:
        data = json.loads(boost_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"WARN: {boost_file}: invalid JSON ({e}) — boost.json not updated",
              file=sys.stderr)
        return True
    existing = data.get("skills")
    if not isinstance(existing, list):
        existing = []
    added = [n for n in skill_names if n not in existing]
    if not added:
        print("boost.json: all vendor skills are already in skills[] — no changes")
        return True
    if dry_run:
        print(f"[dry-run] boost.json: would add to skills[]: {', '.join(added)}")
        return True
    data["skills"] = sorted(existing + added)
    atomic_write_text(boost_file,
                      json.dumps(data, indent=4, ensure_ascii=False) + "\n")
    print(f"boost.json: added to skills[] ({len(added)}): {', '.join(added)}")
    print("Detected Laravel Boost: do `php artisan boost:update` "
          "(or `composer ai:sync`), so that the skills get into CLAUDE.md/AGENTS.md "
          "and copies by tools.")
    return True
