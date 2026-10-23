"""The closed documents of the conductor (``schemas/conductor/v1``): fix-brief, review-summary, run-options, stage-report, review-findings,
triage-result, research-result, advice, progress-line, scout-write-set and prompt-manifest, checked by the closed-profile validator of aicore."""
from __future__ import annotations

from aicore.util import schema

from orch.settings import ORCH_ROOT

CONTRACT_DIR = ORCH_ROOT / "schemas" / "conductor" / "v1"
KINDS = ("advice", "fix-brief", "progress-line", "prompt-manifest", "research-result", "review-findings", "review-receipt", "review-summary", "run-options", "scout-write-set", "stage-report",
         "triage-result")
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
    rows = []
    for issue in schema.validate(doc, kind, registry()):
        where = issue.path or "/"
        rows.append(issue.message if issue.message.startswith(f"{where}:") else f"{where}: {issue.message}")  # one path, not two
    return rows


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


def research_problems(allowed: list, result: dict) -> list[str]:
    """What the schema cannot see in a research-result: a source id outside the ``allowed`` ones (the sources of
    ``[orch.research.sources]`` the role was given), and claims that name no source asked."""
    issues = [f"/sources_used: {name} is not an allowed source ({', '.join(allowed)})"
              for name in result.get("sources_used", []) if name not in allowed]
    if result.get("claims") and not result.get("sources_used"):
        issues.append("/sources_used: claims are given but no source was asked")
    return issues


def advice_problems(ref: str, advice: dict) -> list[str]:
    """What the schema cannot see in an advice: it answers the problem asked (``ref``), its option ids are unique and the
    recommendation is one of them."""
    ids = [option.get("id") for option in advice.get("options", [])]
    issues = [f"/options: id {name} repeats" for name in sorted(set(ids)) if ids.count(name) > 1]
    if advice.get("problem_ref") != ref:
        issues.append(f"/problem_ref: must be {ref!r}, the problem given in the prompt")
    if advice.get("recommendation") not in ids:
        issues.append(f"/recommendation: {advice.get('recommendation')!r} is not the id of an option")
    return issues
