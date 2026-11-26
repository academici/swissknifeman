"""Unit tests for ``extensions.host.check_upstream`` and ``HttpUpstreamFetcher`` (extensions §9)."""

from __future__ import annotations

import base64
import email.message
import hashlib
import io
import urllib.error
import urllib.request
import urllib.response
from typing import Any, cast, override
from uuid import UUID

import pytest

from contracts.extensions.harness import (
    ExtensionsWorld,
    build_world,
    core_files,
    pack_payload,
)
from skm.adapters.resources.upstream_http import HttpUpstreamFetcher
from skm.application_bus.client import QueryMeta, StagedBlobRef
from skm.application_bus.host import HostContext
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, ValidationFailed
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId
from skm.modules.extensions.domain.payload import PackPayload
from skm.modules.extensions.generated.commands import InstallPack, SyncBuiltinPacks
from skm.modules.extensions.generated.documents import (
    PackPayload as PayloadDto,
)
from skm.modules.extensions.generated.documents import (
    PackPayloadFilesItem,
)
from skm.modules.extensions.generated.host import CheckUpstreamRequest, ResourceKind
from skm.modules.extensions.generated.queries import ListResources
from skm.modules.extensions.host import check_upstream
from skm.modules.extensions.ports import UpstreamFetcher


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _install_dto(payload: PackPayload, **fields: Any) -> InstallPack:
    return InstallPack(
        payload=PayloadDto(
            manifest_text=payload.manifest_text,
            files=tuple(
                PackPayloadFilesItem(item.path, base64.b64encode(item.content).decode("ascii"))
                for item in payload.files
            ),
        ),
        origin_label=fields.pop("origin_label", "path:/packs/ext"),
        **fields,
    )


def _skill_manifest(
    key: str,
    *,
    strategy: str = "notify",
    files: list[tuple[str, str, str]],
) -> str:
    file_entries = "\n".join(
        f'[[provenance.files]]\npath = "{path}"\nurl = "{url}"\nsha256 = "{sha}"\nfetched_at = "2026-01-15"\n'
        for path, url, sha in files
    )
    anchor = files[0][2]
    return (
        f'schema = "urn:skm:extensions:skill-manifest:v1"\n'
        f'key = "{key}"\n'
        f'version = "1.0.0"\n'
        f"\n"
        f"[provenance]\n"
        f'source = "upstream"\n'
        f'repo = "https://example.com/repo"\n'
        f'strategy = "{strategy}"\n'
        f'upstream_sha = "{anchor}"\n'
        f"{file_entries}"
    )


class _RecordingFetcher(UpstreamFetcher):
    def __init__(self, responses: dict[str, bytes | Exception]) -> None:
        self.responses = dict(responses)
        self.calls: list[tuple[str, int, int]] = []

    @override
    def fetch(self, url: str, *, max_bytes: int, timeout_seconds: int) -> bytes:
        self.calls.append((url, max_bytes, timeout_seconds))
        outcome = self.responses.get(url)
        if outcome is None:
            raise BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE,
                f"no response configured for {url}",
                details={"url": url},
            )
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _WorldClient:
    def __init__(self, world: ExtensionsWorld, *, page_size: int | None = None) -> None:
        self._ask_fn = world.ask
        self._page_size = page_size
        self.list_calls: list[str | None] = []

    def dispatch(self, command: object, *, idempotency_key: str | None = None) -> object:
        raise AssertionError("check_upstream must never call dispatch")

    def ask(self, query: object, *, meta: QueryMeta | None = None) -> object:
        del meta
        if isinstance(query, ListResources) and self._page_size is not None:
            self.list_calls.append(query.after)
            query = ListResources(
                kind=query.kind,
                scope=query.scope,
                include_quarantined=query.include_quarantined,
                limit=self._page_size,
                after=query.after,
            )
        return self._ask_fn(query)

    def upload_blob(self, content: bytes, *, media_type: str = "application/octet-stream") -> StagedBlobRef:
        raise AssertionError("check_upstream must never call upload_blob")

    def close(self) -> None:
        return None


