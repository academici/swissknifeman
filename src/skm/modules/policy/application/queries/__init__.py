"""Views of permission sets and task authority shared by the policy queries (policy §8)."""

from __future__ import annotations

from typing import cast

from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.policy.domain.operations import TaskAuthority
from skm.modules.policy.domain.paths import PathRule
from skm.modules.policy.domain.permission_set import PermissionSet, canonical_document
from skm.modules.policy.domain.render import view_document
from skm.modules.policy.generated import documents, views
from skm.platform.jsonc.digest import digest

__all__ = ["authority_view", "permission_set_view", "rule_document"]


def rule_document(rule: PathRule) -> JsonObject:
    doc: JsonObject = {"scope": rule.scope.value, "pattern": rule.pattern}
    if rule.mount is not None:
        doc["mount"] = rule.mount
    return doc


def permission_set_view(perms: PermissionSet) -> views.PermissionSetView:
    """The view with the digest of the canonical form (the ``policy_digest`` of execution bundles)."""
    document = view_document(perms)
    document["digest"] = digest(canonical_document(perms))
    return views.PermissionSetView.from_json(document)


def authority_view(authority: TaskAuthority) -> documents.TaskAuthority:
    write_scope: JsonValue = (
        None if authority.write_scope is None else [rule_document(rule) for rule in authority.write_scope]
    )
    document: JsonObject = {
        "write_scope": write_scope,
        "delete_scope": cast("JsonValue", [rule_document(rule) for rule in authority.delete_scope]),
        "operations": cast("JsonValue", sorted(item.value for item in authority.operations)),
        "capabilities": cast("JsonValue", sorted(item.value for item in authority.capabilities)),
    }
    return documents.TaskAuthority.from_json(document)
