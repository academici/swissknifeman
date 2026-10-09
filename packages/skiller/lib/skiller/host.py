"""Host configuration: the single neutral entry point for host-repository knowledge.

A host repository may place `configs/skiller-host.json` (format: schema/host.schema.json,
`urn:skiller:host:v1`) at its root to enable host functions: sibling plugin directories,
default command plugins, version files, machine plugins, external commands and so on.
The host is discovered from where Skiller is installed (`package_root`), never from the
target project, so consumers of a hub install see the hub's host. No config means an
empty host: every host function is off (standalone); that is neither an error nor a
warning. Validation is closed and stdlib-only, mirroring the schema: an unknown key,
a wrong type, an absolute path or `..` stops with `HOST_CONFIG_INVALID: <field>`."""
import functools
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from aicore.util.repo import find_repo_root
from aicore.util.term import die

HOST_CONFIG_ENV = "SKILLER_HOST_CONFIG"
HOST_CONFIG_PATH = "configs/skiller-host.json"
HOST_CONFIG_INVALID = "HOST_CONFIG_INVALID"
SCHEMA_VERSION = 1

# Closed key sets per object; "" is the document root. test_host keeps them equal to
# the published schema (properties / required) — change both together.
OBJECT_KEYS = {
    "": ("schema_version", "plugin_dirs", "default_command_plugins", "version_files",
         "machine_plugins", "runtime_projection_plugins", "codex_link_roots",
         "legacy_runtime_links", "commands", "mcp_servers", "bootstrap"),
    "version_files": ("path", "key"),
    "machine_plugins": ("name", "path", "holds"),
    "legacy_runtime_links": ("link", "plugin", "source"),
    "commands": ("argv", "env_override", "install_hint"),
    "mcp_servers": ("tools", "instructions_tokens"),
}
REQUIRED_KEYS = {
    "": ("schema_version",),
    "version_files": ("path", "key"),
    "machine_plugins": ("name", "path"),
    "legacy_runtime_links": ("link", "plugin", "source"),
    "commands": ("argv",),
}
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _empty_mapping():
    return MappingProxyType({})


@dataclass(frozen=True)
class VersionFile:
    path: str
    key: str


@dataclass(frozen=True)
class MachinePlugin:
    name: str
    path: str
    holds: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeLink:
    link: str
    plugin: str
    source: str


@dataclass(frozen=True)
class HostCommand:
    argv: tuple[str, ...]
    env_override: str | None = None
    install_hint: str | None = None


@dataclass(frozen=True)
class McpServer:
    tools: int | None = None
    instructions_tokens: int | None = None


@dataclass(frozen=True)
class Host:
    """Validated host config. Relative paths resolve against `root` (the host repo root);
    `root`/`source` are None for the empty host."""
    root: Path | None = None
    source: Path | None = None
    plugin_dirs: tuple[str, ...] = ()
    default_command_plugins: tuple[str, ...] = ()
    version_files: tuple[VersionFile, ...] = ()
    machine_plugins: MappingProxyType = field(default_factory=_empty_mapping)
    runtime_projection_plugins: tuple[str, ...] = ()
    codex_link_roots: tuple[str, ...] = ()
    legacy_runtime_links: tuple[RuntimeLink, ...] = ()
    commands: MappingProxyType = field(default_factory=_empty_mapping)
    mcp_servers: MappingProxyType = field(default_factory=_empty_mapping)
    bootstrap: str | None = None

    @classmethod
    def empty(cls):
        return cls()


def _invalid(where):
    die(f"{HOST_CONFIG_INVALID}: {where}")


def _object(value, where, kind):
    if not isinstance(value, dict):
        _invalid(where or "root")
    prefix = f"{where}." if where else ""
    for key in value:
        if key not in OBJECT_KEYS[kind]:
            _invalid(prefix + str(key))
    for key in REQUIRED_KEYS.get(kind, ()):
        if key not in value:
            _invalid(prefix + key)
    return value


