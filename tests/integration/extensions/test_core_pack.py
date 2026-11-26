"""Integration tests for the built-in ``core`` pack (P09.02.a; extensions §4.6-§4.8, context §5.10, §17.7).

Exercises the real ``resources/packs/core`` payload through ``PackagedBuiltinPacks``, ``SyncBuiltinPacks`` on
the real bus, ``extensions.public`` resolution/pinning, workflow and model-catalog parsers, and wheel layout
packaging at ``skm/_resources/packs/core`` without repository paths.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
import zipfile
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from contracts.extensions.harness import (
    NOW,
    ExtensionsWorld,
    FakeEstimator,
    build_world,
)
from fakes.app import FakeScopeChain
from fakes.clock import FrozenClock
from fakes.entropy import DeterministicEntropy
from fakes.ids import SequentialIds
from skm.adapters.memory.access import REPOSITORIES as MEMORY_ACCESS
from skm.adapters.memory.config_store import MemoryConfigStore
from skm.adapters.memory.core import REPOSITORIES as MEMORY_CORE
from skm.adapters.memory.extensions import REPOSITORIES as MEMORY_EXTENSIONS
from skm.adapters.memory.settings import REPOSITORIES as MEMORY_SETTINGS
from skm.adapters.memory.uow import InMemoryBackend
from skm.adapters.memory.workspace import REPOSITORIES as MEMORY_WORKSPACE
from skm.adapters.resources.builtin_packs import PackagedBuiltinPacks
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.ports import Authorizer
from skm.application_bus.registry import BusRegistry
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, PreconditionFailed
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import ProjectId, ResourceVersionId, ScopeId, WorkspaceId
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.kernel.tokens import TokenEstimator
from skm.modules.access.module import MODULE as ACCESS
from skm.modules.access.ports import TokenPepperSource
from skm.modules.access.public import RbacAuthorizer, Role
from skm.modules.execution.domain.workflow.definition import parse_workflow
from skm.modules.extensions import public
from skm.modules.extensions.application.candidate import DEFAULT_ALLOWED_LICENSES, build_candidate
from skm.modules.extensions.application.install import product_version
from skm.modules.extensions.domain.compat import CompatCheckId, CompatStatus, CompatVerdict
from skm.modules.extensions.domain.keys import SemVer
from skm.modules.extensions.domain.kinds import ResourceKind
from skm.modules.extensions.domain.pack import PackState, PackTrust
from skm.modules.extensions.domain.payload import PackPayload, PayloadFile
from skm.modules.extensions.generated.commands import SyncBuiltinPacks
from skm.modules.extensions.module import MODULE as EXTENSIONS
from skm.modules.extensions.ports import BuiltinPacks
from skm.modules.policy.module import MODULE as POLICY
from skm.modules.runtimes.domain.catalog import parse_pricing
from skm.modules.runtimes.generated.documents import model_catalog_from_json
from skm.modules.settings.generated.commands import SetValue, SetValueDefsScopeRef
from skm.modules.settings.module import MODULE as SETTINGS
from skm.modules.workspace.module import MODULE as WORKSPACE
from skm.modules.workspace.public import CreateProject, CreateWorkspace
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.store import ConfigStore, PackConfigSource
from skm.platform.schema.registry import SchemaRegistry
from unit.policy.application.harness import (
    EVERYTHING,
    INSTANCE,
    FixedPepper,
    Packs,
    schemas,
    settings_registry,
)

ROOT = Path(__file__).resolve().parents[3]
PACKS_ROOT = ROOT / "resources" / "packs"
CORE_ROOT = PACKS_ROOT / "core"

ROLES = ("scout", "executor", "reviewer", "triager", "advisor", "researcher", "registrar")
EXPECTED_PROFILES = frozenset((*ROLES, "executor-transparent", "security", "advisor-critic", "plan-auditor"))
EXPECTED_WORKFLOWS = frozenset(
    ("reviewed-development", "quick-fix", "research-only", "review-only", "plan-audit")
)
EXPECTED_SHARED_PROMPTS = frozenset(
    (
        "shared/block_wrapper",
        "shared/raw_block",
        "shared/resume_note",
        "shared/run_rules",
        "shared/system_constraints",
        "shared/task_contract",
        "shared/work_policy",
    )
)
EXPECTED_ROLE_PROMPTS = frozenset(
    (
        "advisor/critic",
        "advisor/plan_auditor",
        "advisor/result_contract",
        "advisor/role",
        "executor/result_contract",
        "executor/role",
        "executor/task_contract",
        "registrar/result_contract",
        "registrar/role",
        "researcher/result_contract",
        "researcher/role",
        "reviewer/result_contract",
        "reviewer/role",
        "reviewer/security",
        "scout/result_contract",
        "scout/role",
        "triager/result_contract",
        "triager/role",
    )
)
EXPECTED_INSTRUCTION_PROMPTS = frozenset(("instructions/client-core",))
EXPECTED_PROMPTS = EXPECTED_SHARED_PROMPTS | EXPECTED_ROLE_PROMPTS | EXPECTED_INSTRUCTION_PROMPTS
EXPECTED_SKILLS = frozenset(("code-review", "review-checklist", "research-method", "security-review"))
EXPECTED_PLAN_TEMPLATES = frozenset(("feature", "bugfix"))
EXPECTED_MODEL_GUIDELINES = frozenset(
    (
        "claude-opus-5-5",
        "claude-sonnet-5-5",
        "gpt-6-astra",
        "gpt-6-sol",
        "gpt-6-luna",
        "gemini-4-neon",
        "gemini-4-carbon",
        "gemini-4-argon",
        "gemini-4-hydrogen",
        "gemini-3-8-flash",
        "grok-4-7",
        "gpt-oss-120b",
    )
)
ALLOWED_VAR_NAMESPACES = frozenset(
    ("task", "plan", "run", "role", "permissions", "runtime", "workspace", "attempt", "raw", "block")
)
TEMPLATE_VAR_RE = re.compile(r"\{\{\s*([a-z_]+\.[a-z0-9_]+)\s*\}\}")
JSON_FENCE_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FORBIDDEN_PERSONAL_TOKENS = ("fable", "gpt-6.1-sol", "/home/", "working/examples", "working/spec")


def _world_with_packaged_gateway() -> ExtensionsWorld:
    """Wire the production ``PackagedBuiltinPacks`` adapter directly onto the command bus."""
    registry = BusRegistry.build(
        (ACCESS, WORKSPACE, SETTINGS, POLICY, EXTENSIONS),
        schemas=schemas(),
        permission_catalog=EVERYTHING,
        disabled_modules=frozenset(),
    )
    clock, ids, entropy = FrozenClock(NOW), SequentialIds(), DeterministicEntropy()
    packs, authorizer = Packs(), RbacAuthorizer(clock)
    factories: dict[type, Callable[[Any], object]] = {
        **MEMORY_CORE,
        **MEMORY_ACCESS,
        **MEMORY_WORKSPACE,
        **MEMORY_SETTINGS,
        **MEMORY_EXTENSIONS,
        ConfigStore: MemoryConfigStore,
        PackConfigSource: lambda _state: packs,
        Authorizer: lambda _state: authorizer,
    }
    backend = InMemoryBackend(
        factories=factories,
        schemas=schemas(),
        subscriptions=registry.subscription_index(),
        ids=ids,
        clock=clock,
    )
    loader = ConfigLoader(settings_registry(), packs)
    bus = Bus(
        registry=registry,
        schemas=schemas(),
        uow_factory=backend.uow_factory(),
        authorizer=authorizer,
        scopes=FakeScopeChain(),
        config=loader,
        clock=clock,
        ids=ids,
        entropy=entropy,
        gateways=GatewayTable(
            {
                TokenPepperSource: FixedPepper(),
                TokenEstimator: FakeEstimator(),
                BuiltinPacks: PackagedBuiltinPacks(PACKS_ROOT),
            },
            "control_plane_gateway",
        ),
        retry=RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
        idempotency_ttl=timedelta(hours=1),
    )
    world = ExtensionsWorld(backend, bus, clock, ids, loader)
    with world.uow() as uow:
        uow.repo(ScopeRegistry).create(INSTANCE, ScopeKind.INSTANCE, parent=None, workspace_id=None)
        uow.commit()
    world.person("owner", {INSTANCE: Role.OWNER})
    world.workspace_id = WorkspaceId(
        world.run(CreateWorkspace(slug="personal", title="Personal")).workspace_id
    )
    world.project_id = ProjectId(
        world.run(CreateProject(workspace_id=world.workspace_id, slug="skm", title="SKM")).project_id
    )
    plan, run = ScopeId(world.ids.new_id()), ScopeId(world.ids.new_id())
    with world.uow() as uow:
        scopes = uow.repo(ScopeRegistry)
        scopes.create(plan, ScopeKind.PLAN, parent=ScopeId(world.project_id), workspace_id=world.workspace_id)
        scopes.create(run, ScopeKind.RUN, parent=plan, workspace_id=world.workspace_id)
        uow.commit()
    world.scope_id = run
    return world


@pytest.fixture
def synced_world() -> ExtensionsWorld:
    world = build_world(PackagedBuiltinPacks(PACKS_ROOT).payloads()[0])
    world.run(SyncBuiltinPacks())
    return world


def _upgraded_core_payload(base: PackPayload, version: str) -> PackPayload:
    """Derive a later core pack to verify ``PackPins`` immutability."""
    current = tomllib.loads(base.manifest_text)["version"]
    manifest_text = base.manifest_text.replace(f'version = "{current}"', f'version = "{version}"', 1)
    updated_files: list[PayloadFile] = []
    for item in base.files:
        text = item.content.decode("utf-8")
        if item.path == "agent-profiles/executor.toml":
            text = text.replace('version = "2.0.0"', f'version = "{version}"', 1)
            text = text.replace('title = "Executor"', f'title = "Executor {version}"', 1)
        elif item.path == "workflows/reviewed-development.toml":
            text = text.replace('version = "2.0.0"', f'version = "{version}"', 1)
        elif item.path == "prompts/shared/work_policy.md":
            text = f"{text}\nUpdated work-policy note in {version}.\n"
        elif item.path == "runtimes/models.toml":
            text = text.replace('catalog_version = "2.0.2"', f'catalog_version = "{version}"', 1)
        updated_files.append(PayloadFile(item.path, text.encode("utf-8")))
    return PackPayload(manifest_text=manifest_text, files=tuple(updated_files))


def _build_wheel_from_pyproject(wheel_path: Path, wheel_cfg: dict[str, Any]) -> None:
    """Materialize a wheel archive using ``[tool.hatch.build.targets.wheel]`` mappings."""
    sources: dict[str, str] = wheel_cfg["sources"]
    only_include: list[str] = wheel_cfg["only-include"]
    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for include_entry in only_include:
            src_target = ROOT / include_entry
            files = [src_target] if src_target.is_file() else sorted(src_target.rglob("*"))
            for file_path in files:
                if not file_path.is_file() or "__pycache__" in file_path.parts or file_path.suffix == ".pyc":
                    continue
                rel_posix = file_path.relative_to(ROOT).as_posix()
                arcname = rel_posix
                for prefix, replacement in sources.items():
                    if rel_posix == prefix or rel_posix.startswith(f"{prefix}/"):
                        suffix = rel_posix[len(prefix) :].lstrip("/")
                        arcname = f"{replacement}/{suffix}".lstrip("/") if replacement else suffix
                        break
                archive.write(file_path, arcname)


@pytest.mark.integration
def test_builtin_sync_core_pack() -> None:
    world = _world_with_packaged_gateway()
    first = world.run(SyncBuiltinPacks())
    manifest = tomllib.loads((CORE_ROOT / "pack.toml").read_text(encoding="utf-8"))
    assert (first.installed[0].slug, first.installed[0].version) == ("core", manifest["version"])
    assert len(first.installed) == 29
    assert first.already_installed == ()

    tables = world.tables()
    expected_total = (
        len(EXPECTED_PROFILES)
        + len(EXPECTED_WORKFLOWS)
        + len(EXPECTED_PROMPTS)
        + len(EXPECTED_SKILLS)
        + len(EXPECTED_PLAN_TEMPLATES)
        + 1
        + len(EXPECTED_MODEL_GUIDELINES)
    )
    assert (len(tables.packs), len(tables.pack_versions)) == (29, 29)
    (pack,) = (item for item in tables.packs.values() if item.slug == "core")
    assert pack.trust is PackTrust.BUILTIN
    assert all(item.trust is PackTrust.THIRD_PARTY for item in tables.packs.values() if item.slug != "core")
    (pack_version,) = (item for item in tables.pack_versions.values() if item.pack_id == pack.id)
    core_versions = [item for item in tables.versions.values() if item.pack_version_id == pack_version.id]
    assert len(core_versions) == expected_total == 61
    assert (pack_version.origin, pack_version.state) == ("builtin", PackState.ACTIVE)
    assert (pack_version.manifest.priority, pack_version.manifest.license) == (0, "Apache-2.0")
    assert pack_version.manifest.requires_skm.matches(product_version())
    assert len(pack_version.manifest.config) == 9
    assert pack_version.manifest.config["ecosystems.ids"] == [
        "python",
        "node",
        "php",
        "cargo",
        "go",
        "ruby",
        "brew",
        "dart",
        "jvm",
    ]

    expected_checks = dict.fromkeys(CompatCheckId, CompatStatus.OK)
    for version in core_versions:
        assert version.compat.verdict is CompatVerdict.CLEAN
        assert {check.id: check.status for check in version.compat.checks} == expected_checks
        assert all(check.detail != "not scanned" for check in version.compat.checks)

    with world.uow() as uow:
        groups = public.exclusive_groups(uow, config=world.config(uow))
    assert set(groups) == {"review-method", "python-testing", "research-method"}

    events_before = len(world.backend.committed.core.events)
    second = world.run(SyncBuiltinPacks())
    assert second.installed == ()
    assert [(item.slug, item.version) for item in second.already_installed] == [
        (item.slug, item.version) for item in first.installed
    ]
    assert world.tables().versions == tables.versions
    new_ext_events = [
        e for e in world.backend.committed.core.events[events_before:] if ":extensions:event:" in e.type
    ]
    assert new_ext_events == []


@pytest.mark.integration
def test_mandatory_resources_resolvable(synced_world: ExtensionsWorld) -> None:
    schema_reg = SchemaRegistry.load_default()
    with synced_world.uow() as uow:
        config = synced_world.config(uow)
        assert public.known_keys(uow, ResourceKind.AGENT_PROFILE, config=config) == EXPECTED_PROFILES
        assert public.known_keys(uow, ResourceKind.WORKFLOW, config=config) == EXPECTED_WORKFLOWS
        assert public.known_keys(uow, ResourceKind.PROMPT_BLOCK, config=config) == EXPECTED_PROMPTS
        assert public.known_keys(uow, ResourceKind.SKILL, config=config) == EXPECTED_SKILLS
        assert public.known_keys(uow, ResourceKind.PLAN_TEMPLATE, config=config) == EXPECTED_PLAN_TEMPLATES
        assert public.known_keys(uow, ResourceKind.RUNTIME_CATALOG, config=config) == frozenset({"models"})
        guidelines = public.known_keys(uow, ResourceKind.MODEL_GUIDELINE, config=config)
        assert guidelines == EXPECTED_MODEL_GUIDELINES

        for key in sorted(EXPECTED_SKILLS):
            skill_view = public.resolve_resource(uow, ResourceKind.SKILL, key, config=config)
            assert (skill_view.key, skill_view.version) == (key, "2.0.0")
            assert skill_view.manifest["schema"] == "urn:skm:extensions:skill-manifest:v1"
            assert skill_view.manifest["key"] == key

        for key in sorted(EXPECTED_PLAN_TEMPLATES):
            pt_view = public.resolve_resource(uow, ResourceKind.PLAN_TEMPLATE, key, config=config)
            assert (pt_view.key, pt_view.version) == (key, "2.0.0")
            assert pt_view.manifest["schema"] == "urn:skm:extensions:plan-template:v1"
            assert pt_view.manifest["key"] == key

        for key in sorted(EXPECTED_WORKFLOWS):
            wf_view = public.resolve_resource(uow, ResourceKind.WORKFLOW, key, config=config)
            workflow, violations = parse_workflow(dict(wf_view.manifest))
            assert violations == ()
            assert workflow is not None
            assert workflow.id == key
            for required_role in workflow.requires_roles:
                public.select_agent_profile(uow, required_role.value, stage_profile=None, config=config)
            for stage in workflow.stages:
                if stage.role is not None:
                    public.select_agent_profile(
                        uow, stage.role.value, stage_profile=stage.params.profile, config=config
                    )

        for key in sorted(EXPECTED_PROMPTS):
            prompt_view = public.resolve_resource(uow, ResourceKind.PROMPT_BLOCK, key, config=config)
            meta, body = public.load_text_resource(uow, ResourceVersionId(prompt_view.resource_version_id))
            assert meta["schema"] == "urn:skm:extensions:prompt-block:v1"
            assert body.strip() != ""
            declared = set(cast("list[str]", meta["variables"]))
            assert declared == set(TEMPLATE_VAR_RE.findall(body))
            assert {var.split(".", 1)[0] for var in declared} <= ALLOWED_VAR_NAMESPACES

        for role in ROLES:
            urn = f"urn:skm:execution:role-result:{role}:v1"
            rc_view = public.resolve_resource(
                uow, ResourceKind.PROMPT_BLOCK, f"{role}/result_contract", config=config
            )
            _meta, rc_body = public.load_text_resource(uow, ResourceVersionId(rc_view.resource_version_id))
            matches = JSON_FENCE_RE.findall(rc_body)
            assert len(matches) == 1
            rendered_snippet = matches[0].replace("{{ role.result_schema }}", urn)
            assert schema_reg.validate(urn, json.loads(rendered_snippet)) == ()

        resolved_cat = public.resolve_resource(uow, ResourceKind.RUNTIME_CATALOG, "models", config=config)
        catalog_view = public.runtime_catalog(uow, (), config)

    assert catalog_view is not None
    assert len(catalog_view.entries) == 1
    entry = catalog_view.entries[0]
    assert (entry.resource_version_id, entry.key) == (resolved_cat.resource_version_id, "models")
    parsed = model_catalog_from_json(entry.manifest)
    assert parsed["catalog_version"] == "2.0.2"
    assert set(parsed["runtimes"]) == {"antigravity", "claude_code", "codex", "grok", "cursor", "gemini_cli"}
    codex_catalog = parsed["runtimes"]["codex"]
    assert "gpt-6.1-terra" in {model["id"] for model in codex_catalog["models"]}
    assert codex_catalog["class_selectors"]["implementation"] == ["gpt-6-sol"]
    for runtime_entry in parsed["runtimes"].values():
        assert len(runtime_entry["models"]) >= 1
        for model in runtime_entry["models"]:
            assert ISO_DATE_RE.match(model["verified_at"])
            assert parse_pricing(model.get("pricing")) is None

    for file_path in sorted(CORE_ROOT.rglob("*")):
        if file_path.is_file() and file_path != CORE_ROOT / "README.md":
            content = file_path.read_text(encoding="utf-8")
            for forbidden in FORBIDDEN_PERSONAL_TOKENS:
                assert forbidden not in content, f"forbidden token {forbidden!r} in {file_path}"


@pytest.mark.integration
def test_agent_profile_selection_and_role_mismatch(synced_world: ExtensionsWorld) -> None:
    with synced_world.uow() as uow:
        config = synced_world.config(uow)
        pins = public.pinned_pack_versions(uow, config=config)
        for role in ROLES:
            selected = public.select_agent_profile(uow, role, stage_profile=None, config=config)
            assert (selected.key, selected.version) == (role, "2.0.0")
            assert selected.pack_version_id == pins["core"]
            parsed = public.load_agent_profile(uow, ResourceVersionId(selected.resource_version_id))
            assert parsed.role == role
            assert parsed.result_schema == f"urn:skm:execution:role-result:{role}:v1"

        transparent = public.select_agent_profile(
            uow, "executor", stage_profile="executor-transparent", config=config
        )
        assert transparent.key == "executor-transparent"

        security = public.select_agent_profile(uow, "reviewer", stage_profile="security", config=config)
        assert security.key == "security"

        critic = public.select_agent_profile(uow, "advisor", stage_profile="advisor-critic", config=config)
        assert critic.key == "advisor-critic"

        auditor = public.select_agent_profile(uow, "advisor", stage_profile="plan-auditor", config=config)
        assert auditor.key == "plan-auditor"

        for key in sorted(EXPECTED_PROFILES):
            view = public.resolve_resource(uow, ResourceKind.AGENT_PROFILE, key, config=config)
            profile = public.load_agent_profile(uow, ResourceVersionId(view.resource_version_id))
            assert (profile.context["inherit_user_global"] is True) == (key == "executor-transparent")
            assert (profile.llm is False) == (key == "registrar")
            expected_policy = (
                "workspace-contained" if key in {"executor", "executor-transparent"} else "read-only"
            )
            assert profile.permissions.policy_profile == expected_policy
            if key == "registrar":
                assert profile.permissions.layer == {"tools": {"allow": []}}
            for block_keys in profile.prompt.blocks.values():
                for block_key in block_keys:
                    public.resolve_resource(uow, ResourceKind.PROMPT_BLOCK, block_key, config=config)

        with pytest.raises(PreconditionFailed) as stage_mismatch:
            public.select_agent_profile(uow, "reviewer", stage_profile="executor", config=config)
        assert stage_mismatch.value.code is ErrorCode.EXTENSION_PROFILE_ROLE_MISMATCH

        with pytest.raises(PreconditionFailed) as security_mismatch:
            public.select_agent_profile(uow, "executor", stage_profile="security", config=config)
        assert security_mismatch.value.code is ErrorCode.EXTENSION_PROFILE_ROLE_MISMATCH

    scope = SetValueDefsScopeRef(level="workspace", scope_id=synced_world.workspace_id)
    synced_world.run(
        SetValue(scope=scope, key="extensions.role_profiles", value={"executor": "executor-transparent"})
    )
    with synced_world.uow() as uow:
        overridden = public.select_agent_profile(
            uow, "executor", stage_profile=None, config=synced_world.config(uow)
        )
        assert overridden.key == "executor-transparent"

    synced_world.run(SetValue(scope=scope, key="extensions.role_profiles", value={"reviewer": "executor"}))
    with synced_world.uow() as uow, pytest.raises(PreconditionFailed) as config_mismatch:
        public.select_agent_profile(uow, "reviewer", stage_profile=None, config=synced_world.config(uow))
    assert config_mismatch.value.code is ErrorCode.EXTENSION_PROFILE_ROLE_MISMATCH


@pytest.mark.integration
def test_work_policy_intensity_tiers_and_invariance(synced_world: ExtensionsWorld) -> None:
    expected_vars = {
        "role.name",
        "role.intensity",
        "role.warn_seconds",
        "role.emergency_wall_seconds",
        "run.verification_intensity",
        "task.work_policy_digest",
    }
    with synced_world.uow() as uow:
        config = synced_world.config(uow)
        for profile_key in sorted(EXPECTED_PROFILES):
            view = public.resolve_resource(uow, ResourceKind.AGENT_PROFILE, profile_key, config=config)
            profile = public.load_agent_profile(uow, ResourceVersionId(view.resource_version_id))
            assert "shared/work_policy" in profile.prompt.blocks.get("task_contract", ())

        wp_view = public.resolve_resource(uow, ResourceKind.PROMPT_BLOCK, "shared/work_policy", config=config)
        meta, body = public.load_text_resource(uow, ResourceVersionId(wp_view.resource_version_id))
        assert set(cast("list[str]", meta["variables"])) == expected_vars
        for tier in ("- Light:", "- Medium:", "- Heavy:"):
            assert tier in body
        lowered = body.lower()
        for invariant_phrase in (
            "required checks",
            "review independence",
            "security review",
            "acceptance criteria",
            "write scope",
            "permissions",
            "separate emergency wall ceiling",
        ):
            assert invariant_phrase in lowered


@pytest.mark.integration
def test_pack_pins_immutability_on_core_upgrade(synced_world: ExtensionsWorld) -> None:
    current_core = synced_world.builtin.current[0]
    with synced_world.uow() as uow:
        config = synced_world.config(uow)
        pins = public.pinned_pack_versions(uow, config=config)
        base_profile = public.select_agent_profile(uow, "executor", stage_profile=None, config=config)
        base_workflow = public.resolve_resource(
            uow, ResourceKind.WORKFLOW, "reviewed-development", config=config
        )
        base_policy = public.resolve_resource(
            uow, ResourceKind.PROMPT_BLOCK, "shared/work_policy", config=config
        )
        base_catalog = public.runtime_catalog(uow, (), config)
        base_profiles_list = public.list_resolved(uow, ResourceKind.AGENT_PROFILE, config=config)

    assert base_catalog is not None
    current_version = SemVer.parse(tomllib.loads(current_core.manifest_text)["version"])
    next_version = str(SemVer(current_version.major, current_version.minor + 1, 0))
    next_core = _upgraded_core_payload(current_core, next_version)
    synced_world.builtin.current = (replace(next_core, manifest_text=current_core.manifest_text),)
    with pytest.raises(Conflict) as conflict:
        synced_world.run(SyncBuiltinPacks())
    assert conflict.value.code is ErrorCode.EXTENSION_DIGEST_CONFLICT

    synced_world.builtin.current = (current_core, next_core)
    upgrade_sync = synced_world.run(SyncBuiltinPacks())
    assert [(item.slug, item.version) for item in upgrade_sync.installed] == [("core", next_version)]
    assert [(item.slug, item.version) for item in upgrade_sync.already_installed] == [
        ("core", str(current_version))
    ]

    with synced_world.uow() as uow:
        config = synced_world.config(uow)
        latest_profile = public.select_agent_profile(uow, "executor", stage_profile=None, config=config)
        latest_workflow = public.resolve_resource(
            uow, ResourceKind.WORKFLOW, "reviewed-development", config=config
        )
        latest_policy = public.resolve_resource(
            uow, ResourceKind.PROMPT_BLOCK, "shared/work_policy", config=config
        )
        latest_catalog = public.runtime_catalog(uow, (), config)

        pinned_profile = public.select_agent_profile(
            uow, "executor", stage_profile=None, config=config, pins=pins
        )
        pinned_workflow = public.resolve_resource(
            uow, ResourceKind.WORKFLOW, "reviewed-development", config=config, pins=pins
        )
        pinned_policy = public.resolve_resource(
            uow, ResourceKind.PROMPT_BLOCK, "shared/work_policy", config=config, pins=pins
        )
        pinned_catalog = public.runtime_catalog(uow, (), config, pins=pins)
        pinned_profiles_list = public.list_resolved(uow, ResourceKind.AGENT_PROFILE, config=config, pins=pins)

    assert latest_catalog is not None
    assert pinned_catalog is not None
    assert (latest_profile.version, latest_workflow.version) == (next_version, next_version)
    assert latest_profile.digest != base_profile.digest
    assert latest_policy.digest != base_policy.digest
    assert latest_catalog.digest != base_catalog.digest

    assert (pinned_profile.resource_version_id, pinned_profile.digest) == (
        base_profile.resource_version_id,
        base_profile.digest,
    )
    assert (pinned_workflow.resource_version_id, pinned_workflow.digest) == (
        base_workflow.resource_version_id,
        base_workflow.digest,
    )
    assert (pinned_policy.resource_version_id, pinned_policy.digest) == (
        base_policy.resource_version_id,
        base_policy.digest,
    )
    assert pinned_catalog.digest == base_catalog.digest
    assert [v.resource_version_id for v in pinned_profiles_list] == [
        v.resource_version_id for v in base_profiles_list
    ]


@pytest.mark.integration
def test_wheel_packaging_has_no_repo_paths(tmp_path: Path) -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    wheel_cfg = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert "src/skm" in wheel_cfg["only-include"]
    assert "resources" in wheel_cfg["only-include"]
    assert wheel_cfg["sources"]["src"] == ""
    assert wheel_cfg["sources"]["resources"] == "skm/_resources"

    version = pyproject["project"]["version"]
    wheel_path = tmp_path / f"skm-{version}-py3-none-any.whl"
    _build_wheel_from_pyproject(wheel_path, wheel_cfg)

    core_payload = PackagedBuiltinPacks(PACKS_ROOT).payloads()[0]
    expected_candidate = build_candidate(
        core_payload,
        estimator=FakeEstimator(),
        scan=True,
        allowed_licenses=DEFAULT_ALLOWED_LICENSES,
    )
    repo_root_str = str(ROOT)
    site_dir = tmp_path / "site"
    with zipfile.ZipFile(wheel_path) as archive:
        names = set(archive.namelist())
        assert "skm/_resources/packs/core/pack.toml" in names
        sub_readmes = [
            name
            for name in names
            if name.startswith("skm/_resources/packs/core/")
            and name.endswith("/README.md")
            and name != "skm/_resources/packs/core/README.md"
        ]
        assert sub_readmes == []
        for payload_file in core_payload.files:
            assert f"skm/_resources/packs/core/{payload_file.path}" in names
        for name in sorted(names):
            if name.startswith("skm/_resources/"):
                assert repo_root_str not in archive.read(name).decode("utf-8")
        archive.extractall(site_dir)

    probe = (
        "import json\n"
        "from pathlib import Path\n"
        "import skm\n"
        "from skm.adapters.resources.builtin_packs import PackagedBuiltinPacks\n"
        "from skm.modules.extensions.application.candidate import DEFAULT_ALLOWED_LICENSES, build_candidate\n"
        "class _Est:\n"
        "    estimator_id = 'fake'\n"
        "    def estimate(self, text: str) -> int: return len(text)\n"
        "payloads = PackagedBuiltinPacks().payloads()\n"
        "cand = build_candidate(\n"
        "    payloads[0], estimator=_Est(), scan=True, allowed_licenses=DEFAULT_ALLOWED_LICENSES\n"
        ")\n"
        "print(json.dumps({\n"
        "    'skm_file': str(Path(skm.__file__).resolve()),\n"
        "    'count': len(payloads),\n"
        "    'resources': len(cand.resources),\n"
        "    'digest': cand.digest,\n"
        "}))\n"
    )
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path / "home"),
        "PYTHONPATH": str(site_dir),
    }
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    info = json.loads(proc.stdout.strip())
    assert Path(info["skm_file"]).is_relative_to(site_dir.resolve())
    assert info["count"] == 29
    assert info["resources"] == 61
    assert info["digest"] == expected_candidate.digest
