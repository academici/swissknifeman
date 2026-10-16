"""Project config (.swissknife.json), profiles and skill selection/plugins."""
from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from pathlib import Path

from aicore.provider.config import (
    ProviderConfigCatalog, ProviderConfigLayer, ResolvedProviderConfig,
    resolve_provider_config as resolve_shared_provider_config)
from aicore.provider.manifest import (
    default_manifest_path, load_provider_manifest, provider_config_catalog)
from aicore.provider.values import ConfigSource
from aicore.state import ProjectContextRequired, resolve_project
from aicore.util.project import detect_project_type

from aicore.content.skill import read_frontmatter_fields as parse_frontmatter_fields
from aicore.delivery.materialize import AGENT_DEFAULTS
from aicore.util.term import confirm, die, warn
from .host import load_host
from .module_skills import host_provided_buckets, module_skill_sources

# CORE-distribution policy: token-saving skills that swissknifeman puts in
# EVERY project by default (see deep_analysis §5–§6). Channels of different granularities:
#   connect (marketplace) — bucket-granular → CORE_BUCKETS;
# vendor (physical. copy)    — skill-granular → CORE_SKILLS + DEFAULT_EXCLUDE.
# DEFAULT_EXCLUDE removes skills that duplicate the hub's own memory tooling from auto-distribution
# (shared-memory ← agent-memory MCP) and hand tools (cross-project-coordinator).
# Disabled by flag --no-core y connect/vendor.
# CORE stores only the general execution discipline. Onboarding, search, GitHub review
# and response style are connected in detail; plan-protocol supplied runtime Task.
def _load_core_policy():
    """CORE-policy from configs/core-policy.json (declarative) with fallback to built-in defaults.
    Self-location via __file__ → runs on import-time (consumers budget/connect/vendor/registry
    take modular level constants). Standalone-safe, stdlib-only: no file/broken → defaults."""
    defaults = {
        "skills": ["general/context-economy", "general/anti-drift",
                   "general/session-handoff", "general/verify-claims"],
        "resident_budget_target": 750,
        "core_plugin": "core",
        "core_buckets": ["general", "oss-dev"],
        "default_exclude": ["shared-memory", "cross-project-coordinator"],
    }
    try:
        p = Path(__file__).resolve().parents[2] / "configs" / "core-policy.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for k in defaults:
                if k in data:
                    defaults[k] = data[k]
    except Exception:
        pass  # standalone/broken file → built-in defaults
    return defaults


_CORE_POLICY = _load_core_policy()

CORE_SKILLS = list(_CORE_POLICY["skills"])
# Supervised name marketplace-plugin (connect-channel), bearing EXACTLY CORE_SKILLS.
# «Smart connection»: instead of whole buckets general(19)+oss-dev(10) ≈ 1956 resident
# tokens in EVERY project connect pushes this lightweight plugin - savings even with the current
# composition. Exact number of skills/tokens - `len(CORE_SKILLS)` and `skiller budget
# --check-core` (non-hardcode snapshot in the comments: «7 ≈ 480» went rotten while growing
# CORE_SKILLS up to 8, see T-2 audit). Skills physically remain in their buckets (plugin
# refers to them by, without copies - marketplace-entry source:"./" + explicit skills[]).
# See The registry.py.
CORE_PLUGIN = _CORE_POLICY["core_plugin"]
# RESIDENT target ceiling (⊕ tier-0) budget CORE_SKILLS: name+description each CORE-skill
# is loaded into EVERY request (permanent tax). `skiller budget --check-core` is verified by the actual resident
# with this target - a gate against silent kernel growth (added a skill to CORE → inflated by resident → signal).
RESIDENT_BUDGET_TARGET = _CORE_POLICY["resident_budget_target"]
# Buckets that I used to push CORE-policy connect in full (is now easy CORE_PLUGIN).
# Saved for back-compat/migrations: connect sees them in settings onboarded projects and
# prompts to remove (otherwise dual boot). Vendor-channel is still taking CORE_SKILLS file by file.
CORE_BUCKETS = list(_CORE_POLICY["core_buckets"])
# Command plugins (NOT skill buckets), which connect is included in EVERY project by default.
# The host repository names them (host config `default_command_plugins`); an empty host has none.
# Like CORE_PLUGIN: are declared in marketplace and are silently skipped on the old marketplace / in the test registry
# (there marketplace.json = {}). Codex publishes commands as skills, so their descriptions
# are included in it listing budget. Disable point by point - enabledPlugins[...]=false
# (connect respects explicit false, as for buckets).
# Lazy, not import-time: a broken host config must not break `skiller --help`/`version`.
def default_command_plugins():
    """Command plugins from the host of this Skiller install (empty host -> [])."""
    return list(load_host(Path(__file__).resolve().parents[2]).default_command_plugins)


