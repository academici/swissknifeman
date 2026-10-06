"""lock — map of external skills of the project (skills-lock.json).

Composition of sources: **swissknifeman** (curated registry) + **Laravel Boost**
(`boost.json::skills[]`). Skill is considered swissknifeman'ovsky if his name is in
`skills.json` registry - then swissknifeman wins; skill from `boost.json::skills[]` —
`laravel-boost`; everything else installed - `local` (own skill of the project, for example.
rolled out from another hub). Conflicts (name in several) are not lost: the winner in
`source`, second in `also_in`. Sources work separately and together, forming a set.

Universe = actually installed skills (agent layouts) ∪ `boost.json::skills`.
The file is committed to the project - this is lock-external skill map (like composer.lock)."""
import json

from .common import atomic_write_json, die, parse_flags, warn
from .config import resolve_target

# Layouts where agents place skills (claude — flat, others - on their own paths).
AGENT_SKILL_DIRS = (".claude/skills", ".cursor/skills", ".ai/skills")
LOCK_VERSION = 1


def _registry_map(env):
    """skills.json registry → {skill_name: bucket}. Private/source-only records
    (`buckets.json` `private_source_only`)
    excluded: they are never legit swissknifeman-source installed
    copies in the consumer project (the only manufacturer - root-bootstrap
    renderer `publication.py`, not this composer)."""
    f = env.root / "skills.json"
    if not f.is_file():
        die("skills.json not found - first skiller registry")
    data = json.loads(f.read_text(encoding="utf-8"))
    skills = data["skills"] if isinstance(data, dict) else data
    from .skillset import private_source_buckets
    private_buckets = private_source_buckets(env)
    out = {}
    for s in skills:
        name = s.get("name") or s.get("id")
        bucket = s.get("bucket", "")
        if name and bucket not in private_buckets:
            out[name] = bucket
    return out


def _installed_skills(target):
    """Names of physically installed skills (by agent layouts)."""
    names = set()
    for rel in AGENT_SKILL_DIRS:
        d = target / rel
        if d.is_dir():
            names |= {p.name for p in d.iterdir() if p.is_dir()}
    return names


def _boost_skills(target):
    """boost.json::skills[] or None, if Laravel Boost is not connected."""
    f = target / "boost.json"
    if not f.is_file():
        return None
    try:
        return list(json.loads(f.read_text(encoding="utf-8")).get("skills", []))
    except json.JSONDecodeError as e:
        # Previously quiet []: conflicts also_in were lost without a signal (audit V-8) —
        # skiller-skills, also listed in the bit boost.json, would look like
        # «only swissknifeman», although real overlap not verified.
        warn(f"{f}: broken JSON — boost-skills are not included in lock (also_in may "
             f"missing): {e}")
        return []


def compose_lock(env, target):
    """Collect skills-lock: swissknifeman wins, boost complements, conflicts in also_in."""
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
            # The skill is explicitly declared in boost.json::skills — is a skill Laravel Boost.
            entry = {"source": "laravel-boost"}
        else:
            # Installed, but neither in the registry nor in boost.json — own skill
            # project (for example, rolled out from another hub). Not attributed Boost'y
            # just because it's connected.
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
              "  Writes <target>/skills-lock.json — map of external skills of the project "
              "(swissknifeman wins, Laravel Boost complements).")
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
        print(f"\n[dry-run] {lock_file}: {len(skills)} skills "
              f"(swissknifeman {n_skm}, laravel-boost {n_boost}, conflicts {overlap})")
        return

    atomic_write_json(lock_file, lock)
    print(f"skills-lock.json ({via}): {len(skills)} skills - "
          f"swissknifeman {n_skm}, laravel-boost {n_boost}, conflicts {overlap} "
          f"(swissknifeman wins, see also_in)")
