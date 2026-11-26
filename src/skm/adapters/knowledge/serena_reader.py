"""Read a prebuilt Serena export without activating Serena or touching checkout configuration."""

import json
import stat
from collections.abc import Iterator, Sequence
from itertools import pairwise
from pathlib import Path, PurePosixPath
from typing import cast
from urllib.parse import urlsplit

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, PreconditionFailed, ValidationFailed
from skm.kernel.json_types import JsonObject
from skm.modules.knowledge.generated.settings import KnowledgeCodeGraphSettings
from skm.platform.jsonc.digest import digest

__all__ = ["SerenaCodeGraphReader"]


def _pin(argv: Sequence[str]) -> str:
    for option, source in pairwise(argv):
        if option == "--from" and source.startswith("git+"):
            url, at, ref = source.rpartition("@")
            try:
                pinned_path = urlsplit(url).path
            except ValueError:
                break
            if at and pinned_path and ref and not any(char.isspace() for char in ref):
                return ref
    raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Serena source must be pinned with @REF")


def _object(value: object) -> JsonObject:
    if not isinstance(value, dict):
        raise ValueError
    return cast("JsonObject", value)


def _records(value: object) -> list[JsonObject]:
    if not isinstance(value, list):
        raise ValueError
    return [_object(item) for item in cast("list[object]", value)]


def _relative_path(value: object) -> PurePosixPath:
    if not isinstance(value, str) or "\\" in value or "#" in value or "\x00" in value:
        raise ValueError
    path = PurePosixPath(value)
    if not path.parts or path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ValueError
    return path


def _ignored(path: PurePosixPath, patterns: Sequence[str]) -> bool:
    return any(part.match(pattern) for part in (path, *path.parents[:-1]) for pattern in patterns)


class SerenaCodeGraphReader:
    """The offline export stores ref, tool_schema, index metadata, symbols and references."""

    def __init__(self, settings: KnowledgeCodeGraphSettings | None = None) -> None:
        self._settings = settings

    def _configured(self) -> KnowledgeCodeGraphSettings:
        if self._settings is None:
            raise CapabilityUnavailable(ErrorCode.CAPABILITY_UNAVAILABLE, "Serena settings are required")
        return self._settings

    def read_symbols(self, root: Path) -> Iterator[JsonObject]:
        return iter(self.read_index(root, self._configured())[1])

    def read_references(self, root: Path) -> Iterator[JsonObject]:
        return iter(self.read_index(root, self._configured())[2])

    def read_index(
        self, root: Path | str, settings: KnowledgeCodeGraphSettings
    ) -> tuple[JsonObject, list[JsonObject], list[JsonObject]]:
        if not settings.enabled:
            raise PreconditionFailed(ErrorCode.MODULE_DISABLED, "The Serena code graph is disabled")
        ref = _pin(settings.argv)
        if ref != _pin(settings.index_argv):
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Serena reader and indexer pins differ")
        checkout = Path(root)
        directory = checkout / ".serena"
        path = directory / "graph.json"
        try:
            if (
                not stat.S_ISDIR(checkout.lstat().st_mode)
                or not stat.S_ISDIR(directory.lstat().st_mode)
                or not stat.S_ISREG(path.lstat().st_mode)
            ):
                raise OSError
            document = _object(json.loads(path.read_text(encoding="utf-8")))
        except OSError as error:
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE, "A readable .serena/graph.json export is required"
            ) from error
        except ValueError as error:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid Serena graph export") from error

        try:
            if document["ref"] != ref:
                raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Serena export @REF does not match")
            tool_schema = document["tool_schema"]
            if not isinstance(tool_schema, dict | list):
                raise ValueError
            if settings.serena_schema_pin and digest(tool_schema) != settings.serena_schema_pin:
                raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Serena tool schema digest does not match")
            index = _object(document["index"]).copy()
            symbols = _records(document["symbols"])
            references = _records(document["references"])
            excluded = {
                str(symbol["path"])
                for symbol in symbols
                if _ignored(_relative_path(symbol["path"]), settings.ignores)
            }
            symbols = [symbol for symbol in symbols if symbol["path"] not in excluded]
            kept_refs = [
                reference
                for reference in references
                if not any(
                    _ignored(_relative_path(_object(reference[end])["path"]), settings.ignores)
                    for end in ("src", "dst")
                )
            ]
            if excluded or len(kept_refs) != len(references):
                skipped = index.get("files_skipped", 0)
                limitations = index.get("limitations", [])
                if type(skipped) is not int or not isinstance(limitations, list):
                    raise ValueError
                index.update(
                    completeness="partial",
                    files_skipped=skipped + len(excluded),
                    limitations=[
                        *limitations,
                        {
                            "code": "generated_excluded",
                            "message": "Paths excluded by code graph settings",
                            "count": len(excluded) or None,
                        },
                    ],
                )
        except (KeyError, TypeError, ValueError) as error:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid Serena graph export") from error
        return index, symbols, kept_refs
