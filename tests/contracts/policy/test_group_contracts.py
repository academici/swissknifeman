"""Declaration and schema contracts of the policy group; it registers only implemented operations."""

import importlib
import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from jsonschema import Draft202012Validator, ValidationError
from jsonschema.protocols import Validator
from referencing import Registry, Resource
from referencing.jsonschema import Schema

from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.module_manifest import ModuleManifest
from skm.kernel.ports_uow import PORT_KIND_ATTRIBUTE

ROOT = Path(__file__).resolve().parents[3]
SCHEMAS = ROOT / "src/skm/schemas"
MODULES = ROOT / "src/skm/modules"
GROUPS = ("policy", "extensions", "runtimes", "planning")
DEPENDENCIES = {
    "policy": ("access", "workspace"),
    "extensions": ("access", "workspace", "policy"),
    "runtimes": ("access", "workspace", "extensions"),
    "planning": ("access", "workspace", "artifacts", "extensions", "runtimes"),
}
UUID = "01900000-0000-7000-8000-000000000001"
DIGEST = "sha256:" + "a" * 64


# Implemented registrations in manifest order, including later owner leaves.
IMPLEMENTED: dict[str, dict[str, tuple[str, ...]]] = {
    "policy": {
        "commands": (
            "policy.propose_intent",
            "policy.approve_intent",
            "policy.deny_intent",
            "policy.start_intent_execution",
            "policy.record_intent_outcome",
            "policy.record_tool_decisions",
            "policy.expire_intents",
        ),
        "queries": (
            "policy.effective_permissions",
            "policy.check_tool_call",
            "policy.explain_permissions",
            "policy.list_profiles",
            "policy.list_intents",
            "policy.get_intent",
        ),
        "events": (
            "IntentProposed",
            "IntentApproved",
            "IntentDenied",
            "IntentExecutionStarted",
            "IntentResolved",
        ),
    },
    "extensions": {
        "commands": (
            "extensions.install_pack",
            "extensions.sync_builtin_packs",
            "extensions.quarantine_resource",
            "extensions.release_quarantine",
            "extensions.uninstall_pack_version",
        ),
        "queries": (
            "extensions.list_packs",
            "extensions.get_pack",
            "extensions.list_resources",
            "extensions.get_resource_version",
            "extensions.resolve_resource",
        ),
        "events": (
            "PackInstalled",
            "PackVersionUninstalled",
            "ResourceVersionAdded",
            "ResourceQuarantined",
            "ResourceReleased",
        ),
        "host_operations": ("extensions.host.install_pack", "extensions.host.check_upstream"),
    },
    "runtimes": {
        "commands": ("runtimes.record_host_runtimes", "runtimes.record_capability_verification"),
        "queries": (
            "runtimes.list_runtimes",
            "runtimes.get_capabilities",
            "runtimes.list_models",
            "runtimes.explain_routing",
        ),
        "events": ("HostRuntimesRecorded", "CapabilityVerified"),
        "host_operations": ("runtimes.host.detect_runtimes",),
    },
    "planning": {
        "commands": (
            "planning.create_plan",
            "planning.design_plan",
            "planning.open_draft",
            "planning.save_draft",
            "planning.abandon_draft",
            "planning.rebase_draft",
            "planning.publish_revision",
            "planning.restore_revision",
            "planning.archive_plan",
            "planning.import_specification",
        ),
        "queries": (
            "planning.get_plan",
            "planning.list_plans",
            "planning.resolve_plan_ref",
            "planning.get_draft",
            "planning.list_drafts",
            "planning.validate_draft",
            "planning.get_revision",
            "planning.list_revisions",
            "planning.get_entity",
            "planning.list_entities",
            "planning.read_text",
            "planning.preview_publication",
            "planning.diff_revisions",
            "planning.ready_preview",
            "planning.simulate",
            "planning.plan_stats",
            "planning.export_specification",
        ),
        "events": (
            "PlanCreated",
            "DraftOpened",
            "DraftSaved",
            "DraftRebased",
            "DraftAbandoned",
            "PlanRevisionPublished",
            "PlanRevisionRestored",
            "PlanArchived",
        ),
    },
}


def _name(item: object) -> str:
    name = getattr(item, "name", None)
    return name if isinstance(name, str) else getattr(item, "__name__", repr(item))


def documents(root: Path) -> dict[str, JsonObject]:
    result: dict[str, JsonObject] = {}
    for path in root.rglob("*.json"):
        doc: JsonObject = json.loads(path.read_text())
        if "$id" in doc:
            result[str(doc["$id"])] = doc
    return result


CURRENT = documents(SCHEMAS)
EXAMPLES = documents(ROOT / "tests/fixtures/corpus/examples/schemas")
REGISTRY = Registry[Schema]().with_resources(
    (urn, Resource[Schema].from_contents(doc)) for urn, doc in CURRENT.items()
)
GROUP_SCHEMAS = {urn: doc for urn, doc in CURRENT.items() if urn.split(":")[2] in GROUPS}


