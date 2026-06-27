"""registry — регенерация skills.json + плагин-манифестов + графа (мейнтейнер)."""
import hashlib
import json

from core import atomic_write_text, find_repo_root, run_cmd

from .common import (MARKETPLACE, die, parse_flags, parse_frontmatter,
                     parse_inline_list, skill_content_hash)
from .config import CORE_PLUGIN, CORE_SKILLS

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
            # Хеш ВСЕГО каталога скилла (sync ловит дрейф snippets/references, не
            # только SKILL.md). Дополняет sha256, см. common.skill_content_hash.
            "content_sha256": skill_content_hash(skill_md.parent),
        }
        # Graph/meta fields: optional, omitted when empty (same as upstream fields)
        for list_key in ("tags", "requires", "produces_for"):
            vals = parse_inline_list(fm.get(list_key, ""))
            if vals:
                entry[list_key] = vals
        # Уровень иерархии (опц.): core|foundation|extension — само-документирование
        # слоя скилла. Скаляр, omit-when-empty; дополняет requires/produces_for и
        # неявные CORE_BUCKETS, НЕ заменяет их. Значение валидируется в validate.sh.
        level = (fm.get("level") or "").strip()
        if level:
            entry["level"] = level
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


def _repo_root(pkg_root):
    """Корень монорепо (где .git и общий .claude-plugin/marketplace.json) — граница
    git вверх от корня пакета. Fallback: сам pkg_root (standalone-раскладка)."""
    return find_repo_root(pkg_root) or pkg_root


def write_plugin_manifests(env, bucket_meta, bucket_dirs):
    """Записать skills/*/.claude-plugin/plugin.json (в пакете) + marketplace.json
    (в корне монорепо). source-пути плагинов — относительно корня репо.
    Возвращает число плагинов."""
    root = env.root
    repo_root = _repo_root(root)
    # Префикс пакета относительно корня репо: "packages/skiller" или "" (standalone)
    rel_pkg = root.relative_to(repo_root).as_posix() if root != repo_root else ""
    prefix = f"./{rel_pkg}" if rel_pkg else "."

    def src(sub):
        """source-путь плагина от корня репо: ./packages/skiller/<sub> или ./<sub>."""
        return f"{prefix}/{sub}" if rel_pkg else f"./{sub}"

    def write_json(path, data):
        atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")

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
            "source": src(f"skills/{bucket}"),
            "description": meta["description"],
            "category": meta.get("category", ""),
            "tags": meta.get("tags", []),
            "package": "skiller",
        })

    # Курируемый лёгкий core-плагин: токен-экономное ALWAYS-ON ядро (== CORE_SKILLS),
    # которое connect раздаёт в каждый проект ВМЕСТО целых бакетов general+oss-dev.
    # marketplace-запись source:"./" (корень репо) + явный skills[] = ПОЛНЫЙ набор плагина:
    # грузятся РОВНО эти 7 скиллов (заменяет дефолтный скан — подтверждено докой Claude Code
    # v2.1.x). Скиллы физически живут в своих бакетах — здесь только ссылки по пути, без копий.
    core_skill_paths = [src(f"skills/{cs}") for cs in CORE_SKILLS
                        if (root / "skills" / cs / "SKILL.md").is_file()]
    if core_skill_paths:
        marketplace_plugins.append({
            "name": CORE_PLUGIN,
            "source": "./",   # корень репо = корень marketplace; skills[] — пути от него
            "skills": core_skill_paths,
            "description": "Curated always-on core: token-economy skills (context-economy, "
                           "anti-drift, verify-claims, …) — lean replacement for the "
                           "general+oss-dev buckets in every project",
            "category": "meta",
            "tags": ["core", "token-economy", "always-on"],
            "package": "skiller",
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
        "source": src("generate-skill"),
        "description": meta_fm.get("description", "Meta-skill for creating new skills"),
        "category": "meta",
        "tags": ["meta", "authoring"],
        "package": "skiller",
    })

    # Management plugin: командное лицо skiller CLI (каталог skm/ со статичным
    # plugin.json + commands/). Не бакет скиллов — добавляем запись в marketplace вручную,
    # чтобы install `skm@swissknifeman` давал slash-команды управления скиллами.
    if (root / "skm" / ".claude-plugin" / "plugin.json").exists():
        marketplace_plugins.append({
            "name": "skm",
            "source": src("skm"),
            "description": "skiller CLI — управление скиллами проекта: бакеты "
                           "(connect/vendor), integrate, статус",
            "category": "meta",
            "tags": ["cli", "skills", "management"],
            "package": "skiller",
        })

    # Соседние пакеты монорепо (packages/<name>/.claude-plugin/plugin.json), кроме самого
    # пакета skiller: maind, harness и др. Источник истины — их plugin.json
    # (name/description/keywords). source считается от корня репо: ./packages/<name>.
    # Поле `package` = имя каталога пакета (провенанс: какой пакет предоставил плагин).
    pkgs_dir = repo_root / "packages"
    if rel_pkg and pkgs_dir.is_dir():
        self_name = root.name  # каталог skiller — его плагины уже добавлены выше
        for pkg in sorted(pkgs_dir.iterdir()):
            if not pkg.is_dir() or pkg.name == self_name:
                continue
            pj = pkg / ".claude-plugin" / "plugin.json"
            if not pj.exists():
                continue
            data = json.loads(pj.read_text(encoding="utf-8"))
            marketplace_plugins.append({
                "name": data.get("name", pkg.name),
                "source": f"./packages/{pkg.name}",
                "description": data.get("description", ""),
                "category": data.get("category", "ecosystem"),
                "tags": data.get("keywords", []),
                "package": pkg.name,
            })

    # marketplace.json — в КОРНЕ монорепо (один манифест на все плагины репо), а не в пакете.
    write_json(repo_root / ".claude-plugin" / "marketplace.json", {
        "name": MARKETPLACE,
        "owner": OWNER,
        "plugins": sorted(marketplace_plugins, key=lambda p: p["name"]),
    })
    return len(marketplace_plugins)