def known_command_plugins():
    """Plugin names accepted beside skill buckets: CORE_PLUGIN and the host command plugins."""
    return {CORE_PLUGIN, *default_command_plugins()}


DEFAULT_EXCLUDE = list(_CORE_POLICY["default_exclude"])
# Minimum safe set for UNRECOGNIZED project type (autodetect → standalone).
# DO NOT expand `["*"]` (= all buckets) default is «soulless dump of everything». Explicit
# `--profile standalone` («put everything») remains available; auto-fallback puts only the core.
# == CORE_BUCKETS (channel-independent consistency): the host-provided bucket `system` carries
# shared-memory and cross-project-coordinator — exactly those hub duplicates, what CORE-politics
# drives through DEFAULT_EXCLUDE. Fallback should not retract them back, so it matches CORE_BUCKETS.
MINIMAL_BUCKETS = list(CORE_BUCKETS)


def core_skill_tuples(env, exclude):
    """CORE_SKILLS → [(bucket, rel, dir, fm_name)]; skips excluded and
    missing. The tuple format is the same as vendor.collect_skills."""
    out = []
    for path in CORE_SKILLS:
        bucket, _, rel = path.partition("/")
        d = env.root / "skills" / bucket / rel
        md = d / "SKILL.md"
        if not md.is_file():
            continue
        fm_name = parse_frontmatter_fields(md)["name"]
        if {fm_name, d.name, path} & exclude:
            continue
        out.append((bucket, rel, d, fm_name))
    return out


