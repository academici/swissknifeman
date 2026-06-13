"""vendor — канал вендоринга (Cursor и другие агенты)."""
import json
import os
import shutil
import sys
from datetime import date

from .boost import sync_boost_json
from .common import (AGENT_DEFAULTS, MANIFEST, die, parse_flags,
                     parse_frontmatter_fields, sanitize, warn)
from .config import all_buckets, load_config, resolve_selection, resolve_target
from .hub import generate_hub, hub_artifacts_exist
from .state import upsert_project


def collect_skills(env, buckets, exclude):
    """Список (bucket, rel, dir, fm_name) скиллов выбранных бакетов минус
    exclude, плюс карта all_skill_rels (bucket -> [rel-пути всех скиллов]).
    Скилл — каталог, прямо содержащий SKILL.md."""
    root = env.root
    skills = []
    all_skill_rels = {}
    for bucket in buckets:
        bucket_dir = root / "skills" / bucket
        for skill_md in sorted(bucket_dir.rglob("SKILL.md")):
            d = skill_md.parent
            rel = d.relative_to(bucket_dir)
            all_skill_rels.setdefault(bucket, []).append(str(rel))
            fm_name = parse_frontmatter_fields(skill_md)["name"]
            ids = {fm_name, d.name, f"{bucket}/{rel}".replace("\\", "/")}
            if ids & exclude:
                continue
            skills.append((bucket, str(rel), d, fm_name))
    return skills, all_skill_rels


def build_requires_index(env):
    """fm_name (или имя каталога) -> (bucket, rel, dir, requires) по всем бакетам."""
    root = env.root
    index = {}
    for bucket in all_buckets(env):
        bucket_dir = root / "skills" / bucket
        for skill_md in sorted(bucket_dir.rglob("SKILL.md")):
            d = skill_md.parent
            fields = parse_frontmatter_fields(skill_md)
            index.setdefault(fields["name"] or d.name,
                             (bucket, str(d.relative_to(bucket_dir)), d,
                              fields["requires"]))
    return index


def resolve_requires(skills, index, exclude):
    """Транзитивно дотянуть `requires`. Мутирует skills, возвращает pulled
    (dep -> requester). --exclude побеждает зависимость (с warning)."""
    selected = {fm_name or d.name for _, _, d, fm_name in skills}
    pulled = {}
    queue = []
    for bucket, rel, d, fm_name in skills:
        key = fm_name or d.name
        queue.extend((dep, key) for dep in index.get(key, ("", "", None, []))[3])

    while queue:
        dep, requester = queue.pop(0)
        if dep in selected:
            continue
        if dep not in index:
            warn(f"'{requester}' requires unknown skill '{dep}' — skipping")
            continue
        bucket, rel, d, dep_requires = index[dep]
        if {dep, d.name, f"{bucket}/{rel}".replace("\\", "/")} & exclude:
            warn(f"'{requester}' requires '{dep}' — excluded by --exclude, skipping")
            continue
        skills.append((bucket, rel, d, dep))
        selected.add(dep)
        pulled[dep] = requester
        queue.extend((dd, dep) for dd in dep_requires)
    return pulled


def flat_names(skills):
    """flat-имена для claude/Boost-раскладки: sanitize + два прохода
    разрешения коллизий (префикс бакета, затем полный путь-слаг)."""
    names = {}
    for i, (bucket, rel, d, fm_name) in enumerate(skills):
        names[i] = sanitize(fm_name) or sanitize(rel.replace("/", "-")) \
            or sanitize(d.name)
    # collision pass 1: prefix bucket
    seen = {}
    for i, n in names.items():
        seen.setdefault(n, []).append(i)
    for n, idxs in list(seen.items()):
        if len(idxs) > 1:
            for i in idxs:
                bucket = skills[i][0]
                if not names[i].startswith(bucket + "-"):
                    warn(f"collision: '{n}' -> '{bucket}-{n}'")
                    names[i] = f"{bucket}-{n}"
    # collision pass 2: full path slug
    seen = {}
    for i, n in names.items():
        seen.setdefault(n, []).append(i)
    for n, idxs in seen.items():
        if len(idxs) > 1:
            for i in idxs:
                bucket, rel = skills[i][0], skills[i][1]
                slug = sanitize(f"{bucket}-{rel.replace('/', '-')}")
                warn(f"collision: '{n}' -> '{slug}'")
                names[i] = slug
    return names


