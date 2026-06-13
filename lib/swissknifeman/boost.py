"""Синк boost.json::skills для Laravel Boost."""
import json
import sys


def sync_boost_json(target, skill_names, dry_run=False):
    """Если в target есть boost.json — идемпотентно дозаписать вендоренные
    скиллы в boost.json::skills (по frontmatter-name), чтобы их подхватил
    `php artisan boost:update`. Возвращает True, если boost.json обнаружен."""
    boost_file = target / "boost.json"
    if not boost_file.is_file():
        return False
    try:
        data = json.loads(boost_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"WARN: {boost_file}: invalid JSON ({e}) — boost.json не обновлён",
              file=sys.stderr)
        return True
    existing = data.get("skills")
    if not isinstance(existing, list):
        existing = []
    added = [n for n in skill_names if n not in existing]
    if not added:
        print("boost.json: все вендоренные скиллы уже в skills[] — без изменений")
        return True
    if dry_run:
        print(f"[dry-run] boost.json: добавил бы в skills[]: {', '.join(added)}")
        return True
    data["skills"] = existing + sorted(added)
    boost_file.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    print(f"boost.json: добавлено в skills[] ({len(added)}): {', '.join(added)}")
    print("Обнаружен Laravel Boost: выполните `php artisan boost:update` "
          "(или `composer ai:sync`), чтобы скиллы попали в CLAUDE.md/AGENTS.md "
          "и копии по тулзам.")
    return True