# --- typed media .swissknife.json --------------------------------
@dataclass(frozen=True, eq=False)
class ProjectConfig(Mapping):
    """Project config `.swissknife.json` as object: typed access instead
    naked `dict` (audit `audits/skm.md` §4, plan).

    **The only carrier of the list of keys.** Previously, the keys lived in three places
    (`CONFIG_KEYS` in `common.py`, `schema/swissknife.schema.json`, code); fields of this
    object would become the fourth, so `CONFIG_KEYS` is now OUTPUT from here -
    `metadata["json_type"]` of each field is carried by the Python-type which `isinstance`
    validates the value (tuple = multi-type, in schema `oneOf`). Both gates are synchronized
    (`skiller doctor` and `tests/test_schema.py`) read derivative `CONFIG_KEYS`
    and are not corrected.

    **Why NOT subclass `dict`** (unlike dict-based config wrappers elsewhere, config wrappers
    NODE): subclass leaves mutation open (`cfg["agent"] = …`) and depreciates
    typing - the attribute and the key would separate silently. Here `frozen=True` plus
    read-only Mapping-projection onto `raw`: old access (`cfg.get("agent")`,
    `cfg["agent"]`, `if cfg:`) continues to work byte-for-byte for consumers,
    have not yet been translated into attributes, but no one has a record.

    `raw` — ORIGINAL dictionary as is (provider branch, `_`/`$`-keys, back-compat
    files from the fleet repositories): normalization/there is no copy, otherwise the object would become
    second source of truth about the contents of the file.
    """

    project_type: str = field(default="", metadata={"json_type": str})
    buckets: list = field(default_factory=list, metadata={"json_type": list})
    # Exact marketplace plugin set; `core`/`planner` can be declared explicitly
    # for projects that intentionally need no profile buckets.
    plugins: list = field(default_factory=list, metadata={"json_type": list})
    exclude: list = field(default_factory=list, metadata={"json_type": list})
    presets: list = field(default_factory=list, metadata={"json_type": list})
    skills_path: str = field(default="", metadata={"json_type": str})
    agent: str = field(default="", metadata={"json_type": str})
    # None ≠ {}: provider branch distinguishes «no key» (layer does not start) from
    # «there is an empty layer» — exactly what I did config.get("providers").
    providers: dict | None = field(default=None, metadata={"json_type": dict})
    # String (path, back-compat memory-hook) OR object {path, sync?} — multi-type
    # leaves for CONFIG_KEYS tuple and into the schema as oneOf (see common.CONFIG_KEYS).
    memory_brain: str | dict | None = field(default=None, metadata={"json_type": (str, dict)})
    coordinator_ignore: list = field(default_factory=list, metadata={"json_type": list})
    shape: str = field(default="", metadata={"json_type": str})
    stacks: list = field(default_factory=list, metadata={"json_type": list})
    skills_map: dict = field(default_factory=dict, metadata={"json_type": dict})
    policy_profile: str = field(default="", metadata={"json_type": str})
    # Not a config key: without "json_type" in metadata field does not fall into CONFIG_KEYS.
    raw: Mapping = field(default_factory=dict, repr=False)
    # Where the skiller keys came from ("config": [skiller]; "legacy": .swissknife.json); names the file in labels.
    source: str = field(default="legacy", repr=False, compare=False)

    # Mapping-projection onto raw — read-only back-compat surface for consumers
    # (and tests), transmitting/reading the config with a dictionary. Values are taken from raw, and not
    # from the fields: `.get("x")` must return exactly what is in the file.
    def __getitem__(self, key):
        return self.raw[key]

    def __iter__(self):
        return iter(self.raw)

    def __len__(self):
        return len(self.raw)

    @classmethod
    def from_raw(cls, data, source="legacy"):
        """Collect an object from what you read JSON WITHOUT validation (does it
        `validate_config` before assembly) and without normalizing values."""
        known = {f.name: f for f in fields(cls) if "json_type" in f.metadata}
        return cls(raw=data, source=source, **{name: data[name] for name in known if name in data})

    @classmethod
    def coerce(cls, config):
        """`ProjectConfig` → as is; dictionary (legacy call, test, branch without file)
        → typed object. Normalization point for functions that are historically
        took `dict` and must continue to take it."""
        if isinstance(config, cls):
            return config
        return cls.from_raw(config or {})

    @classmethod
    def load(cls, env, target):
        """Read the skiller settings of a project: `[skiller]` in `.swissknifeman/config.toml`, else the
        legacy `.swissknife.json` (same messages `die`, same order of checks, the empty config in the
        absence of both as the previous `load_config`).

        `raw` is the content of `.swissknife.json` (keys of other modules such as `providers` and
        `memory_brain` stay in it) with the skiller keys replaced by the keys that were set in the
        effective settings, so `cfg.get("buckets")` is absent when no layer set it. Legacy skiller keys
        that `config.toml` overrides as a whole are dropped from `raw`."""
        from . import settings
        loaded = settings.load(target, env=env)
        if loaded.legacy is None and loaded.source == "none":
            return cls()
        raw = {key: value for key, value in (loaded.legacy or {}).items()
               if key not in settings.SKILLER_KEYS or loaded.source == "legacy"}
        raw.update(loaded.selection())
        return cls.from_raw(raw, source="config" if loaded.source == "config" else "legacy")


# Derived from fields ProjectConfig: one bearer name, the value is collected.
# Re-exported as `skiller.common.CONFIG_KEYS` — historic house named after
# it is taken by both gates in synchronization with the circuit and documentation.
CONFIG_KEYS = {f.name: f.metadata["json_type"]
               for f in fields(ProjectConfig) if "json_type" in f.metadata}


