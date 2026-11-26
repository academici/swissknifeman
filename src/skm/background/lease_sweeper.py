"""Expire leases through the application bus; no host or model calls."""

from .scheduler import ExecutionService

__all__ = ["LeaseSweeper"]


class LeaseSweeper(ExecutionService):
    name = "lease_sweeper"
    operation = "execution.expire_leases"
    count_key = "expired"
