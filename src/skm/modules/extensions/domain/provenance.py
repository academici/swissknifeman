"""Provenance and compatibility-waiver value types for pack resources (extensions §4.9)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import cast

__all__ = [
    "CompatAcceptance",
    "Provenance",
    "ProvenanceSource",
    "UpstreamFile",
    "UpstreamStrategy",
    "parse_compat_accepted",
    "parse_provenance",
]


class ProvenanceSource(StrEnum):
    LOCAL = "local"
    UPSTREAM = "upstream"


class UpstreamStrategy(StrEnum):
    REPLACE = "replace"
    NOTIFY = "notify"
    FORK = "fork"
    MERGE = "merge"


@dataclass(frozen=True, slots=True)
class UpstreamFile:
    path: str
    url: str
    sha256: str
    fetched_at: date


@dataclass(frozen=True, slots=True)
class Provenance:
    source: ProvenanceSource
    repo: str | None = None
    strategy: UpstreamStrategy | None = None
    license: str | None = None
    upstream_sha: str | None = None
    files: tuple[UpstreamFile, ...] = ()
    audit_verdict: str | None = None
    audit_at: date | None = None


@dataclass(frozen=True, slots=True)
class CompatAcceptance:
    file: str
    checks: tuple[str, ...]
    reason: str


def _parse_date(val: object) -> date | None:
    if isinstance(val, date):
        return val
    if isinstance(val, str) and val:
        return date.fromisoformat(val)
    return None


def parse_provenance(data: Mapping[str, object] | None) -> Provenance:
    """Parse optional ``[provenance]`` table from a skill manifest."""
    if not data:
        return Provenance(source=ProvenanceSource.LOCAL)
    source = ProvenanceSource(str(data.get("source", "local")))
    strategy_raw = data.get("strategy")
    strategy = UpstreamStrategy(str(strategy_raw)) if isinstance(strategy_raw, str) else None
    raw_files = data.get("files")
    files: list[UpstreamFile] = []
    if isinstance(raw_files, Sequence) and not isinstance(raw_files, (str, bytes)):
        for raw_item in cast("Sequence[object]", raw_files):
            if isinstance(raw_item, Mapping):
                item = cast("Mapping[str, object]", raw_item)
                fetched = _parse_date(item.get("fetched_at")) or date(1970, 1, 1)
                files.append(
                    UpstreamFile(
                        path=str(item.get("path", "")),
                        url=str(item.get("url", "")),
                        sha256=str(item.get("sha256", "")),
                        fetched_at=fetched,
                    )
                )
    repo = data.get("repo")
    lic = data.get("license")
    sha = data.get("upstream_sha")
    verdict = data.get("audit_verdict")
    return Provenance(
        source=source,
        repo=str(repo) if isinstance(repo, str) else None,
        strategy=strategy,
        license=str(lic) if isinstance(lic, str) else None,
        upstream_sha=str(sha) if isinstance(sha, str) else None,
        files=tuple(files),
        audit_verdict=str(verdict) if isinstance(verdict, str) else None,
        audit_at=_parse_date(data.get("audit_at")),
    )


def parse_compat_accepted(data: Sequence[Mapping[str, object]] | None) -> tuple[CompatAcceptance, ...]:
    """Parse optional ``[[compat_accepted]]`` array of tables from a skill manifest."""
    if not data:
        return ()
    result: list[CompatAcceptance] = []
    for row in data:
        raw_checks = row.get("checks", ())
        checks = (
            tuple(str(c) for c in cast("Sequence[object]", raw_checks))
            if isinstance(raw_checks, Sequence) and not isinstance(raw_checks, (str, bytes))
            else ()
        )
        result.append(
            CompatAcceptance(
                file=str(row.get("file", "")),
                checks=checks,
                reason=str(row.get("reason", "")),
            )
        )
    return tuple(result)