def _type_label(pytype):
    """A human-readable label of the expected type for the error message. Tuple of types
    (e.g. memory_brain = (str, dict)) → «string or object»."""
    names = {str: "string", list: "list of strings", dict: "object",
             int: "integer", bool: "boolean"}
    if isinstance(pytype, tuple):
        return " or ".join(names.get(t, t.__name__) for t in pytype)
    return names.get(pytype, pytype.__name__)


def validate_config(env, config, cfg_file):
    import difflib
    profile_names = sorted(p.stem for p in (env.root / "profiles").glob("*.json"))
    for key, value in config.items():
        if key.startswith(("_", "$")):  # _comment / $schema — DX, not validated
            continue
        if key not in CONFIG_KEYS:
            hint = difflib.get_close_matches(key, CONFIG_KEYS, n=1)
            suffix = f" — did you mean '{hint[0]}'?" if hint else ""
            die(f"{cfg_file}: unknown key '{key}'{suffix}")
        if not isinstance(value, CONFIG_KEYS[key]):
            die(f"{cfg_file}: '{key}' must be a {_type_label(CONFIG_KEYS[key])}")
        if CONFIG_KEYS[key] is list and not all(isinstance(v, str) for v in value):
            die(f"{cfg_file}: '{key}' must be a list of strings")
    # memory_brain-object: path required (lowercase form is just the way to go, back-compat).
    mb = config.get("memory_brain")
    if isinstance(mb, dict) and not (isinstance(mb.get("path"), str) and mb["path"]):
        die(f"{cfg_file}: 'memory_brain' object must have a non-empty 'path'")
    if config.get("project_type") and config["project_type"] not in profile_names:
        die(f"{cfg_file}: unknown project_type '{config['project_type']}' "
            f"(available: {', '.join(profile_names)})")
    if config.get("agent") and config["agent"] not in AGENT_DEFAULTS:
        die(f"{cfg_file}: unknown agent '{config['agent']}' "
            f"(available: {', '.join(AGENT_DEFAULTS)})")
    # Keys are declared in CONFIG_KEYS (are validated for back-compat .swissknife.json),
    # but are NOT readable by logic connect/vendor — we are not silent, otherwise the user will register
    # and will not understand why there is no effect. (project_type/buckets/exclude/agent/skills_path/
    # memory_brain — are actually consumed and are not included here.)
    _RESERVED = {
        "skills_map": "reserved but not yet implemented - ignored",
        "shape": "reserved for agent-packs, not yet implemented - ignored",
        "stacks": "reserved for agent-packs, not yet implemented - ignored",
        "coordinator_ignore": "legacy-key without consumer - ignored",
    }
    for _key, _msg in _RESERVED.items():
        if config.get(_key):
            warn(f"{cfg_file}: '{_key}' {_msg}")


def load_config(env, target):
    """Historical name of the factory (15 sites in the package + external tests) — now
    returns `ProjectConfig`, not naked `dict`."""
    return ProjectConfig.load(env, target)


def provider_config_layer(config, project_id="local"):
    """Return the project-owned provider layer, or ``None`` when it is absent."""
    value = ProjectConfig.coerce(config).providers
    if value is None:
        return None
    return ProviderConfigLayer(
        ConfigSource("project", f"project:{project_id}", ".swissknife.json", "/providers"),
        value,
    )


def resolve_provider_config(config, catalog: ProviderConfigCatalog, *, project_id="local",
                            operation=None, fleet_project=None, fleet_defaults=None) -> ResolvedProviderConfig:
    """Thin skiller carrier adapter; selection/delivery semantics stay unchanged."""
    return resolve_shared_provider_config(catalog=catalog, operation=operation,
                                          project=provider_config_layer(config, project_id),
                                          fleet_project=fleet_project,
                                          fleet_defaults=fleet_defaults)


def resolve_distribution_providers(config, *, project_id="local", manifest_path=None):
    """Resolve selected skill-distribution providers through the frozen P1 adapter."""
    manifest_path = Path(manifest_path) if manifest_path is not None else (
        default_manifest_path())
    catalog = provider_config_catalog(load_provider_manifest(manifest_path))
    return resolve_provider_config(config, catalog, project_id=project_id)


