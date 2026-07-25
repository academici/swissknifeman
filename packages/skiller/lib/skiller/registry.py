"""registry — регенерация skills.json + плагин-манифестов + графа (мейнтейнер)."""
import hashlib
import json
import sys

from core import atomic_write_text, find_repo_root, safe_load_json

from .common import (MARKETPLACE, die, parse_flags, parse_frontmatter,
                     parse_inline_list, skill_content_hash)
from .config import CORE_PLUGIN, CORE_SKILLS
from .publication import (SiblingPlugin, assert_root_bootstrap_set_completeness,
                          build_publication_catalog, render_claude_publication,
                          render_codex_publication, render_repository_bootstrap_projections)

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
        # R-4 (аудит): fm-имя почти всегда перекрывает path-fallback выше — но
        # build_registry() не требует прогнанного validate.sh (гейт `name` во
        # frontmatter — отдельный шаг). Скилл без `name` посреди разработки всё ещё
        # получает разумное имя из пути, а не падает/остаётся безымянным. Оставлено
        # намеренно, не забытая сложность.
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
            # Битый upstream.json НЕ роняем голым traceback на полпути генерации и
            # НЕ проваливаем тихо в source="local" (это исказило бы провенанс
            # внешнего скилла в marketplace) — внятная ошибка с путём к файлу.
            up = safe_load_json(
                upstream_file,
                on_error=lambda e, f=upstream_file: die(f"битый upstream.json: {f}: {e}"),
            )
            files = up.get("files", [])
            # provenance-запись: body_path (P7.3 thin-navigator) явно называет, какая
            # files[]-запись — «тело» апстрима, когда SKILL.md — навигатор, а не
            # зеркало; иначе как раньше — запись SKILL.md, иначе первая (fork/merge:
            # files[].path указывает на pristine-зеркало в references/, напр. в
            # strategy=fork без выделенного body_path).
            body_path = up.get("body_path") or None
            main = (body_path and next(
                        (f for f in files if f.get("path") == body_path), None)) \
                or next((f for f in files if f.get("path") == "SKILL.md"), None) \
                or (files[0] if files else {})
            entry["source"] = up.get("source", "http")
            entry["upstream"] = main.get("url", "")
            if main.get("fetched_at"):
                entry["fetched_at"] = main["fetched_at"]
        else:
            entry["source"] = "local"
        skills.append(entry)

    # R-3 (аудит): единственный источник reference-материалов — oss-dev/references.
    # Осознанное ограничение, не забытый частный случай: `parent` ниже ("oss-development")
    # — конкретное имя владеющего скилла в ЭТОМ бакете, а не обобщаемое правило (для
    # другого бакета с references/ понадобился бы свой parent — сейчас такого нет,
    # см. `find skills -maxdepth 2 -type d -name references`). Если появится второй
    # бакет с references/, обобщать здесь ЭТУ функцию, а не гадать заранее.
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
    # Alias-бакеты (P7.5, будущие слияния бакетов — D14 запрещает исполнять их СЕЙЧАС):
    # метаданные-запись БЕЗ физического skills/<bucket> — старое имя бакета переживает
    # слияние как список ссылок на скиллы цели `alias_of` (см. build_plugin_manifests).
    # Не «orphan» (забытый каталог), а явная миграционная запись.
    alias_entries = {b: m for b, m in bucket_meta.items()
                     if isinstance(m, dict) and m.get("alias_of")}
    missing = [b for b in bucket_dirs if b not in bucket_meta]
    orphans = [b for b in bucket_meta
              if b not in bucket_dirs and b not in alias_entries]
    if missing:
        die(f"buckets.json: missing entries for: {', '.join(missing)}")
    if orphans:
        die(f"buckets.json: entries without skills/ dir: {', '.join(orphans)}")
    bad_targets = [b for b, m in alias_entries.items()
                  if m["alias_of"] not in bucket_dirs]
    if bad_targets:
        die("buckets.json: alias_of указывает на несуществующий бакет: " + ", ".join(
            f"{b}->{alias_entries[b]['alias_of']}" for b in bad_targets))

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


