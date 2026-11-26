"""Handler for ``integrations.get_desired_projection`` (integrations §4.11, §5.1, §8)."""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal, cast
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import HostId, ProjectId, ResourceVersionId, ScopeId
from skm.kernel.outcomes import Diagnostic as KernelDiagnostic
from skm.kernel.outcomes import Severity
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.extensions import public as extensions
from skm.modules.integrations.application.projection_views import project_scope, resolve_project_binding_host
from skm.modules.integrations.domain.bundle import (
    BundleSkill,
    normalize_desired_json,
    normalize_desired_map,
    parse_bundle_manifest,
    validate_pack_prefix,
)
from skm.modules.integrations.domain.desired_inputs import (
    BundleTargetAccumulator,
    build_agent_doc,
    build_core_instruction_block,
    build_project_instruction_block,
    collect_host_subscription_events,
    empty_instruction_block,
    encode_inputs_digest_bytes,
    format_diagnostic,
    skill_matches_target,
    skill_requires,
    steering_matches_project,
    steering_priority,
)
from skm.modules.integrations.domain.hook_rules import HookMode
from skm.modules.integrations.domain.permission_docs import (
    build_permission_request_doc,
    serialize_permission_set,
)
from skm.modules.integrations.domain.profiles import PermissionProfile, resolve_profile
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.generated.queries import GetDesiredProjection
from skm.modules.integrations.generated.settings import IntegrationsHostView, IntegrationsSettings
from skm.modules.integrations.generated.views import (
    DesiredProjectionView,
    DesiredProjectionViewDefsHostSubscriptionEvent,
    DesiredProjectionViewDefsJsonValue,
)
from skm.modules.policy.public import (
    PermissionSet,
    effective_permissions,
    is_subset,
    permissions_digest,
    representable_paths,
)
from skm.modules.runtimes.public import catalog as runtimes_catalog
from skm.modules.workspace import public as workspace
from skm.modules.workspace.public import CheckoutBindingId
from skm.platform.config import ConfigLoader, ConfigStore, EffectiveConfig, PackConfigSource, ScopeTree
from skm.platform.jsonc.digest import digest_bytes

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]

_CLIENT_CORE_PROMPT_KEY: Final[str] = "instructions/client-core"
_POLICY_PROFILE_ID: Final[Mapping[PermissionProfile, str]] = {
    PermissionProfile.OBSERVE: "read-only",
    PermissionProfile.WORKSPACE_CONTAINED: "workspace-contained",
    PermissionProfile.TRUSTED_FULL_ACCESS: "trusted-full-access",
}


def _dj(val: object) -> DesiredProjectionViewDefsJsonValue:
    return cast("DesiredProjectionViewDefsJsonValue", normalize_desired_json(val))


def _dmap(val: Mapping[str, object]) -> dict[str, DesiredProjectionViewDefsJsonValue]:
    return cast("dict[str, DesiredProjectionViewDefsJsonValue]", normalize_desired_map(val))


class _EmptyPacks:
    __slots__ = ()

    def generation(self) -> int:
        return 0

    def fragments(self, scope_chain: Any) -> tuple[Any, ...]:  # noqa: ARG002
        return ()


def _host_allows_trusted(uow: UnitOfWork, ctx: QueryContext, host_id: HostId) -> bool:
    store, scopes = uow.repo(ConfigStore), uow.repo(ScopeTree)
    try:
        packs: PackConfigSource = uow.repo(PackConfigSource)
    except Exception:  # noqa: BLE001
        packs = _EmptyPacks()
    host_ref = ScopeRef(ScopeKind.HOST, ScopeId(UUID(str(host_id))))
    eff = ConfigLoader(ctx.config.registry, packs).effective_host(store, scopes, host_ref)
    return eff.section(IntegrationsHostView).trusted_full_access.allowed