def _list(value, where):
    if not isinstance(value, list):
        _invalid(where)
    return value


def _mapping(value, where):
    if not isinstance(value, dict):
        _invalid(where)
    for key in value:
        if not NAME.match(key):
            _invalid(f"{where}.{key}")
    return value


def _string(value, where):
    if not isinstance(value, str) or not value:
        _invalid(where)
    return value


def _name(value, where):
    if not isinstance(value, str) or not NAME.match(value):
        _invalid(where)
    return value


def _relpath(value, where):
    """Repository-relative POSIX path (or glob): no absolute, `..`, `\\` or empty parts."""
    if (not isinstance(value, str) or not value or "\\" in value
            or PurePosixPath(value).is_absolute()
            or any(part in {"", ".."} for part in value.split("/"))):
        _invalid(where)
    return value


def _count(value, where):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _invalid(where)
    return value


def _names(data, key):
    return tuple(_name(item, f"{key}[{i}]") for i, item in enumerate(_list(data[key], key)))


def _relpaths(value, where):
    return tuple(_relpath(item, f"{where}[{i}]") for i, item in enumerate(_list(value, where)))


def _command(value, where):
    _object(value, where, "commands")
    argv = _list(value["argv"], f"{where}.argv")
    if not argv:
        _invalid(f"{where}.argv")
    for i, arg in enumerate(argv):
        _string(arg, f"{where}.argv[{i}]")
    if "/" in argv[0]:
        _relpath(argv[0], f"{where}.argv[0]")
    override = value.get("env_override")
    if override is not None and (not isinstance(override, str) or not ENV_NAME.match(override)):
        _invalid(f"{where}.env_override")
    hint = value.get("install_hint")
    if hint is not None:
        _string(hint, f"{where}.install_hint")
    return HostCommand(argv=tuple(argv), env_override=override, install_hint=hint)


def parse_host(data, root, source=None):
    """Validate a decoded host document and return a frozen `Host`."""
    _object(data, "", "")
    version = data["schema_version"]
    if isinstance(version, bool) or version != SCHEMA_VERSION:
        _invalid("schema_version")
    fields = {"root": root, "source": source}
    if "plugin_dirs" in data:
        fields["plugin_dirs"] = _relpaths(data["plugin_dirs"], "plugin_dirs")
    for key in ("default_command_plugins", "runtime_projection_plugins"):
        if key in data:
            fields[key] = _names(data, key)
    if "version_files" in data:
        rows = []
        for i, item in enumerate(_list(data["version_files"], "version_files")):
            where = f"version_files[{i}]"
            _object(item, where, "version_files")
            rows.append(VersionFile(path=_relpath(item["path"], f"{where}.path"),
                                    key=_string(item["key"], f"{where}.key")))
        fields["version_files"] = tuple(rows)
    if "machine_plugins" in data:
        machines = {}
        for machine, items in _mapping(data["machine_plugins"], "machine_plugins").items():
            rows = []
            for i, item in enumerate(_list(items, f"machine_plugins.{machine}")):
                where = f"machine_plugins.{machine}[{i}]"
                _object(item, where, "machine_plugins")
                rows.append(MachinePlugin(
                    name=_name(item["name"], f"{where}.name"),
                    path=_relpath(item["path"], f"{where}.path"),
                    holds=_relpaths(item.get("holds", []), f"{where}.holds")))
            machines[machine] = tuple(rows)
        fields["machine_plugins"] = MappingProxyType(machines)
    if "codex_link_roots" in data:
        fields["codex_link_roots"] = _relpaths(data["codex_link_roots"], "codex_link_roots")
    if "legacy_runtime_links" in data:
        rows = []
        for i, item in enumerate(_list(data["legacy_runtime_links"], "legacy_runtime_links")):
            where = f"legacy_runtime_links[{i}]"
            _object(item, where, "legacy_runtime_links")
            rows.append(RuntimeLink(link=_relpath(item["link"], f"{where}.link"),
                                    plugin=_name(item["plugin"], f"{where}.plugin"),
                                    source=_relpath(item["source"], f"{where}.source")))
        fields["legacy_runtime_links"] = tuple(rows)
    if "commands" in data:
        fields["commands"] = MappingProxyType({
            name: _command(value, f"commands.{name}")
            for name, value in _mapping(data["commands"], "commands").items()})
    if "mcp_servers" in data:
        servers = {}
        for name, value in _mapping(data["mcp_servers"], "mcp_servers").items():
            where = f"mcp_servers.{name}"
            _object(value, where, "mcp_servers")
            servers[name] = McpServer(
                tools=_count(value.get("tools"), f"{where}.tools"),
                instructions_tokens=_count(value.get("instructions_tokens"),
                                           f"{where}.instructions_tokens"))
        fields["mcp_servers"] = MappingProxyType(servers)
    if "bootstrap" in data:
        fields["bootstrap"] = _relpath(data["bootstrap"], "bootstrap")
    return Host(**fields)


