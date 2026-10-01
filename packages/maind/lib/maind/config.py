"""Node config maind: config.json at the root of the monorepo (primary; legacy .maind.json
is picked up by the same resolver) + fallback on legacy .projects.json (brain).

Validation - on stdlib (without jsonschema): declarative type maps + difflib-tips,
as in swissknifeman/config.py. load_config returns (config, source) for compatibility;
Config.load(env) — wrapper over the same, encapsulates path/source/save and access to sections,
to change the config logic in one place. Config — subclass dict (old access
config["projects"] continues to work)."""
from __future__ import annotations

import copy
import difflib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from core import (ConfigSource, ProviderConfigCatalog, ProviderConfigLayer,
                  ResolvedProviderConfig,
                  load_provider_manifest, provider_config_catalog,
                  resolve_provider_config as resolve_shared_provider_config)
from .common import (detect_project_type, die, docs_visibility_for, sanitize,
                     warn)
from .constants import (CODE_GRAPH_DEFAULTS, DIGEST_BUDGET_CHARS, DIGEST_ITEM_MAX_CHARS,
                        DIGEST_SHARED_MAX, EMIT_EXAMPLE_DEFAULT, GRAPH_ADAPTERS,
                        HEARTBEAT_DEFAULT_MS, LEGACY_GRAPH_ADAPTERS, MAX_IDLE_DEFAULT_MS,
                        MEMORY_HTTP_PORT, MEMORY_STREAM_PORT, PERPLEXITY_WEB_DEFAULTS,
                        SERVICE_NAME)

# project.id hits scope-memory token `[[s:project:<id>]]` (memory.mark_scope) and in
# name namespace — therefore we limit it to a safe alphabet, otherwise special characters (']', space,
# line feed) break parsing scope when recall/forget and can replace someone else's scope.
PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# Names doc-default folders (when the project did not explicitly specify).
DEFAULT_DOCS_FOLDER_NAMES = ("docs", "docs-public")


def normalize_docs_folders(raw, default_visibility="private"):
    """Old flat list ['docs','docs-public'] And a new list of objects
    {id,vault,repo,visibility} → a single list of normalized objects. Mirror
    brain.folders.normalize_folders (brain — separate repo, cannot be imported).
    Status rule for bare name migration: 'docs-public' → public (old hardcode),
    otherwise → default_visibility (by project type). Duplicates by id collapse."""
    if not raw:
        raw = list(DEFAULT_DOCS_FOLDER_NAMES)
    out, seen = [], set()
    for item in raw:
        if isinstance(item, str):
            name = item.strip()
            vis = "public" if name == "docs-public" else (default_visibility or "private")
            fo = {"id": name, "vault": name, "repo": name, "visibility": vis}
        elif isinstance(item, dict):
            vault = (item.get("vault") or item.get("id") or "").strip()
            repo = (item.get("repo") or vault).strip()
            fid = (item.get("id") or vault).strip()
            vis = item.get("visibility")
            if vis not in ("public", "private"):
                vis = "public" if vault == "docs-public" else (default_visibility or "private")
            fo = {"id": fid, "vault": vault, "repo": repo, "visibility": vis}
        else:
            continue
        if fo["id"] in seen:
            continue
        seen.add(fo["id"])
        out.append(fo)
    return out


# Top keys .maind.json (except _-meta). Value - expected Python-type.
TOP_KEYS = {
    "node": dict,
    "memory": dict,
    "graph": dict,
    "code_graph": dict,
    "agents": dict,
    "projects": list,
    "namespaces": dict,
    "integrations": dict,
    "mcp": dict,
    "observability": dict,
    "providers": dict,
    "role_packs": dict,        # role → agent-pack (option C: project.roles → auto-delivery of the pack)
}