def load_bucket_aliases(env):
    """Alias-бакеты (P7.5) из buckets.json: {старое_имя: целевой_бакет}. Лёгкий читатель
    (без build_registry) для update.py/status.py — им не нужна вся структура реестра ради
    одной подсказки. Пусто, если файла нет (standalone/тест-фикстура без buckets.json) или
    алиасов не объявлено — сегодня в реальном реестре их нет (D14: P7 не сливает бакеты)."""
    meta_file = env.root / "buckets.json"
    if not meta_file.is_file():
        return {}
    try:
        bucket_meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {b: m["alias_of"] for b, m in bucket_meta.items()
            if isinstance(m, dict) and m.get("alias_of")}


def alias_migration_hints(aliases, enabled_names):
    """Одна строка на КАЖДЫЙ активный alias-бакет — «бакет X теперь Y», без нагнетания
    (P7.5 Code Guidance). `aliases` — {старое: целевое} из load_bucket_aliases,
    `enabled_names` — плагины, реально включённые (True) в settings проекта."""
    return [f"бакет '{name}' теперь '{aliases[name]}' — обновите enabledPlugins, "
            f"когда удобно."
            for name in sorted(enabled_names) if name in aliases]


def _repo_root(pkg_root):
    """Корень монорепо (где .git и общий .claude-plugin/marketplace.json) — граница
    git вверх от корня пакета. Fallback: сам pkg_root (standalone-раскладка)."""
    return find_repo_root(pkg_root) or pkg_root


def _legacy_build_plugin_manifests(env, bucket_meta, bucket_dirs):
    """Вычислить ВСЕ plugin-манифесты БЕЗ записи: [(path, data_dict)] в порядке записи;
    последний элемент — marketplace.json (корень репо). Чистая (source of truth для
    write_plugin_manifests и registry --check drift-гейта). source-пути от корня репо."""
    root = env.root
    repo_root = _repo_root(root)
    # Префикс пакета относительно корня репо: "packages/skiller" или "" (standalone)
    rel_pkg = root.relative_to(repo_root).as_posix() if root != repo_root else ""
    prefix = f"./{rel_pkg}" if rel_pkg else "."

    def src(sub):
        """source-путь плагина от корня репо: ./packages/skiller/<sub> или ./<sub>."""
        return f"{prefix}/{sub}" if rel_pkg else f"./{sub}"

    manifests = []

    def write_json(path, data):
        manifests.append((path, data))

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

    # Alias-бакеты (P7.5, слияния бакетов — механизм СЕЙЧАС без применения, D14): старое имя
    # бакета остаётся marketplace-плагином (13 проектов на enabledPlugins — back-compat), но
    # без своего skills/<bucket>. Та же техника, что у курируемого `core` ниже: marketplace-
    # запись source:"./" + явный skills[]-список ссылок на скиллы, физически живущие теперь в
    # целевом бакете (`alias_of` в buckets.json). Поле `alias_of` в самой записи — пометка в
    # метаданных, которую читают update.py/status.py для подсказки «бакет X теперь Y».
    # bucket_dirs не содержит alias-имена (нет физического каталога) — отдельный проход по
    # bucket_meta. Пусто, пока ни одно слияние не объявлено → живой registry-дифф не меняется.
    for name in sorted(bucket_meta):
        meta = bucket_meta[name]
        if not isinstance(meta, dict) or not meta.get("alias_of"):
            continue
        alias_paths = [src(f"skills/{s}") for s in meta.get("skills", [])
                       if (root / "skills" / s / "SKILL.md").is_file()]
        if not alias_paths:
            continue
        marketplace_plugins.append({
            "name": name,
            "source": "./",
            "skills": alias_paths,
            "description": meta.get("description")
                or f"Alias: бакет перенесён в '{meta['alias_of']}'",
            "category": meta.get("category", ""),
            "tags": meta.get("tags", []),
            "package": "skiller",
            "alias_of": meta["alias_of"],
        })

    # Курируемый лёгкий core-плагин: токен-экономное ALWAYS-ON ядро (== CORE_SKILLS),
    # которое connect раздаёт в каждый проект ВМЕСТО целых бакетов general+oss-dev.
    # marketplace-запись source:"./" (корень репо = корень marketplace) + явный skills[] =
    # ПОЛНЫЙ набор плагина: грузятся РОВНО перечисленные скиллы, дефолтный скан <source>/skills/
    # не подмешивается. Подтверждено официальной докой (verified 2026-07-02, RAG):
    # https://code.claude.com/docs/en/plugin-marketplaces#advanced-plugin-entries —
    # «With a marketplace-root source, the listed paths are the complete set for that entry,
    # and other directories in the shared skills/ folder don't load.» Фолбэк на дефолтный
    # скан («If none of the listed paths exist, the default scan runs instead») тоже безопасен:
    # дефолтный скан — это <repo>/skills/ (которого в этом репо нет), а не рекурсия по всему
    # дереву. Скиллы физически живут в своих бакетах — здесь только ссылки по пути, без копий.
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
    return manifests