def _make_host_ctx(
    world: ExtensionsWorld,
    fetcher: UpstreamFetcher,
    config: object | None = None,
    *,
    client: _WorldClient | None = None,
) -> HostContext:
    return HostContext(
        host_id=HostId(UUID(int=1)),
        client=cast("Any", client or _WorldClient(world)),
        config=config if config is not None else {"extensions.upstream.fetch_timeout_seconds": 15},
        gateways=GatewayTable({UpstreamFetcher: fetcher}, kind="host_gateway"),
        log=None,
        cancel=CancelSource().token,
    )


@pytest.fixture
def world() -> ExtensionsWorld:
    w = build_world(pack_payload(version="1.0.0", files=core_files(version="1.0.0")))
    w.run(SyncBuiltinPacks())
    return w


def test_check_upstream_reports_up_to_date_changed_unreachable_and_local_idempotently(
    world: ExtensionsWorld,
) -> None:
    skill_a_body = b"# Skill A v1\n"
    skill_b_body = b"# Skill B v1\n"
    skill_c_body = b"# Skill C v1\n"
    local_body = b"# Local skill\n"

    url_a = "https://example.com/repo/skills/alpha/SKILL.md"
    url_b = "https://example.com/repo/skills/beta/SKILL.md"
    url_c = "https://example.com/repo/skills/gamma/SKILL.md"

    ext_pack = pack_payload(
        "upstream-pack",
        trust="operator",
        files={
            "skills/alpha/manifest.toml": _skill_manifest(
                "alpha",
                strategy="replace",
                files=[("SKILL.md", url_a, _sha(skill_a_body))],
            ),
            "skills/alpha/SKILL.md": skill_a_body.decode("utf-8"),
            "skills/beta/manifest.toml": _skill_manifest(
                "beta",
                strategy="fork",
                files=[("SKILL.md", url_b, _sha(skill_b_body))],
            ),
            "skills/beta/SKILL.md": skill_b_body.decode("utf-8"),
            "skills/gamma/manifest.toml": _skill_manifest(
                "gamma",
                strategy="merge",
                files=[("SKILL.md", url_c, _sha(skill_c_body))],
            ),
            "skills/gamma/SKILL.md": skill_c_body.decode("utf-8"),
            "skills/local-only/manifest.toml": (
                'schema = "urn:skm:extensions:skill-manifest:v1"\nkey = "local-only"\nversion = "1.0.0"\n'
            ),
            "skills/local-only/SKILL.md": local_body.decode("utf-8"),
        },
    )
    world.run(_install_dto(ext_pack, trust="operator"))
    world.set_config("extensions.packs.enabled", ["core", "upstream-pack"])

    updated_b = b"# Skill B v2 (remote update)\n"
    fetcher = _RecordingFetcher(
        {
            url_a: skill_a_body,
            url_b: updated_b,
            url_c: BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "connection timed out"),
        }
    )
    ctx = _make_host_ctx(
        world,
        fetcher,
        config={
            "extensions.upstream.fetch_timeout_seconds": 12,
            "extensions.install.max_archive_bytes": 65536,
        },
    )

    events_before = len(world.backend.committed.core.events)
    versions_before = dict(world.tables().versions)

    first = check_upstream.run(
        ctx,
        CheckUpstreamRequest(pack="upstream-pack", kind=ResourceKind.SKILL),
    )
    second = check_upstream.SPEC.run(
        ctx,
        {"pack": "upstream-pack", "kind": "skill"},
    )
    assert first == second

    by_key = {item.key: item for item in first.items}
    assert set(by_key) == {"alpha", "beta", "gamma", "local-only"}

    assert by_key["alpha"].status == "up_to_date"
    assert by_key["alpha"].strategy == "replace"
    assert by_key["alpha"].files[0].recorded_sha256 == _sha(skill_a_body)
    assert by_key["alpha"].files[0].upstream_sha256 == _sha(skill_a_body)

    assert by_key["beta"].status == "changed"
    assert by_key["beta"].strategy == "fork"
    assert by_key["beta"].files[0].recorded_sha256 == _sha(skill_b_body)
    assert by_key["beta"].files[0].upstream_sha256 == _sha(updated_b)

    # Unreachable must never be reported as up_to_date
    assert by_key["gamma"].status == "unreachable"
    assert by_key["gamma"].strategy == "merge"
    assert by_key["gamma"].files[0].recorded_sha256 == _sha(skill_c_body)
    assert by_key["gamma"].files[0].upstream_sha256 is None

    assert by_key["local-only"].status == "local"
    assert by_key["local-only"].strategy is None
    assert by_key["local-only"].files == ()

    # Verify timeout and max_bytes were forwarded to UpstreamFetcher
    assert all(max_b == 65536 and timeout_s == 12 for _, max_b, timeout_s in fetcher.calls)

    # Filter by key
    single = check_upstream.run(
        ctx,
        CheckUpstreamRequest(pack="upstream-pack", kind=ResourceKind.SKILL, key="beta"),
    )
    assert [item.key for item in single.items] == ["beta"]

    # Read-only invariant: no domain events emitted and no resource versions mutated
    assert len(world.backend.committed.core.events) == events_before
    assert dict(world.tables().versions) == versions_before