NODE_ROLES = {"primary", "secondary", "mirror"}
PROJECT_STATUSES = {"active", "archived", "planning"}
LOG_LEVELS = {"debug", "info", "warn", "error"}
# memory.role (ADR-0001, P4.2): standalone — today's regime (your daemon, default,
# back-compat) · host — this machine is held by the ONLY living demon · client — your
# no memory, goes to memory.url (raising the local daemon is PROHIBITED by the code, D27).
MEMORY_ROLES = {"standalone", "host", "client"}
LOOPBACK_HOSTNAMES = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def _is_loopback_url(url):
    """True, if host URL — loopback/wildcard (client with this url would be confused
    remote daemon with its own)."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host in LOOPBACK_HOSTNAMES


# ── validation ───────────────────────────────────────────────────────────────
def _check_section(cfg_file, section, value, types, enums=None):
    """Checks dict-section: known keys - by type; enum-keys - by set;
    unknown keys - warn (forward-compat, not fatal)."""
    enums = enums or {}
    if not isinstance(value, dict):
        die(f"{cfg_file}: section '{section}' must be an object")
    for k, v in value.items():
        if k.startswith("_"):
            continue
        if k in enums:
            if v not in enums[k]:
                die(f"{cfg_file}: {section}.{k} = '{v}' — valid: "
                    f"{', '.join(sorted(map(str, enums[k])))}")
        elif k in types:
            if not isinstance(v, types[k]):
                die(f"{cfg_file}: {section}.{k} must be of type {types[k].__name__}")
        else:
            warn(f"{cfg_file}: unknown key {section}.{k} (ignored)")


def validate_config(config, cfg_file):
    """Throws die on schema error. Unknown top keys are fatal (with hint);
    unknown attachments - warning."""
    if not isinstance(config, dict):
        die(f"{cfg_file}: config root must be an object")
    for key in config:
        if key.startswith("_"):
            continue
        if key not in TOP_KEYS:
            hint = difflib.get_close_matches(key, list(TOP_KEYS), n=1)
            suffix = f" — maybe '{hint[0]}'?" if hint else ""
            die(f"{cfg_file}: unknown key '{key}'{suffix}")
        if not isinstance(config[key], TOP_KEYS[key]):
            want = "array" if TOP_KEYS[key] is list else "object"
            die(f"{cfg_file}: '{key}' should be {want}")

    _check_section(cfg_file, "node", config.get("node", {}),
                   {"id": str, "name": str, "description": str},
                   {"role": NODE_ROLES})
    _check_section(cfg_file, "memory", config.get("memory", {}),
                   {"enabled": bool, "config_path": str, "http_port": int,
                    "stream_port": int, "data_dir": str, "url": str, "digest": dict,
                    "role": str, "secret_file": str, "bind_host": str},
                   {"role": MEMORY_ROLES})
    mem = config.get("memory") or {}
    if mem.get("role") == "client":
        url = mem.get("url")
        if not url:
            die(f"{cfg_file}: memory.role='client' requires memory.url (memory host address) — "
                f"client does not raise its daemon (D27)")
        if _is_loopback_url(url):
            die(f"{cfg_file}: memory.role='client' — memory.url='{url}' indicates loopback; "
                f"client must specify the memory HOST address, not its own daemon")
    _check_section(cfg_file, "graph", config.get("graph", {}),
                   {"enabled": bool, "adapter": str, "persist": bool,
                    "persist_path": str, "store_layout": str})
    # adapter: canonical {federation, disabled}; legacy (memory/graphify/networkx)
    # accepted with warning (is normalized to federation in merge_defaults).
    adapter = (config.get("graph") or {}).get("adapter")
    if adapter is not None and adapter not in GRAPH_ADAPTERS:
        if adapter in LEGACY_GRAPH_ADAPTERS:
            warn(f"{cfg_file}: graph.adapter='{adapter}' is deprecated → is used "
                 f"'federation' (single layout; graphify — separate MCP-layer)")
        else:
            die(f"{cfg_file}: graph.adapter = '{adapter}' — valid: "
                f"{', '.join(sorted(GRAPH_ADAPTERS))}")
    _check_section(cfg_file, "agents", config.get("agents", {}),
                   {"registry_enabled": bool, "heartbeat_interval_ms": int,
                    "max_idle_ms": int, "definitions": list})
    _check_section(cfg_file, "observability", config.get("observability", {}),
                   {"service_name": str, "metrics_enabled": bool,
                    "traces_enabled": bool, "session_start_health_hook": bool,
                    "session_log_retention_days": int, "serena_log_retention_days": int},
                   {"log_level": LOG_LEVELS})
    if "providers" in config and not isinstance(config["providers"].get("defaults"), dict):
        die(f"{cfg_file}: providers.defaults must be an object")
    if "providers" in config and set(config["providers"]) - {"defaults"}:
        die(f"{cfg_file}: providers contains an unknown key")

    registry = config.get("namespaces") or {}
    for i, proj in enumerate(config.get("projects", [])):
        if not isinstance(proj, dict):
            die(f"{cfg_file}: projects[{i}] must be an object")
        for fld in ("id", "name"):
            if fld in proj and not isinstance(proj[fld], str):
                die(f"{cfg_file}: projects[{i}].{fld} must be a string")
        pid = proj.get("id")
        if isinstance(pid, str) and not PROJECT_ID_RE.match(pid):
            die(f"{cfg_file}: projects[{i}].id = '{pid}' — invalid id; allowed "
                f"only [A-Za-z0-9._-] (id goes to scope-memory token and namespace)")
        if "status" in proj and proj["status"] not in PROJECT_STATUSES:
            die(f"{cfg_file}: projects[{i}].status = '{proj['status']}' — valid: "
                f"{', '.join(sorted(PROJECT_STATUSES))}")
        if "providers" in proj and not isinstance(proj["providers"], dict):
            die(f"{cfg_file}: projects[{i}].providers must be an object")
        if "namespaces" in proj:
            ns = proj["namespaces"]
            if not isinstance(ns, list) or not all(isinstance(x, str) for x in ns):
                die(f"{cfg_file}: projects[{i}].namespaces must be a list of strings")
            for n in ns:                       # registry set → typo hint
                if registry and n not in registry and n not in ("*", "default"):
                    warn(f"{cfg_file}: projects[{i}] refers to an unregistered "
                         f"namespace '{n}' (not in section namespaces)")
        if "memory_namespaces" in proj:
            memory_ns = proj["memory_namespaces"]
            if not isinstance(memory_ns, list) or not all(isinstance(x, str)
                                                           for x in memory_ns):
                die(f"{cfg_file}: projects[{i}].memory_namespaces must be a list of strings")
        if "code_providers" in proj:
            code_providers = proj["code_providers"]
            if not isinstance(code_providers, list) or not all(isinstance(x, str)
                                                                for x in code_providers):
                die(f"{cfg_file}: projects[{i}].code_providers must be a list of strings")
        if "docs_folders" in proj:
            df = proj["docs_folders"]
            if not isinstance(df, list):
                die(f"{cfg_file}: projects[{i}].docs_folders must be a list")
            for j, it in enumerate(df):
                if isinstance(it, str):
                    continue                   # flat shape (back-compat)
                if not isinstance(it, dict) or not (it.get("vault") or it.get("id")):
                    die(f"{cfg_file}: projects[{i}].docs_folders[{j}] — string or "
                        f"object with 'vault' (opt. repo/visibility/id)")
                vis = it.get("visibility")
                if vis is not None and vis not in ("public", "private"):
                    # forward-compat: don't dump the config, just warn
                    warn(f"{cfg_file}: projects[{i}].docs_folders[{j}].visibility="
                         f"'{vis}' — expected public|private (defaulted)")


# ── defaults ─────────────────────────────────────────────────────────────────
def merge_defaults(config):
    """Fills in mandatory defaults so that the calling code doesn't catch KeyError.
    Does not mutate the passed config (deep copy at the beginning) and does not divide nested
    objects with neither input nor module-level defaults."""
    config = copy.deepcopy(config)

    mem = config.get("memory") or {}
    mem.setdefault("enabled", True)
    mem.setdefault("role", "standalone")   # default back-compat: existing nodes do not change behavior
    mem.setdefault("http_port", MEMORY_HTTP_PORT)
    mem.setdefault("stream_port", MEMORY_STREAM_PORT)
    mem.setdefault("config_path", "config/memory/iii-config.yaml")
    mem.setdefault("data_dir", "./data")
    dg = mem.get("digest") or {}
    dg.setdefault("budget_chars", DIGEST_BUDGET_CHARS)
    dg.setdefault("item_max_chars", DIGEST_ITEM_MAX_CHARS)
    dg.setdefault("shared_max", DIGEST_SHARED_MAX)
    mem["digest"] = dg
    config["memory"] = mem

    gr = config.get("graph") or {}
    gr.setdefault("enabled", True)
    gr.setdefault("adapter", "federation")
    # legacy adapter → federation (single layout; the engine is always stdlib)
    if gr["adapter"] in LEGACY_GRAPH_ADAPTERS:
        gr["adapter"] = "federation"
    config["graph"] = gr

    # code_graph: code graph policy from the config on top fallback-defaults (top-level keys).
    # copy.deepcopy(v) — to lists/default dictionaries were not shared with CODE_GRAPH_DEFAULTS.
    cg = config.get("code_graph") or {}
    for k, v in CODE_GRAPH_DEFAULTS.items():
        if k not in cg:
            cg[k] = copy.deepcopy(v)
    config["code_graph"] = cg

    ag = config.get("agents") or {}
    ag.setdefault("registry_enabled", True)
    ag.setdefault("heartbeat_interval_ms", HEARTBEAT_DEFAULT_MS)
    ag.setdefault("max_idle_ms", MAX_IDLE_DEFAULT_MS)
    ag.setdefault("definitions", [])
    config["agents"] = ag

    obs = config.get("observability") or {}
    obs.setdefault("service_name", SERVICE_NAME)
    obs.setdefault("log_level", "info")
    obs.setdefault("metrics_enabled", True)
    obs.setdefault("traces_enabled", False)
    obs.setdefault("session_start_health_hook", False)
    config["observability"] = obs

    config["node"] = config.get("node") or {}
    config["projects"] = config.get("projects") or []
    config["namespaces"] = config.get("namespaces") or {}
    config["integrations"] = config.get("integrations") or {}
    mcp = config.get("mcp") or {}
    # perplexity_web — fallback defaults ONLY if the section is specified (otherwise we don’t inflate the config
    # to those who perplexity-web did not include; disabled-by-default via PERPLEXITY_WEB_DEFAULTS).
    if isinstance(mcp.get("perplexity_web"), dict):
        pw = mcp["perplexity_web"]
        for k, v in PERPLEXITY_WEB_DEFAULTS.items():
            pw.setdefault(k, v)
    mcp.setdefault("emit_example", EMIT_EXAMPLE_DEFAULT)  # default-on (P2.4), opt-out: false
    config["mcp"] = mcp
    return config


# ── brain .projects.json → maind (real diagram brain, not from doc'a) ─────────
def _infer_type(local_path):
    """Best-effort project type by markers - single detector core. Missing
    path → 'unknown' (sentinel maind; core always gives real id)."""
    if not local_path:
        return "unknown"
    p = Path(os.path.expanduser(local_path))
    if not p.is_dir():
        return "unknown"
    return detect_project_type(p)


def map_brain_project(bp):
    """Record brain .projects.json → project entry maind (superset).

    brain-diagram: {name, enabled, vault_path, repo (path to code!), folders}.
    Fields id/local_path/type from doc'and in brain are missing - synthesize."""
    name = bp.get("name", "")
    slug = sanitize(name)
    local_path = bp.get("repo")  # in brain repo = local code path
    return {
        "id": slug,
        "name": name,
        "local_path": local_path,
        "vault_path": bp.get("vault_path"),
        "repo": None,                       # GitHub slug owner/repo — not in brain-cache
        "type": _infer_type(local_path),
        "enabled": bp.get("enabled", True),
        # normalize into an object model; visibility default - by project type
        "docs_folders": normalize_docs_folders(
            bp.get("folders"), docs_visibility_for(_infer_type(local_path))),
        "memory_scope": f"project:{slug}" if slug else None,
        "agents": [],
        "skills": [],
        "tags": [],
        "namespaces": [],                   # maind-only; brain not a source namespace
        "status": "active",
        "dependencies": [],
    }