def _package_version(root):
    """Read the frozen P3 publication-version source explicitly."""
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    version = package.get("version")
    if not isinstance(version, str):
        die("package.json: version must be a string")
    return version


def _publication_versions(root):
    """D27 per-unit version map (`configs/publication-versions.json`): separates the skiller
    package API SemVer from finite per-unit manifest versions, so an unaffected bucket manifest
    stays byte-identical across an unrelated owner's package-API bump. Absent (standalone/fixture
    root predating the map) → `(None, None)`: `build_publication_catalog` then falls back to
    stamping every unit with `package_version` uniformly — the pre-D27 behavior, unchanged."""
    path = root / "configs" / "publication-versions.json"
    if not path.is_file():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{path}: невалидный JSON: {e}")
    if not isinstance(data, dict):
        die(f"{path}: корень должен быть объектом")
    units = data.get("units")
    if not isinstance(units, dict) or not all(isinstance(v, str) for v in units.values()):
        die(f"{path}: 'units' должен быть объектом {{unit: version}}")
    default = data.get("default_unit_version")
    if not isinstance(default, str) or not default:
        die(f"{path}: 'default_unit_version' обязателен и должен быть строкой")
    return units, default


def _sibling_plugins(repo_root, package_root):
    """Scan the bounded sibling-package manifest input before catalog construction."""
    if package_root == repo_root or not (repo_root / "packages").is_dir():
        return ()
    siblings = []
    for package in sorted((repo_root / "packages").iterdir()):
        if not package.is_dir() or package == package_root:
            continue
        manifest = package / ".claude-plugin" / "plugin.json"
        if not manifest.is_file():
            continue
        codex_manifest = package / ".codex-plugin" / "plugin.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        siblings.append(SiblingPlugin(
            name=data.get("name", package.name), package=package.name,
            description=data.get("description", ""),
            category=data.get("category", "ecosystem"),
            tags=tuple(data.get("keywords", [])),
            source_path=f"packages/{package.name}",
            content_hash=hashlib.sha256(manifest.read_bytes()).hexdigest(),
            codex_supported=codex_manifest.is_file(),
        ))
    return tuple(siblings)


