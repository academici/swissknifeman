"""registry — регенерация skills.json + плагин-манифестов + графа (мейнтейнер)."""
import hashlib
import json
import subprocess

from .common import MARKETPLACE, die, parse_flags, parse_frontmatter, parse_inline_list

OWNER = {"name": "Dmitry Vostrikov", "email": "dv.vostrikov@gmail.com"}


def build_registry(env):
    """Собрать структуру skills.json из skills/**/SKILL.md и references.
    Возвращает (registry_dict, bucket_meta, bucket_dirs)."""
    root = env.root
    skills = []
    references = []

    for skill_md in sorted(root.glob("skills/**/SKILL.md")):
        rel = skill_md.relative_to(root)
        parts = rel.parts
        if len(parts) < 3:
            continue
        bucket = parts[1]
        # Nested paths: devops/docker/php -> docker-php
        if len(parts) > 4:
            name = f"{parts[-2]}-{parts[-3]}" if parts[-3] != bucket else parts[-2]
        else:
            name = parts[2]
        fm = parse_frontmatter(skill_md)
        name = fm.get("name") or name
        sha = hashlib.sha256(skill_md.read_bytes()).hexdigest()
        entry = {
            "name": name,
            "bucket": bucket,
            "path": str(rel),
            "version": fm.get("version") or "0.1.0",
            "description": fm.get("description", ""),
            "sha256": sha,
        }
        # Graph/meta fields: optional, omitted when empty (same as upstream fields)
        for list_key in ("tags", "requires", "produces_for"):
            vals = parse_inline_list(fm.get(list_key, ""))
            if vals:
                entry[list_key] = vals
        # Provenance: upstream.json next to SKILL.md marks an external skill
        upstream_file = skill_md.parent / "upstream.json"
        if upstream_file.exists():
            up = json.loads(upstream_file.read_text(encoding="utf-8"))
            files = up.get("files", [])
            main = next((f for f in files if f.get("path") == "SKILL.md"),
                        files[0] if files else {})
            entry["source"] = up.get("source", "http")
            entry["upstream"] = main.get("url", "")
            if main.get("fetched_at"):
                entry["fetched_at"] = main["fetched_at"]
        else:
            entry["source"] = "local"
        skills.append(entry)

    for ref in sorted((root / "skills/oss-dev/references").glob("*.md")):
        references.append({
            "name": ref.stem,
            "path": str(ref.relative_to(root)),
            "parent": "oss-development",
            "sha256": hashlib.sha256(ref.read_bytes()).hexdigest(),
        })

    buckets = {}
    for s in skills:
        buckets.setdefault(s["bucket"], 0)
        buckets[s["bucket"]] += 1

    # --- bucket metadata (buckets.json) --------------------------------------
    meta_file = root / "buckets.json"
    if not meta_file.exists():
        die("buckets.json not found — every bucket needs description/category/tags")
    bucket_meta = json.loads(meta_file.read_text(encoding="utf-8"))
    bucket_dirs = sorted(d.name for d in (root / "skills").iterdir() if d.is_dir())
    missing = [b for b in bucket_dirs if b not in bucket_meta]
    orphans = [b for b in bucket_meta if b not in bucket_dirs]
    if missing:
        die(f"buckets.json: missing entries for: {', '.join(missing)}")
    if orphans:
        die(f"buckets.json: entries without skills/ dir: {', '.join(orphans)}")

    registry = {
        "version": 5,
        "name": "swissknifeman",
        "repository": "https://github.com/academici/swissknifeman",
        "schema": "https://github.com/academici/swissknifeman/blob/main/SKILL_TEMPLATE.md",
        "buckets": {b: {"description": bucket_meta[b]["description"],
                        "count": c, "status": "active"}
                    for b, c in sorted(buckets.items())},
        "skills": skills,
        "references": references,
    }
    return registry, bucket_meta, bucket_dirs


def write_plugin_manifests(env, bucket_meta, bucket_dirs):
    """Записать skills/*/.claude-plugin/plugin.json + marketplace.json.
    Возвращает число плагинов."""
    root = env.root

    def write_json(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")

    def skills_dirs(plugin_root):
        """Dirs (relative, ./-prefixed) whose subdirs contain SKILL.md files."""
        dirs = set()
        for skill_md in plugin_root.rglob("SKILL.md"):
            rel = skill_md.parent.parent.relative_to(plugin_root)
            dirs.add("./" if str(rel) == "." else f"./{rel.as_posix()}")
        return sorted(dirs)

    marketplace_plugins = []
    for bucket in bucket_dirs:
        bucket_dir = root / "skills" / bucket
        dirs = skills_dirs(bucket_dir)
        if not dirs:
            continue
        meta = bucket_meta[bucket]
        write_json(bucket_dir / ".claude-plugin" / "plugin.json", {
            "name": bucket,
            "description": meta["description"],
            "skills": dirs[0] if len(dirs) == 1 else dirs,
        })
        marketplace_plugins.append({
            "name": bucket,
            "source": f"./skills/{bucket}",
            "description": meta["description"],
            "category": meta.get("category", ""),
            "tags": meta.get("tags", []),
        })

    meta_skill_dir = root / "generate-skill"
    meta_fm = parse_frontmatter(meta_skill_dir / "generate-skill" / "SKILL.md")
    write_json(meta_skill_dir / ".claude-plugin" / "plugin.json", {
        "name": "generate-skill",
        "description": meta_fm.get("description", "Meta-skill for creating new skills"),
        "skills": "./",
    })
    marketplace_plugins.append({
        "name": "generate-skill",
        "source": "./generate-skill",
        "description": meta_fm.get("description", "Meta-skill for creating new skills"),
        "category": "meta",
        "tags": ["meta", "authoring"],
    })

    write_json(root / ".claude-plugin" / "marketplace.json", {
        "name": MARKETPLACE,
        "owner": OWNER,
        "plugins": sorted(marketplace_plugins, key=lambda p: p["name"]),
    })
    return len(marketplace_plugins)


def cmd_registry(env, argv):
    # registry не принимает флагов, но help/неизвестные обрабатываем единообразно
    opts = parse_flags(argv, {})
    if opts["help"]:
        print("swissknifeman registry")
        return
    root = env.root
    registry, bucket_meta, bucket_dirs = build_registry(env)

    (root / "skills.json").write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n")
    print(f"Updated skills.json: {len(registry['skills'])} skills, "
          f"{len(registry['references'])} references")

    n_plugins = write_plugin_manifests(env, bucket_meta, bucket_dirs)
    print(f"Updated plugin manifests: {n_plugins} plugins "
          f"(.claude-plugin/marketplace.json)")

    subprocess.run([str(root / "scripts" / "generate-graph.sh")], check=True)
