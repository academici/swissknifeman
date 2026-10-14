"""custom — user skills beside the library: `skiller.custom_dirs` (machine) and `<project>/.swissknifeman/skills`.

A custom directory has the layout of the library: `<bucket>/<folder>/SKILL.md` with an optional `selection.json`.
Layers in order of precedence: library < machine < project. A custom skill with the id of an earlier one overrides
it only when its `selection.replaces` names that id; otherwise the load fails with `EXTENSION_AMBIGUOUS`.
Notes (never errors): `OVERRIDE`, `NAME_COLLISION`, `TRIGGER_OVERLAP` (another id with the same triggers), `DEPRECATED_REPLACED`,
`DEPRECATED`."""
from pathlib import Path

from aicore.content.skill import read_frontmatter, skill_digest

from .selection import read_sidecar, registry_selection

PROJECT_SKILLS = Path(".swissknifeman") / "skills"
ORIGINS = ("library", "machine", "project")


class ExtensionAmbiguous(ValueError):
    """A custom skill shares an id with an earlier skill and does not declare `selection.replaces`."""


def entry_id(entry):
    """`bucket/folder` of a registry entry (library) or of a scanned custom entry."""
    if entry.get("id"):
        return entry["id"]
    parts = Path(entry["path"]).parts
    return f"{parts[1]}/{parts[2]}" if len(parts) >= 4 else f"{entry['bucket']}/{entry['name']}"


def scan(root, origin):
    """The skills under `root` (`<bucket>/<folder>/SKILL.md`) as registry-like entries with `origin` and `digest`."""
    entries = []
    for skill_md in sorted(Path(root).glob("*/*/SKILL.md")):
        skill_dir = skill_md.parent
        if skill_md.is_symlink() or skill_dir.is_symlink() or skill_dir.parent.is_symlink():
            continue  # a link could pull a file from outside the custom tree into the prompt
        bucket, folder = skill_dir.parent.name, skill_dir.name
        try:
            name = read_frontmatter(skill_md).get("name") or folder
            sidecar = read_sidecar(skill_dir)
        except (OSError, ValueError) as exc:
            raise ValueError(f"{skill_md}: {exc}") from None
        entry = {"id": f"{bucket}/{folder}", "name": str(name), "bucket": bucket, "path": str(skill_md.resolve()),
                 "skill_dir": str(skill_dir.resolve()), "origin": origin, "digest": skill_digest(skill_dir)}
        if sidecar is not None:
            entry["selection"] = registry_selection(sidecar)
        entries.append(entry)
    return entries


def discover(project, machine_dirs):
    """`[(origin, entries)]` for the machine directories and the project directory, in precedence order."""
    machine = []
    for directory in machine_dirs:
        machine.extend(scan(Path(directory).expanduser(), "machine"))
    return [("machine", machine), ("project", scan(Path(project) / PROJECT_SKILLS, "project"))]


def _triggers(entry):
    triggers = (entry.get("selection") or {}).get("triggers") or {}
    return {(kind, value) for kind, values in triggers.items() for value in values}


def merge(library, layers):
    """`(entries, notes)`: the library entries with the custom layers applied. `layers` is a list of layers in
    precedence order, each `(origin, entries)` or a plain list of scanned entries. Raises :class:`ExtensionAmbiguous`."""
    custom = []
    for layer in layers:
        custom.extend(layer[1] if isinstance(layer, tuple) else layer)
    table = {entry_id(e): dict(e, origin=e.get("origin", "library")) for e in library}
    notes = []
    for entry in custom:
        sid, selection = entry["id"], entry.get("selection") or {}
        if sid in table:
            if selection.get("replaces") != sid:
                raise ExtensionAmbiguous(
                    f"EXTENSION_AMBIGUOUS: {entry['origin']} skill {entry['path']} has the id {sid} of a "
                    f"{table[sid]['origin']} skill; set selection.replaces to \"{sid}\" to override it")
            if (table[sid].get("selection") or {}).get("decision") == "DEPRECATE":
                notes.append({"code": "DEPRECATED_REPLACED", "id": sid,
                              "detail": "the replaced skill is deprecated"})
            notes.append({"code": "OVERRIDE", "id": sid, "detail": f"{entry['origin']} replaces {table[sid]['origin']}"})
        else:
            clash = sorted(other for other, row in table.items() if row.get("name") == entry["name"])
            if clash:
                notes.append({"code": "NAME_COLLISION", "id": sid,
                              "detail": f"same name as {', '.join(clash)}; a lookup by name keeps the earlier skill, use the id"})
            overlap = sorted(other for other, row in table.items() if _triggers(entry) and _triggers(entry) == _triggers(row))
            if overlap:
                notes.append({"code": "TRIGGER_OVERLAP", "id": sid, "detail": "same triggers as " + ", ".join(overlap)})
        if selection.get("decision") == "DEPRECATE":
            notes.append({"code": "DEPRECATED", "id": sid, "detail": f"the {entry['origin']} skill is deprecated"})
        table[sid] = entry
    return list(table.values()), notes