class _FakeHttpResponse:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._stream = io.BytesIO(body)
        self.status = status
        self.headers = headers or {}

    def read(self, amt: int = -1) -> bytes:
        return self._stream.read(amt)

    def __enter__(self) -> _FakeHttpResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_http_upstream_fetcher_enforces_https_timeout_and_max_bytes() -> None:
    payload = b"hello upstream\n"
    seen_timeouts: list[float] = []

    def fake_urlopen(req: Any, timeout: float = 0.0) -> _FakeHttpResponse:
        seen_timeouts.append(timeout)
        url = req.full_url
        if "oversized-header" in url:
            return _FakeHttpResponse(b"x", headers={"Content-Length": "999999"})
        if "oversized-body" in url:
            return _FakeHttpResponse(b"x" * 2048)
        if "http-500" in url:
            return _FakeHttpResponse(b"", status=500)
        if "network-error" in url:
            raise urllib.error.URLError("connection refused")
        return _FakeHttpResponse(payload, headers={"Content-Length": str(len(payload))})

    fetcher = HttpUpstreamFetcher(urlopen=fake_urlopen)

    # 1. Valid HTTPS fetch within limits succeeds
    got = fetcher.fetch("https://example.com/SKILL.md", max_bytes=1024, timeout_seconds=7)
    assert got == payload
    assert seen_timeouts == [7.0]

    # 2. Non-HTTPS URLs are rejected before network I/O
    for bad_url in ("http://example.com/SKILL.md", "file:///etc/passwd", "", "https://example.com/a b"):
        with pytest.raises(BackendUnavailable) as exc_info:
            fetcher.fetch(bad_url, max_bytes=1024, timeout_seconds=5)
        assert exc_info.value.code is ErrorCode.BACKEND_UNAVAILABLE

    # 3. Content-Length and body byte caps raise BackendUnavailable
    for cap_url in ("https://example.com/oversized-header", "https://example.com/oversized-body"):
        with pytest.raises(BackendUnavailable) as cap_exc:
            fetcher.fetch(cap_url, max_bytes=100, timeout_seconds=5)
        assert cap_exc.value.code is ErrorCode.BACKEND_UNAVAILABLE
        assert cap_exc.value.details["reason"] == "max_bytes_exceeded"

    # 4. HTTP error status and transport errors raise BackendUnavailable
    for err_url in ("https://example.com/http-500", "https://example.com/network-error"):
        with pytest.raises(BackendUnavailable) as err_exc:
            fetcher.fetch(err_url, max_bytes=1024, timeout_seconds=5)
        assert err_exc.value.code is ErrorCode.BACKEND_UNAVAILABLE


class _RedirectTestHandler(urllib.request.HTTPSHandler, urllib.request.HTTPHandler):
    """Fake handler simulating HTTP 302 redirects without opening network sockets."""

    @staticmethod
    def _resp(url: str, code: int, body: bytes, headers: email.message.Message) -> urllib.response.addinfourl:
        r = urllib.response.addinfourl(io.BytesIO(body), headers, url, code)
        cast("Any", r).msg = "OK" if code == 200 else "Found"
        return r

    @override
    def https_open(self, req: urllib.request.Request) -> urllib.response.addinfourl:
        url = req.full_url
        headers = email.message.Message()
        if url == "https://example.com/downgrade":
            headers["Location"] = "http://example.com/insecure-target"
            return self._resp(url, 302, b"", headers)
        if url == "https://example.com/ftp-downgrade":
            headers["Location"] = "ftp://example.com/file"
            return self._resp(url, 302, b"", headers)
        if url == "https://example.com/https-redirect":
            headers["Location"] = "https://example.com/final"
            return self._resp(url, 302, b"", headers)
        if url == "https://example.com/final":
            body = b"redirected safely over https\n"
            headers["Content-Length"] = str(len(body))
            return self._resp(url, 200, body, headers)
        raise AssertionError(f"unexpected https url: {url}")

    @override
    def http_open(self, req: urllib.request.Request) -> urllib.response.addinfourl:
        raise AssertionError(f"http_open must never be reached: {req.full_url}")


