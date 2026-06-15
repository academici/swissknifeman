"""Derive-движок: строит граф проекта из ИСТОЧНИКОВ ИСТИНЫ, а не из ручного дубля.

Три плана связей (см. constants.GRAPH_PLANES), каждый со своим `via`:
- code     — composer.json / package.json (+ path-repos): `project ─requires→ package`,
             `package ─provided_by→ project`, cross `project ─depends_on→ project`.
- doc      — Brain frontmatter `uses:/used_by:` (только ЧТЕНИЕ vault, без дублей).
- override — `<repo>/.maind.graph.json` для связей, которых нет в коде/доках (runtime/API).
- skills   — skills-lock.json (порт seed_skills): `project ─uses→ skill ─provided_by→ tool`.

Каждый derive_project_graph строит стор проекта ЗАНОВО (идемпотентно, без накопления
устаревших рёбер) и помечает узлы/рёбра owner-проектом → федерация резолвит владение."""
import json
import os
from pathlib import Path

from .common import warn
from .federation import project_graph, rebuild_index, store_path
from .graph import Graph

# Вендоры первых сторон экосистемы (фильтр composer-зависимостей от laravel/symfony/…).
FIRST_PARTY_VENDORS = {"axioma-studio", "botkit", "corex", "azguard", "docvault",
                       "academici", "flex", "flexcrm", "getchat"}

# Алиасы doc-имён (frontmatter/wikilinks) → id проекта для незарегистрированных в .maind.json.
DOC_ALIASES = {
    "corex": "corex", "azguard": "azguard", "docvault": "docvault", "botkit": "botkit",
    "getchat": "getchat", "getchatcore": "getchatcore", "flexcrm": "flexcrm",
    "flexcms": "flexcms", "flexstore": "flexstore", "axiomaerpsdk": "axiomaerpsdk",
}

_SKIP_DIRS = {"vendor", "node_modules", ".git", "dist", "build", ".maind"}


# ── разрешение имён ──────────────────────────────────────────────────────────
def _project_ids(config):
    return {p["id"] for p in (config.get("projects") or [])}


def _slug(name):
    return "".join(c if c.isalnum() else "" for c in str(name).lower())


def resolve_project(name, config):
    """doc-имя/slug → (project_id, registered). Незарегистрированное → внешний узел."""
    ids = _project_ids(config)
    s = _slug(name)
    if s in ids:
        return s, True
    if s in DOC_ALIASES and DOC_ALIASES[s] in ids:
        return DOC_ALIASES[s], True
    if s in DOC_ALIASES:
        return DOC_ALIASES[s], False
    return s, s in ids


def _is_first_party(pkg_name, providers):
    if pkg_name in providers:
        return True
    vendor = pkg_name.split("/", 1)[0] if "/" in pkg_name else ""
    return vendor in FIRST_PARTY_VENDORS


# ── скан composer/package манифестов ─────────────────────────────────────────
def _manifest_files(repo, filename, max_depth=3):
    """Все <filename> в репо (root + вложенные), кроме vendor/node_modules, до глубины."""
    repo = Path(repo)
    out = []
    root_n = len(repo.parts)
    for dirpath, dirnames, filenames in os.walk(repo):
        depth = len(Path(dirpath).parts) - root_n
        if depth >= max_depth:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        if filename in filenames:
            out.append(Path(dirpath) / filename)
    return out


def _load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def build_provider_index(env, config):
    """{package_name → project_id}: какой проект ПРЕДОСТАВЛЯЕТ пакет (по composer `name`)."""
    providers = {}
    for p in config.get("projects") or []:
        local = p.get("local_path")
        if not local:
            continue
        repo = Path(os.path.expanduser(local))
        if not repo.is_dir():
            continue
        for f in _manifest_files(repo, "composer.json"):
            data = _load_json(f)
            name = (data or {}).get("name")
            if name:
                providers.setdefault(name, p["id"])
    return providers


