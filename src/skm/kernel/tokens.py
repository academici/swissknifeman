"""Token estimation contract (kernel-platform §2.11c).

Pure and deterministic, identical on the server and the host. The built-in ``heuristic-v1`` lives in
``platform/tokens/heuristic.py``; plugins of kind ``token_estimator`` add others. Host collect/finalize
receive the estimator as an explicit argument, not from the host GatewayTable.
"""

from typing import Protocol

from skm.kernel.gateways import control_plane_gateway

__all__ = ["TokenEstimator"]


@control_plane_gateway
class TokenEstimator(Protocol):
    estimator_id: str

    def estimate(self, text: str) -> int: ...
