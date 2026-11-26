"""Host operation registry of the ``workspace`` module (workspace §9)."""

from skm.kernel.module_manifest import HostOperationSpec

from .bind_checkout import SPEC as BIND_CHECKOUT_SPEC
from .register_this_host import SPEC as REGISTER_THIS_HOST_SPEC
from .rotate_worker_token import SPEC as ROTATE_WORKER_TOKEN_SPEC
from .verify_checkout import SPEC as VERIFY_CHECKOUT_SPEC

__all__ = ["HOST_OPERATIONS"]

HOST_OPERATIONS: tuple[HostOperationSpec, ...] = (
    BIND_CHECKOUT_SPEC,
    VERIFY_CHECKOUT_SPEC,
    REGISTER_THIS_HOST_SPEC,
    ROTATE_WORKER_TOKEN_SPEC,
)
