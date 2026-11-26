"""Read PEP 621 package declarations from a checkout."""

import re
import stat
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, ValidationFailed
from skm.kernel.json_types import JsonObject

__all__ = ["PyprojectReader"]

_IGNORED = frozenset({"vendor", "node_modules", ".git", "dist", "build"})
_REQUIREMENT = re.compile(r"([a-zA-Z0-9][-_.a-zA-Z0-9]*)(.*)")


def manifest_files(root: Path, filename: str) -> Iterator[Path]:
    def on_error(error: OSError) -> None:
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE, "Cannot scan checkout manifests"
        ) from error

    try:
        if not stat.S_ISDIR(root.lstat().st_mode):
            raise OSError("checkout is not a directory")
    except OSError as error:
        on_error(error)

    for directory, dirs, files in root.walk(on_error=on_error):
        dirs[:] = sorted(name for name in dirs if name not in _IGNORED)
        if filename in files:
            path = directory / filename
            if stat.S_ISREG(path.lstat().st_mode):
                yield path


def invalid_manifest(root: Path, path: Path) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        "Invalid package manifest",
        details={"path": path.relative_to(root).as_posix()},
    )


def table(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ValueError
    return cast("dict[str, object]", raw)


def declaration(package: str, version: object, path: str, ecosystem: str, relationship: str) -> JsonObject:
    if not package or not (isinstance(version, str) or version is None):
        raise ValueError
    return {
        "package": package,
        "version": version,
        "path": path,
        "ecosystem": ecosystem,
        "relationship": relationship,
    }


def _requirements(raw: object, path: str) -> Iterator[JsonObject]:
    if not isinstance(raw, list):
        raise ValueError
    for item in cast("list[object]", raw):
        match = _REQUIREMENT.fullmatch(item.strip()) if isinstance(item, str) else None
        if match is None:
            raise ValueError
        package = re.sub(r"[-_.]+", "-", match[1]).lower()
        yield declaration(package, match[2].strip() or None, path, "pypi", "requires")


class PyprojectReader:
    def __init__(self, parse: Callable[[str], dict[str, object]]) -> None:
        self._parse = parse

    def dependencies(self, root: Path) -> tuple[JsonObject, ...]:
        records: list[JsonObject] = []
        for path in manifest_files(root, "pyproject.toml"):
            relative = path.relative_to(root).as_posix()
            try:
                project = table(self._parse(path.read_text(encoding="utf-8")).get("project", {}))
                if "name" in project:
                    name = project["name"]
                    if not isinstance(name, str):
                        raise ValueError
                    records.append(
                        declaration(
                            re.sub(r"[-_.]+", "-", name).lower(),
                            project.get("version"),
                            relative,
                            "pypi",
                            "provided_by",
                        )
                    )
                records.extend(_requirements(project.get("dependencies", []), relative))
                for items in table(project.get("optional-dependencies", {})).values():
                    records.extend(_requirements(items, relative))
            except (OSError, ValueError) as error:
                raise invalid_manifest(root, path) from error
        return tuple(records)