def build_catalog(env, bucket_meta, bucket_dirs, registry=None):
    """Shared semantic-catalog construction — the immutable P1 input every provider renderer
    consumes AND the read-only D42 core/donor-bucket diagnostic (doctor.py), so the
    identity→carrier mapping is read from exactly one seam, never re-derived (P1.5)."""
    root = env.root
    repo_root = _repo_root(root)
    if registry is None:
        registry, _meta, _dirs = build_registry(env)
    meta_skill = parse_frontmatter(root / "generate-skill" / "generate-skill" / "SKILL.md")
    unit_versions, default_unit_version = _publication_versions(root)
    return build_publication_catalog(
        registry=registry, bucket_meta=bucket_meta, bucket_dirs=bucket_dirs,
        core_skills=CORE_SKILLS, core_plugin=CORE_PLUGIN,
        package_version=_package_version(root), siblings=_sibling_plugins(repo_root, root),
        generate_skill_description=meta_skill.get("description", "Meta-skill for creating new skills"),
        skm_present=(root / "skm" / ".claude-plugin" / "plugin.json").is_file(),
        unit_versions=unit_versions, default_unit_version=default_unit_version,
    )


def build_claude_publication(env, bucket_meta, bucket_dirs, registry=None):
    """Render legacy Claude artifacts through the immutable P3 semantic catalog."""
    root = env.root
    repo_root = _repo_root(root)
    catalog = build_catalog(env, bucket_meta, bucket_dirs, registry)
    return render_claude_publication(catalog, repo_root=repo_root, package_root=root)


def build_codex_publication(env, bucket_meta, bucket_dirs, registry=None):
    """Render native Codex outputs from the same immutable semantic catalog."""
    root = env.root
    repo_root = _repo_root(root)
    catalog = build_catalog(env, bucket_meta, bucket_dirs, registry)
    return render_codex_publication(catalog, repo_root=repo_root, package_root=root)


def build_repository_bootstrap_publication(env):
    """Render the 26 thin root-bootstrap projections + combined lock (P1.2, D31)."""
    root = env.root
    repo_root = _repo_root(root)
    return render_repository_bootstrap_projections(repo_root=repo_root, package_root=root)


def build_plugin_manifests(env, bucket_meta, bucket_dirs, registry=None):
    """Compatibility view of Claude artifacts for the legacy registry writer/checker."""
    return [(artifact.target, json.loads(artifact.managed_bytes.decode("utf-8")))
            for artifact in build_claude_publication(env, bucket_meta, bucket_dirs, registry)]


def _manifest_text(data):
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _has_repository_bootstrap_config(root):
    """Standalone/fixture roots predating P1.2 carry no root-bootstrap config — skip the
    renderer entirely rather than fail closed on a file that was never meant to exist there."""
    return (root / "configs" / "repository-bootstrap-skills.json").is_file()


def write_plugin_manifests(env, bucket_meta, bucket_dirs):
    """Записать все plugin-манифесты + marketplace.json (атомарно). Возвращает число плагинов."""
    manifests = build_plugin_manifests(env, bucket_meta, bucket_dirs)
    for path, data in manifests:
        atomic_write_text(path, _manifest_text(data))
    for artifact in build_codex_publication(env, bucket_meta, bucket_dirs):
        atomic_write_text(artifact.target, artifact.managed_bytes.decode("utf-8"))
    if _has_repository_bootstrap_config(env.root):
        bootstrap_artifacts = build_repository_bootstrap_publication(env)
        for artifact in bootstrap_artifacts:
            atomic_write_text(artifact.target, artifact.managed_bytes.decode("utf-8"))
        # P1.5 (D40 invariant i): fail closed on write too — an undeclared root directory
        # (e.g. a stray hand-written adapter reappearing) is never a silent "unique carrier".
        completeness_failures = assert_root_bootstrap_set_completeness(
            _repo_root(env.root), bootstrap_artifacts)
        if completeness_failures:
            die("root-bootstrap root-set completeness:\n" +
                "\n".join(f"  - {item}" for item in completeness_failures))
    # число плагинов = размер marketplace.plugins (последний манифест — marketplace.json)
    return len(manifests[-1][1]["plugins"])


