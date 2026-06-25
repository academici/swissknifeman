#!/usr/bin/env bash
# Validate repository structure: SKILL.md frontmatter, upstream.json,
# profiles/*.json, skills.json, snippet manifests.
# Used locally and by .github/workflows/validate.yml.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$REPO_ROOT" <<'PY'
import json, re, sys
from pathlib import Path

root = Path(sys.argv[1])  # корень пакета (skills/, lib/, buckets.json)
# marketplace.json — в корне монорепо; source-пути плагинов относительны корня репо.
# (Канон — core.repo.find_repo_root; здесь самодостаточный дубль: heredoc гоняется
#  до установки PYTHONPATH на core — осознанно не импортируем.)
def _repo_root(p):
    for cand in (p, *p.parents):
        if (cand / ".git").exists():
            return cand
    return p
repo_root = _repo_root(root)
errors = []
warnings = []

UPSTREAM_SOURCES = {"github", "http", "file"}
# replace = зеркало (автонакат); notify = адаптированная копия (только сообщать);
# fork = форк с нашими правками (обёртка + pristine-зеркало в files[].path; на дрейфе
#        review_pending=true блокирует распространение — ручной перенос, потом --resolve).
UPSTREAM_STRATEGIES = {"replace", "notify", "fork"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Допустимые значения enum-полей frontmatter + формат версии (semver).
RISK_VALUES = {"read", "draft", "write", "external"}
ADAPTER_VALUES = {"claude", "cursor", "fable"}
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
# Внутрискилловые относительные ссылки (snippets/…, references/…) в теле SKILL.md —
# должны резолвиться. ../ и .agents/.claude (раскладка проекта-потребителя) и
# прозовые URL'ы НЕ проверяем (ложные срабатывания на upstream/imported).
INTRA_LINK_RE = re.compile(r"\]\((snippets/[^)#]+|references/[^)#]+)\)")
# lean SKILL.md: тело — точка входа, детали в references/snippets (progressive disclosure).
# Мягкий порог: тело сверх него → warn (не error), подсказка вынести детали.
# См. docs/guide/skill-taxonomy.md.
LEAN_MAX_BODY_LINES = 150


def parse_frontmatter(path):
    """Return dict of frontmatter keys, or None if no frontmatter block."""
    lines = path.read_text(encoding="utf-8").replace("\r\n", "\n").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fm = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fm
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip()
    return None  # unterminated block


def parse_inline_list(value):
    """Inline YAML list ('[a, "b", c]') -> list of strings; anything else -> []."""
    value = (value or "").strip()
    if not (value.startswith("[") and value.endswith("]")):
        return []
    items = [i.strip().strip('"').strip("'") for i in value[1:-1].split(",")]
    return [i for i in items if i]


def load_upstream(skill_dir):
    f = skill_dir / "upstream.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        errors.append(f"{f.relative_to(root)}: invalid JSON: {e}")
        return {}


# --- 1. SKILL.md frontmatter ---------------------------------------------
skill_files = sorted(root.glob("skills/**/SKILL.md"))
meta_skill = root / "generate-skill/generate-skill/SKILL.md"
if meta_skill.exists():
    skill_files.append(meta_skill)

for skill_md in skill_files:
    rel = skill_md.relative_to(root)
    skill_dir = skill_md.parent
    upstream = load_upstream(skill_dir)
    fm = parse_frontmatter(skill_md)

    if fm is None:
        if upstream is not None and upstream.get("strategy") == "replace":
            errors.append(
                f"{rel}: no frontmatter and upstream strategy=replace — "
                f"frontmatter-less upstreams must use strategy=notify"
            )
        else:
            errors.append(f"{rel}: missing frontmatter block")
        continue

    required = ["name", "description"] if upstream is not None \
        else ["name", "bucket", "version", "description"]
    for field in required:
        if not fm.get(field):
            errors.append(f"{rel}: missing required frontmatter field: {field}")

    # --- 1a. enum / semver / bucket-vs-dir / declared snippets / intra-links ---
    parts = rel.parts
    path_bucket = parts[1] if parts[0] == "skills" and len(parts) > 2 else None

    risk = fm.get("risk", "")
    if risk and risk not in RISK_VALUES:
        errors.append(f"{rel}: risk '{risk}' не из {sorted(RISK_VALUES)}")

    bad_adapters = [a for a in parse_inline_list(fm.get("adapters", ""))
                    if a not in ADAPTER_VALUES]
    if bad_adapters:
        errors.append(f"{rel}: неизвестные adapters {bad_adapters} "
                      f"(допустимо {sorted(ADAPTER_VALUES)})")

    # version/bucket — только для локальных (upstream-скиллы держат минимальный frontmatter)
    if upstream is None:
        ver = fm.get("version", "")
        if ver and not SEMVER_RE.match(ver):
            errors.append(f"{rel}: version '{ver}' не semver (\\d+.\\d+.\\d+)")
        fm_bucket = fm.get("bucket", "")
        if path_bucket and fm_bucket and fm_bucket != path_bucket:
            errors.append(f"{rel}: frontmatter bucket '{fm_bucket}' != каталог "
                          f"'{path_bucket}'")

    # объявленные в frontmatter сниппеты должны существовать на диске
    for snip in parse_inline_list(fm.get("snippets", "")):
        if not (skill_dir / "snippets" / snip).exists():
            errors.append(f"{rel}: snippets[{snip}] объявлен, но файла нет на диске")

    # внутрискилловые ссылки snippets/… references/… в теле — должны резолвиться
    body = skill_md.read_text(encoding="utf-8")
    for m in INTRA_LINK_RE.finditer(body):
        tgt = m.group(1).split("#")[0]
        if not (skill_dir / tgt).exists():
            errors.append(f"{rel}: битая ссылка на {tgt} (файла нет)")

    # lean SKILL.md: тело (без frontmatter) сверх порога → мягкий warn.
    # upstream-скиллы (imported/external) пропускаем — их объём интенциональный (адаптированная
    # копия внешнего документа), lean-стандарт распространяется на АВТОРСКИЕ local-скиллы.
    lines = body.splitlines()
    body_start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                body_start = i + 1
                break
    body_lines = len([ln for ln in lines[body_start:] if ln.strip()])
    if body_lines > LEAN_MAX_BODY_LINES and load_upstream(skill_dir) is None:
        warnings.append(f"{rel}: тело SKILL.md {body_lines} непустых строк "
                        f"(> {LEAN_MAX_BODY_LINES}) — вынеси детали в references/snippets "
                        f"(lean SKILL.md, docs/guide/skill-taxonomy.md)")

# --- 2. upstream.json -----------------------------------------------------
for up_file in sorted(root.glob("skills/**/upstream.json")) + \
        sorted((root / "generate-skill").glob("**/upstream.json")):
    rel = up_file.relative_to(root)
    skill_dir = up_file.parent
    if not (skill_dir / "SKILL.md").exists():
        errors.append(f"{rel}: upstream.json without sibling SKILL.md")
    try:
        data = json.loads(up_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        errors.append(f"{rel}: invalid JSON: {e}")
        continue

    if data.get("schema_version") != 1:
        errors.append(f"{rel}: schema_version must be 1")
    if data.get("source") not in UPSTREAM_SOURCES:
        errors.append(f"{rel}: source must be one of {sorted(UPSTREAM_SOURCES)}")
    if data.get("strategy") not in UPSTREAM_STRATEGIES:
        errors.append(f"{rel}: strategy must be one of {sorted(UPSTREAM_STRATEGIES)}")
    # fork: форк-скилл с локальными правками. review_pending=true — апстрим разошёлся с
    # зеркалом, нужна ручная доработка → ГЕЙТ: блокируем валидацию (и тем самым registry/релиз),
    # пока агент не перенесёт дифф и не сделает update-upstreams.sh --resolve.
    if data.get("strategy") == "fork":
        rp = data.get("review_pending")
        if rp is not None and not isinstance(rp, bool):
            errors.append(f"{rel}: review_pending must be a boolean")
        if rp is True:
            errors.append(
                f"{rel}: review_pending=true — upstream форка разошёлся с зеркалом; "
                f"сверь diff и перенеси правки в SKILL.md, затем "
                f"scripts/update-upstreams.sh --resolve --skill <id>")
        lr = data.get("last_review", "")
        if lr and not DATE_RE.match(lr):
            errors.append(f"{rel}: last_review must be YYYY-MM-DD or empty")
    if data.get("source") == "file":
        warnings.append(f"{rel}: source=file is for local fixtures/tests only")

    files = data.get("files")
    if not isinstance(files, list) or not files:
        errors.append(f"{rel}: files must be a non-empty array")
        continue
    for i, entry in enumerate(files):
        for key in ("path", "url", "sha256", "fetched_at"):
            if key not in entry:
                errors.append(f"{rel}: files[{i}] missing key: {key}")
        path = entry.get("path", "")
        if path:
            target = (skill_dir / path).resolve()
            if not str(target).startswith(str(skill_dir.resolve())):
                errors.append(f"{rel}: files[{i}].path escapes skill dir: {path}")
            elif not target.exists():
                errors.append(f"{rel}: files[{i}].path does not exist: {path}")
        fetched = entry.get("fetched_at", "")
        if fetched and not DATE_RE.match(fetched):
            errors.append(f"{rel}: files[{i}].fetched_at must be YYYY-MM-DD or empty")

# --- 3. profiles/*.json ---------------------------------------------------
# Канон таксономии — core.project.PROJECT_TYPES; здесь самодостаточный дубль
# (heredoc гоняется до PYTHONPATH на core — осознанно не импортируем; держать
#  в синхроне с core/project.py). Ссылки на пресеты/паки/mcp живут в пакете
# harness — проверяем только если он на месте (монорепо), иначе graceful skip.
PROJECT_TYPE_IDS = {
    "obsidian-vault", "laravel-project", "php-package", "dart-flutter",
    "python-backend", "node-frontend", "node-package", "standalone",
}
AA_MODES = {"strict", "permissive", "bypass", "off"}
MEM_MODES = {"file", "federation", "agentmemory", "maind", "off"}
MODEL_TIERS = {"inherit", "opus", "sonnet", "haiku"}
hc_dir = repo_root / "packages" / "harness" / "configs" / "claude-code"
profile_names = set()
profiles_dir = root / "profiles"
if profiles_dir.is_dir():
    for prof in sorted(profiles_dir.glob("*.json")):
        rel = prof.relative_to(root)
        try:
            data = json.loads(prof.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            errors.append(f"{rel}: invalid JSON: {e}")
            continue
        profile_names.add(prof.stem)
        if data.get("name") != prof.stem:
            errors.append(f"{rel}: name must match filename ({prof.stem})")
        buckets = data.get("buckets")
        if not isinstance(buckets, list) or not buckets:
            errors.append(f"{rel}: buckets must be a non-empty array")
        elif buckets != ["*"]:
            for b in buckets:
                if not (root / "skills" / b).is_dir():
                    errors.append(f"{rel}: unknown bucket: {b}")
        # --- расширенные опц. ключи: agent_pack/presets/mcp/hooks/model_tiers ---
        pack = data.get("agent_pack")
        if pack is not None and not isinstance(pack, (str, list)):
            errors.append(f"{rel}: agent_pack must be a string or list")
        packs = [pack] if isinstance(pack, str) else (pack if isinstance(pack, list) else [])
        if hc_dir.is_dir():
            for pk in packs:
                if not (hc_dir / "agent-packs" / str(pk) / "pack.json").exists():
                    errors.append(f"{rel}: agent_pack '{pk}' — нет pack.json в harness")
            for preset in data.get("harness_presets", []) or []:
                if not (hc_dir / f"settings.{preset}.json").exists():
                    errors.append(f"{rel}: harness_preset '{preset}' — нет settings.{preset}.json")
            for srv in data.get("mcp", []) or []:
                if not (hc_dir / "mcp" / f"{srv}.json").exists():
                    errors.append(f"{rel}: mcp '{srv}' — нет mcp/{srv}.json")
        hooks = data.get("hooks") or {}
        if not isinstance(hooks, dict):
            errors.append(f"{rel}: hooks must be an object")
        else:
            aa = hooks.get("auto_approve")
            if aa is not None and aa not in AA_MODES:
                errors.append(f"{rel}: hooks.auto_approve '{aa}' не из {sorted(AA_MODES)}")
            mem = hooks.get("memory")
            if mem is not None and mem not in MEM_MODES:
                errors.append(f"{rel}: hooks.memory '{mem}' не из {sorted(MEM_MODES)}")
        tiers = data.get("model_tiers") or {}
        if not isinstance(tiers, dict):
            errors.append(f"{rel}: model_tiers must be an object")
        else:
            for role, tier in tiers.items():
                if tier not in MODEL_TIERS:
                    errors.append(f"{rel}: model_tiers.{role} '{tier}' "
                                  f"не из {sorted(MODEL_TIERS)}")
    # --- 3b. покрытие: каждый id таксономии имеет profiles/<id>.json ---
    missing = PROJECT_TYPE_IDS - profile_names
    if missing:
        errors.append(f"profiles/: нет профилей для типов {sorted(missing)} "
                      f"(см. core.project.PROJECT_TYPES)")

# --- 4. skills.json -------------------------------------------------------
reg = root / "skills.json"
if reg.exists():
    try:
        json.loads(reg.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"skills.json: invalid JSON: {e}")
else:
    errors.append("skills.json not found")

# --- 5. snippet manifests -------------------------------------------------
for manifest in sorted(root.glob("skills/**/snippets/index.json")):
    rel = manifest.relative_to(root)
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"{rel}: invalid JSON: {e}")
        continue
    for s in data.get("snippets", []):
        f = manifest.parent / s.get("file", "")
        if not f.exists():
            errors.append(f"{rel}: missing snippet: {s.get('file')}")

# --- 6. buckets.json --------------------------------------------------------
KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
bucket_dirs = sorted(d.name for d in (root / "skills").iterdir() if d.is_dir())
bucket_meta = {}
meta_file = root / "buckets.json"
if not meta_file.exists():
    errors.append("buckets.json not found")
else:
    try:
        bucket_meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"buckets.json: invalid JSON: {e}")
        bucket_meta = {}
    for b in bucket_dirs:
        if b not in bucket_meta:
            errors.append(f"buckets.json: missing entry for bucket: {b}")
    for b, meta in bucket_meta.items():
        if b not in bucket_dirs:
            errors.append(f"buckets.json: entry without skills/ dir: {b}")
        if not (isinstance(meta, dict) and meta.get("description")):
            errors.append(f"buckets.json: {b}: description must be non-empty")


# --- 6b. presets/*.json (именованные кластеры скиллов) ----------------------
# Пресет = группа скиллов для vendor-выборки: {name, description, extends?,
# buckets?, include?}. resolve_skillset раскрывает presets → buckets/include.
# Проверяем: name==файл (kebab), непустой description, extends/buckets/include
# резолвятся, циклов в extends нет. Каталог опционален (graceful skip).
presets_dir = root / "presets"
if presets_dir.is_dir():
    skill_names, skill_paths = set(), set()
    for skill_md in skill_files:
        fm = parse_frontmatter(skill_md) or {}
        nm = (fm.get("name", "") or "").strip().strip('"').strip("'")
        if nm:
            skill_names.add(nm)
        parts = skill_md.parent.relative_to(root).parts
        if len(parts) >= 3 and parts[0] == "skills":
            skill_paths.add("/".join(parts[1:]))  # bucket/rel
    preset_names = {p.stem for p in presets_dir.glob("*.json")}
    preset_extends = {}
    for pf in sorted(presets_dir.glob("*.json")):
        rel = pf.relative_to(root)
        try:
            data = json.loads(pf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            errors.append(f"{rel}: invalid JSON: {e}")
            continue
        if data.get("name") != pf.stem:
            errors.append(f"{rel}: name must match filename ({pf.stem})")
        if not KEBAB_RE.match(pf.stem):
            errors.append(f"{rel}: preset name must be kebab-case")
        if not data.get("description"):
            errors.append(f"{rel}: description must be non-empty")
        ext = data.get("extends", []) or []
        if not isinstance(ext, list):
            errors.append(f"{rel}: extends must be a list")
            ext = []
        for parent in ext:
            if parent not in preset_names:
                errors.append(f"{rel}: extends unknown preset '{parent}'")
        preset_extends[pf.stem] = [e for e in ext if e in preset_names]
        for b in data.get("buckets", []) or []:
            if b not in bucket_dirs:
                errors.append(f"{rel}: unknown bucket '{b}'")
        for tok in data.get("include", []) or []:
            if tok not in skill_names and tok not in skill_paths:
                errors.append(f"{rel}: include '{tok}' не резолвится в скилл "
                              f"(нужно имя или bucket/rel)")
    # циклы в extends (iterative DFS, white/grey/black)
    PW, PG, PB = 0, 1, 2
    pcol = {n: PW for n in preset_extends}
    for pstart in sorted(preset_extends):
        if pcol[pstart] != PW:
            continue
        pstack = [(pstart, iter(preset_extends.get(pstart, [])))]
        pcol[pstart] = PG
        ppath = [pstart]
        while pstack:
            pnode, pit = pstack[-1]
            padv = False
            for pdep in pit:
                if pcol.get(pdep) == PG:
                    cyc = ppath[ppath.index(pdep):] + [pdep]
                    errors.append(f"presets: extends cycle: {' -> '.join(cyc)}")
                elif pcol.get(pdep) == PW:
                    pcol[pdep] = PG
                    ppath.append(pdep)
                    pstack.append((pdep, iter(preset_extends.get(pdep, []))))
                    padv = True
                    break
            if not padv:
                pcol[pnode] = PB
                ppath.pop()
                pstack.pop()


# --- 7. plugin manifests (.claude-plugin/) ----------------------------------
def expected_skills_dirs(plugin_root):
    """Same algorithm as sync.sh: parents of skill dirs, ./-prefixed."""
    dirs = set()
    for skill_md in plugin_root.rglob("SKILL.md"):
        rel = skill_md.parent.parent.relative_to(plugin_root)
        dirs.add("./" if str(rel) == "." else f"./{rel.as_posix()}")
    return sorted(dirs)


STALE_HINT = "run 'skiller registry' (or ./sync.sh --update-registry)"
plugin_roots = {b: root / "skills" / b for b in bucket_dirs}
plugin_roots["generate-skill"] = root / "generate-skill"
# Management plugin (командное лицо CLI, без скиллов) — валидируем как обычный плагин,
# если каталог есть; registry.py добавляет его в marketplace.json синхронно.
if (root / "skm" / ".claude-plugin" / "plugin.json").exists():
    plugin_roots["skm"] = root / "skm"

# Соседние пакеты монорепо (packages/<name>, кроме swissknifeman) — командные/MCP-плагины
# без skills-поля; их plugin.json — источник истины, registry добавляет их в marketplace.
# Здесь только собираем их имена для match-проверки (полная валидация — в их пакете).
sibling_plugin_names = []
pkgs_dir = repo_root / "packages"
if root != repo_root and pkgs_dir.is_dir():
    for pkg in sorted(pkgs_dir.iterdir()):
        if not pkg.is_dir() or pkg.name == root.name:
            continue
        pj = pkg / ".claude-plugin" / "plugin.json"
        if pj.exists():
            try:
                sibling_plugin_names.append(
                    json.loads(pj.read_text(encoding="utf-8")).get("name", pkg.name))
            except json.JSONDecodeError as e:
                errors.append(f"packages/{pkg.name}/.claude-plugin/plugin.json: invalid JSON: {e}")

for plugin_name, plugin_root in sorted(plugin_roots.items()):
    pj = plugin_root / ".claude-plugin" / "plugin.json"
    rel = pj.relative_to(root)
    if not pj.exists():
        errors.append(f"{rel}: missing ({STALE_HINT})")
        continue
    try:
        data = json.loads(pj.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"{rel}: invalid JSON: {e}")
        continue
    if data.get("name") != plugin_name:
        errors.append(f"{rel}: name must be '{plugin_name}'")
    if not KEBAB_RE.match(data.get("name", "")):
        errors.append(f"{rel}: name must be kebab-case")
    if not data.get("description"):
        errors.append(f"{rel}: description must be non-empty")
    declared = data.get("skills", [])
    declared = [declared] if isinstance(declared, str) else declared
    if sorted(declared) != expected_skills_dirs(plugin_root):
        errors.append(f"{rel}: stale skills dirs ({STALE_HINT})")

mp_file = repo_root / ".claude-plugin" / "marketplace.json"
if not mp_file.exists():
    errors.append(f".claude-plugin/marketplace.json: missing ({STALE_HINT})")
else:
    try:
        mp = json.loads(mp_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f".claude-plugin/marketplace.json: invalid JSON: {e}")
        mp = {}
    if mp:
        if mp.get("name") != "swissknifeman":
            errors.append(".claude-plugin/marketplace.json: name must be 'swissknifeman'")
        if not mp.get("owner", {}).get("name"):
            errors.append(".claude-plugin/marketplace.json: owner.name must be set")
        entries = mp.get("plugins", [])
        names = [p.get("name", "") for p in entries]
        if len(names) != len(set(names)):
            errors.append(".claude-plugin/marketplace.json: duplicate plugin names")
        expected_names = list(plugin_roots) + sibling_plugin_names
        if sorted(names) != sorted(expected_names):
            errors.append(
                f".claude-plugin/marketplace.json: plugins must match dirs on disk "
                f"({STALE_HINT})")
        for p in entries:
            src = p.get("source", "")
            # source-пути относительны корня репо (./packages/skiller/...)
            if not (repo_root / src).is_dir():
                errors.append(
                    f".claude-plugin/marketplace.json: {p.get('name')}: "
                    f"source dir not found: {src}")
            if not p.get("description"):
                errors.append(
                    f".claude-plugin/marketplace.json: {p.get('name')}: "
                    f"description must be non-empty")

# --- 7b. no skills nested inside a skill dir ---------------------------------
# Claude Code discovers a dir with SKILL.md as a leaf skill; SKILL.md deeper
# inside it is silently invisible to plugin discovery.
for skill_md in skill_files:
    d = skill_md.parent
    nested = [p for p in d.rglob("SKILL.md") if p != skill_md]
    for p in nested:
        errors.append(
            f"{p.relative_to(root)}: nested inside skill "
            f"'{d.relative_to(root)}' — invisible to plugin discovery; "
            f"flatten it (e.g. '{d.name}-{p.parent.name}' next to '{d.name}')")

# --- 8. skill-name uniqueness ------------------------------------------------
# Plugin namespace flattens per plugin: dup inside a bucket = error.
# Across buckets namespacing keeps it legal, but vendoring modes collide: warn.
by_bucket = {}
for skill_md in skill_files:
    fm = parse_frontmatter(skill_md) or {}
    name = fm.get("name", "")
    if not name:
        continue
    bucket = skill_md.relative_to(root).parts[1] \
        if skill_md.relative_to(root).parts[0] == "skills" else "generate-skill"
    by_bucket.setdefault(bucket, {}).setdefault(name, []).append(
        str(skill_md.relative_to(root)))
seen_names = {}
for bucket, names in sorted(by_bucket.items()):
    for name, paths in sorted(names.items()):
        if len(paths) > 1:
            errors.append(
                f"duplicate skill name '{name}' in bucket '{bucket}': "
                f"{', '.join(paths)}")
        seen_names.setdefault(name, []).append(bucket)
for name, in_buckets in sorted(seen_names.items()):
    if len(in_buckets) > 1:
        warnings.append(
            f"skill name '{name}' appears in buckets {', '.join(in_buckets)} — "
            f"legal with plugin namespaces, collides in vendoring modes")

# --- 9. dependency graph (requires / produces_for) ---------------------------
# Edge names are frontmatter `name` values. Cycles are checked over `requires`
# only: an `A requires B` + `B produces_for A` pair is a normal complementary
# link, not a cycle.
graph_requires = {}
graph_produces = {}
name_to_rel = {}
for skill_md in skill_files:
    rel = skill_md.relative_to(root)
    fm = parse_frontmatter(skill_md) or {}
    name = fm.get("name", "").strip().strip('"').strip("'")
    if not name:
        continue
    name_to_rel.setdefault(name, str(rel))
    for key, store in (("requires", graph_requires), ("produces_for", graph_produces)):
        raw = fm.get(key, "").strip()
        deps = parse_inline_list(raw)
        if raw and raw != "[]" and not deps:
            warnings.append(
                f"{rel}: {key} is set but not an inline list ('{raw}') — "
                f"use '[a, b]' syntax; multiline YAML lists are not parsed")
        store[name] = deps

all_names = set(graph_requires) | set(graph_produces)
for name in sorted(all_names):
    src = name_to_rel[name]
    for key, store in (("requires", graph_requires), ("produces_for", graph_produces)):
        for dep in store.get(name, []):
            if dep == name:
                errors.append(f"{src}: {key} references itself")
            elif dep not in all_names:
                errors.append(f"{src}: {key} unknown skill '{dep}'")

# Cycle detection over `requires` (iterative DFS, white/grey/black colouring)
WHITE, GREY, BLACK = 0, 1, 2
colour = {n: WHITE for n in all_names}
for start in sorted(all_names):
    if colour[start] != WHITE:
        continue
    stack = [(start, iter(graph_requires.get(start, [])))]
    colour[start] = GREY
    path = [start]
    while stack:
        node, it = stack[-1]
        advanced = False
        for dep in it:
            if dep not in all_names:
                continue
            if colour[dep] == GREY:
                cycle = path[path.index(dep):] + [dep]
                errors.append(f"requires cycle: {' -> '.join(cycle)}")
            elif colour[dep] == WHITE:
                colour[dep] = GREY
                path.append(dep)
                stack.append((dep, iter(graph_requires.get(dep, []))))
                advanced = True
                break
        if not advanced:
            colour[node] = BLACK
            path.pop()
            stack.pop()

# --- 10. internal project skills (.claude/skills/) ---------------------------
# Внутренние скиллы разработки реестра: НЕ экспортируются и НЕ попадают в
# skills.json — линтуются мягко (только name+description, без полей реестра).
registry_names = set(seen_names)
# Локальные dev-скиллы могут жить и в .claude/skills пакета, и в КОРНЕ МОНОРЕПО
# (перенесены туда ради видимости из корня). Линтуем оба места (standalone-safe).
_skill_roots = [root]
_mono = root.parent.parent          # packages/<pkg> → корень монорепо
if _mono != root and (_mono / ".claude" / "skills").is_dir():
    _skill_roots.append(_mono)
_internal_skills = []
for _sr in _skill_roots:
    for _p in sorted(_sr.glob(".claude/skills/*/SKILL.md")):
        _internal_skills.append((_sr, _p))
for _sr, skill_md in _internal_skills:
    rel = skill_md.relative_to(_sr)
    fm = parse_frontmatter(skill_md)
    if fm is None:
        errors.append(f"{rel}: missing frontmatter block")
        continue
    name = fm.get("name", "").strip().strip('"').strip("'")
    if not name or not fm.get("description"):
        errors.append(f"{rel}: internal skill needs name + description")
        continue
    if not KEBAB_RE.match(name):
        errors.append(f"{rel}: name must be kebab-case")
    if name != skill_md.parent.name:
        errors.append(f"{rel}: name '{name}' must match dir '{skill_md.parent.name}'")
    if name in registry_names:
        warnings.append(
            f"{rel}: internal skill name '{name}' collides with a registry skill")

# --- 10b. slash-команды плагина skm (frontmatter) ----------------------------
# Командное лицо CLI: каждый skm/commands/*.md должен иметь frontmatter с
# непустым description (иначе команда без подписи в меню Claude Code).
for cmd_md in sorted(root.glob("skm/commands/*.md")):
    rel = cmd_md.relative_to(root)
    fm = parse_frontmatter(cmd_md)
    if fm is None:
        errors.append(f"{rel}: missing/unterminated frontmatter block")
    elif not fm.get("description"):
        errors.append(f"{rel}: slash-команда без непустого description")

# --- 10c. agent `skills:` references resolve to registry skills --------------
# Агенты бакетов (skills/<bucket>/agents/*.md) предзагружают скиллы нативным
# полем `skills: [bucket:name, ...]` (Claude Code subagent preload). Каждый
# namespaced-элемент обязан указывать на реальный скилл реестра — иначе CC
# тихо пропускает его с warning в debug-лог.
registry_bn = set()
for skill_md in skill_files:
    fm = parse_frontmatter(skill_md)
    if not fm:
        continue
    b = (fm.get("bucket", "") or "").strip().strip('"').strip("'")
    n = (fm.get("name", "") or "").strip().strip('"').strip("'")
    if b and n:
        registry_bn.add(f"{b}:{n}")
for agent_md in sorted(root.glob("skills/*/agents/*.md")):
    rel = agent_md.relative_to(root)
    fm = parse_frontmatter(agent_md)
    if not fm:
        continue
    for entry in parse_inline_list(fm.get("skills", "")):
        if ":" not in entry:
            warnings.append(
                f"{rel}: skills-элемент '{entry}' без namespace (нужно bucket:name)")
        elif entry not in registry_bn:
            errors.append(
                f"{rel}: skills-элемент '{entry}' не резолвится в скилл реестра")

# --- report ----------------------------------------------------------------
for w in warnings:
    print(f"WARN: {w}")
for e in errors:
    print(f"ERROR: {e}")

checked = len(skill_files)
if errors:
    print(f"\n{checked} skills checked — {len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1)
print(f"{checked} skills checked — all valid ({len(warnings)} warning(s))")
PY

# --- 11. CLI + shell scripts ---------------------------------------------------
[[ -x "$REPO_ROOT/bin/skiller" ]] || {
  echo "ERROR: bin/skiller missing or not executable" >&2; exit 1; }
for sh in "$REPO_ROOT/bin/skiller" "$REPO_ROOT/install.sh" \
          "$REPO_ROOT/sync.sh" "$REPO_ROOT"/scripts/*.sh; do
  bash -n "$sh" || { echo "ERROR: bash -n failed: $sh" >&2; exit 1; }
done
# Пресеты/хуки Claude Code вынесены в пакет harness (см. packages/harness);
# их bash-проверка — в packages/harness/scripts/validate.sh.
echo "CLI + shell scripts: syntax OK"

# --- 12. lib/skiller package + unit/integration tests --------------------------
[[ -d "$REPO_ROOT/lib/skiller" ]] || {
  echo "ERROR: lib/skiller package missing" >&2; exit 1; }
# MONOREPO_ROOT (на два уровня выше пакета) — чтобы импортировался пакет `core`;
# опционально: в standalone-раскладке каталога core нет, путь не добавляется.
MONOREPO_ROOT="$(cd "$REPO_ROOT/../.." 2>/dev/null && pwd || true)"
[ -d "$MONOREPO_ROOT/core" ] || MONOREPO_ROOT=""
PYTHONPATH="$REPO_ROOT/lib${MONOREPO_ROOT:+:$MONOREPO_ROOT}" python3 -c "import skiller.cli" || {
  echo "ERROR: lib/skiller fails to import" >&2; exit 1; }
"$REPO_ROOT/scripts/test.sh" || { echo "ERROR: tests failed" >&2; exit 1; }
