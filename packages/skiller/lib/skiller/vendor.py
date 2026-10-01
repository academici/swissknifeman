"""vendor — vendor channel (Cursor and other agents)."""
import json
import os
import shutil
import sys

from .boost import sync_boost_json
from .common import (AGENT_DEFAULTS, MANIFEST, apply_permissions, die,
                     is_within, is_within_lexical, parse_flags,
                     parse_frontmatter_fields, resolve_requires_bfs,
                     safe_copy_skill, sanitize, warn, write_skill_manifest)
from .config import (DEFAULT_EXCLUDE, all_buckets, core_skill_tuples,
                     load_config, resolve_selection, resolve_target)
from .hub import generate_hub, hub_artifacts_exist
from .state import upsert_project


def collect_skills(env, buckets, exclude):
    """List (bucket, rel, dir, fm_name) skills of the selected buckets minus
    exclude, plus map all_skill_rels (bucket -> [rel-paths of all skills]).
    Skill - a directory directly containing SKILL.md."""
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
    """fm_name (or directory name) -> (bucket, rel, dir, requires) for all buckets."""
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


def resolve_requires(skills, index, exclude, *, diagnostics=None):
    """Transitively hold out `requires`. Mutates skills, returns pulled
    (dep -> requester). --exclude beats addiction (with warning). BFS — shared with
    skillset._pull_requires via common.resolve_requires_bfs (V-1: before two
    independent, already separated bodies)."""
    selected = {fm_name or d.name for _, _, d, fm_name in skills}
    seed = [(dep, fm_name or d.name) for _bucket, _rel, d, fm_name in skills
            for dep in index.get(fm_name or d.name, ("", "", None, []))[3]]

    def lookup(dep):
        if dep not in index:
            return None
        bucket, rel, d, dep_requires = index[dep]
        tokens = {dep, d.name, f"{bucket}/{rel}".replace("\\", "/")}
        return {"key": dep, "requires": dep_requires, "exclude_tokens": tokens,
                "_payload": (bucket, rel, d, dep)}

    pulled = {}
    for node, requester in resolve_requires_bfs(
            seed, lookup, selected, exclude, diagnostics=diagnostics):
        skills.append(node["_payload"])
        pulled[node["key"]] = requester
    return pulled