def _project_requires(repo):
    """Множество первичных composer-зависимостей проекта (require + require-dev, все манифесты)."""
    deps = set()
    for f in _manifest_files(repo, "composer.json"):
        data = _load_json(f) or {}
        for sect in ("require", "require-dev"):
            for dep in (data.get(sect) or {}):
                if "/" in dep:           # пакеты, не php/ext-*
                    deps.add(dep)
    return deps


def _provided_packages(repo):
    """Имена пакетов, которые этот репо предоставляет (composer `name` всех манифестов)."""
    names = []
    for f in _manifest_files(repo, "composer.json"):
        name = (_load_json(f) or {}).get("name")
        if name:
            names.append(name)
    return names


# ── план: code ───────────────────────────────────────────────────────────────
def derive_code(g, project, config, providers):
    """composer/package → узлы пакетов + requires/provided_by + cross depends_on (via=code)."""
    pid = project["id"]
    pnode = f"project:{pid}"
    local = project.get("local_path")
    if not local:
        return 0
    repo = Path(os.path.expanduser(local))
    if not repo.is_dir():
        return 0
    edges = 0
    own = set(_provided_packages(repo))
    for name in own:
        g.add_node(f"package:{name}", "package", project=pid, name=name.split("/")[-1])
        g.add_edge(f"package:{name}", pnode, "provided_by", via="code", plane="code")
        edges += 1
    for dep in _project_requires(repo):
        if not _is_first_party(dep, providers):
            continue
        g.add_node(f"package:{dep}", "package", name=dep.split("/")[-1])
        g.add_edge(pnode, f"package:{dep}", "requires", via="code", plane="code")
        edges += 1
        owner = providers.get(dep)
        if owner and owner != pid:
            g.add_node(f"project:{owner}", "project")
            g.add_edge(pnode, f"project:{owner}", "depends_on", via="code", plane="code")
            edges += 1
    # package.json (node) — первичные deps по тому же принципу
    pkg = _load_json(repo / "package.json")
    if pkg:
        for dep in {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}:
            if _is_first_party(dep, providers):
                g.add_node(f"package:{dep}", "package", name=dep.split("/")[-1])
                g.add_edge(pnode, f"package:{dep}", "requires", via="code", plane="code")
                edges += 1
    return edges


