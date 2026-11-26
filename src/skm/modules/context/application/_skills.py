"""Resolve and select skills for the control-plane context draft."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from skm.kernel.errors import NotFound
from skm.kernel.ids import ResourceVersionId
from skm.kernel.json_types import JsonObject
from skm.modules.context.domain.blocks import BlockType, TrustLevel
from skm.modules.context.domain.candidates import objects, strings
from skm.modules.context.domain.draft import ConditionalBlock
from skm.modules.context.domain.host_inputs import HostInputKind, HostInputRequest, HostSelector
from skm.modules.context.domain.reasons import ExcludeReason, IncludeReason
from skm.modules.context.domain.skill_selection import SkillEntry, SkillRequest, select_skills
from skm.modules.extensions import public as extensions

if TYPE_CHECKING:
    from uuid import UUID

    from skm.kernel.ports_uow import UnitOfWork
    from skm.modules.context.domain.manifest import DraftAssembler
    from skm.modules.context.domain.policy import SkillsMode
    from skm.modules.context.domain.request import ContextRequest
    from skm.modules.context.generated.settings import ContextSettings
    from skm.modules.planning import public as planning
    from skm.platform.config import EffectiveConfig

_MODES = ("none", "allowlist", "auto")


@dataclass(frozen=True, slots=True)
class _ResolvedSkill:
    view: extensions.ResourceVersionView
    entry: SkillEntry
    body: str
    description: str

    @property
    def source_ref(self) -> str:
        return f"resource:skill:{self.view.key}@{self.view.version}"


def _selection_manifest(view: extensions.ResourceVersionView) -> extensions.SkillManifest:
    # The facade returns validated manifest data. Project only the fields read by select_skills.
    manifest = view.manifest
    triggers = manifest.get("triggers", {})
    return cast(
        "extensions.SkillManifest",
        SimpleNamespace(
            version=extensions.SemVer.parse(view.version),
            kind=SimpleNamespace(value=manifest.get("kind", "domain")),
            roles=strings(manifest.get("roles")),
            requires=strings(manifest.get("requires")),
            requires_tools=strings(manifest.get("requires_tools")),
            adapters=strings(manifest.get("adapters")),
            replaced_by=manifest.get("replaced_by"),
            exclusive_group=manifest.get("exclusive_group"),
            triggers=SimpleNamespace(
                paths=strings(triggers.get("paths")), deps=strings(triggers.get("deps"))
            ),
        ),
    )


def _body_and_description(text: str) -> tuple[str, str]:
    text = text.removeprefix("\ufeff").replace("\r\n", "\n")
    lines = text.split("\n")
    if lines[0].strip() != "---":
        return text.strip(), ""
    # Installation already validates the frontmatter and restricts it to name and description.
    end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    description = next(
        line.split(":", 1)[1].strip()
        for line in lines[1:end]
        if line.partition(":")[0].strip() == "description"
    )
    if len(description) >= 2 and description[0] == description[-1] and description[0] in "\"'":
        description = description[1:-1]
    return "\n".join(lines[end + 1 :]).strip(), description


def _core_pack_id(uow: UnitOfWork, config: EffectiveConfig, pins: extensions.PackPins | None) -> UUID | None:
    try:
        chosen = extensions.pinned_pack_versions(uow, config=config) if pins is None else pins
    except NotFound:
        # An unrelated enabled pack may be absent. Keep the default trust in that case.
        return None
    return chosen.get("core")


def _plan_skills(
    spec: planning.Specification | None, request: ContextRequest
) -> tuple[tuple[str, extensions.VersionConstraint | None], ...]:
    if spec is None or request.entity_id is None:
        return ()
    nodes = (spec.entity(request.entity_id), *spec.ancestors(request.entity_id))
    by_id = {item.id: item for item in spec.items}
    constraints: dict[str, extensions.VersionConstraint | None] = {}
    for node in nodes:
        if (item := by_id.get(node.id)) is not None:
            for skill in item.skills:
                constraints.setdefault(
                    skill.key, extensions.VersionConstraint.parse(skill.version) if skill.version else None
                )
    return tuple(constraints.items())


def _emit_selected(b: DraftAssembler, selected: JsonObject, skills: dict[str, _ResolvedSkill]) -> None:
    trace = selected.get("trace")
    reasons = trace.get("reasons") if isinstance(trace, dict) else None

    def emit(key: str, reason: IncludeReason) -> None:
        skill = skills[key]
        b.add(
            BlockType.SKILLS,
            f"Skill: {key}",
            skill.body,
            "resource",
            skill.source_ref,
            source_version=skill.view.digest,
            trust=skill.entry.trust,
            mandatory=reason in (IncludeReason.EXPLICIT_PLAN, IncludeReason.EXPLICIT_PROFILE),
            reason=reason,
        )

    if isinstance(reasons, dict):
        for key in strings(selected.get("included")):
            emit(key, IncludeReason(str(reasons[key])))
    for item in objects(selected.get("conditional")):
        previous_count = len(b.draft_blocks)
        emit(str(item["key"]), IncludeReason(str(item["reason"])))
        if len(b.draft_blocks) > previous_count:
            b.conditional_blocks.append(
                ConditionalBlock(b.draft_blocks.pop(), "deps_any", frozenset(strings(item["deps"])))
            )

    excluded = selected.get("excluded")
    if isinstance(excluded, dict):
        for key, reason in sorted(excluded.items()):
            # A missing explicit key could belong to a quarantined skill.
            if (skill := skills.get(key)) is not None:
                b.exclude(
                    BlockType.SKILLS,
                    "resource",
                    skill.source_ref,
                    ExcludeReason(str(reason)),
                    source_version=skill.view.digest,
                    trust=skill.entry.trust,
                )


def _request_dependencies(b: DraftAssembler, paths: tuple[str, ...], max_bytes: int) -> None:
    mounts = {path.split(":", 1)[0] if ":" in path else "repo" for path in paths} or {"repo"}
    existing = {
        (item.mount, item.path) for item in b.host_inputs if item.kind is HostInputKind.DEPENDENCY_MANIFEST
    }
    for mount in sorted(mounts):
        for path in ("pyproject.toml", "package.json", "composer.json"):
            if (mount, path) not in existing:
                b.host_inputs.append(
                    HostInputRequest(
                        b.next_hi(),
                        HostInputKind.DEPENDENCY_MANIFEST,
                        mount,
                        path,
                        (),
                        HostSelector("whole"),
                        max_bytes,
                        False,
                        None,
                        TrustLevel.REPOSITORY,
                        f"repo:{mount}/{path}#whole",
                        False,
                        (),
                        None,
                    )
                )


def emit_skills(
    b: DraftAssembler,
    uow: UnitOfWork,
    spec: planning.Specification | None,
    profile: extensions.AgentProfile,
    request: ContextRequest,
    settings: ContextSettings,
    *,
    config: EffectiveConfig,
) -> None:
    include = strings(profile.context.get("include"))
    if BlockType.SKILLS not in include:
        return
    profile_mode = str(profile.context.get("skills_mode", "none"))
    mode = cast(
        "SkillsMode",
        min(profile_mode, settings.skills.max_mode.value, key=_MODES.index),
    )
    if mode == "none":
        return

    pins = cast("extensions.PackPins | None", request.pack_pins)
    resolved = extensions.list_resolved(uow, extensions.ResourceKind.SKILL, config=config, pins=pins)
    if not resolved:
        return
    core_id = _core_pack_id(uow, config, pins)
    skills: dict[str, _ResolvedSkill] = {}
    for view in resolved:
        trust = TrustLevel.SYSTEM if view.pack_version_id == core_id else TrustLevel.THIRD_PARTY
        if trust is TrustLevel.THIRD_PARTY and not settings.allow_third_party:
            continue
        version_id = ResourceVersionId(view.resource_version_id)
        version = extensions.get_resource_version(uow, version_id, include_bodies=True)
        body, desc = _body_and_description((version.bodies or {})["SKILL.md"])
        entry = SkillEntry(view.key, version_id, _selection_manifest(view), b.estimator.estimate(body), trust)
        skills[view.key] = _ResolvedSkill(view, entry, body, desc)

    paths = request.permissions.write_scope
    skill_request = SkillRequest(
        role=request.purpose.role,
        runtime_id=request.runtime.runtime_id,
        capabilities=request.runtime.capabilities,
        tools=request.runtime.tools,
        path_patterns=paths,
        explicit_plan=_plan_skills(spec, request),
        explicit_profile=strings(profile.context.get("skills_include")),
        exclude=frozenset(strings(profile.context.get("skills_exclude"))),
        mode=mode,
        budget=settings.skills.budget_tokens,
        max_count=settings.skills.max_count,
    )
    groups: JsonObject = {
        name: {"max": group.max}
        for name, group in extensions.exclusive_groups(uow, config=config, pins=pins).items()
    }
    selected = select_skills(tuple(skill.entry for skill in skills.values()), skill_request, groups)
    _emit_selected(b, selected, skills)
    if b.conditional_blocks:
        _request_dependencies(b, paths, settings.host_inputs.file_max_bytes)
    if BlockType.SKILL_INDEX in include and (keys := strings(selected.get("discoverable"))):
        lines = [
            f"- `{key}`" + (f" — {skills[key].description}" if skills[key].description else "")
            for key in keys
        ]
        b.add(
            BlockType.SKILL_INDEX,
            "Skill Index",
            "\n".join(lines),
            "core",
            "core:skill_index",
            trust=TrustLevel.SYSTEM,
            reason=IncludeReason.DISCOVERABLE_INDEX,
        )
