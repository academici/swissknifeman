"""Row mapping of the extensions PostgreSQL adapters (extensions §11; DDL ``0018``).

A row that does not fit its domain value is storage damage (``INTERNAL_ERROR``). Driver errors pass through
``translate_pg_error``, so the unique constraints of ``0018`` surface as ``ALREADY_EXISTS``.
"""

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.errors import translate_pg_error
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, NotFound
from skm.kernel.ids import PrincipalId, ResourceVersionId
from skm.kernel.json_types import JsonValue
from skm.modules.extensions.domain.compat import CompatVerdict
from skm.modules.extensions.domain.keys import PackId, PackVersionId, ResourceId, SemVer
from skm.modules.extensions.domain.kinds import ResourceKind
from skm.modules.extensions.domain.pack import (
    Pack,
    PackState,
    PackTrust,
    PackVersion,
    PackVersionSummary,
    parse_pack_manifest,
)
from skm.modules.extensions.domain.resource import (
    Resource,
    ResourceFile,
    ResourceVersion,
    ResourceVersionSummary,
    compat_report_from_json,
)

__all__ = [
    "Row",
    "not_found",
    "pack_from_row",
    "pack_summary_from_row",
    "pack_version_from_row",
    "resource_from_row",
    "resource_summary_from_row",
    "resource_version_from_row",
    "run",
]

type Row = tuple[object, ...]


def run[T](call: Callable[[], T]) -> T:
    try:
        return call()
    except psycopg.Error as exc:
        raise translate_pg_error(exc) from exc


def _damaged(table: str, ref: object, exc: Exception) -> InternalError:
    error = InternalError(
        ErrorCode.INTERNAL_ERROR,
        f"skm_extensions.{table} row is malformed",
        details={"table": f"skm_extensions.{table}", "id": str(ref)},
    )
    error.__cause__ = exc
    return error


def not_found(kind: str, ref: object) -> NotFound:
    return NotFound(ErrorCode.NOT_FOUND, f"{kind} not found", details={"kind": kind, "ref": str(ref)})


def pack_from_row(row: Row) -> Pack:
    try:
        return Pack(
            id=PackId(cast("UUID", row[0])),
            slug=cast("str", row[1]),
            title=cast("str", row[2]),
            publisher=cast("str", row[3]),
            trust=PackTrust(cast("str", row[4])),
            created_at=cast("datetime", row[5]),
        )
    except (TypeError, ValueError) as exc:
        raise _damaged("packs", row[0], exc) from exc


def pack_version_from_row(row: Row) -> PackVersion:
    try:
        return PackVersion(
            id=PackVersionId(cast("UUID", row[0])),
            pack_id=PackId(cast("UUID", row[1])),
            version=SemVer.parse(cast("str", row[2])),
            digest=cast("str", row[3]),
            manifest=parse_pack_manifest(cast("Mapping[str, object]", row[4])),
            state=PackState(cast("str", row[5])),
            origin=cast("str", row[6]),
            installed_at=cast("datetime", row[7]),
            installed_by=PrincipalId(cast("UUID", row[8])),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _damaged("pack_versions", row[0], exc) from exc


def pack_summary_from_row(row: Row) -> PackVersionSummary:
    try:
        return PackVersionSummary(
            version_id=PackVersionId(cast("UUID", row[0])),
            pack_id=PackId(cast("UUID", row[1])),
            slug=cast("str", row[2]),
            title=cast("str", row[3]),
            trust=PackTrust(cast("str", row[4])),
            version=SemVer.parse(cast("str", row[5])),
            digest=cast("str", row[6]),
            priority=cast("int", row[7]),
            state=PackState(cast("str", row[8])),
            installed_at=cast("datetime", row[9]),
        )
    except (TypeError, ValueError) as exc:
        raise _damaged("pack_versions", row[0], exc) from exc


def resource_from_row(row: Row) -> Resource:
    try:
        return Resource(
            id=ResourceId(cast("UUID", row[0])),
            kind=ResourceKind(cast("str", row[1])),
            key=cast("str", row[2]),
            first_pack_id=PackId(cast("UUID", row[3])),
            created_at=cast("datetime", row[4]),
        )
    except (TypeError, ValueError) as exc:
        raise _damaged("resources", row[0], exc) from exc


def resource_summary_from_row(row: Row) -> ResourceVersionSummary:
    try:
        return ResourceVersionSummary(
            id=ResourceVersionId(cast("UUID", row[0])),
            kind=ResourceKind(cast("str", row[1])),
            key=cast("str", row[2]),
            pack_version_id=PackVersionId(cast("UUID", row[3])),
            version=SemVer.parse(cast("str", row[4])),
            digest=cast("str", row[5]),
            verdict=CompatVerdict(cast("str", row[6])),
        )
    except (TypeError, ValueError) as exc:
        raise _damaged("resource_versions", row[0], exc) from exc


def resource_version_from_row(row: Row, files: tuple[Row, ...]) -> ResourceVersion:
    try:
        return ResourceVersion(
            id=ResourceVersionId(cast("UUID", row[0])),
            resource_id=ResourceId(cast("UUID", row[1])),
            kind=ResourceKind(cast("str", row[2])),
            key=cast("str", row[3]),
            pack_version_id=PackVersionId(cast("UUID", row[4])),
            version=SemVer.parse(cast("str", row[5])),
            digest=cast("str", row[6]),
            manifest=cast("Mapping[str, JsonValue]", row[7]),
            files=tuple(
                ResourceFile(
                    cast("str", item[0]), cast("int", item[1]), cast("str", item[2]), cast("str", item[3])
                )
                for item in files
            ),
            tokens_estimate=cast("int", row[8]),
            compat=compat_report_from_json(cast("Mapping[str, object]", row[9])),
            created_at=cast("datetime", row[10]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _damaged("resource_versions", row[0], exc) from exc
