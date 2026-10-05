"""exec/v1 schema registry, semantic validation and document digests."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Callable, NamedTuple

from orch import CONTRACT_VERSION
from orch import schema

URN_PREFIX = "urn:swissknifeman:orch:exec:"
KINDS = (
    "execution-input", "run-policy", "role-manifest", "capability-record", "run-event",
    "stage-result", "effect-receipt", "check-evidence", "launch-plan",
)
LIFECYCLE_PHRASES = (
    "report_api", "plan.py start", "plan.py finish", "unit return", "task:plan-run",
)


class Issue(NamedTuple):
    path: str
    code: str
    message: str
    level: str = "error"


SEMANTIC: dict[str, Callable[[object], list[Issue]]] = {}


def load_registry() -> schema.Registry:
    """Load the cached registry from this package, independent of the current cwd."""
    directory = Path(__file__).resolve().parents[2] / "schemas" / "exec" / "v1"
    return schema.load_registry(directory, urn_prefix=URN_PREFIX, kinds=KINDS)


def semantic_checks(doc: object, kind: str) -> list[Issue]:
    if kind not in KINDS:
        raise schema.SchemaProfileError(f"unknown schema kind: {kind!r}")
    issues = []
    if isinstance(doc, dict) and doc.get("contract_version") != CONTRACT_VERSION:
        issues.append(Issue("/contract_version", "CONTRACT_VERSION",
                            f"contract_version must equal {CONTRACT_VERSION!r}"))
    check = SEMANTIC.get(kind)
    if check is not None:
        issues.extend(check(doc))
    return issues


def validate(doc: object, kind: str, registry: schema.Registry | None = None) -> list[Issue]:
    """Reject incompatible versions, then collect schema and semantic issues."""
    semantic = semantic_checks(doc, kind)
    # A different contract version cannot be interpreted using exec/v1 schemas.
    if any(issue.code == "CONTRACT_VERSION" for issue in semantic):
        return semantic
    reg = registry if registry is not None else load_registry()
    return [Issue(*issue) for issue in schema.validate(doc, kind, reg)] + semantic


def canonical_digest(doc: dict) -> str:
    """Hash canonical UTF-8 JSON, excluding only the document's top-level digest."""
    payload = {key: value for key, value in doc.items() if key != "digest"}
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()