def flat_names(skills):
    """flat-names for claude/Boost-layouts: sanitize + two passes
    collision resolution (bucket prefix, then full slug path)."""
    names = {}
    for i, (_bucket, rel, d, fm_name) in enumerate(skills):
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
        if b not in known and b not in {"core", "task"}:
            die(f"unknown bucket: {b}")
    buckets = [b for b in buckets if b in known]

    # exclude = union of flag and config (safety-oriented, not precedence-based)
    exclude = set(flag_exclude) | set(config.exclude)
    no_core = opts.get("no_core", False)
    if not no_core:
        # CORE-policy: we do not distribute double hubs/default hand tools
        exclude |= set(DEFAULT_EXCLUDE)

    agent = opts.get("agent", "") or config.agent or "generic"
    if agent not in AGENT_DEFAULTS:
        die(f"unknown agent '{agent}' (available: {', '.join(AGENT_DEFAULTS)})")

    skills_path = opts.get("skills_path", "") or config.skills_path \
        or AGENT_DEFAULTS[agent]
    dest_root = target / skills_path

    # Layout: flat (.ai/skills/<name>/SKILL.md) vs bucket
    # (.ai/skills/<bucket>/<name>/SKILL.md). Laravel Boost detects
    # user-skills through glob('.ai/skills/*') to ONE level (SkillComposer),
    # therefore in Boost-projects need flat, otherwise boost:update won't see them.
    flat_layout = (agent == "claude") or (target / "boost.json").is_file()

    # --- collect skills (dir directly containing SKILL.md) ---------------------
    skills, all_skill_rels = collect_skills(env, buckets, exclude)

    # CORE: token skills are always distributed (if not --no-core), even when their bucket
    # is not included in the project profile (general/oss-dev usually outside of code profiles).
    core_added = []
    if not no_core:
        have = {f"{b}/{r}" for b, r, _, _ in skills}
        for tup in core_skill_tuples(env, exclude):
            if f"{tup[0]}/{tup[1]}" not in have:
                skills.append(tup)
                core_added.append(f"{tup[0]}/{tup[1]}")

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
    if source == "autodetect-fallback":
        print("⚠ ATTENTION: project type not recognized - MINIMUM set transferred (core),\n"
              "  and not «everything». For optimal dialing, specify the profile explicitly:\n"
              "  skiller vendor --profile <node-frontend|laravel-project|php-package|…>\n"
              "  or exact buckets: skiller vendor --buckets a,b,c")
    print(f"Agent:       {agent}")
    print(f"Skills path: {skills_path}")
    print(f"Buckets:     {' '.join(buckets)}")
    if exclude:
        print(f"Exclude:     {' '.join(sorted(exclude))}")
    print(f"Skills:      {len(skills)}")
    if core_added:
        print(f"CORE:        {' '.join(core_added)} (are distributed by default; --no-core disables)")
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
        """True — copied (or dry-run: scheduled). False — missing
        (containment-stop/TOCTOU-race, already warn'is located inside safe_copy_skill) —
        the caller should NOT put it in installed/manifest (V-2)."""
        if dry_run:
            print(f"[dry-run] {src.relative_to(root)} -> {dst}")
            return True
        # Unified secure copy (containment + removal symlink/file/directory + TOCTOU-
        # recheck + SKILL_IGNORE) — shared with skillset.sync, so that security details are not
        # were leaving. Alien SKILL.*.md/evals/upstream.json/.claude-plugin does not go to the project.
        return safe_copy_skill(src, dst, dest_root)

    def copy_support_file(src, dst):
        """Safe to copy SINGLE support-file (e.g. skills/oss-dev/references/*.md)
        inside dest_root: containment-check + atomic record (tmp+os.replace) — parity
        with safe_copy_skill (it copies skill catalogs via copytree). Previously these files
        walked naked shutil.copy2 past and containment, and atomicity (V-7)."""
        if not is_within_lexical(dst, dest_root):
            warn(f"pass support-file: path outside the destination directory: {dst}")
            return False
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(f".{dst.name}.tmp-{os.getpid()}")
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
        return True

    def load_manifest(manifest_file):
        if not manifest_file.exists():
            return {}
        try:
            return json.loads(manifest_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            # A broken manifest should not be dropped do_vendor unhandled exception
            # (was found by regression on U-1: update --all → do_vendor reads the manifest
            # AGAIN for reinstall/prune-accounting) — degradation: interpreted as «manifest
            # no» (old entries not found → without collision-detection by old_paths,
            # clean reinstall).
            warn(f"{manifest_file}: broken JSON of the manifesto - I ignore it, interpret it as "
                 f"missing: {e}")
            return {}

    def contained(path):
        return is_within(path, dest_root)

    def write_manifest(manifest_file, layout, installed, support_files=None):
        write_skill_manifest(manifest_file, profile=profile_name, agent=agent,
                             layout=layout, installed=installed,
                             support_files=support_files)

    skip_copy, skip_support = [], []
    if flat_layout:
        if agent == "claude":
            print("NOTE: --agent claude vendoring is deprecated for Claude Code "
                  "projects — prefer the plugin marketplace: skiller connect",
                  file=sys.stderr)
        elif (target / "boost.json").is_file():
            print("NOTE: detected Laravel Boost — using flat-layout "
                  "(.ai/skills/<name>/SKILL.md), to boost:update found skills",
                  file=sys.stderr)
        manifest_file = dest_root / MANIFEST
        if not dry_run:
            for entry in load_manifest(manifest_file).get("skills", []):
                stale = dest_root / entry["flat_name"]
                if stale.is_dir() and contained(stale):
                    shutil.rmtree(stale)
            dest_root.mkdir(parents=True, exist_ok=True)
        installed = []
        for i, (_bucket, _rel, d, _fm_name) in enumerate(skills):
            if copy_skill(d, dest_root / flats[i]):
                installed.append({"flat_name": flats[i],
                                  "source_path": str(d.relative_to(root))})
            else:
                skip_copy.append(flats[i])
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
                # SKILL.*.md — non-canonical localized/reference alternates, not a vendor
                if item.name.startswith("SKILL.") and item.name.endswith(".md"):
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
        for _bucket, _rel, d, path in planned:
            if copy_skill(d, dest_root / path):
                installed.append({"path": path, "source_path": str(d.relative_to(root))})
            else:
                skip_copy.append(path)
        support_rels = []
        for item, rel_path in support:
            dst = dest_root / rel_path
            if dry_run:
                print(f"[dry-run] {item.relative_to(root)} -> {dst}")
                support_rels.append(rel_path)
            elif copy_support_file(item, dst):
                support_rels.append(rel_path)
            else:
                skip_support.append(rel_path)
        if not dry_run:
            write_manifest(manifest_file, "bucket", installed, support_rels)

    if skip_copy:
        warn(f"skipped when copying ({len(skip_copy)}): {', '.join(skip_copy)} "
             f"— NOT installed, see warnings above")
    if skip_support:
        warn(f"missing support-files ({len(skip_support)}): {', '.join(skip_support)}")
    print(("[dry-run] " if dry_run else "")
          + f"Installed {len(installed)} skills -> {dest_root}"
          + (f" ({len(skip_copy)} missing)" if skip_copy else ""))

    # Laravel Boost: add vendor skills to boost.json::skills
    vendored_names = sorted({fm_name for _, _, _, fm_name in skills})
    sync_boost_json(target, vendored_names, dry_run=dry_run)

    # permissions-presets (deny garbage + allow stack) in .claude/settings.local.json
    if not opts.get("no_permissions"):
        apply_permissions(env, target, dry_run=dry_run)

    hub = opts.get("hub", False)
    if hub and not dry_run:
        generate_hub(env, target)
    elif not dry_run:
        print("Hint: root hub of skills - skiller update or "
              "restart from --hub")

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
        "--no-core": "bool", "--no-permissions": "bool",
    })
    if opts["help"]:
        print("skiller vendor [--agent claude|cursor|generic] "
              "[--profile P|--buckets a,b] [--exclude x,y] [--skills-path P] "
              "[--list] [--dry-run] [--force] [--hub] [--no-core] [--no-permissions]")
        return
    target, _ = resolve_target(env, opts, allow_home_confirm=True)
    do_vendor(env, target, opts)
