"""Skills carried by host modules: the host-provided bucket mechanism.

A library bucket marked `"provided_by": "host"` in `buckets.json` has no catalog under
`skills/`. The host maps it to plugins (`bucket_aliases` in the host config) and names the
sibling plugin directories (`plugin_dirs`); this module reads the skills those plugins declare
in their `.claude-plugin/plugin.json` and presents them in the same shapes the library
uses, so connect, vendor, sync, budget and status treat them like any other bucket.

The library never names a module: bucket names come from `buckets.json`, plugin names from
the host config and the plugin manifests. Without a host (standalone) every host bucket is
empty and expanding one only warns.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from aicore.content.skill import read_frontmatter_fields, skill_content_hash
from aicore.util.paths import is_within
from aicore.util.repo import find_repo_root
from aicore.util.term import die, warn
from .host import host_plugin_dirs, load_host

_WARNED = set()


def reset_warnings():
    """Forget which once-per-process warnings were already printed (tests)."""
    _WARNED.clear()


def _warn_once(message):
    if message not in _WARNED:
        _WARNED.add(message)
        warn(message)


@dataclass(frozen=True)
class ModuleSkill:
    """One skill of a host plugin. `plugin` plays the role of the bucket."""
    plugin: str
    rel: str
    name: str
    skill_dir: Path
    path: str
    requires: tuple[str, ...] = ()

    @property
    def key(self):
        return self.plugin if self.rel == "." else f"{self.plugin}/{self.rel}"


def _host_root(env):
    host = load_host(env.root)
    return host, (host.root or find_repo_root(env.root) or env.root)


def _declared_skill_dirs(package, declared):
    values = [declared] if isinstance(declared, str) else declared
    if not isinstance(values, list):
        return []
    found = []
    for value in values:
        if not isinstance(value, str) or not value.startswith("./"):
            continue
        path = package / value
        if not path.is_dir():
            _warn_once(f"host plugin '{package.name}': skills path '{value}' not found; skipped")
        elif not is_within(path, package):
            _warn_once(f"host plugin '{package.name}': skills path '{value}' is outside the "
                       "plugin; skipped")
        elif path not in found:
            found.append(path)
    return found


def module_skill_sources(env):
    """{plugin name: skills directories} of the host plugins that declare `skills`.

    Empty without a host. The key is the manifest `name` (the folder name when absent)."""
    host, root = _host_root(env)
    if not host.plugin_dirs:
        return {}
    sources = {}
    for package in host_plugin_dirs(root, env.root, host):
        try:
            manifest = json.loads((package / ".claude-plugin" / "plugin.json")
                                  .read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, dict) or "skills" not in manifest:
            continue
        name = manifest.get("name") or package.name
        dirs = _declared_skill_dirs(package, manifest["skills"])
        if not dirs:
            continue
        if name in sources:
            _warn_once(f"host plugin '{name}' is declared by more than one package; "
                       "the first one is used")
            continue
        sources[name] = tuple(dirs)
    return sources


def _relative_to_root(path, root):
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.resolve().relative_to(root.resolve()).as_posix()


def module_skills(env, plugins=None):
    """Skills of all (or the named) source plugins, sorted by `(plugin, rel)`."""
    sources = module_skill_sources(env)
    _host, root = _host_root(env)
    names = sorted(sources) if plugins is None else sorted(set(plugins) & set(sources))
    out = []
    for plugin in names:
        seen = set()
        for skills_dir in sources[plugin]:
            for skill_md in sorted(skills_dir.rglob("SKILL.md")):
                directory = skill_md.parent
                if not is_within(directory, skills_dir):
                    _warn_once(f"host plugin '{plugin}': skill outside the plugin skipped: "
                               f"{skill_md}")
                    continue
                rel = directory.relative_to(skills_dir).as_posix()
                if rel in seen:
                    continue
                seen.add(rel)
                fields = read_frontmatter_fields(skill_md)
                out.append(ModuleSkill(
                    plugin=plugin, rel=rel, name=fields["name"] or directory.name,
                    skill_dir=directory, path=_relative_to_root(skill_md, root),
                    requires=tuple(fields["requires"])))
    return sorted(out, key=lambda item: (item.plugin, item.rel))


def host_provided_buckets(env):
    """Bucket names the library declares as provided by the host (`provided_by: host`)."""
    meta_file = env.root / "buckets.json"
    if not meta_file.is_file():
        return frozenset()
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return frozenset()
    if not isinstance(meta, dict):
        return frozenset()
    return frozenset(name for name, data in meta.items()
                     if isinstance(data, dict) and data.get("provided_by") == "host")


def expand_bucket(env, name):
    """Plugins behind a bucket name.

    A host bucket gives the plugins of its `bucket_aliases` that exist as sources (a missing
    one is skipped with a warning); a source plugin name gives itself; anything else gives
    `()` - a library bucket is resolved by the caller."""
    if name in host_provided_buckets(env):
        aliases = load_host(env.root).bucket_aliases.get(name, ())
        sources = module_skill_sources(env)
        found = []
        for plugin in aliases:
            if plugin in sources:
                found.append(plugin)
            else:
                _warn_once(f"bucket '{name}': host plugin '{plugin}' not found; skipped")
        if not found and not aliases:
            _warn_once(f"bucket '{name}' is provided by the host; no host modules here; skipped")
        return tuple(found)
    if name in module_skill_sources(env):
        return (name,)
    return ()


def host_bucket_owners(env):
    """{plugin: host buckets that expand to it}, to match `<host bucket>/<rel>` spellings."""
    owners = {}
    for bucket, plugins in host_bucket_plugins(env).items():
        for plugin in plugins:
            owners.setdefault(plugin, []).append(bucket)
    return owners


def host_bucket_plugins(env):
    """{host bucket: plugins} for every bucket the library leaves to the host."""
    return {name: expand_bucket(env, name) for name in sorted(host_provided_buckets(env))}


def check_collisions(env):
    """A library bucket directory must not share a name with a host bucket or a source plugin."""
    skills = env.root / "skills"
    if not skills.is_dir():
        return
    taken = set(host_provided_buckets(env)) | set(module_skill_sources(env))
    for directory in sorted(skills.iterdir()):
        if directory.is_dir() and directory.name in taken:
            die(f"bucket name '{directory.name}' is both a library bucket and a host module "
                "plugin")


def source_relpath(env, path):
    """POSIX-free relative spelling of a skill source: against the library root when inside
    it, else against the host root (module skills)."""
    path = Path(path)
    try:
        return str(path.relative_to(env.root))
    except ValueError:
        _host, root = _host_root(env)
        return str(Path(_relative_to_root(path, root)))


def source_exists(env, source_path):
    """Whether a recorded skill source still exists under the library or the host root."""
    _host, root = _host_root(env)
    return (env.root / source_path).exists() or (root / source_path).exists()


def source_plugin_of(env, source_path):
    """Plugin whose skills directory holds the host-relative `source_path`, or None."""
    _host, root = _host_root(env)
    target = (root / source_path).resolve()
    for plugin, dirs in module_skill_sources(env).items():
        if any(is_within(target, directory) for directory in dirs):
            return plugin
    return None


def registry_entries(env, plugins=None):
    """Module skills in the shape of `skills.json` entries used by sync (`origin: host`)."""
    entries = []
    for item in module_skills(env, plugins):
        skill_md = item.skill_dir / "SKILL.md"
        entries.append({
            "name": item.name, "bucket": item.plugin,
            "rel": "" if item.rel == "." else item.rel, "path": item.path,
            "sha256": hashlib.sha256(skill_md.read_bytes()).hexdigest(),
            "content_sha256": skill_content_hash(item.skill_dir),
            "requires": list(item.requires), "skill_dir": item.skill_dir, "origin": "host",
        })
    return entries
