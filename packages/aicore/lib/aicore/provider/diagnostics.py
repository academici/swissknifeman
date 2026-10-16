"""Stable diagnostic rendering without values from provider targets."""
from .status import StatusDiagnostic


def render(diagnostic: StatusDiagnostic) -> dict[str, str]:
    return {"severity": diagnostic.severity, "code": diagnostic.code,
            "message": diagnostic.message, "source_ref": diagnostic.source_ref}
