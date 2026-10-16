"""The only place where the runtime reaches the aicore foundation.

The plan engine works without aicore; features that need it ask here. Submodules import aicore
inside their functions, so importing them never fails when the foundation is absent.
"""
from __future__ import annotations

from pathlib import Path

_PROBE: dict = {}


def _probe() -> dict:
    """Try ``import aicore`` once per process and remember the outcome."""
    if not _PROBE:
        try:
            import aicore
        except ImportError as exc:
            _PROBE.update(available=False, root=None, reason=str(exc) or "AICORE_NOT_FOUND")
        else:
            # <root>/lib/aicore/__init__.py -> <root>
            _PROBE.update(available=True, root=str(Path(aicore.__file__).resolve().parents[2]), reason=None)
    return _PROBE


def available() -> bool:
    """True when aicore can be imported."""
    return bool(_probe()["available"])


def status() -> dict:
    """``{"aicore": "available" | "unavailable", "root": str | None, "reason": str | None}``."""
    probe = _probe()
    return {"aicore": "available" if probe["available"] else "unavailable",
            "root": probe["root"], "reason": probe["reason"]}


def require(feature: str) -> None:
    """Refuse an explicit request that needs the foundation when it is missing."""
    if not available():
        from planner.plan.model import PlanError
        raise PlanError("AICORE_REQUIRED", f"{feature} needs the aicore foundation; set AICORE_ROOT")
