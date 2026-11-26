from collections.abc import Mapping
from typing import Protocol
from uuid import uuid4

import pytest

from skm.application_bus.host import HostServices
from skm.kernel.errors import CapabilityUnavailable, Forbidden, InternalError
from skm.kernel.gateways import GatewayTable, control_plane_gateway, host_gateway, shared_gateway
from skm.kernel.ids import HostId
from skm.kernel.module_manifest import HostOperationSpec
from skm.kernel.ports_uow import Surface


@host_gateway
class HostPort(Protocol): ...


@control_plane_gateway
class CpPort(Protocol): ...


@shared_gateway
class SharedPort(Protocol): ...


class Unmarked(Protocol): ...


class _Impl: ...


def test_gateway_table_routing_and_marker() -> None:
    impl, shared = _Impl(), _Impl()
    host = GatewayTable(entries={HostPort: impl, SharedPort: shared}, kind="host_gateway")
    assert host.get(HostPort) is impl
    assert host.has(SharedPort)
    assert host.get(SharedPort) is shared
    with pytest.raises(TypeError):
        host.get(CpPort)
    with pytest.raises(TypeError):
        host.has(Unmarked)
    cp = GatewayTable(entries={}, kind="control_plane_gateway")
    assert not cp.has(CpPort)
    with pytest.raises(CapabilityUnavailable) as err:
        cp.get(CpPort)
    assert err.value.code.value == "CAPABILITY_UNAVAILABLE"
    with pytest.raises(TypeError):
        cp.get(HostPort)


def _services(
    surface: Surface, calls: list[str], ops: Mapping[str, HostOperationSpec] | None = None
) -> HostServices:
    spec = HostOperationSpec(
        name="m.host.do_it",
        run=lambda ctx, req: (ctx.host_id, ctx.config, req),
        request=object,
        result=object,
        surfaces=frozenset({Surface.CLI}),
    )
    return HostServices(
        host_id=HostId(uuid4()),
        surface=surface,
        gateways=GatewayTable(entries={}, kind="host_gateway"),
        host_config=lambda: "cfg",
        operations=ops if ops is not None else {spec.name: spec},
        owned_resources=(lambda: calls.append("a"), lambda: calls.append("b")),
    )


def test_run_checks_name_and_surface() -> None:
    svc = _services(Surface.CLI, [])
    out = svc.run("m.host.do_it", "req", client=object(), cancel=object())  # type: ignore[arg-type]
    assert out == (svc.host_id, "cfg", "req")
    with pytest.raises(InternalError):
        svc.run("nope", None, client=object(), cancel=object())  # type: ignore[arg-type]
    worker = _services(Surface.WORKER, [], ops=svc.operations)
    with pytest.raises(Forbidden) as err:
        worker.run("m.host.do_it", None, client=object(), cancel=object())  # type: ignore[arg-type]
    assert err.value.details["reason_code"] == "SURFACE_NOT_ALLOWED"


def test_close_releases_owned_once_in_reverse() -> None:
    calls: list[str] = []
    svc = _services(Surface.CLI, calls)
    svc.close()
    svc.close()
    assert calls == ["b", "a"]


def test_rejects_non_host_table() -> None:
    with pytest.raises(TypeError):
        HostServices(
            host_id=HostId(uuid4()),
            surface=Surface.CLI,
            gateways=GatewayTable(entries={}, kind="control_plane_gateway"),
            host_config=lambda: None,
            operations={},
        )


def test_run_without_log_gives_working_logger() -> None:
    seen: list[object] = []
    spec = HostOperationSpec(
        name="m.host.log_it",
        run=lambda ctx, req: (ctx.log.info("m.host.logged"), seen.append(ctx.log), "ok")[2],
        request=object,
        result=object,
        surfaces=frozenset({Surface.CLI}),
    )
    svc = _services(Surface.CLI, [], ops={spec.name: spec})
    assert svc.run(spec.name, None, client=object(), cancel=object()) == "ok"  # type: ignore[arg-type]
    assert seen
    assert seen[0] is not None
    marker = object()
    svc2 = _services(Surface.CLI, [], ops={spec.name: spec})
    svc2.log_factory = type("L", (), {"info": lambda self, e, **k: seen.append(marker)})
    svc2.run(spec.name, None, client=object(), cancel=object())  # type: ignore[arg-type]
    assert marker in seen


@pytest.mark.parametrize("name", ["workspace.bind_checkout", ".host.x", "m.host.", "m.host.x.y", "M.host.x"])
def test_bad_operation_namespace_rejected_without_call(name: str) -> None:
    called: list[str] = []
    spec = HostOperationSpec(
        name=name,
        run=lambda c, r: called.append("x"),
        request=object,
        result=object,
        surfaces=frozenset({Surface.CLI}),
    )
    with pytest.raises(ValueError, match="host operation"):
        _services(Surface.CLI, [], ops={name: spec})
    svc = _services(Surface.CLI, [])
    object.__setattr__(svc, "operations", {name: spec})  # registry mutated after construction
    with pytest.raises(ValueError, match="host operation"):
        svc.run(name, None, client=object(), cancel=object())  # type: ignore[arg-type]
    assert not called


def test_registry_key_must_match_spec_name_and_good_name_routes() -> None:
    spec = HostOperationSpec(
        name="workspace.host.bind_checkout",
        run=lambda c, r: "bound",
        request=object,
        result=object,
        surfaces=frozenset({Surface.CLI}),
    )
    with pytest.raises(ValueError, match="host operation"):
        _services(Surface.CLI, [], ops={"workspace.host.other": spec})
    svc = _services(Surface.CLI, [], ops={spec.name: spec})
    assert svc.run(spec.name, None, client=object(), cancel=object()) == "bound"  # type: ignore[arg-type]