@pytest.mark.parametrize("module", GROUPS)
def test_module_contracts_import_and_register_only_implemented_operations(module: str) -> None:
    for path in (MODULES / module).rglob("*.py"):
        if "tests" not in path.parts:
            importlib.import_module(".".join(path.relative_to(ROOT / "src").with_suffix("").parts))
    manifest = cast(ModuleManifest, importlib.import_module(f"skm.modules.{module}.module").MODULE)
    assert manifest.depends_on == DEPENDENCIES[module]
    assert manifest.settings_sections == (module,)
    assert manifest.db_schema == "skm_" + module
    assert not manifest.optional
    implemented = IMPLEMENTED.get(module, {})
    for field in ("commands", "queries", "events", "host_operations"):
        registered = tuple(_name(item) for item in getattr(manifest, field))
        assert registered == implemented.get(field, ()), f"{module}.{field}"
    assert not manifest.subscribers
    for port in manifest.repository_ports:
        assert getattr(port, PORT_KIND_ATTRIBUTE) == "repository"
    for port in manifest.gateway_ports:
        assert getattr(port, PORT_KIND_ATTRIBUTE) in {
            "host_gateway",
            "control_plane_gateway",
            "shared_gateway",
        }
    event_types = importlib.import_module(f"skm.modules.{module}.domain.events").EVENT_TYPES
    assert set(event_types) == {urn for urn in GROUP_SCHEMAS if urn.startswith(f"urn:skm:{module}:event:")}


@pytest.mark.parametrize("urn", sorted(GROUP_SCHEMAS))
def test_schema_syntax_and_every_reference_target(urn: str) -> None:
    document = GROUP_SCHEMAS[urn]
    Draft202012Validator.check_schema(document)

    def walk(value: object) -> None:
        if isinstance(value, dict):
            node = cast(dict[str, object], value)
            if "$ref" in node:
                target_urn, _, fragment = str(node["$ref"]).partition("#")
                # Future groups must have a known normative owner; no network retrieve.
                target = (EXAMPLES | CURRENT)[target_urn] if target_urn else document
                resolved: object = target
                for key in fragment.split("/")[1:]:
                    assert isinstance(resolved, dict)
                    resolved = cast(dict[str, object], resolved)[key.replace("~1", "/").replace("~0", "~")]
            for child in node.values():
                walk(child)
        elif isinstance(value, list):
            for child in cast(list[object], value):
                walk(child)

    walk(document)


def validator_for(urn: str) -> Validator:
    return Draft202012Validator(CURRENT[urn], registry=REGISTRY)


def validate(urn: str, value: JsonObject) -> None:
    validator_for(urn).validate(value)


@pytest.mark.parametrize("source", [{"revision_id": UUID}, {"draft_id": UUID, "expected_edit_version": 1}])
def test_entity_read_accepts_exactly_one_source(source: JsonObject) -> None:
    validate("urn:skm:planning:query:list-entities:v1", {"plan_id": UUID, **source})


@pytest.mark.parametrize(
    "source",
    [
        {},
        {"draft_id": UUID},
        {"revision_id": UUID, "draft_id": UUID, "expected_edit_version": 1},
        {"revision_id": UUID, "expected_edit_version": 1},
        {"draft_id": UUID, "expected_edit_version": 0},
    ],
)
def test_entity_read_rejects_missing_mixed_or_unversioned_source(source: JsonObject) -> None:
    with pytest.raises(ValidationError):
        validate("urn:skm:planning:query:list-entities:v1", {"plan_id": UUID, **source})


def test_save_requires_one_change_form() -> None:
    base: JsonObject = {"plan_id": UUID, "draft_id": UUID, "expected_edit_version": 1}
    validate("urn:skm:planning:command:save-draft:v1", {**base, "merge_patch": {"title": "New"}})
    for invalid in (base, {**base, "merge_patch": {}, "changes": []}):
        with pytest.raises(ValidationError):
            validate("urn:skm:planning:command:save-draft:v1", invalid)


def test_publish_requires_prepared_content_digest() -> None:
    base: JsonObject = {"plan_id": UUID, "draft_id": UUID, "expected_edit_version": 1, "reason": "publish"}
    validate("urn:skm:planning:command:publish-revision:v1", {**base, "expected_content_digest": DIGEST})
    with pytest.raises(ValidationError):
        validate("urn:skm:planning:command:publish-revision:v1", base)


def test_pack_install_disallows_builtin_trust_from_surface() -> None:
    request: JsonObject = {"payload": {"manifest_text": "", "files": []}, "origin_label": "path:pack"}
    validate("urn:skm:extensions:command:install-pack:v1", request)
    with pytest.raises(ValidationError):
        validate("urn:skm:extensions:command:install-pack:v1", {**request, "trust": "builtin"})