def check_drift(env):
    """[relpath] сгенерированных артефактов, отставших от источников ([] если чисто).
    Пересобирает реестр+манифесты+_index.md+graph.md+budget.md в памяти и сверяет с
    диском — гейт против тихого дрейфа (validate.sh лишь проверял валидность JSON).
    graph.md/budget.md добавлены в аудите R-2: `cmd_registry` их генерит, но раньше
    drift-гейт про них не знал — CLAUDE.md обещает «генерёжка — не править руками»
    для обоих, а гейт этого не проверял."""
    root = env.root
    repo_root = _repo_root(root)
    registry, bucket_meta, bucket_dirs = build_registry(env)
    drift = []

    def _cmp(path, expected):
        try:
            actual = path.read_text(encoding="utf-8")
        except OSError:
            actual = None
        if actual != expected:
            try:
                rel = path.relative_to(repo_root).as_posix()
            except ValueError:
                rel = str(path)
            drift.append(rel)

    _cmp(root / "skills.json", json.dumps(registry, indent=2, ensure_ascii=False) + "\n")
    _cmp(root / "skills" / "_index.md", render_index(registry, bucket_meta))
    for path, data in build_plugin_manifests(env, bucket_meta, bucket_dirs, registry):
        _cmp(path, _manifest_text(data))
    for artifact in build_codex_publication(env, bucket_meta, bucket_dirs, registry):
        _cmp(artifact.target, artifact.managed_bytes.decode("utf-8"))
    if _has_repository_bootstrap_config(root):
        bootstrap_artifacts = build_repository_bootstrap_publication(env)
        for artifact in bootstrap_artifacts:
            _cmp(artifact.target, artifact.managed_bytes.decode("utf-8"))
        # P1.5 (D40 invariant i): registry --check must catch an undeclared root directory,
        # not only stale bytes of a declared one — ownership, never suppression.
        drift.extend(assert_root_bootstrap_set_completeness(repo_root, bootstrap_artifacts))

    graph_text, _n_nodes, _n_edges = render_graph(registry)
    _cmp(_docs_root(root) / "docs" / "guide" / "graph.md", graph_text)

    # budget.md — только если skills.json уже есть на диске (write_budget_map die'ит
    # без него); при первом `registry` (файла ещё нет) сравнивать не с чем — не гейт.
    from .budget import render_budget_map
    if (root / "skills.json").is_file():
        budget_text, *_rest = render_budget_map(root, registry)
        _cmp(_docs_root(root) / "docs" / "guide" / "budget.md", budget_text)
    return drift


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


def _docs_root(p):
    """Ближайший вверх каталог с docs/guide (сам пакет; fallback — p). Паритет с
    budget._docs_root (обе доки живут в packages/skiller/docs)."""
    for cand in (p, *p.parents):
        if (cand / "docs" / "guide").is_dir():
            return cand
    return p