@functools.lru_cache(maxsize=None)
def _read_host(source, root):
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _invalid(f"json ({source}: {exc})")
    return parse_host(data, root, source)


def clear_host_cache():
    """Forget loaded hosts (tests, or a process that rewrites the config)."""
    _read_host.cache_clear()


def load_host(package_root):
    """Discover the host of a Skiller install: `$SKILLER_HOST_CONFIG`, else the repo root's
    `configs/skiller-host.json` when Skiller is nested in that repo, else `Host.empty()`."""
    package_root = Path(package_root).resolve()
    repo_root = find_repo_root(package_root)
    override = os.environ.get(HOST_CONFIG_ENV)
    if override:
        source = Path(override)
        if not source.is_absolute():
            die(f"{HOST_CONFIG_ENV}: must be an absolute path: {override}")
        if not source.is_file():
            die(f"{HOST_CONFIG_ENV}: not found: {override}")
        return _read_host(source.resolve(), repo_root or package_root)
    if repo_root is None or repo_root == package_root:
        return Host.empty()
    source = repo_root / HOST_CONFIG_PATH
    if not source.is_file():
        return Host.empty()
    return _read_host(source.resolve(), repo_root)


def host_command(source, name):
    """argv of host command `name` with argv[0] resolved, or None (no host, no command,
    binary missing). `source` is an `Env` (its root is the Skiller package root) or the
    package root. argv[0]: `env_override` value when set (must exist), else a path
    relative to the host root when it contains `/`, else a PATH lookup."""
    # Path has its own `.root` ("/"), so only non-path sources are treated as an Env.
    package_root = source if isinstance(source, (str, os.PathLike)) else source.root
    host = load_host(package_root)
    command = host.commands.get(name)
    if command is None:
        return None
    first, rest = command.argv[0], list(command.argv[1:])
    override = os.environ.get(command.env_override) if command.env_override else None
    if override:
        path = Path(os.path.expanduser(override))
        return [str(path), *rest] if path.exists() else None
    if "/" in first:
        path = host.root / first
        return [str(path), *rest] if path.exists() else None
    found = shutil.which(first)
    return [found, *rest] if found else None


def host_plugin_dirs(repo_root, package_root, host):
    """Sibling plugin directories: `plugin_dirs` glob matches holding
    `.claude-plugin/plugin.json`, sorted per pattern, deduplicated, except Skiller itself."""
    repo_root = Path(repo_root)
    own = Path(package_root).resolve()
    found, seen = [], set()
    for pattern in host.plugin_dirs:
        for candidate in sorted(repo_root.glob(pattern)):
            resolved = candidate.resolve()
            if (resolved in seen or resolved == own or not candidate.is_dir()
                    or not (candidate / ".claude-plugin" / "plugin.json").is_file()):
                continue
            seen.add(resolved)
            found.append(candidate)
    return found
