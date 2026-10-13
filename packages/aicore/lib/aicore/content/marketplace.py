"""The hub marketplace: the Claude index and the Codex index assembled from the ``unit.json`` of the modules.

Each module lists the plugins it ships in ``provides.plugins``: an entry with ``manifest`` (the ``plugin.json``
of one plugin), ``source`` (the plugin folder) or ``catalog`` (a ``plugin-catalog/v1`` file the module generates
for several plugins). :func:`assemble` turns them into the bytes of ``.claude-plugin/marketplace.json`` and
``.agents/plugins/marketplace.json`` of the hub; ``aicore marketplace build`` writes or checks them.

Entries are sorted by name; a repeated name is ``MARKETPLACE_DUPLICATE``. An entry of a module gets ``package``
(the module id). An entry is in the Codex index when its plugin folder holds ``.codex-plugin/plugin.json`` or
when a catalog entry has ``codex``. stdlib and aicore only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, NamedTuple, Optional, Sequence, TextIO

from ..config.units import unit_dirs
from ..util import schema as _schema
from ..util.io import atomic_write_text
from .publication import codex_marketplace_entry, manifest_bytes

CLAUDE_INDEX = ".claude-plugin/marketplace.json"
CODEX_INDEX = ".agents/plugins/marketplace.json"
UMBRELLA_CONFIG = "configs/umbrella.json"
_CATALOG_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schemas" / "plugin-catalog" / "v1"


class MarketplaceError(ValueError):
    """A refusal with a stable code; ``str()`` is ``<CODE>: <message>``."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class Unit(NamedTuple):
    """A module as the marketplace needs it: id, folder and the parsed ``unit.json``."""

    id: str
    root: Path
    doc: Dict[str, Any]