class _PacksConfigView:
    __slots__ = ("_base", "_enabled", "_extra_pins")

    def __init__(
        self,
        base: EffectiveConfig,
        enabled: Sequence[str] | None = None,
        extra_pins: Mapping[str, str] | None = None,
    ) -> None:
        self._base = base
        self._enabled = None if enabled is None else list(enabled)
        self._extra_pins = dict(extra_pins or {})

    def get(self, key: str) -> Any:
        if key == "extensions.packs.enabled" and self._enabled is not None:
            return list(self._enabled)
        if key == "extensions.resources.pinned" and self._extra_pins:
            return {**self._extra_pins, **cast("Mapping[str, str]", self._base.get(key))}
        return self._base.get(key)


@dataclass(slots=True)
class _ResolveState:
    uow: UnitOfWork
    ctx: QueryContext
    diagnostics: list[KernelDiagnostic] = field(default_factory=list[KernelDiagnostic])
    seen_q: set[tuple[extensions.ResourceKind, str]] = field(
        default_factory=set[tuple[extensions.ResourceKind, str]]
    )

    def resolve(
        self,
        kind: extensions.ResourceKind,
        key: str,
        *,
        config: EffectiveConfig | None = None,
    ) -> extensions.ResourceVersionView | None:
        cfg = self.ctx.config if config is None else config
        try:
            return extensions.resolve_resource(self.uow, kind, key, config=cfg)
        except PreconditionFailed as exc:
            if exc.code is ErrorCode.RESOURCE_QUARANTINED:
                if (kind, key) not in self.seen_q:
                    self.seen_q.add((kind, key))
                    self.diagnostics.append(
                        KernelDiagnostic(
                            code=ErrorCode.RESOURCE_QUARANTINED.value,
                            message=f"{kind.value} {key!r} is quarantined",
                            severity=Severity.WARNING,
                            target=f"{kind.value}:{key}",
                            details={"kind": kind.value, "key": key},
                        )
                    )
                return None
            raise
        except NotFound:
            return None


def _check_agent_ceiling(
    st: _ResolveState,
    chain: tuple[ScopeRef, ...],
    profile: extensions.AgentProfile,
    effective_profile: PermissionProfile,
    ceiling: PermissionSet,
    *,
    bundle_key: str,
) -> None:
    allow_unconfined = effective_profile is PermissionProfile.TRUSTED_FULL_ACCESS
    if profile.permissions.policy_profile == "trusted-full-access" and not allow_unconfined:
        raise ValidationFailed(
            ErrorCode.EXTENSION_WIDENS_PERMISSIONS, f"profile {profile.key!r} exceeds ceiling"
        )
    try:
        requested = effective_permissions(
            st.uow,
            scope_chain=chain,
            config=st.ctx.config,
            profile_id=profile.permissions.policy_profile,
            role_layer=None,
            task_layer=None,
            allow_unconfined=allow_unconfined,
        )
    except Forbidden as exc:
        raise ValidationFailed(
            ErrorCode.EXTENSION_WIDENS_PERMISSIONS, f"profile {profile.key!r} forbidden"
        ) from exc
    prof_v = (
        ()
        if permissions_digest(requested) == permissions_digest(ceiling)
        else is_subset(
            build_permission_request_doc(
                requested,
                merged_fs_read=representable_paths(requested.fs_read),
                merged_fs_write=representable_paths(requested.fs_write),
            ),
            ceiling,
        )
    )
    layer_req = {"profile_id": profile.permissions.policy_profile, **dict(profile.permissions.layer or {})}
    violations = (*prof_v, *is_subset(layer_req, ceiling))
    if violations:
        raise ValidationFailed(
            ErrorCode.EXTENSION_WIDENS_PERMISSIONS,
            f"bundle {bundle_key!r} profile {profile.key!r} widens permissions",
            details={
                "bundle": bundle_key,
                "profile": profile.key,
                "violations": [v.field for v in violations],
            },
        )


