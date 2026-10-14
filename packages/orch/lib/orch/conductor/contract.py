"""The closed documents of the conductor (``schemas/conductor/v1``): run-options, stage-report, review-findings,
triage-result, progress-line and scout-write-set, checked by the closed-profile validator of aicore."""
from __future__ import annotations

from aicore.util import schema

from orch.settings import ORCH_ROOT

CONTRACT_DIR = ORCH_ROOT / "schemas" / "conductor" / "v1"
KINDS = ("progress-line", "review-findings", "run-options", "scout-write-set", "stage-report", "triage-result")
_REGISTRY: list = []


def registry():
    if not _REGISTRY:
        found, kinds = schema.load_contract_set(CONTRACT_DIR)
        if tuple(kinds) != KINDS:
            raise schema.SchemaProfileError(f"conductor/v1 holds {kinds}, expected {list(KINDS)}")
        _REGISTRY.append(found)
    return _REGISTRY[0]


def problems(doc: object, kind: str) -> list[str]:
    """Violations of ``conductor/v1`` ``kind`` by ``doc`` as ``path: message`` lines (empty when valid)."""
    if kind not in KINDS:
        raise schema.SchemaProfileError(f"unknown conductor kind: {kind!r}")
    return [f"{issue.path or '/'}: {issue.message}" for issue in schema.validate(doc, kind, registry())]


def triage_problems(findings: dict, triage: dict) -> list[str]:
    """Every finding of the round appears exactly once in the triage-result, and nothing else does."""
    expected = [item["id"] for item in findings.get("findings", [])]
    seen = [entry["finding"] for key in ("confirmed", "rejected") for entry in triage.get(key, [])]
    issues = [f"/{key}: finding {name} is not in the review round" for key in ("confirmed", "rejected")
              for name in (entry["finding"] for entry in triage.get(key, [])) if name not in expected]
    issues += [f"/: finding {name} is triaged {seen.count(name)} times" for name in sorted(set(seen))
               if seen.count(name) > 1]
    issues += [f"/: finding {name} is not triaged" for name in expected if name not in seen]
    severe = {item["id"] for item in findings.get("findings", []) if item.get("severity") in ("Blocker", "Major")}
    issues += [f"/rejected: {entry['finding']} is a Blocker or Major finding rejected without a reproduction that ran"
               for entry in triage.get("rejected", []) if entry.get("finding") in severe and not entry.get("reproduction")]
    return issues
