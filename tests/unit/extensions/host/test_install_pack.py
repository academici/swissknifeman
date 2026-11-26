"""Unit tests for ``skm.modules.extensions.host.install_pack`` (extensions §8)."""

from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest

from skm.application_bus.host import HostContext
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId
from skm.modules.extensions.domain.payload import PackPayload, PayloadFile
from skm.modules.extensions.generated.commands import InstallPack
from skm.modules.extensions.generated.results import (
    InstallPackResult,
    InstallPackResultResourcesItem,
)
from skm.modules.extensions.generated.results import ResourceKind as ResultKind
from skm.modules.extensions.host.install_pack import SPEC, run
from skm.modules.extensions.ports import PackReader


class _FakePackReader:
    def __init__(self, payload: PackPayload) -> None:
        self._payload = payload
        self.dirs_read: list[str] = []
        self.archives_read: list[str] = []

    def read_dir(self, root: str) -> PackPayload:
        self.dirs_read.append(root)
        return self._payload

    def read_archive(self, path: str) -> PackPayload:
        self.archives_read.append(path)
        return self._payload


class _FakeClient:
    def __init__(self, result: InstallPackResult) -> None:
        self._result = result
        self.dispatched: list[InstallPack] = []

    def dispatch(self, command: object, *, idempotency_key: str | None = None) -> object:
        assert isinstance(command, InstallPack)
        self.dispatched.append(command)
        return self._result


def _sample_result() -> InstallPackResult:
    return InstallPackResult(
        pack_id=uuid4(),
        pack_version_id=uuid4(),
        slug="sample",
        version="1.0.0",
        digest="sha256:" + "a" * 64,
        status="installed",
        resources=(
            InstallPackResultResourcesItem(
                kind=ResultKind.SKILL,
                key="review",
                version="1.0.0",
                digest="sha256:" + "b" * 64,
                verdict="clean",
                overrides=False,
            ),
        ),
        quarantined=(),
        diagnostics=(),
    )


def _make_ctx(client: _FakeClient, reader: object, config: object = None) -> HostContext:
    return HostContext(
        client=cast("Any", client),
        gateways=GatewayTable({PackReader: reader}, "host_gateway"),
        host_id=HostId(uuid4()),
        config=config if config is not None else object(),
        log=object(),
        cancel=CancelSource().token,
    )


def test_host_install_pack_from_directory_dispatches_install_pack() -> None:
    payload = PackPayload(
        manifest_text='slug = "sample"\n',
        files=(PayloadFile("skills/review/SKILL.md", b"# Review\n"),),
    )
    reader = _FakePackReader(payload)
    client = _FakeClient(_sample_result())
    ctx = _make_ctx(client, reader)

    report = run(ctx, {"path": "/packs/sample", "trust": "operator", "dry_run": True})
    assert reader.dirs_read == ["/packs/sample"]
    assert reader.archives_read == []
    assert len(client.dispatched) == 1
    cmd = client.dispatched[0]
    assert cmd.origin_label == "path:/packs/sample"
    assert cmd.trust == "operator"
    assert cmd.dry_run is True
    assert report.slug == "sample"
    assert len(report.resources) == 1
    assert report.resources[0].key == "review"


def test_host_install_pack_from_archive_uses_read_archive_and_sha256_origin(
    tmp_path: Path,
) -> None:
    archive_file = tmp_path / "sample.tar.gz"
    payload = PackPayload(manifest_text='slug = "sample"\n', files=())
    reader = _FakePackReader(payload)
    client = _FakeClient(_sample_result())
    ctx = _make_ctx(client, reader)

    report = run(ctx, {"path": str(archive_file)})
    assert reader.archives_read == [str(archive_file)]
    assert reader.dirs_read == []
    cmd = client.dispatched[0]
    assert cmd.origin_label.startswith("archive:")
    assert not cmd.origin_label.startswith("archive:sha256:")
    assert len(cmd.origin_label.removeprefix("archive:")) == 64
    assert cmd.trust == "third_party"
    assert report.status == "installed"
    assert SPEC.name == "extensions.host.install_pack"


def test_host_install_pack_validates_path_or_archive_and_respects_on_incompatible() -> None:
    payload = PackPayload(manifest_text='slug = "sample"\n', files=())
    reader = _FakePackReader(payload)
    client = _FakeClient(_sample_result())
    ctx = _make_ctx(client, reader, config={"extensions.compat.on_incompatible": "refuse"})

    with pytest.raises(ValidationFailed) as exc_info:
        run(ctx, {})
    assert exc_info.value.code is ErrorCode.SCHEMA_INVALID
    assert exc_info.value.details["reason"] == "path_required"

    run(ctx, {"archive": "/packs/archive-without-ext"})
    assert reader.archives_read == ["/packs/archive-without-ext"]
    assert client.dispatched[0].allow_quarantine is False


def test_host_install_pack_reader_failure_does_not_dispatch() -> None:
    class _FailingReader:
        def read_dir(self, root: str) -> PackPayload:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "symlink in pack",
                details={"reason": "symlink_not_allowed", "path": root},
            )

        def read_archive(self, path: str) -> PackPayload:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "zip slip",
                details={"reason": "path_invalid", "path": path},
            )

    client = _FakeClient(_sample_result())
    ctx = _make_ctx(client, _FailingReader())

    with pytest.raises(ValidationFailed):
        run(ctx, {"path": "/packs/bad-dir"})
    with pytest.raises(ValidationFailed):
        run(ctx, {"path": "/packs/bad.tar.gz"})
    assert client.dispatched == []