def _assemble_instructions(
    st: _ResolveState,
    project_slug: str,
    settings: IntegrationsSettings,
) -> tuple[Mapping[str, DesiredProjectionViewDefsJsonValue], dict[str, DesiredProjectionViewDefsJsonValue]]:
    if not settings.instructions.enabled:
        return _dmap(empty_instruction_block(enabled=False)), _dmap(empty_instruction_block(enabled=False))
    inc_core = bool(getattr(settings.instructions, "include_core", True))
    core_block = _dmap(empty_instruction_block(enabled=inc_core))
    if inc_core:
        cview = st.resolve(extensions.ResourceKind.PROMPT_BLOCK, _CLIENT_CORE_PROMPT_KEY)
        if cview is not None:
            _meta, cbody = extensions.load_text_resource(st.uow, ResourceVersionId(cview.resource_version_id))
            core_block = _dmap(
                build_core_instruction_block(
                    key=cview.key, version=cview.version, digest=cview.digest, body=cbody
                )
            )
    if not getattr(settings.instructions, "include_project", True):
        return core_block, _dmap(empty_instruction_block(enabled=False))

    known_st = sorted(extensions.known_keys(st.uow, extensions.ResourceKind.STEERING, config=st.ctx.config))
    matched = [
        v
        for k in known_st
        if (v := st.resolve(extensions.ResourceKind.STEERING, k)) is not None
        and steering_matches_project(v.manifest, project_slug)
    ]
    sections_in = [
        (
            v.key,
            v.version,
            steering_priority(v.manifest),
            v.digest,
            extensions.load_text_resource(st.uow, ResourceVersionId(v.resource_version_id))[1],
        )
        for v in sorted(matched, key=lambda item: (-steering_priority(item.manifest), item.key))
    ]
    proj_block = build_project_instruction_block(sections_in, project_text=settings.instructions.project_text)
    return core_block, _dmap(proj_block)


def _pinned_or_empty(uow: UnitOfWork, config: EffectiveConfig) -> extensions.PackPins:
    try:
        return extensions.pinned_pack_versions(uow, config=config)
    except NotFound:
        return {}


def _resolve_presets(
    st: _ResolveState,
    presets: Sequence[str],
) -> tuple[frozenset[str], set[str], list[str]]:
    cfg = st.ctx.config
    core_pins = _pinned_or_empty(st.uow, cast("EffectiveConfig", _PacksConfigView(cfg, ())))
    core_keys: frozenset[str] = (
        extensions.known_keys(st.uow, extensions.ResourceKind.SKILL, config=cfg, pins=core_pins)
        if core_pins
        else frozenset()
    )
    preset_skills: set[str] = set()
    matched_packs: list[str] = []
    bundle_keys: frozenset[str] | None = None
    for preset in presets:
        if preset == "core":
            preset_skills.update(core_keys)
            continue
        probe_cfg = cast("EffectiveConfig", _PacksConfigView(cfg, (preset,)))
        if core_pins:
            pvid = _pinned_or_empty(st.uow, probe_cfg).get(preset)
            pskills = (
                extensions.known_keys(st.uow, extensions.ResourceKind.SKILL, config=cfg, pins={preset: pvid})
                if pvid is not None
                else None
            )
        else:
            probed = extensions.known_keys(st.uow, extensions.ResourceKind.SKILL, config=probe_cfg)
            pskills = probed if probed else None
        if pskills is not None:
            matched_packs.append(preset)
            preset_skills.update(pskills)
            continue
        if bundle_keys is None:
            bundle_keys = extensions.known_keys(
                st.uow, extensions.ResourceKind.INTEGRATION_BUNDLE, config=cfg
            )
        if preset in bundle_keys:
            bview = st.resolve(extensions.ResourceKind.INTEGRATION_BUNDLE, preset)
            if bview is not None:
                preset_skills.update(s.key for s in parse_bundle_manifest(bview.manifest).skills)
    return core_keys, preset_skills, matched_packs


