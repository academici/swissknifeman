"""lock — карта внешних скиллов проекта (skills-lock.json).

Композиция источников: **swissknifeman** (курируемый реестр) + **Laravel Boost**
(`boost.json::skills[]`). Скилл считается swissknifeman'овским, если его имя есть в
`skills.json` реестра — тогда swissknifeman wins; скилл из `boost.json::skills[]` —
`laravel-boost`; всё прочее установленное — `local` (собственный скилл проекта, напр.
раскатанный из другого хаба). Конфликты (имя в нескольких) не теряются: победитель в
`source`, второй в `also_in`. Источники работают порознь и вместе, складываясь в набор.

Universe = реально установленные скиллы (агентские раскладки) ∪ `boost.json::skills`.
Файл коммитится в проект — это lock-карта внешних скиллов (как composer.lock)."""
import json
import os
from pathlib import Path

from .common import die, parse_flags
from .config import resolve_target

# Раскладки, куда агенты ставят скиллы (claude — плоско, прочие — по своим путям).
AGENT_SKILL_DIRS = (".claude/skills", ".cursor/skills", ".ai/skills")
LOCK_VERSION = 1


def _registry_map(env):
    """skills.json реестра → {skill_name: bucket}."""
    f = env.root / "skills.json"
    if not f.is_file():
        die("skills.json не найден — сначала skiller registry")
    data = json.loads(f.read_text(encoding="utf-8"))
    skills = data["skills"] if isinstance(data, dict) else data
    out = {}
    for s in skills:
        name = s.get("name") or s.get("id")
        if name:
            out[name] = s.get("bucket", "")
    return out


def _installed_skills(target):
    """Имена физически установленных скиллов (по агентским раскладкам)."""
    names = set()
    for rel in AGENT_SKILL_DIRS:
        d = target / rel
        if d.is_dir():
            names |= {p.name for p in d.iterdir() if p.is_dir()}
    return names


def _boost_skills(target):
    """boost.json::skills[] или None, если Laravel Boost не подключён."""
    f = target / "boost.json"
    if not f.is_file():
        return None
    try:
        return list(json.loads(f.read_text(encoding="utf-8")).get("skills", []))
    except json.JSONDecodeError:
        return []


def compose_lock(env, target):
    """Собрать skills-lock: swissknifeman wins, boost дополняет, конфликты в also_in."""
    reg = _registry_map(env)
    boost = _boost_skills(target)
    universe = _installed_skills(target) | set(boost or [])
    skills = {}
    for name in sorted(universe):
        if name in reg:
            entry = {"source": "swissknifeman", "bucket": reg[name]}
            if boost and name in boost:
                entry["also_in"] = ["laravel-boost"]
        elif boost and name in boost:
            # Скилл явно объявлен в boost.json::skills — это скилл Laravel Boost.
            entry = {"source": "laravel-boost"}
        else:
            # Установлен, но ни в реестре, ни в boost.json — собственный скилл
            # проекта (например, раскатанный из другого хаба). Не приписываем Boost'у
            # только потому, что он подключён.
            entry = {"source": "local"}
        skills[name] = entry
    sources = {"swissknifeman": {"ref": "registry"}}
    if boost is not None:
        sources["laravel-boost"] = {"via": "boost.json"}
    return {"version": LOCK_VERSION, "skills": skills, "sources": sources}


def cmd_lock(env, argv):
    opts = parse_flags(argv, {"--target": "str", "--dry-run": "bool"})
    if opts["help"]:
        print("skiller lock [--target DIR] [--dry-run]\n"
              "  Пишет <target>/skills-lock.json — карту внешних скиллов проекта "
              "(swissknifeman wins, Laravel Boost дополняет).")
        return
    target, via = resolve_target(env, opts)
    lock = compose_lock(env, target)
    skills = lock["skills"]
    n_skm = sum(1 for e in skills.values() if e["source"] == "swissknifeman")
    n_boost = sum(1 for e in skills.values() if e["source"] == "laravel-boost")
    overlap = sum(1 for e in skills.values() if e.get("also_in"))
    lock_file = target / "skills-lock.json"

    if opts["dry_run"]:
        print(json.dumps(lock, ensure_ascii=False, indent=2))
        print(f"\n[dry-run] {lock_file}: {len(skills)} скиллов "
              f"(swissknifeman {n_skm}, laravel-boost {n_boost}, конфликтов {overlap})")
        return

    tmp = lock_file.with_name("skills-lock.json.tmp")
    tmp.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, lock_file)
    print(f"skills-lock.json ({via}): {len(skills)} скиллов — "
          f"swissknifeman {n_skm}, laravel-boost {n_boost}, конфликтов {overlap} "
          f"(swissknifeman wins, см. also_in)")