def render_provider_diagnostic(diagnostic):
    """Package-owned Russian text while preserving the shared diagnostic envelope."""
    return f"provider config: {diagnostic.code} ({diagnostic.path})"


def autodetect(target):
    """Project type (== profile name) — single detector core. Each returned id
    must have profiles/<id>.json (coverage gate in validate.sh)."""
    return detect_project_type(target)


def load_profile(env, name):
    f = env.root / "profiles" / f"{name}.json"
    if not f.exists():
        available = ", ".join(
            sorted(p.stem for p in (env.root / "profiles").glob("*.json")))
        die(f"unknown profile '{name}' (available: {available})")
    return json.loads(f.read_text(encoding="utf-8"))


def library_buckets(env):
    """Buckets that have a catalog under `skills/` (not the ones the host provides)."""
    return sorted(d.name for d in (env.root / "skills").iterdir() if d.is_dir())


def all_buckets(env):
    """Selectable bucket names: library catalogs plus the buckets the host provides."""
    return sorted({*library_buckets(env), *host_provided_buckets(env)})


def selectable_buckets(env):
    """Names accepted as a bucket by vendor, sync and budget: every bucket plus the host
    module plugins (a plugin name selects exactly that plugin's skills)."""
    return sorted({*all_buckets(env), *module_skill_sources(env)})


def _expand_presets_buckets(env, config):
    """Expand `presets[]` from .swissknife.json to the list of buckets (reusing
    skillset.resolve_presets — extends/cycle-detection once, without a duplicate).

    Channels .swissknife.json (connect + legacy vendor) — bucket-granular, so we take
    ONLY bucket-presets component; them skill-granular `include` doesn't make sense here
    (in connect is ignored, as is `exclude`). If the preset only carries `include` without
    `buckets` — we warn you so that the empty effect does not look like a silent bug.
    Lazy import: skillset will import config → on module-level would be a loop."""
    names = ProjectConfig.coerce(config).presets or []
    if not names:
        return []
    from .skillset import resolve_presets  # lazy: avoid cyclic import
    pre_buckets, pre_include, _skipped = resolve_presets(env, names)
    if pre_include and not pre_buckets:
        warn(f"{_where(config)}: presets contain only skill-granular 'include' without "
             "'buckets' — in bucket-granular channels (connect/legacy vendor) no effect; "
             "for skill-level use vendor sync ([skiller.sync] in .swissknifeman/config.toml)")
    return list(dict.fromkeys(pre_buckets))


def _where(config):
    """Name of the source of the selection keys, for labels: the legacy file or the `[skiller]` section."""
    return "[skiller]" if config.source == "config" else ".swissknife.json"


