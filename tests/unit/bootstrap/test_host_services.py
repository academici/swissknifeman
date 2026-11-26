from typing import Protocol
from uuid import uuid4

import pytest

from skm.bootstrap.host_services import build_host_services
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.gateways import control_plane_gateway, host_gateway
from skm.kernel.ids import HostId
from skm.kernel.module_manifest import HostOperationSpec
from skm.kernel.ports_uow import Surface


@host_gateway
class HPort(Protocol): ...


@control_plane_gateway
class ContextOwnerGuardLike(Protocol): ...


def _op(name: str, surfaces: set[Surface]) -> HostOperationSpec:
    return HostOperationSpec(name, lambda ctx, r: r, object, object, frozenset(surfaces))


def _build(surface: Surface = Surface.CLI, bootstrap: dict | None = None, **kw):
    return build_host_services(
        bootstrap if bootstrap is not None else {"host": {"id": str(uuid4())}},
        client=object(),  # type: ignore[arg-type]
        plugins=(),
        environ={},
        surface=surface,
        host_config=lambda: None,
        **kw,
    )


def test_operations_filtered_by_surface() -> None:
    svc = _build(operations=[_op("a.host.x", {Surface.CLI}), _op("a.host.y", {Surface.WORKER})])
    assert set(svc.operations) == {"a.host.x"}
    assert svc.gateways.kind == "host_gateway"


def test_duplicate_operation_rejected() -> None:
    with pytest.raises(ValidationFailed):
        _build(operations=[_op("a.host.x", {Surface.CLI}), _op("a.host.x", {Surface.CLI})])


def test_host_table_rejects_control_plane_port() -> None:
    assert _build(gateways={HPort: object()}).gateways.has(HPort)
    with pytest.raises(TypeError):
        _build(gateways={ContextOwnerGuardLike: object()})


def test_serve_surfaces_have_no_host_services() -> None:
    with pytest.raises(ValidationFailed):
        _build(Surface.API)


def test_auto_host_id() -> None:
    boot = {"host": {"id": "auto"}}
    with pytest.raises(PreconditionFailed) as err:
        _build(Surface.WORKER, boot)
    assert err.value.details["reason"] == "host_not_registered"
    with pytest.raises(ValidationFailed) as err2:
        _build(Surface.WORKER, boot, access_mode="http")
    assert err2.value.details["reason"] == "auto_forbidden_in_http"
    rec = HostId(uuid4())
    assert _build(Surface.WORKER, boot, recorded_host_id=rec).host_id == rec


def test_bad_host_id() -> None:
    with pytest.raises(ValidationFailed):
        _build(bootstrap={"host": {"id": "x"}})


@pytest.mark.parametrize("surface", [Surface.CLI, Surface.WORKER, Surface.HOOK])
def test_auto_reads_recorded_host_json(surface: Surface, tmp_path) -> None:
    import json

    rec = uuid4()
    (tmp_path / "host.json").write_text(json.dumps({"host_id": str(rec), "registered_at": "x"}))
    boot = {"host": {"id": "auto"}, "paths": {"state_dir": str(tmp_path)}}
    assert _build(surface, boot).host_id == HostId(rec)
    assert _build(Surface.WORKER, boot, access_mode="http").host_id == HostId(rec)


def test_explicit_uuid_wins_over_host_json(tmp_path) -> None:
    import json

    (tmp_path / "host.json").write_text(json.dumps({"host_id": str(uuid4())}))
    explicit = uuid4()
    boot = {"host": {"id": str(explicit)}, "paths": {"state_dir": str(tmp_path)}}
    assert _build(Surface.CLI, boot).host_id == HostId(explicit)


def test_auto_without_host_json_keeps_errors(tmp_path) -> None:
    boot = {"host": {"id": "auto"}, "paths": {"state_dir": str(tmp_path)}}
    with pytest.raises(PreconditionFailed):
        _build(Surface.HOOK, boot)
    with pytest.raises(ValidationFailed):
        _build(Surface.WORKER, boot, access_mode="http")
    (tmp_path / "host.json").write_text("{not json")
    with pytest.raises(ValidationFailed):
        _build(Surface.CLI, boot)


def test_operation_namespace_enforced_at_build() -> None:
    with pytest.raises(ValueError, match="host operation"):
        _build(operations=[_op("workspace.bind_checkout", {Surface.CLI})])
    assert (
        "workspace.host.bind_checkout"
        in _build(operations=[_op("workspace.host.bind_checkout", {Surface.CLI})]).operations
    )


def test_built_services_run_op_with_default_logger() -> None:
    spec = HostOperationSpec(
        "m.host.say",
        lambda ctx, r: (ctx.log.info("m.host.said"), "ok")[1],
        object,
        object,
        frozenset({Surface.CLI}),
    )
    svc = _build(operations=[spec])
    assert svc.run("m.host.say", None, client=object(), cancel=object()) == "ok"  # type: ignore[arg-type]
