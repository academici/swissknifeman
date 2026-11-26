"""Role/scope steering selection and deterministic conflict resolution (context §5.4)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.languages import LANGUAGE_EXTENSIONS
from skm.modules.context.domain.candidates import metadata, path_matches, strings

if TYPE_CHECKING:
    from skm.modules.context.domain.contracts import Candidate, Selected
    from skm.modules.context.domain.policy import ContextPolicy
    from skm.modules.context.domain.request import ContextRequest

_LANGUAGES = LANGUAGE_EXTENSIONS


def _scope_matches(meta: JsonObject, request: ContextRequest) -> bool:
    scope = meta.get("scope", {})
    if not isinstance(scope, dict):
        return False
    paths = request.permissions.write_scope
    checks = {
        "projects": request.project_slug,
        "task_types": str(meta.get("work_kind", "")),
        "risk": request.task_risk,
    }
    if any(strings(scope.get(k)) and value not in strings(scope[k]) for k, value in checks.items()):
        return False
    directories = strings(scope.get("directories"))
    if directories and not any(_directory_matches(d, p) for d in directories for p in paths):
        return False
    languages = strings(scope.get("languages"))
    return not languages or any(
        "." not in p.rsplit("/", 1)[-1] or p.endswith(_LANGUAGES.get(lang, ("<unknown>",)))
        for lang in languages
        for p in paths
    )


def _directory_matches(directory: str, path: str) -> bool:
    normalized = path.split(":", 1)[-1]
    prefix = normalized.split("*", 1)[0].split("?", 1)[0]
    return path_matches(directory, normalized) or prefix.startswith(directory.rstrip("/*") + "/")


def select_steering(
    candidates: Sequence[Candidate], request: ContextRequest, policy: ContextPolicy
) -> Selected:
    included: list[JsonValue] = []
    excluded: list[JsonValue] = []
    del policy
    ordered = sorted(
        candidates, key=lambda c: (-int(cast("int", metadata(c).get("priority", 0))), str(c["source_ref"]))
    )
    for candidate in ordered:
        meta = metadata(candidate)
        scope = meta.get("scope", {})
        global_scope = isinstance(scope, dict) and bool(scope.get("global", False))
        reason: str | None = None
        if strings(meta.get("applies_to")) and request.purpose.role not in strings(meta["applies_to"]):
            reason = "role_not_applicable"
        elif not global_scope and not _scope_matches(meta, request):
            reason = "scope_mismatch"
        else:
            for other in (item for item in included if isinstance(item, dict)):
                om = metadata(other)
                key, other_key = (
                    str(meta.get("key", candidate["source_ref"])),
                    str(om.get("key", other["source_ref"])),
                )
                if other_key in strings(meta.get("conflicts_with")) or key in strings(
                    om.get("conflicts_with")
                ):
                    if meta.get("priority", 0) == om.get("priority", 0):
                        raise PreconditionFailed(ErrorCode.CONTEXT_CONFLICT, "steering priorities conflict")
                    reason = "conflict_lower_priority"
                    break
        if reason:
            excluded.append(
                {
                    "block_type": candidate["block_type"],
                    "source_ref": candidate["source_ref"],
                    "reason": reason,
                }
            )
        else:
            included.append({**candidate, "reason": "scope_global" if global_scope else "scope_match"})
    return {"included": included, "excluded": excluded}