def resolve_selection(env, target, config, flag_profile, flag_items):
    """Shared precedence: flags > .swissknife.json > autodetect.
    Returns (items, profile_name, profile_source, source_label, include_meta).

    In the thread.swissknife.json `presets[]` unfold into buckets (via
    skillset.resolve_presets) and combined with explicit `buckets`, is then subtracted
    `exclude`: buckets = (resolve_presets(presets) ∪ buckets) − exclude. Formula
    symmetrical vendor sync (resolve_skillset), but at the bucket level (channels
    .swissknife.json bucket-granular). Accuracy precedence saved: presets
    only take effect when the selection comes from .swissknife.json (not from flags/profile)."""
    config = ProjectConfig.coerce(config)
    buckets = all_buckets(env)
    if flag_items:
        return flag_items, None, "items", "flags", False
    if flag_profile:
        prof = load_profile(env, flag_profile)
        items = buckets if prof["buckets"] == ["*"] else prof["buckets"]
        return items, flag_profile, "flag", "--profile", prof.get("include_meta", False)
    if config.plugins:
        return list(config.plugins), None, "config", f"{_where(config)} plugins", False
    preset_buckets = _expand_presets_buckets(env, config)
    if config.buckets or preset_buckets:
        # (presets ∪ buckets) − exclude. exclude in bucket-granular channels skill-level
        # (connect ignores him with NOTE), but at the level of bucket names we subtract correctly -
        # is symmetrical to the formula vendor sync; dedup keeps order (presets before buckets).
        merged = list(dict.fromkeys(preset_buckets + list(config.buckets or [])))
        excl = set(config.exclude or [])
        items = [b for b in merged if b not in excl]
        label = (f"{_where(config)} presets+buckets" if preset_buckets and config.buckets
                 else f"{_where(config)} presets" if preset_buckets
                 else f"{_where(config)} buckets")
        return items, None, "config", label, False
    if config.project_type:
        prof = load_profile(env, config.project_type)
        items = buckets if prof["buckets"] == ["*"] else prof["buckets"]
        return (items, config.project_type, "config",
                f"{_where(config)} project_type", prof.get("include_meta", False))
    name = autodetect(target)
    prof = load_profile(env, name)
    # Type not recognized (fallback profile standalone = `["*"]`) → DO NOT put everything in a row:
    # give the minimum kernel and source marker `autodetect-fallback`, so that the caller
    # (connect/vendor) warned and suggested specifying the profile explicitly. Explicit `--profile
    # standalone` doesn't fit here (is being processed by branch flag_profile above).
    if prof["buckets"] == ["*"]:
        items = [b for b in MINIMAL_BUCKETS if b in buckets]
        return items, name, "autodetect-fallback", "autodetect-fallback", False
    return prof["buckets"], name, "autodetect", "autodetect", prof.get("include_meta", False)


def resolve_profile_name(target, config, flag_profile):
    """Profile name in the same hierarchy as resolve_selection: --profile >
    .swissknife.json project_type > autodetect. None — if the choice is made explicit
    buckets (no profile)."""
    config = ProjectConfig.coerce(config)
    if flag_profile:
        return flag_profile
    if config.buckets:
        return None
    if config.project_type:
        return config.project_type
    return autodetect(target)


# --- project root discovery ----------------------------------------------------
PROJECT_MARKERS = ((".swissknifeman/config.toml", "file"), (".swissknife.json", "file"),
                   (".swissknifeman/config.json", "file"), (".claude", "dir"), (".git", "any"))


def find_project_root(env, start=None):
    """``(root, via)`` of the nearest dir upward holding one of PROJECT_MARKERS (``via`` is the marker), else
    ``(None, None)``. The search ends at the home directory; ``SKM_PROJECT_ROOT`` names the project outright. The
    walk is ``aicore.state.resolve_project`` with these markers."""
    try:
        context = resolve_project((start or Path.cwd()).resolve(), env=os.environ, home=env.home.resolve(),
                                  markers=PROJECT_MARKERS, stop_at_home=True)
    except ProjectContextRequired as error:
        die(str(error))
    if context is None:
        return None, None
    return context.root, {".claude": ".claude/"}.get(context.marker, context.marker or "SKM_PROJECT_ROOT")


def resolve_target(env, opts, allow_home_confirm=False):
    """--target wins; otherwise walk up from CWD. Refuses the registry repo."""
    if opts.get("target"):
        target = Path(os.path.expanduser(opts["target"])).resolve()
        if not target.is_dir():
            die(f"directory not found: {target}")
        via = "--target"
    else:
        target, via = find_project_root(env)
        if target is None:
            die("project root not found above CWD (was looking for .swissknifeman/config.toml, "
                ".swissknife.json, .claude/, .git). Go to project or create "
                ".swissknifeman/config.toml at its root.")
        if target == env.home.resolve() and allow_home_confirm:
            print("The project root was defined as the home directory.")
            if not confirm(f"Continue with {target}?"):
                die("canceled - go to project or specify --target")
    if target == env.root.resolve() and env.cmd in ("connect", "vendor", "update", "sync", "init"):
        die("you are inside the registry itself swissknifeman — go to "
            "consuming project")
    return target, via