def render_index(registry, bucket_meta):
    """Markdown-реестр для discovery (skills/_index.md): скиллы по бакетам + tag matrix.
    Полностью генерируется из skills.json — человекочитаемое лицо машинного реестра."""
    skills = registry["skills"]
    by_bucket = {}
    for s in skills:
        by_bucket.setdefault(s["bucket"], []).append(s)
    tag_map = {}
    for s in skills:
        for t in s.get("tags", []):
            tag_map.setdefault(t, []).append(s["name"])

    lines = [
        "# Реестр скиллов swissknifeman",
        "",
        "<!-- GENERATED `skiller registry` — не редактировать вручную -->",
        "",
        "Источник истины портируемых скиллов (машинный реестр — `skills.json`). "
        "Раздача в проекты: `skiller connect` (плагины-бакеты) / `vendor` "
        "(физ. перенос). CORE-набор токен-скиллов (`general`/`oss-dev`) раздаётся "
        "по умолчанию — см. `connect`/`vendor`.",
        "",
        f"Всего: {len(skills)} скиллов в {len(by_bucket)} бакетах.",
        "",
        "## Скиллы по бакетам",
    ]
    for bucket in sorted(by_bucket):
        desc = bucket_meta.get(bucket, {}).get("description", "")
        items = sorted(by_bucket[bucket], key=lambda s: s["name"])
        lines += ["", f"### {bucket} — {desc} ({len(items)})", "",
                  "| Скилл | Описание | Теги |", "|:--|:--|:--|"]
        for s in items:
            d = s.get("description", "").replace("|", "\\|")
            if len(d) > 90:
                d = d[:89] + "…"
            tags = ", ".join(f"`{t}`" for t in s.get("tags", []))
            lines.append(f"| `{s['name']}` | {d} | {tags} |")

    lines += ["", "## Tag matrix", "",
              "Поиск скиллов по тегу (грузи точечно, не весь бакет).", "",
              "| Тег | Скиллы |", "|:--|:--|"]
    for tag in sorted(tag_map):
        names = ", ".join(f"`{n}`" for n in sorted(set(tag_map[tag])))
        lines.append(f"| `{tag}` | {names} |")
    return "\n".join(lines) + "\n"


def cmd_registry(env, argv):
    # registry не принимает флагов, но help/неизвестные обрабатываем единообразно
    opts = parse_flags(argv, {})
    if opts["help"]:
        print("skiller registry")
        return
    root = env.root
    registry, bucket_meta, bucket_dirs = build_registry(env)

    atomic_write_text(root / "skills.json",
                      json.dumps(registry, indent=2, ensure_ascii=False) + "\n")
    print(f"Updated skills.json: {len(registry['skills'])} skills, "
          f"{len(registry['references'])} references")

    # Потребитель поля level: распределение по уровням иерархии. Молчит, пока ни
    # один скилл не помечен (level — opt-in), загорается по мере проставления.
    levels = {}
    for s in registry["skills"]:
        lv = s.get("level")
        if lv:
            levels[lv] = levels.get(lv, 0) + 1
    if levels:
        order = ["core", "foundation", "extension"]
        parts = [f"{lv} {levels[lv]}" for lv in order if lv in levels]
        parts += [f"{lv} {n}" for lv, n in sorted(levels.items())
                  if lv not in order]
        untagged = len(registry["skills"]) - sum(levels.values())
        print(f"  уровни (level): {', '.join(parts)}; без уровня: {untagged}")

    atomic_write_text(root / "skills" / "_index.md",
                      render_index(registry, bucket_meta))
    print("Updated skills/_index.md (tag matrix)")

    n_plugins = write_plugin_manifests(env, bucket_meta, bucket_dirs)
    print(f"Updated plugin manifests: {n_plugins} plugins "
          f"(.claude-plugin/marketplace.json)")

    run_cmd([str(root / "scripts" / "generate-graph.sh")])

    # Карта токенового бюджета (трёхъярусная) — in-process, чтобы токен-математика
    # жила в одном модуле budget.py (а не дублировалась в bash+heredoc, как graph).
    from .budget import write_budget_map
    write_budget_map(env)
