"""The rules of a repeat around ``orch.retry.decide``: the conductor's defaults, the stop code of a failure class, a
quota whose reset has already passed, and the pause before a repeat. The attempts themselves (routes, gates, waits,
prompts) are ``application/retry_service.py``."""
from __future__ import annotations

from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock

# An unclassified failure was always repeated (within ``limits.retries``); retry.decide would stop on it by default.
CONDUCTOR_ON_ERROR = {"unknown": {"action": "retry"}}
# The stop code of a failure class; a class that is not listed keeps the code of the failed role (``ROLE_FAILED``, ...).
PROVIDER_STOP_CODES = {"authentication": "PROVIDER_AUTH", "authorization": "PROVIDER_AUTHZ", "quota": "PROVIDER_QUOTA",
                       "rate_limit": "PROVIDER_QUOTA", "invalid_request": "PROVIDER_REFUSED",
                       "content_policy": "PROVIDER_REFUSED", "context_limit": "PROVIDER_CONTEXT",
                       "model_unavailable": "MODEL_UNAVAILABLE"}
TRANSIENT_CLASSES = ("provider_internal", "transport", "rate_limit")  # the provider CLI repeats these itself
JITTER_CAP_S, JITTER_BASE_S = 300, 30


def past_reset(error: dict) -> bool:
    """A refused quota whose reset (``retry_after_s``, never negative) is 0: the provider's own reset time has passed and it
    still refuses. That is an unknown reset, not a reset now: no wait of 0 s, no gate, no "resume after <now>"."""
    return error.get("class") == "quota" and error.get("retry_after_s") == 0


PAUSE_TICK_S = 30  # how often a long pause says it is alive (``tick``)


def pause(seconds: float, cancel=None, tick=None) -> None:
    """Sleep ``seconds``, looking at ``cancel`` every second and calling ``tick`` (the heartbeat of the run) every
    ``PAUSE_TICK_S`` seconds."""
    remaining, since = float(seconds), 0.0
    while remaining > 0:
        if cancel is not None and cancel.is_set():
            raise Stop("REVIEW_CANCELLED", "cancelled while waiting for the provider: the checks are red")
        step = min(1.0, remaining)
        clock.sleep(step)
        remaining -= step
        since += step
        if tick is not None and since >= PAUSE_TICK_S:
            since = 0.0
            tick()