def test_push_intent_disallows_force() -> None:
    request: JsonObject = {
        "repository_id": UUID,
        "remote": "example.com/repo",
        "target_ref": "refs/heads/main",
        "before_sha": "a" * 40,
        "after_sha": "b" * 40,
        "refspecs": ["refs/heads/main:refs/heads/main"],
        "force": False,
        "endpoint": {
            "transport": "https",
            "hostname": "example.com",
            "effective_port": 443,
            "repository_path": "repo",
        },
        "binding_identity": {
            "binding_id": UUID,
            "host_id": UUID,
            "repository_id": UUID,
            "locator_digest": DIGEST,
        },
    }
    validate("urn:skm:policy:intent-args-git-push:v1", request)
    with pytest.raises(ValidationError):
        validate("urn:skm:policy:intent-args-git-push:v1", {**request, "force": True})


def proposal() -> JsonObject:
    return {"scope_id": UUID, "subject_ref": "run:test", "kind": "pr_create", "args": {}, "reason": "Review"}


@pytest.mark.parametrize("name", ["profile_id", "role_layer", "task_layer"])
def test_proposal_accepts_explicit_null_composition_input(name: str) -> None:
    validate("urn:skm:policy:command:propose-intent:v1", {**proposal(), name: None})


@pytest.mark.parametrize("name", ["role_layer", "task_layer"])
@pytest.mark.parametrize("layer", [{}, {"network": {"mode": "none"}}])
def test_proposal_accepts_permission_layers(name: str, layer: JsonObject) -> None:
    validate("urn:skm:policy:command:propose-intent:v1", {**proposal(), name: layer})


@pytest.mark.parametrize("name", ["role_layer", "task_layer"])
@pytest.mark.parametrize("layer", [False, 1, "read-only", [], {"unknown": True}])
def test_proposal_rejects_invalid_permission_layers(name: str, layer: JsonValue) -> None:
    with pytest.raises(ValidationError):
        validate("urn:skm:policy:command:propose-intent:v1", {**proposal(), name: layer})


def test_proposal_remains_closed() -> None:
    with pytest.raises(ValidationError):
        validate("urn:skm:policy:command:propose-intent:v1", {**proposal(), "unknown": None})


def pr_intent() -> JsonObject:
    return {
        "repository_id": UUID,
        "base": "main",
        "head": "feature",
        "title_digest": DIGEST,
        "body_digest": DIGEST,
        "endpoint": {
            "transport": "https",
            "hostname": "api.example.com",
            "effective_port": 443,
            "repository_path": "/org/repo",
        },
        "binding_identity": {
            "binding_id": UUID,
            "host_id": UUID,
            "repository_id": UUID,
            "locator_digest": DIGEST,
        },
    }


def test_pr_intent_accepts_pinned_endpoint_and_binding() -> None:
    validate("urn:skm:policy:intent-args-pr-create:v1", pr_intent())


@pytest.mark.parametrize("field", ["endpoint", "binding_identity"])
def test_pr_intent_requires_endpoint_and_binding(field: str) -> None:
    request = pr_intent()
    del request[field]
    with pytest.raises(ValidationError):
        validate("urn:skm:policy:intent-args-pr-create:v1", request)


@pytest.mark.parametrize(
    ("field", "member"),
    [
        ("endpoint", "transport"),
        ("endpoint", "hostname"),
        ("endpoint", "effective_port"),
        ("endpoint", "repository_path"),
        ("binding_identity", "binding_id"),
        ("binding_identity", "host_id"),
        ("binding_identity", "repository_id"),
        ("binding_identity", "locator_digest"),
    ],
)
def test_pr_intent_rejects_incomplete_endpoint_or_binding(field: str, member: str) -> None:
    request = pr_intent()
    nested = request[field]
    assert isinstance(nested, dict)
    del nested[member]
    with pytest.raises(ValidationError):
        validate("urn:skm:policy:intent-args-pr-create:v1", request)


@pytest.mark.parametrize(
    ("field", "member", "value"),
    [
        ("binding_identity", "locator_digest", "c" * 64),
        ("binding_identity", "locator_digest", None),
        ("binding_identity", "local_locator", "/checkout"),
        ("endpoint", "credentials", "secret"),
        ("endpoint", "userinfo", "user:secret"),
    ],
)
def test_pr_intent_rejects_invalid_digest_and_unexpected_sensitive_fields(
    field: str, member: str, value: JsonValue
) -> None:
    request = deepcopy(pr_intent())
    nested = request[field]
    assert isinstance(nested, dict)
    nested[member] = value
    with pytest.raises(ValidationError):
        validate("urn:skm:policy:intent-args-pr-create:v1", request)