def _assemble_skills(
    st: _ResolveState,
    settings: IntegrationsSettings,
    target: TargetId,
    bundle_skills: Sequence[BundleSkill],
) -> tuple[Mapping[str, DesiredProjectionViewDefsJsonValue], ...]:
    if not settings.skills.enabled and not bundle_skills:
        return ()
    _catalog = runtimes_catalog(st.uow, config=st.ctx.config)
    excluded = frozenset(settings.skills.exclude)
    core_keys, preset_keys, matched_packs = (
        _resolve_presets(st, settings.skills.presets)
        if settings.skills.enabled
        else (frozenset[str](), set[str](), list[str]())
    )
    raw_en = st.ctx.config.get("extensions.packs.enabled")
    base_en = (
        [str(x) for x in cast("Sequence[object]", raw_en)]
        if isinstance(raw_en, Sequence) and not isinstance(raw_en, (str, bytes))
        else []
    )
    bpins = {f"skill:{s.key}": s.version for s in bundle_skills if s.version is not None}
    skill_cfg = cast(
        "EffectiveConfig",
        _PacksConfigView(st.ctx.config, [*base_en, *matched_packs] if matched_packs else None, bpins),
    )

    cache: dict[str, extensions.ResourceVersionView | None] = {}

    def _get(k: str) -> extensions.ResourceVersionView | None:
        if k not in cache:
            cache[k] = st.resolve(extensions.ResourceKind.SKILL, k, config=skill_cfg)
        return cache[k]

    inc: set[str] = set(settings.skills.include) if settings.skills.enabled else set()
    queue: deque[str] = deque(sorted((preset_keys | inc | {s.key for s in bundle_skills}) - excluded))
    visited: set[str] = set()
    selected: dict[str, extensions.ResourceVersionView] = {}
    while queue:
        key = queue.popleft()
        if key in visited or key in excluded:
            continue
        visited.add(key)
        view = _get(key)
        if view is not None:
            selected[key] = view
            queue.extend(r for r in skill_requires(view.manifest) if r not in visited and r not in excluded)
    if settings.skills.enabled and settings.skills.include_core:
        for ck in sorted(core_keys - excluded):
            cv = _get(ck)
            if cv is not None and str(cv.manifest.get("tier", "core")) == "core":
                selected.setdefault(ck, cv)

    payloads: list[Mapping[str, DesiredProjectionViewDefsJsonValue]] = []
    for key in sorted(selected):
        if not skill_matches_target(selected[key].manifest, target):
            continue
        full = extensions.get_resource_version(
            st.uow, ResourceVersionId(selected[key].resource_version_id), include_bodies=True
        )
        payloads.append(
            {
                "key": full.key,
                "version": full.version,
                "digest": full.digest,
                "resource_version_id": str(full.resource_version_id),
                "manifest": _dj(full.manifest),
                "bodies": _dj(dict(sorted((full.bodies or {}).items()))),
            }
        )
    return tuple(payloads)


def _assemble_default_agents(
    st: _ResolveState,
    settings: IntegrationsSettings,
) -> tuple[Mapping[str, DesiredProjectionViewDefsJsonValue], ...]:
    resolved = extensions.list_resolved(st.uow, extensions.ResourceKind.AGENT_PROFILE, config=st.ctx.config)
    prefix = settings.agents.pack_prefix
    out: list[Mapping[str, DesiredProjectionViewDefsJsonValue]] = []
    for view in sorted(resolved, key=lambda v: v.key):
        prof = extensions.load_agent_profile(st.uow, ResourceVersionId(view.resource_version_id))
        ename = f"{prefix}-{prof.key}" if prefix else prof.key
        out.append(_dmap(build_agent_doc(prof, name=ename, digest=view.digest)))
    return tuple(out)


