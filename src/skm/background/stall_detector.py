"""Evaluate stalls through a fresh control-plane command on each tick."""

from .scheduler import ExecutionService

__all__ = ["StallDetector"]


class StallDetector(ExecutionService):
    name = "stall_detector"
    operation = "execution.detect_stalls"
    count_key = "detected"