def do_vendor(env, target, opts, register=True):
    root = env.root
    config = load_config(env, target)
    flag_buckets = [b for b in opts.get("buckets", "").split(",") if b]
    flag_exclude = [e for e in opts.get("exclude", "").split(",") if e]
    list_only = opts.get("list", False)
    dry_run = opts.get("dry_run", False)
    force = opts.get("force", False)

    buckets, profile_name, profile_source, source, include_meta = \
        resolve_selection(env, target, config, opts.get("profile", ""), flag_buckets)
    if profile_source == "items":
        profile_source = "buckets"

    known = all_buckets(env)
    for b in buckets:
        if b not in known:
            die(f"unknown bucket: {b}")

    # exclude = union of flag and config (safety-oriented, not precedence-based)
    exclude = set(flag_exclude) | set(config.get("exclude", []))

    agent = opts.get("agent", "") or config.get("agent", "") or "generic"
    if agent not in AGENT_DEFAULTS:
        die(f"unknown agent '{agent}' (available: {', '.join(AGENT_DEFAULTS)})")

    skills_path = opts.get("skills_path", "") or config.get("skills_path", "") \
        or AGENT_DEFAULTS[agent]
    dest_root = target / skills_path

    # Layout: flat (.ai/skills/<name>/SKILL.md) vs bucket
    # (.ai/skills/<bucket>/<name>/SKILL.md). Laravel Boost обнаруживает
    # user-скиллы через glob('.ai/skills/*') на ОДИН уровень (SkillComposer),
    # поэтому в Boost-проектах нужен flat, иначе boost:update их не увидит.
    flat_layout = (agent == "claude") or (target / "boost.json").is_file()

    # --- collect skills (dir directly containing SKILL.md) ---------------------
    skills, all_skill_rels = collect_skills(env, buckets, exclude)

    if include_meta and (root / "generate-skill/generate-skill/SKILL.md").exists():
        d = root / "generate-skill/generate-skill"
        fm_name = parse_frontmatter_fields(d / "SKILL.md")["name"]
        if not ({fm_name, "generate-skill"} & exclude):
            skills.append(("generate-skill", ".", d, fm_name))

    # --- dependency resolution (frontmatter `requires`) -------------------------
    # Selected skills pull their `requires` transitively, across buckets; a pulled
    # skill keeps its own bucket path in bucket layout. --exclude wins over a
    # dependency (exclude is safety-oriented) — skipped with a warning.
    index = build_requires_index(env)
    pulled = resolve_requires(skills, index, exclude)

    # --- report / list -------------------------------------------------------------
    print(f"Target:      {target}")
    print(f"Profile:     {profile_name or '-'} (via {source})")
    print(f"Agent:       {agent}")
    print(f"Skills path: {skills_path}")
    print(f"Buckets:     {' '.join(buckets)}")
    if exclude:
        print(f"Exclude:     {' '.join(sorted(exclude))}")
    print(f"Skills:      {len(skills)}")
    if pulled:
        print(f"Dependencies: {len(pulled)} pulled via requires")

    flats = flat_names(skills) if flat_layout else {}
    if list_only:
        for i, (bucket, rel, d, fm_name) in enumerate(skills):
            suffix = f" -> {flats[i]}/" if flat_layout else ""
            key = fm_name or d.name
            dep_note = f"  (dependency of {pulled[key]})" if key in pulled else ""
            print(f"  {bucket}/{rel}{suffix}{dep_note}")
        return None

    # --- install ---------------------------------------------------------------------
    def copy_skill(src, dst):
        if dry_run:
            print(f"[dry-run] {src.relative_to(root)} -> {dst}")
            return
        shutil.copytree(src, dst, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("upstream.json",
                                                      ".claude-plugin"))

    def load_manifest(manifest_file):
        if manifest_file.exists():
            return json.loads(manifest_file.read_text(encoding="utf-8"))
        return {}

    def contained(path):
        return str(path.resolve()).startswith(str(dest_root.resolve()) + os.sep)

    def write_manifest(manifest_file, layout, installed, support_files=None):
        data = {
            "installed_at": date.today().isoformat(),
            "profile": profile_name,
            "agent": agent,
            "layout": layout,
            "skills": installed,
        }
        if support_files is not None:
            data["support_files"] = support_files
        manifest_file.write_text(json.dumps(data, indent=2, ensure_ascii=False)
                                 + "\n", encoding="utf-8")

    if flat_layout:
        if agent == "claude":
            print("NOTE: --agent claude vendoring is deprecated for Claude Code "
                  "projects — prefer the plugin marketplace: swissknifeman connect",
                  file=sys.stderr)
        elif (target / "boost.json").is_file():
            print("NOTE: обнаружен Laravel Boost — использую flat-раскладку "
                  "(.ai/skills/<name>/SKILL.md), чтобы boost:update нашёл скиллы",
                  file=sys.stderr)
        manifest_file = dest_root / MANIFEST
        if not dry_run:
            for entry in load_manifest(manifest_file).get("skills", []):
                stale = dest_root / entry["flat_name"]
                if stale.is_dir() and contained(stale):
                    shutil.rmtree(stale)
            dest_root.mkdir(parents=True, exist_ok=True)
        installed = []
        for i, (bucket, rel, d, fm_name) in enumerate(skills):
            copy_skill(d, dest_root / flats[i])
            installed.append({"flat_name": flats[i],
                              "source_path": str(d.relative_to(root))})
        if not dry_run:
            write_manifest(manifest_file, "flat", installed)
    else:
        # bucket layout: manifest-driven clean reinstall, no silent overwrites
        manifest_file = dest_root / MANIFEST
        old = load_manifest(manifest_file)
        old_paths = {e["path"] for e in old.get("skills", [])}

        # support files (e.g. skills/oss-dev/references/) for selected buckets
        support = []  # (src, rel "<bucket>/<rel_item>")
        for bucket in buckets:
            bucket_dir = root / "skills" / bucket
            for item in sorted(bucket_dir.rglob("*")):
                if item.is_dir() or item.name in ("SKILL.md", "upstream.json"):
                    continue
                rel_item = item.relative_to(bucket_dir)
                if ".claude-plugin" in rel_item.parts:
                    continue
                if any(str(rel_item).startswith(r + os.sep)
                       for r in all_skill_rels.get(bucket, []) if r != "."):
                    continue
                support.append((item, f"{bucket}/{rel_item}"))

        planned = [(bucket, rel, d, f"{bucket}/{rel}" if rel != "." else bucket)
                   for bucket, rel, d, fm_name in skills]
        collisions = [p for _, _, _, p in planned
                      if (dest_root / p).exists() and p not in old_paths]
        if collisions and not force:
            for p in collisions:
                print(f"ERROR: exists and was not installed by swissknifeman: "
                      f"{dest_root / p}", file=sys.stderr)
            die(f"{len(collisions)} collision(s) — rerun with --force to overwrite")

        if not dry_run:
            for p in sorted(old_paths | set(old.get("support_files", [])),
                            reverse=True):
                stale = dest_root / p
                if not contained(stale):
                    continue
                if stale.is_dir():
                    shutil.rmtree(stale)
                elif stale.is_file():
                    stale.unlink()
                parent = stale.parent
                while parent != dest_root and parent.is_dir() and \
                        not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
            dest_root.mkdir(parents=True, exist_ok=True)

        installed = []
        for bucket, rel, d, path in planned:
            copy_skill(d, dest_root / path)
            installed.append({"path": path, "source_path": str(d.relative_to(root))})
        support_rels = []
        for item, rel_path in support:
            dst = dest_root / rel_path
            support_rels.append(rel_path)
            if dry_run:
                print(f"[dry-run] {item.relative_to(root)} -> {dst}")
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dst)
        if not dry_run:
            write_manifest(manifest_file, "bucket", installed, support_rels)

    print(("[dry-run] " if dry_run else "")
          + f"Installed {len(skills)} skills -> {dest_root}")

    # Laravel Boost: дозаписать вендоренные скиллы в boost.json::skills
    vendored_names = sorted({fm_name for _, _, _, fm_name in skills})
    sync_boost_json(target, vendored_names, dry_run=dry_run)

    hub = opts.get("hub", False)
    if hub and not dry_run:
        generate_hub(env, target)
    elif not dry_run:
        print(f"Hint: корневой хаб скиллов — swissknifeman update или "
              f"перезапуск с --hub")

    record = {
        "path": str(target),
        "channel": "vendor",
        "profile": profile_name,
        "profile_source": profile_source,
        "agent": agent,
        "buckets": list(buckets),
        "exclude": sorted(exclude),
        "skills_path": skills_path,
        "hub": hub or hub_artifacts_exist(target),
    }
    if register and not dry_run:
        upsert_project(env, record)
    return record


def cmd_vendor(env, argv):
    opts = parse_flags(argv, {
        "--target": "str", "--agent": "str", "--profile": "str",
        "--buckets": "str", "--exclude": "str", "--skills-path": "str",
        "--list": "bool", "--dry-run": "bool", "--force": "bool", "--hub": "bool",
    })
    if opts["help"]:
        print("swissknifeman vendor [--agent claude|cursor|generic] "
              "[--profile P|--buckets a,b] [--exclude x,y] [--skills-path P] "
              "[--list] [--dry-run] [--force] [--hub]")
        return
    target, _ = resolve_target(env, opts, allow_home_confirm=True)
    do_vendor(env, target, opts)