# ── план: doc (Brain frontmatter, только чтение) ─────────────────────────────
def _frontmatter(text):
    """Грубый парс YAML-фронтматтера (между первыми '---'): только нужные нам списки."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}
    out, cur = {}, None
    for ln in lines[1:end]:
        if cur and ln[:1] in (" ", "\t") and ln.strip().startswith("-"):
            out[cur].append(ln.strip()[1:].strip().strip("'\""))
            continue
        cur = None
        if ":" not in ln:
            continue
        key, val = ln.split(":", 1)
        key, val = key.strip(), val.strip()
        if val.startswith("[") and val.endswith("]"):
            out[key] = [x.strip().strip("'\"") for x in val[1:-1].split(",") if x.strip()]
        elif val == "":
            out[key] = []
            cur = key
    return out


def _control_tower(project):
    """Путь к control-tower ноте в Brain: <vault_path>/<Name>.md (или _index.md)."""
    vp = project.get("vault_path")
    if not vp:
        return None
    base = Path(os.path.expanduser(vp))
    if not base.is_dir():
        return None
    for cand in (base / f"{project.get('name', '')}.md",
                 base / f"{base.name}.md", base / "_index.md"):
        if cand.is_file():
            return cand
    return None


def derive_doc(g, project, config):
    """Brain frontmatter uses/used_by → cross-рёбра `uses` (via=doc). Нет ноты → 0."""
    pid = project["id"]
    pnode = f"project:{pid}"
    note = _control_tower(project)
    if note is None:
        return 0
    try:
        fm = _frontmatter(note.read_text(encoding="utf-8"))
    except OSError:
        return 0
    edges = 0
    for name in fm.get("uses") or []:
        tid, reg = resolve_project(name, config)
        if tid and tid != pid:
            g.add_node(f"project:{tid}", "project", registered=reg)
            g.add_edge(pnode, f"project:{tid}", "uses", via="doc", plane="doc")
            edges += 1
    for name in fm.get("used_by") or []:
        tid, reg = resolve_project(name, config)
        if tid and tid != pid:
            g.add_node(f"project:{tid}", "project", registered=reg)
            g.add_edge(f"project:{tid}", pnode, "uses", via="doc", plane="doc")
            edges += 1
    return edges


# ── план: override (.maind.graph.json) ───────────────────────────────────────
def derive_override(g, project, config):
    """`<repo>/.maind.graph.json` → объявленные cross-рёбра (via=override)."""
    local = project.get("local_path")
    if not local:
        return 0
    f = Path(os.path.expanduser(local)) / ".maind.graph.json"
    data = _load_json(f)
    if not data:
        return 0
    pid = project["id"]
    pnode = f"project:{pid}"
    edges = 0
    for link in data.get("links") or []:
        to = link.get("to")
        if not to:
            continue
        tid, reg = resolve_project(to, config)
        etype = link.get("type", "relates_to")
        plane = link.get("plane", "runtime")
        g.add_node(f"project:{tid}", "project", registered=reg)
        attrs = {"via": "override", "plane": plane}
        if link.get("note"):
            attrs["note"] = link["note"]
        try:
            g.add_edge(pnode, f"project:{tid}", etype, **attrs)
            edges += 1
        except ValueError:
            warn(f"override {f}: недопустимый тип ребра '{etype}' — пропуск")
    return edges


# ── план: skills (порт seed_skills) ──────────────────────────────────────────
_PROVIDERS = ("swissknifeman", "laravel-boost", "brain")


def _lock_skills(project):
    local = project.get("local_path")
    if not local:
        return None
    f = Path(os.path.expanduser(local)) / "skills-lock.json"
    data = _load_json(f)
    return (data or {}).get("skills") if data else None


def derive_skills(g, project):
    """skills-lock.json → project ─uses→ skill ─provided_by→ tool (via=skills, plane=meta)."""
    pid = project["id"]
    pnode = f"project:{pid}"
    skills = _lock_skills(project)
    if not skills:
        return 0
    edges = 0
    for name, entry in skills.items():
        snode = f"skill:{name}"
        g.add_node(snode, "skill", project=pid, bucket=entry.get("bucket", ""))
        g.add_edge(pnode, snode, "uses", via="skills", plane="meta")
        edges += 1
        for src in [entry.get("source")] + list(entry.get("also_in") or []):
            if src in _PROVIDERS:
                g.add_node(f"tool:{src}", "tool")
                g.add_edge(snode, f"tool:{src}", "provided_by", via="skills", plane="meta")
                edges += 1
    return edges


# ── оркестрация ──────────────────────────────────────────────────────────────
def derive_project_graph(env, config, project, providers=None):
    """Построить стор проекта ЗАНОВО из всех источников. Возвращает stats-dict."""
    if providers is None:
        providers = build_provider_index(env, config)
    pid = project["id"]
    sp = store_path(env, config, project)
    g = Graph(env, config, path=sp)
    g._loaded = True  # строим с нуля (идемпотентно, без устаревших рёбер)
    g.add_node(f"project:{pid}", "project", project=pid,
               name=project.get("name", pid), ptype=project.get("type", "unknown"))
    by_via = {
        "code": derive_code(g, project, config, providers),
        "doc": derive_doc(g, project, config),
        "override": derive_override(g, project, config),
        "skills": derive_skills(g, project),
    }
    g.save()
    s = g.stats()
    return {"id": pid, "nodes": s["nodes"], "edges": s["edges"], "by_via": by_via}


def derive_all(env, config):
    """Derive всех enabled-проектов + пересборка индекса. Возвращает список stats."""
    providers = build_provider_index(env, config)
    out = []
    for p in config.get("projects") or []:
        if p.get("enabled", True):
            out.append(derive_project_graph(env, config, p, providers))
    rebuild_index(env, config)
    return out