def _assemble_bundles(
    st: _ResolveState,
    chain: tuple[ScopeRef, ...],
    settings: IntegrationsSettings,
    target: TargetId,
    effective_profile: PermissionProfile,
    perms: PermissionSet,
) -> tuple[
    tuple[Mapping[str, DesiredProjectionViewDefsJsonValue], ...],
    tuple[BundleSkill, ...],
    tuple[Mapping[str, DesiredProjectionViewDefsJsonValue], ...],
]:
    acc = BundleTargetAccumulator(
        target=target, pack_prefix=validate_pack_prefix(settings.agents.pack_prefix)
    )
    seen_bundles: set[str] = set()
    skills_out: list[BundleSkill] = []

    for bundle_key in settings.bundles:
        if bundle_key in seen_bundles:
            continue
        seen_bundles.add(bundle_key)
        summary = st.resolve(extensions.ResourceKind.INTEGRATION_BUNDLE, bundle_key)
        if summary is None:
            if (extensions.ResourceKind.INTEGRATION_BUNDLE, bundle_key) in st.seen_q:
                continue
            raise NotFound(ErrorCode.NOT_FOUND, f"bundle {bundle_key!r} not found")
        full = extensions.get_resource_version(
            st.uow, ResourceVersionId(summary.resource_version_id), include_bodies=True
        )
        manifest = parse_bundle_manifest(full.manifest)
        if not acc.check_target_supported(manifest, st.diagnostics):
            continue
        skills_out.extend(manifest.skills)
        bmeta = (manifest.key, manifest.version, full.digest)
        for bagent in manifest.agents:
            ename = acc.reserve_agent_name(bagent.key)
            pview = st.resolve(extensions.ResourceKind.AGENT_PROFILE, bagent.profile)
            if pview is None:
                if (extensions.ResourceKind.AGENT_PROFILE, bagent.profile) in st.seen_q:
                    continue
                raise NotFound(ErrorCode.NOT_FOUND, f"agent_profile {bagent.profile!r} not found")
            prof = extensions.load_agent_profile(st.uow, ResourceVersionId(pview.resource_version_id))
            _check_agent_ceiling(st, chain, prof, effective_profile, perms, bundle_key=manifest.key)
            acc.record_agent(ename, build_agent_doc(prof, name=ename, digest=pview.digest, bundle_meta=bmeta))
        acc.collect_assets(
            manifest,
            bundle_digest=full.digest,
            bodies=full.bodies,
            file_metas=tuple((f.path, f.size_bytes, f.digest) for f in full.files),
        )

    return (
        tuple(_dmap(a) for a in sorted(acc.agents, key=lambda i: str(i.get("name", "")))),
        tuple(skills_out),
        tuple(_dmap(doc) for _, _, _, doc in sorted(acc.assets, key=lambda i: i[:3])),
    )


def _assemble_mcp_servers(
    settings: IntegrationsSettings,
) -> Mapping[str, Mapping[str, DesiredProjectionViewDefsJsonValue]]:
    servers: dict[str, Mapping[str, DesiredProjectionViewDefsJsonValue]] = {}
    if settings.mcp.include_skm:
        servers["skm"] = {"command": "skm", "args": ("mcp", "serve"), "type": "stdio", "enabled": True}
    for name, entry in sorted(settings.mcp.servers.items()):
        if entry.enabled is False:
            servers.pop(name, None)
            continue
        spec: dict[str, DesiredProjectionViewDefsJsonValue] = {"enabled": True}
        for attr in ("type", "command", "args", "url", "tool_count"):
            if (val := getattr(entry, attr)) is not None:
                spec[attr] = val
        if entry.env_refs is not None:
            spec["env_refs"] = {k: str(v) for k, v in sorted(entry.env_refs.items())}
        servers[name] = spec
    return servers


