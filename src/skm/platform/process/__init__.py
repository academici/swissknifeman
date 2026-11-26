"""Child process execution: explicit argv and environment, bounded pipes and pidfd-based ownership.

PID numbers are diagnostic only; containment and ownership are proved through pidfds and process groups.
"""
