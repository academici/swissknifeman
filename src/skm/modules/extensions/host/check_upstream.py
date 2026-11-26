"""``extensions.host.check_upstream`` (extensions §9): compare recorded provenance with upstream over HTTPS.

Read-only and idempotent host operation: queries installed resources through ``ctx.client.ask(...)``, fetches
upstream files via ``UpstreamFetcher`` with explicit timeout and byte limits, and delegates digest comparison
to ``skm.modules.extensions.domain.upstream.compare_upstream``. Never mutates pack/resource state or writes
new versions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final, Protocol, cast
from uuid import UUID

from skm.kernel.errors import BackendUnavailable, NotFound, PreconditionFailed, SkmError
from skm.kernel.generated.defs import ScopeRefDto
from skm.kernel.module_manifest import HostOperationSpec
from skm.modules.access.public import WhoAmI, WhoAmIView
from skm.modules.extensions.domain.kinds import ResourceKind as DomainResourceKind
from skm.modules.extensions.domain.provenance import (
    Provenance,
    ProvenanceSource,
    parse_provenance,
)
from skm.modules.extensions.domain.upstream import compare_upstream
from skm.modules.extensions.generated.host import (
    CheckUpstreamReport,
    CheckUpstreamReportItemsItem,
    CheckUpstreamReportItemsItemFilesItem,
    CheckUpstreamRequest,
)
from skm.modules.extensions.generated.host import (
    ResourceKind as HostResourceKind,
)
from skm.modules.extensions.generated.queries import (
    GetResourceVersion,
    ListResources,
    ResolveResource,
)
from skm.modules.extensions.generated.queries import (
    ResourceKind as QueryResourceKind,
)
from skm.modules.extensions.generated.views import (
    ResolutionView,
    ResourcesView,
    ResourceVersionView,
)
from skm.modules.extensions.ports import UpstreamFetcher

if TYPE_CHECKING:
    from skm.application_bus.host import HostContext

__all__ = ["SPEC", "CheckUpstreamOperation", "run"]

_DEFAULT_TIMEOUT_SECONDS: Final = 20
_DEFAULT_MAX_BYTES: Final = 10 * 1024 * 1024
_SCHEMA_DEFAULT_ARCHIVE_BYTES: Final = 52_428_800


class CheckUpstreamOperation(Protocol):
    def __call__(
        self, ctx: HostContext, request: CheckUpstreamRequest | Mapping[str, object]
    ) -> CheckUpstreamReport: ...


def _extract_provenance(manifest: Mapping[str, object]) -> Provenance:
    nested = manifest.get("provenance")
    if isinstance(nested, Mapping):
        return parse_provenance(cast("Mapping[str, object]", nested))
    if "source" in manifest or "files" in manifest or "strategy" in manifest:
        return parse_provenance(manifest)
    return Provenance(source=ProvenanceSource.LOCAL)


def _coerce_request(request: CheckUpstreamRequest | Mapping[str, object]) -> CheckUpstreamRequest:
    if isinstance(request, CheckUpstreamRequest):
        return request
    payload: dict[str, object] = {}
    pack = request.get("pack")
    if isinstance(pack, str) and pack:
        payload["pack"] = pack
    kind = request.get("kind")
    if isinstance(kind, DomainResourceKind | HostResourceKind | QueryResourceKind):
        payload["kind"] = kind.value
    elif isinstance(kind, str) and kind:
        payload["kind"] = kind
    key = request.get("key")
    if isinstance(key, str) and key:
        payload["key"] = key
    return CheckUpstreamRequest.from_json(payload)


def _safe_config_int(config: object, key: str) -> int | None:
    getter = getattr(config, "get", None)
    val: object = None
    if callable(getter):
        try:
            val = getter(key)
        except SkmError:
            val = None
    elif isinstance(config, Mapping):
        val = cast("Mapping[str, object]", config).get(key)
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    return None


def _read_limits(ctx: HostContext, request: CheckUpstreamRequest | Mapping[str, object]) -> tuple[int, int]:
    timeout_seconds = _DEFAULT_TIMEOUT_SECONDS
    max_bytes = _DEFAULT_MAX_BYTES
    config = getattr(ctx, "config", None)
    if config is not None:
        raw_timeout = _safe_config_int(config, "extensions.upstream.fetch_timeout_seconds")
        if raw_timeout is not None and raw_timeout > 0:
            timeout_seconds = raw_timeout
        raw_max = _safe_config_int(config, "extensions.install.max_archive_bytes")
        if raw_max is not None and 0 < raw_max != _SCHEMA_DEFAULT_ARCHIVE_BYTES:
            max_bytes = raw_max
    if isinstance(request, Mapping):
        req_timeout = request.get("timeout_seconds")
        if isinstance(req_timeout, int) and not isinstance(req_timeout, bool) and req_timeout > 0:
            timeout_seconds = req_timeout
        req_max = request.get("max_bytes")
        if isinstance(req_max, int) and not isinstance(req_max, bool) and req_max > 0:
            max_bytes = req_max
    return max_bytes, timeout_seconds


def _candidate_scopes(
    ctx: HostContext,
    request: CheckUpstreamRequest | Mapping[str, object],
) -> tuple[ScopeRefDto, ...]:
    if isinstance(request, Mapping) and "scope" in request:
        raw_scope = request["scope"]
        if isinstance(raw_scope, ScopeRefDto):
            return (raw_scope,)
        if isinstance(raw_scope, Mapping):
            return (ScopeRefDto.from_json(cast("Mapping[str, Any]", raw_scope)),)
    try:
        who = ctx.client.ask(WhoAmI())
    except SkmError:
        who = None
    if isinstance(who, Mapping):
        who = WhoAmIView.from_json(cast("Mapping[str, object]", who))
    if isinstance(who, WhoAmIView):
        seen: set[tuple[str, UUID]] = set()
        scopes: list[ScopeRefDto] = []
        ordered = sorted(
            who.memberships,
            key=lambda m: (0 if str(m.scope_kind) == "instance" else 1, str(m.scope_kind)),
        )
        for m in ordered:
            kind_str = str(m.scope_kind)
            sid = UUID(str(m.scope_id))
            if (kind_str, sid) not in seen:
                seen.add((kind_str, sid))
                scopes.append(ScopeRefDto(kind=cast("Any", kind_str), id=sid))
        return tuple(scopes)
    return ()


def _resolve_manifest(
    ctx: HostContext,
    entry: Any,
    scopes: Sequence[ScopeRefDto],
) -> Mapping[str, object]:
    raw_manifest = getattr(entry, "manifest", None)
    if isinstance(raw_manifest, Mapping):
        return cast("Mapping[str, object]", raw_manifest)

    rv_id = getattr(entry, "resource_version_id", None) or getattr(entry, "id", None)
    if isinstance(rv_id, UUID):
        rv = ctx.client.ask(GetResourceVersion(resource_version_id=rv_id, include_bodies=False))
        if isinstance(rv, ResourceVersionView):
            return rv.manifest
        rv_manifest = getattr(rv, "manifest", None)
        if isinstance(rv_manifest, Mapping):
            return cast("Mapping[str, object]", rv_manifest)

    kind_val = entry.kind.value if hasattr(entry.kind, "value") else str(entry.kind)
    query_kind = QueryResourceKind(kind_val)
    entry_ver = getattr(entry, "version", None)
    entry_digest = getattr(entry, "digest", None)

    for scope_dto in scopes:
        try:
            resolved = ctx.client.ask(ResolveResource(kind=query_kind, key=str(entry.key), scope=scope_dto))
        except (NotFound, PreconditionFailed, SkmError):
            resolved = None

        if isinstance(resolved, ResourceVersionView):
            ver_ok = entry_ver is None or str(resolved.version) == str(entry_ver)
            dig_ok = entry_digest is None or str(resolved.digest) == str(entry_digest)
            if ver_ok and dig_ok:
                return resolved.manifest
        elif isinstance(resolved, ResolutionView) and resolved.chosen is not None:
            chosen = resolved.chosen
            ver_ok = entry_ver is None or str(chosen.version) == str(entry_ver)
            dig_ok = entry_digest is None or str(chosen.digest) == str(entry_digest)
            if ver_ok and dig_ok:
                return chosen.manifest

    return {}


def _list_entries(ctx: HostContext, req: CheckUpstreamRequest) -> list[Any]:
    query_kind = QueryResourceKind(req.kind.value) if req.kind is not None else None
    items: list[Any] = []
    after: str | None = None
    seen_cursors: set[str] = set()
    while True:
        raw = ctx.client.ask(
            ListResources(
                kind=query_kind,
                include_quarantined=False,
                after=after,
            )
        )
        next_cursor: str | None = None
        if isinstance(raw, ResourcesView):
            items.extend(raw.items)
            next_cursor = raw.next_cursor
        elif isinstance(raw, ResourceVersionView):
            items.append(raw)
        elif isinstance(raw, ResolutionView):
            if raw.chosen is not None:
                items.append(raw.chosen)
        elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            items.extend(cast("Sequence[Any]", raw))
        else:
            raw_items = getattr(raw, "items", None)
            if isinstance(raw_items, Sequence) and not isinstance(raw_items, (str, bytes)):
                items.extend(cast("Sequence[Any]", raw_items))
            raw_next = getattr(raw, "next_cursor", None)
            if isinstance(raw_next, str) and raw_next:
                next_cursor = raw_next
        if next_cursor is None or next_cursor in seen_cursors:
            break
        seen_cursors.add(next_cursor)
        after = next_cursor

    filtered: list[Any] = []
    for item in items:
        item_pack = getattr(item, "pack_slug", None)
        if req.pack is not None and item_pack is not None and str(item_pack) != req.pack:
            continue
        item_kind = item.kind.value if hasattr(item.kind, "value") else str(item.kind)
        if req.kind is not None and item_kind != req.kind.value:
            continue
        if req.key is not None and str(item.key) != req.key:
            continue
        filtered.append(item)

    filtered.sort(
        key=lambda item: (
            item.kind.value if hasattr(item.kind, "value") else str(item.kind),
            str(item.key),
            str(getattr(item, "pack_slug", "")),
        )
    )
    return filtered


def run(ctx: HostContext, request: CheckUpstreamRequest | Mapping[str, object]) -> CheckUpstreamReport:
    """Check tracked upstream files for installed resources without modifying local state."""
    req = _coerce_request(request)
    max_bytes, timeout_seconds = _read_limits(ctx, request)
    scopes = _candidate_scopes(ctx, request)
    fetcher = ctx.gateways.get(UpstreamFetcher)

    entries = _list_entries(ctx, req)
    report_items: list[CheckUpstreamReportItemsItem] = []

    for entry in entries:
        kind_val = entry.kind.value if hasattr(entry.kind, "value") else str(entry.kind)
        domain_kind = DomainResourceKind(kind_val)
        host_kind = HostResourceKind(kind_val)
        key = str(entry.key)
        manifest = _resolve_manifest(ctx, entry, scopes)
        prov = _extract_provenance(manifest)

        fetched: dict[str, bytes | None] = {}
        if prov.source is ProvenanceSource.UPSTREAM:
            for tracked in prov.files:
                url = tracked.url
                if not url and prov.repo:
                    url = f"{prov.repo.rstrip('/')}/{tracked.path.lstrip('/')}"
                if not url:
                    fetched[tracked.path] = None
                    continue
                try:
                    fetched[tracked.path] = fetcher.fetch(
                        url,
                        max_bytes=max_bytes,
                        timeout_seconds=timeout_seconds,
                    )
                except (BackendUnavailable, SkmError, OSError, TimeoutError, ValueError):
                    fetched[tracked.path] = None

        compared = compare_upstream(domain_kind, key, prov, fetched)
        report_items.append(
            CheckUpstreamReportItemsItem(
                kind=host_kind,
                key=compared.key,
                strategy=compared.strategy,
                status=compared.status,
                files=tuple(
                    CheckUpstreamReportItemsItemFilesItem(
                        path=f.path,
                        recorded_sha256=f.recorded_sha256,
                        upstream_sha256=f.upstream_sha256,
                    )
                    for f in compared.files
                ),
            )
        )

    return CheckUpstreamReport(items=tuple(report_items))


SPEC: Final = HostOperationSpec(
    name="extensions.host.check_upstream",
    run=run,
    request=cast("type[object]", dict),
    result=CheckUpstreamReport,
    surfaces=cast("frozenset[Any]", frozenset({"cli"})),
)
