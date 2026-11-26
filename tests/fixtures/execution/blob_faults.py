"""Build another real App over the same PG database with a faulting BlobStore gateway."""

from contextlib import contextmanager

from skm.bootstrap.composition import CompositionOverrides, StoredScopeChain, build_app
from skm.kernel.gateways import GatewayTable
from skm.kernel.ports_uow import Surface
from skm.modules.artifacts.ports import BlobStore
from support.fault_injection import FaultyBlobStore


@contextmanager
def application_with_blob_fault(side, plan):
    store = FaultyBlobStore(side.app.gateways.get(BlobStore), plan)
    app = build_app(
        side.boot,
        surface=Surface.CLI,
        environ={},
        invocation={},
        backend="postgres",
        overrides=CompositionOverrides(
            side.app.bus._authorizer,
            StoredScopeChain(),
            clock=side.clock,
            instance_id=side.app.instance_id,
            gateways=GatewayTable({**side.app.gateways.entries, BlobStore: store}, "control_plane_gateway"),
        ),
    )
    try:
        assert app.gateways.get(BlobStore) is store
        yield app
    finally:
        app.close()