def test_http_upstream_fetcher_rejects_https_to_http_or_ftp_redirect() -> None:
    fetcher = HttpUpstreamFetcher(handlers=(_RedirectTestHandler(),))

    # HTTPS -> HTTPS redirect is allowed
    got = fetcher.fetch("https://example.com/https-redirect", max_bytes=1024, timeout_seconds=5)
    assert got == b"redirected safely over https\n"

    # HTTPS -> HTTP and HTTPS -> FTP redirects are rejected with BackendUnavailable(non_https_url)
    for downgrade_url in ("https://example.com/downgrade", "https://example.com/ftp-downgrade"):
        with pytest.raises(BackendUnavailable) as exc_info:
            fetcher.fetch(downgrade_url, max_bytes=1024, timeout_seconds=5)
        assert exc_info.value.code is ErrorCode.BACKEND_UNAVAILABLE
        assert exc_info.value.details["reason"] == "non_https_url"


class _HostChainConfigStub:
    """Simulates a Chain.HOST EffectiveConfig raising CONFIG_SCOPE_NOT_ALLOWED on work-chain keys."""

    def get(self, key: str) -> object:
        raise ValidationFailed(
            ErrorCode.CONFIG_SCOPE_NOT_ALLOWED,
            f"key {key!r} belongs to the work chain, not host chain",
            details={"key": key, "chain": "work"},
        )


def test_check_upstream_handles_host_chain_config_and_paginates_list_resources(
    world: ExtensionsWorld,
) -> None:
    skill_a_body = b"# Alpha\n"
    skill_b_body = b"# Beta\n"
    skill_c_body = b"# Gamma\n"
    url_a = "https://example.com/repo/a.md"
    url_b = "https://example.com/repo/b.md"
    url_c = "https://example.com/repo/c.md"

    ext_pack = pack_payload(
        "paged-pack",
        trust="operator",
        files={
            "skills/alpha/manifest.toml": _skill_manifest(
                "alpha", strategy="notify", files=[("SKILL.md", url_a, _sha(skill_a_body))]
            ),
            "skills/alpha/SKILL.md": skill_a_body.decode("utf-8"),
            "skills/beta/manifest.toml": _skill_manifest(
                "beta", strategy="notify", files=[("SKILL.md", url_b, _sha(skill_b_body))]
            ),
            "skills/beta/SKILL.md": skill_b_body.decode("utf-8"),
            "skills/gamma/manifest.toml": _skill_manifest(
                "gamma", strategy="notify", files=[("SKILL.md", url_c, _sha(skill_c_body))]
            ),
            "skills/gamma/SKILL.md": skill_c_body.decode("utf-8"),
        },
    )
    world.run(_install_dto(ext_pack, trust="operator"))
    world.set_config("extensions.packs.enabled", ["core", "paged-pack"])

    fetcher = _RecordingFetcher({url_a: skill_a_body, url_b: skill_b_body, url_c: skill_c_body})
    paged_client = _WorldClient(world, page_size=1)
    ctx = _make_host_ctx(
        world,
        fetcher,
        config=_HostChainConfigStub(),
        client=paged_client,
    )

    report = check_upstream.run(ctx, CheckUpstreamRequest(pack="paged-pack", kind=ResourceKind.SKILL))
    assert [item.key for item in report.items] == ["alpha", "beta", "gamma"]
    assert all(item.status == "up_to_date" for item in report.items)
    # Verify multiple pages were fetched via next_cursor
    assert len(paged_client.list_calls) >= 3
    assert paged_client.list_calls[0] is None
    assert all(cursor is not None for cursor in paged_client.list_calls[1:])
