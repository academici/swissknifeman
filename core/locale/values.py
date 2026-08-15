"""Immutable values shared by the locale resolver and render boundaries."""
from dataclasses import dataclass

SURFACES = ("response", "plan", "diagnostics")


@dataclass(frozen=True)
class LocaleDiagnostic:
    severity: str
    code: str
    surface: str
    message: str

    def as_dict(self):
        return {"severity": self.severity, "code": self.code, "surface": self.surface,
                "message": self.message}


@dataclass(frozen=True)
class SurfaceLocale:
    surface: str
    rank: int
    kind: str
    requested: str
    canonical: str | None
    resolved: str | None
    fallback: bool
    diagnostic: str | None

    def as_dict(self):
        return {name: getattr(self, name) for name in (
            "surface", "rank", "kind", "requested", "canonical", "resolved",
            "fallback", "diagnostic")}


@dataclass(frozen=True)
class LocaleResult:
    contract_version: str
    surfaces: tuple[SurfaceLocale, ...] | None
    diagnostics: tuple[LocaleDiagnostic, ...]

    def as_dict(self):
        return {"contract_version": self.contract_version,
                "result": None if self.surfaces is None else {"surfaces": [x.as_dict() for x in self.surfaces]},
                "diagnostics": [x.as_dict() for x in self.diagnostics]}
