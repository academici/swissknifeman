"""Read npm package declarations from a checkout."""

import json
from pathlib import Path

from skm.kernel.json_types import JsonObject

from .pyproject import declaration, invalid_manifest, manifest_files, table

__all__ = ["PackageJsonReader"]


def json_dependencies(
    root: Path, filename: str, ecosystem: str, sections: tuple[str, ...]
) -> tuple[JsonObject, ...]:
    records: list[JsonObject] = []
    for path in manifest_files(root, filename):
        relative = path.relative_to(root).as_posix()
        try:
            document = table(json.loads(path.read_text(encoding="utf-8")))
            if "name" in document:
                name = document["name"]
                if not isinstance(name, str):
                    raise ValueError
                records.append(declaration(name, document.get("version"), relative, ecosystem, "provided_by"))
            for section in sections:
                for name, version in table(document.get(section, {})).items():
                    if ecosystem == "composer" and "/" not in name:
                        continue  # Platform requirements (PHP, extensions, libraries) are not packages.
                    records.append(declaration(name, version, relative, ecosystem, "requires"))
        except (OSError, ValueError) as error:
            raise invalid_manifest(root, path) from error
    return tuple(records)


class PackageJsonReader:
    def dependencies(self, root: Path) -> tuple[JsonObject, ...]:
        return json_dependencies(
            root,
            "package.json",
            "npm",
            ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"),
        )