def handle(query: GetDesiredProjection, ctx: QueryContext, uow: UnitOfWork) -> DesiredProjectionView:
    project_id = ProjectId(query.project_id)
    binding_id = CheckoutBindingId(query.checkout_binding_id)
    target = TargetId(query.target)
    workspace.require_active_project(uow, project_id)
    project_slug = workspace.get_project(uow, project_id).slug
    _ws_id, host_id = resolve_project_binding_host(uow, project_id, binding_id, now=ctx.clock.now())

    settings = ctx.config.section(IntegrationsSettings)
    prof_res = resolve_profile(
        PermissionProfile(settings.permission_profile.value),
        host_allows_trusted=_host_allows_trusted(uow, ctx, host_id),
    )
    eff_prof = prof_res.profile
    chain = workspace.scope_chain(uow, ScopeId(UUID(str(project_id))))
    perms = effective_permissions(
        uow,
        scope_chain=chain,
        config=ctx.config,
        profile_id=_POLICY_PROFILE_ID[eff_prof],
        role_layer=None,
        task_layer=None,
        allow_unconfined=(eff_prof is PermissionProfile.TRUSTED_FULL_ACCESS),
    )
    serialized_perms = _dmap(serialize_permission_set(perms, digest=permissions_digest(perms)))

    st = _ResolveState(uow=uow, ctx=ctx)
    instructions_core, instructions_project = _assemble_instructions(st, project_slug, settings)
    if settings.bundles:
        agents, b_skills, b_assets = _assemble_bundles(st, chain, settings, target, eff_prof, perms)
        if b_assets:
            instructions_project["bundle_assets"] = b_assets
    else:
        b_skills, agents = (), _assemble_default_agents(st, settings)

    skills = _assemble_skills(st, settings, target, b_skills)
    mcp_servers = _assemble_mcp_servers(settings)
    hook_modes: dict[str, Literal["off", "warn", "strict"]] = {
        k: HookMode(v.value).value for k, v in sorted(settings.hooks.mode.items())
    }
    host_events = tuple(
        DesiredProjectionViewDefsHostSubscriptionEvent(kind=cast("Any", k), classes=c)
        for k, c in collect_host_subscription_events(ctx.config.get("hooks.subscriptions"))
    )
    diagnostics = tuple(_dmap(format_diagnostic(d)) for d in (*prof_res.diagnostics, *st.diagnostics))
    inputs_digest = digest_bytes(
        encode_inputs_digest_bytes(
            {
                "project_id": str(query.project_id),
                "target": target.value,
                "instructions_core": instructions_core,
                "instructions_project": instructions_project,
                "skills": skills,
                "permissions": serialized_perms,
                "profile": eff_prof.value,
                "hook_modes": hook_modes,
                "mcp_servers": mcp_servers,
                "agents": agents,
                "config_generation": ctx.config.generation,
                "host_subscription_events": [i.to_json() for i in host_events],
            }
        )
    )
    view = DesiredProjectionView(
        project_id=query.project_id,
        target=query.target,
        instructions_core=instructions_core,
        instructions_project=instructions_project,
        skills=skills,
        permissions=serialized_perms,
        profile=eff_prof.value,
        hook_modes=hook_modes,
        mcp_servers=mcp_servers,
        agents=agents,
        inputs_digest=inputs_digest,
        config_generation=ctx.config.generation,
        diagnostics=diagnostics,
        host_subscription_events=host_events,
    )
    sz = len(json.dumps(view.to_json(), separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    if sz > settings.desired.max_bytes:
        raise PreconditionFailed(
            ErrorCode.INTEGRATION_DESIRED_TOO_LARGE,
            "desired projection exceeds max_bytes",
            details={"size_bytes": sz},
        )
    return view


SPEC = QuerySpec(
    name="integrations.get_desired_projection",
    dto=GetDesiredProjection,
    result=DesiredProjectionView,
    permission="integration.read",
    scope_of=project_scope,
    handler=handle,
)
