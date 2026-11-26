"""Enforce authoritative deadlines through the application bus."""

from .scheduler import ExecutionService

__all__ = ["TimeoutEnforcer"]


class TimeoutEnforcer(ExecutionService):
    name = "timeout_enforcer"
    operation = "execution.enforce_timeouts"
    count_key = "failed"