def render_graph(registry):
    """Mermaid-граф зависимостей скиллов (requires/produces_for) из registry-dict.
    Портировано из scripts/generate-graph.sh (был bash+heredoc — единственный
    генерируемый артефакт БЕЗ python-функции, отсюда drift-гейт его не видел,
    аудит R-2). Раньше отдельный процесс; теперь тот же источник математики, что
    у skills.json/_index.md — check_drift сравнивает С ЭТОЙ функцией, не гадает."""
    skills = registry["skills"]
    by_name = {s["name"]: s for s in skills}

    requires_edges = set()
    produces_edges = set()
    for s in skills:
        for dep in s.get("requires", []):
            if dep in by_name:
                requires_edges.add((s["name"], dep))
    for s in skills:
        for dst in s.get("produces_for", []):
            if dst in by_name and (dst, s["name"]) not in requires_edges:
                produces_edges.add((s["name"], dst))

    connected = {n for e in requires_edges | produces_edges for n in e}

    buckets = {}
    for name in sorted(connected):
        buckets.setdefault(by_name[name]["bucket"], []).append(name)

    isolated = {}
    for s in skills:
        if s["name"] not in connected:
            isolated.setdefault(s["bucket"], []).append(s["name"])

    def node_id(name):
        return name.replace("-", "_")

    lines = [
        "# Граф зависимостей скиллов",
        "",
        "> Сгенерировано `skiller registry` (registry.render_graph) из `skills.json` — "
        "не редактировать вручную.",
        "> Пересборка: `skiller registry`.",
        "",
        "Сплошная стрелка `A --> B` — `A` требует `B` (`requires`): `skiller vendor` дотянет `B`",
        "при установке `A`. Пунктирная `A -.-> B` — результат `A` служит входом для `B`",
        "(`produces_for`). Показаны только скиллы, участвующие в графе; изолированные —",
        "в таблице ниже.",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    for bucket in sorted(buckets):
        lines.append(f"  subgraph {node_id(bucket)}[\"{bucket}\"]")
        for name in buckets[bucket]:
            lines.append(f"    {node_id(name)}[\"{name}\"]")
        lines.append("  end")
    for src, dst in sorted(requires_edges):
        lines.append(f"  {node_id(src)} -->|requires| {node_id(dst)}")
    for src, dst in sorted(produces_edges):
        lines.append(f"  {node_id(src)} -.->|feeds| {node_id(dst)}")
    lines += [
        "```",
        "",
        f"**В графе:** {len(connected)} скиллов, {len(requires_edges)} рёбер requires, "
        f"{len(produces_edges)} рёбер produces_for.",
        "",
        f"## Изолированные скиллы ({sum(len(v) for v in isolated.values())})",
        "",
        "Скиллы без связей `requires`/`produces_for` — самодостаточны.",
        "",
        "| Бакет | Скиллы |",
        "|---|---|",
    ]
    for bucket in sorted(isolated):
        names = ", ".join(f"`{n}`" for n in sorted(isolated[bucket]))
        lines.append(f"| {bucket} | {names} |")
    lines.append("")
    return "\n".join(lines), len(connected), len(requires_edges) + len(produces_edges)


def write_graph(env, registry):
    """Записать docs/guide/graph.md (атомарно). Возвращает (n_nodes, n_edges)."""
    text, n_nodes, n_edges = render_graph(registry)
    out = _docs_root(env.root) / "docs" / "guide" / "graph.md"
    atomic_write_text(out, text)
    return n_nodes, n_edges


def cmd_registry(env, argv):
    opts = parse_flags(argv, {"--check": "bool"})
    if opts["help"]:
        print("skiller registry [--check]\n"
              "  без флага — регенерировать skills.json/_index.md/манифесты/граф/бюджет;\n"
              "  --check   — НЕ писать, а сверить артефакты с источниками (drift-гейт, rc=1 при дрейфе).")
        return
    if opts["check"]:
        drift = check_drift(env)
        if drift:
            print("DRIFT: сгенерированные артефакты отстали от источников — прогони `skiller registry`:",
                  file=sys.stderr)
            for d in drift:
                print(f"  - {d}", file=sys.stderr)
            sys.exit(1)
        print("registry --check: артефакты актуальны "
              "(skills.json/_index.md/манифесты/graph.md/budget.md)")
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

    if _has_repository_bootstrap_config(root):
        n_bootstrap = len(build_repository_bootstrap_publication(env))
        print(f"Updated root-bootstrap projections: {n_bootstrap} artifacts "
              f"(.claude/skills + .agents/skills + publication-lock.json, P1.2/D31)")

    n_nodes, n_edges = write_graph(env, registry)
    print(f"Updated docs/guide/graph.md: {n_nodes} nodes, {n_edges} edges")

    # Карта токенового бюджета (трёхъярусная) — in-process, чтобы токен-математика
    # жила в одном модуле budget.py, а не дублировалась.
    from .budget import write_budget_map
    write_budget_map(env)