def load_brain_projects(path):
    """Reading brain .projects.json (file or directory with it) → list of projects maind."""
    path = Path(os.path.expanduser(path))
    if path.is_dir():
        path = path / ".projects.json"
    if not path.is_file():
        die(f"not found brain .projects.json: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{path}: broken JSON: {e}")
    return [map_brain_project(bp) for bp in data.get("projects", [])]


# ── priority loading ──────────────────────────────────────────────────
def load_config(env):
    """Returns (config, source). Priority: config.json (root monorepo;
    linked-worktree config.json (read-only, same Git common-dir only) → legacy
    .maind.json is picked up by the same resolver env.default_config) →
    legacy .projects.json (brain, read-only, with warning) → empty config."""
    primary = env.config_read_path
    if primary.is_file():
        try:
            config = json.loads(primary.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            die(f"{primary}: broken JSON: {e}")
        validate_config(config, primary)
        return merge_defaults(config), ("linked-worktree-config"
                                        if primary != env.default_config else primary.name)

    legacy = env.root / ".projects.json"
    if legacy.is_file():
        warn("config.json not found - reading legacy .projects.json (brain) in mode "
             "read-only; run `maind migrate from-brain .projects.json` for "
             "permanent configuration")
        config = {
            "projects": load_brain_projects(legacy),
            "integrations": {"brain": {"enabled": True, "projects_sync": True,
                                       "sync_direction": "import"}},
        }
        return merge_defaults(config), "brain-fallback"

    return merge_defaults({}), "empty"


# ── wrapper over the config ─────────────────────────────────────────────────────
class Config(dict):
    """Lightweight wrapper for the node config. Subclass dict — old access
    (`cfg["projects"]`, `cfg.get(...)`, `cfg.items()`) works without changes.
    Top: load/save, origin (path/source) and section accessors -
    single point where the config logic lives (file name resolution, validation, migration).

    Usage:
        cfg = Config.load(env)          # reads env.default_config (config.json)
        cfg.projects                    # list of projects (or [])
        cfg.project("corex")            # project record by id or None
        cfg.save(env)                   # atomic-write back
    """

    def __init__(self, data=None, *, source="empty", path=None):
        super().__init__(data or {})
        self.source = source        # origin: "config.json"|".maind.json"|"brain-fallback"|"empty"
        self.path = path            # Path, read from (None for empty/fallback)

    @classmethod
    def load(cls, env):
        """Read node config via common resolver (config.json at the root of the monorepo,
        with legacy-fallback). Returns Config with filled source/path."""
        data, source = load_config(env)
        path = env.config_read_path if source not in ("brain-fallback", "empty") else None
        return cls(data, source=source, path=path)

    def save(self, env):
        """Atomic-writing the config back (via single writer projects.write_config).
        Before writing - schema validation (Config — subclass dict, direct mutations outside could
        violate invariants): do not write something that is obviously corrupted state."""
        validate_config(self, str(self.path) if self.path else "in-memory")
        from .projects import write_config
        write_config(env, self)

    # ── section accessors (filtering logic/searches are kept here) ──────────────
    @property
    def projects(self):
        return list(self.get("projects") or [])

    def project(self, project_id):
        """Record project by id, or None."""
        for p in self.get("projects") or []:
            if p.get("id") == project_id:
                return p
        return None

    def provider_config_layers(self, project_id):
        return provider_config_layers(self, project_id)

    def resolve_provider_config(self, catalog, project_id, *, project_config=None,
                                operation=None):
        return resolve_provider_config(self, catalog, project_id,
                                       project_config=project_config, operation=operation)

    @property
    def namespaces(self):
        return self.get("namespaces") or {}

    @property
    def integrations(self):
        return self.get("integrations") or {}


def provider_config_layers(config, project_id):
    """Return maind-owned fleet layers without changing the loaded legacy carrier."""
    defaults = (config.get("providers") or {}).get("defaults")
    default_layer = None if defaults is None else ProviderConfigLayer(
        ConfigSource("fleet-defaults", "fleet-defaults:config", "config.json", "/providers/defaults"), defaults)
    matches = []
    for index, project in enumerate(config.get("projects") or []):
        if project.get("id") == project_id and "providers" in project:
            matches.append(ProviderConfigLayer(
                ConfigSource("fleet-project", f"fleet-project:{project_id}", "config.json",
                             f"/projects/{index}/providers"), project["providers"]))
    return default_layer, tuple(matches)


def resolve_provider_config(config, catalog: ProviderConfigCatalog | None, project_id, *,
                            project_config=None, operation=None) -> ResolvedProviderConfig:
    """Thin maind carrier adapter; fleet/project precedence is owned by core."""
    if catalog is None:
        manifest_path = Path(__file__).resolve().parents[4] / "configs/provider-capabilities.json"
        catalog = provider_config_catalog(load_provider_manifest(manifest_path))
    defaults, projects = provider_config_layers(config, project_id)
    project_layer = None if project_config is None else ProviderConfigLayer(
        ConfigSource("project", f"project:{project_id}", ".swissknife.json", "/providers"), project_config)
    return resolve_shared_provider_config(catalog=catalog, operation=operation, project=project_layer,
                                          fleet_project=projects, fleet_defaults=defaults)


def render_provider_diagnostic(diagnostic):
    return f"provider config: {diagnostic.code} ({diagnostic.path})"