def discover(env: Optional[Mapping[str, str]] = None) -> Dict[str, Unit]:
    """Modules by id from the folders of ``SKM_UNITS_PATH`` (else the ``packages/`` of the hub); first one wins."""
    found: Dict[str, Unit] = {}
    for folder in unit_dirs(env):
        try:
            doc = json.loads((folder / "unit.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        unit_id = doc.get("id") if isinstance(doc, dict) else None
        if isinstance(unit_id, str) and unit_id:
            found.setdefault(unit_id, Unit(unit_id, folder, doc))
    return found


def _read_json(path: Path, code: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MarketplaceError(code, f"{path}: {exc}") from exc


def _hub_path(hub: Path, path: Path, unit_id: str) -> str:
    """``./``-prefixed path of ``path`` from the hub root; a path outside the hub is refused."""
    try:
        relative = path.resolve().relative_to(hub).as_posix()
    except ValueError:
        raise MarketplaceError("MARKETPLACE_SOURCE_OUTSIDE",
                               f"module {unit_id}: {path} is outside the hub {hub}") from None
    return "./" + relative if relative != "." else "./"


def _catalog_doc(unit: Unit, path: Path, supplied: Mapping[Path, bytes]) -> Dict[str, Any]:
    if path.resolve() in supplied:
        try:
            doc = json.loads(supplied[path.resolve()].decode("utf-8"))
        except ValueError as exc:
            raise MarketplaceError("MARKETPLACE_CATALOG_INVALID", f"{path}: {exc}") from exc
    else:
        doc = _read_json(path, "MARKETPLACE_CATALOG_MISSING")
    if _CATALOG_SCHEMA_DIR.is_dir():
        registry, kind = _schema.load_contract(_CATALOG_SCHEMA_DIR)
        issues = _schema.validate(doc, kind, registry)
        if issues:
            raise MarketplaceError("MARKETPLACE_CATALOG_INVALID",
                                   f"module {unit.id}: {path}: {issues[0].message}")
    return doc


def _plugin_json_entry(unit: Unit, name: str, folder: Path, hub: Path, entries: list, codex: list) -> None:
    manifest = folder / ".claude-plugin" / "plugin.json"
    data = _read_json(manifest, "MARKETPLACE_MANIFEST_MISSING")
    if not isinstance(data, dict) or data.get("name", name) != name:
        raise MarketplaceError("MARKETPLACE_NAME_MISMATCH",
                               f"module {unit.id}: {manifest} does not name the plugin {name!r}")
    source = _hub_path(hub, folder, unit.id)
    description = data.get("description", "")
    category = data.get("category", "ecosystem")
    tags = data.get("keywords", [])
    entries.append({"name": name, "source": source, "description": description,
                    "category": category, "tags": tags, "package": unit.id})
    if (folder / ".codex-plugin" / "plugin.json").is_file():
        codex.append(codex_marketplace_entry(name, source, description, {"category": category, "tags": tags}))


def _catalog_entries(unit: Unit, doc: Mapping[str, Any], hub: Path, entries: list, codex: list) -> None:
    for item in doc["plugins"]:
        if item["source"] == "./":
            source = "./"
        else:
            source = _hub_path(hub, unit.root / item["source"], unit.id)
        entry: Dict[str, Any] = {"name": item["name"], "source": source}
        if "skills" in item:
            entry["skills"] = [_hub_path(hub, unit.root / skill, unit.id) for skill in item["skills"]]
        entry.update(description=item["description"], category=item["category"],
                     tags=list(item["tags"]), package=unit.id)
        if "alias_of" in item:
            entry["alias_of"] = item["alias_of"]
        entries.append(entry)
        extra = item.get("codex")
        if extra is None:
            continue
        codex_source = _hub_path(hub, unit.root / extra["source"], unit.id) if "source" in extra else source
        if codex_source == "./":
            raise MarketplaceError("MARKETPLACE_CODEX_SOURCE",
                                   f"module {unit.id}: plugin {item['name']!r} needs codex.source")
        record = codex_marketplace_entry(
            item["name"], codex_source, extra.get("description", item["description"]),
            {"category": extra.get("category", item["category"]), "tags": extra.get("tags", item["tags"])})
        record["install_policy"] = extra["install_policy"]
        record["auth"] = extra["auth"]
        codex.append(record)


def _identity(hub: Path, docs: Sequence[Mapping[str, Any]], name, owner):
    """Marketplace name and owner: arguments, then ``configs/umbrella.json#marketplace``, then a catalog."""
    declared: Mapping[str, Any] = {}
    umbrella = hub / UMBRELLA_CONFIG
    if umbrella.is_file():
        value = _read_json(umbrella, "MARKETPLACE_IDENTITY_INVALID").get("marketplace")
        declared = value if isinstance(value, dict) else {}
    if not declared:
        declared = next((doc["marketplace"] for doc in docs if "marketplace" in doc), {})
    name = name or declared.get("name")
    owner = owner or declared.get("owner")
    if not name or not owner:
        raise MarketplaceError("MARKETPLACE_IDENTITY_MISSING",
                               "no marketplace name and owner: pass them, declare marketplace in "
                               f"{UMBRELLA_CONFIG} or in a plugin catalog")
    return name, dict(owner)


def assemble(units: Mapping[str, Any], hub_root, *, name: Optional[str] = None,
             owner: Optional[Mapping[str, str]] = None,
             catalogs: Optional[Mapping[Path, bytes]] = None) -> Dict[str, bytes]:
    """Bytes of the two hub indexes by path relative to ``hub_root``.

    ``units`` maps a module id to anything with ``id``, ``root`` and ``doc`` (``unit.json``). ``catalogs``
    supplies the bytes of catalog files that are not on disk yet (keys: the path of the file).
    """
    hub = Path(hub_root).resolve()
    supplied = {Path(path).resolve(): data for path, data in (catalogs or {}).items()}
    entries: List[Dict[str, Any]] = []
    codex: List[Dict[str, Any]] = []
    docs: List[Mapping[str, Any]] = []
    for unit_id in sorted(units):
        unit = units[unit_id]
        unit = Unit(unit.id, Path(unit.root), unit.doc)
        provides = unit.doc.get("provides")
        for plugin in (provides.get("plugins") if isinstance(provides, dict) else None) or []:
            if "catalog" in plugin:
                path = unit.root / plugin["catalog"]
                doc = _catalog_doc(unit, path, supplied)
                docs.append(doc)
                _catalog_entries(unit, doc, hub, entries, codex)
            elif "source" in plugin:
                _plugin_json_entry(unit, plugin["name"], unit.root / plugin["source"], hub, entries, codex)
            elif "manifest" in plugin:
                folder = (unit.root / plugin["manifest"]).parent.parent
                _plugin_json_entry(unit, plugin["name"], folder, hub, entries, codex)
    seen: Dict[str, str] = {}
    for entry in entries:
        if entry["name"] in seen:
            raise MarketplaceError("MARKETPLACE_DUPLICATE",
                                   f"plugin {entry['name']!r} is declared by {seen[entry['name']]} "
                                   f"and {entry['package']}")
        seen[entry["name"]] = entry["package"]
    market_name, market_owner = _identity(hub, docs, name, owner)
    return {
        CLAUDE_INDEX: manifest_bytes({"name": market_name, "owner": market_owner,
                                      "plugins": sorted(entries, key=lambda item: item["name"])}),
        CODEX_INDEX: manifest_bytes({"name": market_name,
                                     "plugins": sorted(codex, key=lambda item: str(item["name"]))}),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aicore marketplace",
                                     description="The hub marketplace assembled from unit.json.")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    build = commands.add_parser("build", help="write the Claude marketplace and the Codex index of the hub")
    build.add_argument("--hub", required=True, metavar="ROOT", help="hub root")
    build.add_argument("--check", action="store_true",
                       help="write nothing; exit 1 and list the files that differ")
    return parser


def main(argv: Sequence[str], *, env: Optional[Mapping[str, str]] = None, cwd: Optional[Path] = None,
         out: Optional[TextIO] = None, err: Optional[TextIO] = None) -> int:
    """``aicore marketplace build --hub ROOT [--check]``: exit 0 done, 1 refusal or drift, 2 usage."""
    out, err = out or sys.stdout, err or sys.stderr
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    hub = Path(args.hub)
    if not hub.is_absolute() and cwd is not None:
        hub = Path(cwd) / hub
    hub = hub.resolve()
    environment = dict(os.environ if env is None else env)
    environment.setdefault("SKM_UNITS_PATH", str(hub / "packages"))
    try:
        files = assemble(discover(environment), hub)
    except MarketplaceError as exc:
        err.write(f"aicore marketplace: {exc}\n")
        return 1
    if args.check:
        drift = []
        for relative, data in sorted(files.items()):
            try:
                same = (hub / relative).read_bytes() == data
            except OSError:
                same = False
            if not same:
                drift.append(relative)
        if drift:
            err.write("DRIFT: the marketplace differs from unit.json; run `aicore marketplace build --hub`:\n")
            for relative in drift:
                err.write(f"  - {relative}\n")
            return 1
        out.write("marketplace: up to date\n")
        return 0
    for relative, data in sorted(files.items()):
        atomic_write_text(hub / relative, data.decode("utf-8"))
        out.write(f"wrote {relative}\n")
    return 0
