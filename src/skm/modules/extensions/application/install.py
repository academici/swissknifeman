"""``install_candidate``: the one write path of a pack, shared by ``install_pack`` and ``sync_builtin_packs``
(extensions §7.1 steps 3-15, §7.2).

The caller's transaction takes the whole pack or nothing. A version stays immutable: the same version with the
same digest and the same stored files is ``already_installed``, with another digest or other files
``EXTENSION_DIGEST_CONFLICT``, also between concurrent installers, which the registry lock puts in a row. A
digest alone proves nothing (``digest_rules``). ``trust`` and ``origin`` come from the caller, never from the
pack: only the sync passes ``builtin`` and no DTO reaches that path. What cannot be proven yet is refused with
``CAPABILITY_UNAVAILABLE``: every pack but a builtin one, whose admission rests on the compatibility scan
(P09.01.b), a bundle whose agents have no defined permission request, and a stored version whose files are
gone.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, cast

import skm
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import (
    CapabilityUnavailable,
    Conflict,
    Forbidden,
    NotFound,
    PreconditionFailed,
    ValidationFailed,
)
from skm.kernel.ids import ResourceVersionId
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.extensions.application.candidate import schema_registry
from skm.modules.extensions.application.permission_proof import profile_violations
from skm.modules.extensions.domain.agent_profile import check_profile_trust, parse_agent_profile
from skm.modules.extensions.domain.compat import CompatStatus, CompatVerdict
from skm.modules.extensions.domain.events import (
    PackInstalled,
    ResourceQuarantined,
    ResourceVersionAdded,
)
from skm.modules.extensions.domain.keys import PackId, PackVersionId, ResourceId, SemVer
from skm.modules.extensions.domain.kinds import ResourceKind
from skm.modules.extensions.domain.pack import (
    BUILTIN_ORIGIN,
    CORE_PACK,
    TRUST_RANK,
    Pack,
    PackState,
    PackTrust,
    PackVersion,
)
from skm.modules.extensions.domain.permission_guard import permission_request, widens_permissions
from skm.modules.extensions.domain.quarantine import QuarantineEntry
from skm.modules.extensions.domain.resource import (
    Resource,
    ResourceVersion,
    compat_report_to_json,
    proven_bodies,
)
from skm.modules.extensions.generated.results import (
    InstallPackResult,
    InstallPackResultQuarantinedItem,
    InstallPackResultResourcesItem,
)
from skm.modules.extensions.generated.results import ResourceKind as ResultKind
from skm.modules.extensions.ports import PackRepository, QuarantineRepository, ResourceRepository
from skm.modules.policy.public import effective_permissions, is_subset
from skm.platform.config.keys import Sensitivity

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from datetime import datetime

    from skm.kernel.clock import Clock
    from skm.kernel.id_generator import IdGenerator
    from skm.kernel.ids import PrincipalId
    from skm.kernel.json_types import JsonValue
    from skm.kernel.ports_uow import UnitOfWork
    from skm.modules.extensions.application.candidate import PackCandidate, ResourceCandidate
    from skm.modules.extensions.domain.pack import PackManifest
    from skm.modules.extensions.domain.resource import ResourceVersionSummary
    from skm.modules.policy.public import PermissionSet
    from skm.platform.config import EffectiveConfig

__all__ = ["install_candidate", "product_version"]

_RELEASE: Final = re.compile(r"([0-9]+)\.([0-9]+)\.([0-9]+)")
_ROLE_RESULT: Final = "urn:skm:execution:role-result:{role}:v1"


def product_version() -> SemVer:
    """The running product as a release triple: a PEP 440 suffix (``2.0.0.dev0``) is no SemVer prerelease."""
    found = _RELEASE.match(skm.__version__)
    if found is None:  # an unversioned checkout satisfies no bound rather than every bound
        return SemVer(0, 0, 0)
    return SemVer(int(found[1]), int(found[2]), int(found[3]))


def _check_requires_skm(manifest: PackManifest) -> None:
    current = product_version()
    if not manifest.requires_skm.matches(current):
        raise PreconditionFailed(
            ErrorCode.EXTENSION_INCOMPATIBLE,
            f"pack {manifest.slug} does not support this product version",
            details={
                "reason": "requires_skm",
                "requires_skm": str(manifest.requires_skm),
                "version": str(current),
            },
        )


def _check_trust(manifest: PackManifest, *, trust: PackTrust, origin: str) -> None:
    """§7.1 step 4: the manifest cannot raise its own trust and ``builtin`` belongs to the builtin origin."""
    builtin_origin = origin == BUILTIN_ORIGIN
    if not builtin_origin and PackTrust.BUILTIN in (trust, manifest.trust):
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "trust builtin is reserved for the packs of the product itself",
            details={"reason": "builtin_trust_not_allowed", "slug": manifest.slug},
        )
    if manifest.trust is not trust or (builtin_origin and trust is PackTrust.OPERATOR):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "the manifest declares another trust than its installer",
            details={"reason": "trust_mismatch", "declared": manifest.trust.value, "given": trust.value},
        )
    if manifest.slug == CORE_PACK and trust is not PackTrust.BUILTIN:
        # always active and protected from retirement: installed first, it would take the place of the product
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "the slug core is reserved for the pack of the product itself",
            details={"reason": "core_slug_reserved", "trust": trust.value},
        )


def _check_overrides(
    uow: UnitOfWork, candidate: PackCandidate, *, pack: Pack | None, trust: PackTrust
) -> frozenset[tuple[ResourceKind, str]]:
    """§4.13: a pair another pack holds needs a declaration and enough trust. Every holder counts, not only
    the first owner, or a third party could replace an operator behind another third party that came first.
    Returns the overriding pairs."""
    packs, resources = uow.repo(PackRepository), uow.repo(ResourceRepository)
    versions = {row.version_id: row for row in packs.list_versions()}
    declared = {(item.kind, item.key) for item in candidate.manifest.overrides}
    overriding: set[tuple[ResourceKind, str]] = set()
    for item in candidate.resources:
        existing = resources.find(item.kind, item.key)
        if existing is None or (pack is not None and existing.first_pack_id == pack.id):
            continue
        holders = (
            versions[row.pack_version_id] for row in resources.versions_of(item.kind, item.key, [*versions])
        )
        strongest = max(
            (
                packs.get(existing.first_pack_id).trust,
                *(row.trust for row in holders if pack is None or row.pack_id != pack.id),
            ),
            key=TRUST_RANK.__getitem__,
        )
        if (item.kind, item.key) not in declared or TRUST_RANK[trust] < TRUST_RANK[strongest]:
            raise Conflict(
                ErrorCode.EXTENSION_OVERRIDE_NOT_DECLARED,
                f"{item.kind.value}:{item.key} belongs to another pack",
                details={"kind": item.kind.value, "key": item.key, "owner_trust": strongest.value},
            )
        overriding.add((item.kind, item.key))
    return frozenset(overriding)


def _requested_permissions(
    uow: UnitOfWork, config: EffectiveConfig, policy_profile: str
) -> PermissionSet | None:
    """What a policy profile permits on any host; ``None``: it needs ``policy.host.allow_unconfined``, which
    the host of the step decides and which only an operator pack may ask for. Unknown: ``CONFIG_INVALID``.

    Without the flag composition takes ``none`` out of the isolation set, but a flagged host runs the profile
    with it, so the request keeps it: a request that the host of the install cut is no proof for that host."""

    def composed(*, allow_unconfined: bool) -> PermissionSet:
        return effective_permissions(
            uow,
            scope_chain=(),
            config=config,
            profile_id=policy_profile,
            role_layer=None,
            task_layer=None,
            allow_unconfined=allow_unconfined,
        )

    try:
        composed(allow_unconfined=False)
    except Forbidden as exc:
        if exc.details.get("reason") == "unconfined_not_allowed_on_host":
            return None
        raise
    return composed(allow_unconfined=True)


def _check_result_schema(role: str, key: str, result_schema: str) -> None:
    """§4.6 rule 5: the concrete registered result URN of the profile's own role."""
    expected = _ROLE_RESULT.format(role=role)
    if result_schema != expected or expected not in schema_registry().urns():
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"profile {key} does not name the result schema of its role",
            details={
                "reason": "result_schema_not_role_result",
                "key": key,
                "role": role,
                "urn": result_schema,
                "expected": expected,
            },
        )


def _refuse_bundle_agents(candidate: PackCandidate) -> None:
    """§7.1 step 10: a bundle names agents by profile reference and nothing defines the permission request
    of that reference yet (integrations, P10), so no widening check can be claimed for it."""
    for item in candidate.resources:
        if item.kind is ResourceKind.INTEGRATION_BUNDLE and item.manifest.get("agents"):
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                f"the agents of bundle {item.key} cannot be checked against the ceiling",
                details={"reason": "bundle_permission_check_unavailable", "owner": "P10", "key": item.key},
            )


def _require_compat_scan(candidate: PackCandidate, trust: PackTrust) -> None:
    """§7.1 steps 6, 14: without a scan a verdict proves nothing, and who installs a pack is no proof of
    what it says. Every admitted pack, builtin or external, must have scanned resources."""
    if (trust is not PackTrust.BUILTIN and not candidate.resources) or not all(
        item.scanned for item in candidate.resources
    ):
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "the compatibility scan this install depends on is not available",
            details={"reason": "compat_scanner_unavailable", "owner": "P09.01.b", "trust": trust.value},
        )


def _pairs(pairs: Iterable[tuple[ResourceKind, str]]) -> list[JsonValue]:
    return [{"kind": kind.value, "key": key} for kind, key in sorted(pairs)]


def _evidence_unavailable(pairs: Iterable[tuple[ResourceKind, str]]) -> CapabilityUnavailable:
    return CapabilityUnavailable(
        ErrorCode.CAPABILITY_UNAVAILABLE,
        "the stored files of the resource cannot prove that the offered ones are the same",
        details={"reason": "stored_evidence_unavailable", "resources": _pairs(pairs)},
    )


def _stored_bodies(uow: UnitOfWork, row: ResourceVersionSummary) -> Mapping[str, bytes]:
    stored = uow.repo(ResourceRepository).get_version(row.id, include_bodies=True)
    bodies = proven_bodies(stored)
    if bodies is None:
        raise _evidence_unavailable([(row.kind, row.key)])
    return bodies


def _check_replay(uow: UnitOfWork, candidate: PackCandidate, existing: PackVersion) -> None:
    """§7.1 step 7 under the registry lock: the digests are equal, so only the stored paths and bytes tell
    whether this is the version that is installed. The rows of the digest must all be there to tell it."""
    rows = {
        (row.kind, row.key): row
        for row in uow.repo(ResourceRepository).list_in_pack_versions([existing.id], kind=None)
    }
    offered = {(item.kind, item.key): item for item in candidate.resources}
    if rows.keys() != offered.keys():
        raise _evidence_unavailable(rows.keys() ^ offered.keys())
    differing = [pair for pair, item in offered.items() if _stored_bodies(uow, rows[pair]) != item.bodies]
    if differing or existing.manifest != candidate.manifest:
        manifest = candidate.manifest
        raise Conflict(
            ErrorCode.EXTENSION_DIGEST_CONFLICT,
            f"pack {manifest.slug} {manifest.version} is installed with other content under the same digest",
            details={
                "reason": "digest_collision",
                "slug": manifest.slug,
                "version": str(manifest.version),
                "installed": existing.digest,
                "offered": candidate.digest,
                "resources": _pairs(differing),
            },
        )


def _check_digest_aliases(uow: UnitOfWork, candidate: PackCandidate) -> None:
    """§4.12 step 6: a pin by digest takes any version of its pair with that digest, in any pack, also a
    retired one. So a pair never holds other files under a digest it already has; equal files are fine."""
    resources = uow.repo(ResourceRepository)
    versions = [row.version_id for row in uow.repo(PackRepository).list_versions()]
    for item in candidate.resources:
        if resources.find(item.kind, item.key) is None:
            continue
        for row in resources.versions_of(item.kind, item.key, versions):
            if row.digest == item.digest and _stored_bodies(uow, row) != item.bodies:
                raise Conflict(
                    ErrorCode.EXTENSION_DIGEST_CONFLICT,
                    f"{item.kind.value}:{item.key} is installed with other files under the same digest",
                    details={
                        "reason": "digest_collision",
                        "slug": candidate.manifest.slug,
                        "version": str(candidate.manifest.version),
                        "resources": _pairs([(item.kind, item.key)]),
                    },
                )


def _check_profiles(
    uow: UnitOfWork, config: EffectiveConfig, candidate: PackCandidate, *, trust: PackTrust
) -> None:
    """§4.6 rules 3-5, §7.1 step 10: a profile that widens or its pack may not hold refuses the whole pack."""
    _refuse_bundle_agents(candidate)
    instance = ScopeRef(ScopeKind.INSTANCE, uow.repo(ScopeRegistry).instance().id)
    ceiling = effective_permissions(
        uow,
        scope_chain=(instance,),
        config=config,
        profile_id=None,
        role_layer=None,
        task_layer=None,
        allow_unconfined=False,
    )
    violations: list[JsonValue] = []
    prompt_keys = {item.key for item in candidate.resources if item.kind is ResourceKind.PROMPT_BLOCK}
    resources = uow.repo(ResourceRepository)
    for item in candidate.resources:
        if item.kind is not ResourceKind.AGENT_PROFILE:
            continue
        profile = parse_agent_profile(item.manifest)
        check_profile_trust(profile, trust)
        _check_result_schema(profile.role, profile.key, profile.result_schema)
        for keys in profile.prompt.blocks.values():
            for key in keys:
                if key not in prompt_keys and resources.find(ResourceKind.PROMPT_BLOCK, key) is None:
                    raise NotFound(
                        ErrorCode.NOT_FOUND,
                        f"profile {profile.key} names an unknown prompt block",
                        details={"kind": "prompt_block", "key": key, "profile": profile.key},
                    )
        requested = _requested_permissions(uow, config, profile.permissions.policy_profile)
        if requested is None and trust is not PackTrust.OPERATOR:
            violations.append(
                {
                    "key": profile.key,
                    "field": "policy_profile",
                    "reason": "requires_host_flag",
                    "detail": profile.permissions.policy_profile,
                }
            )
        found = (
            *(() if requested is None else profile_violations(requested, ceiling)),
            *widens_permissions(permission_request(profile.permissions), ceiling, is_subset=is_subset),
        )
        violations.extend(
            {"key": profile.key, "field": item.field, "reason": item.reason, "detail": item.detail}
            for item in found
        )
    if violations:
        raise ValidationFailed(
            ErrorCode.EXTENSION_WIDENS_PERMISSIONS,
            "a profile of the pack asks for more than the ceiling allows",
            details={"violations": violations},
        )


def _check_config_fragment(config: EffectiveConfig, manifest: PackManifest, *, trust: PackTrust) -> None:
    """§7.1 step 12 (K16): a fragment is an operator decision, and never touches a ceiling or a secret."""
    if not manifest.config:
        return
    if trust is PackTrust.THIRD_PARTY:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "a third party pack cannot carry a configuration fragment",
            details={"reason": "config_fragment_not_allowed_for_third_party"},
        )
    registry = config.registry
    for key, value in manifest.config.items():
        spec = registry.find(key)
        if spec is None:
            raise ValidationFailed(ErrorCode.CONFIG_UNKNOWN_KEY, f"unknown key {key}", details={"key": key})
        if not spec.pack or spec.sensitivity is Sensitivity.SECRET:
            raise ValidationFailed(
                ErrorCode.CONFIG_SCOPE_NOT_ALLOWED, f"{key} has no pack level", details={"key": key}
            )
        if registry.value_issues(key, value):
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, f"invalid value of {key}", details={"key": key})


def _failed_checks(item: ResourceCandidate) -> tuple[str, ...]:
    return tuple(check.detail for check in item.compat.checks if check.status is CompatStatus.FAIL)


def _result(
    candidate: PackCandidate,
    *,
    pack_id: PackId,
    version_id: PackVersionId,
    status: str,
    overriding: frozenset[tuple[ResourceKind, str]],
) -> InstallPackResult:
    return InstallPackResult(
        pack_id=pack_id,
        pack_version_id=version_id,
        slug=candidate.manifest.slug,
        version=str(candidate.manifest.version),
        digest=candidate.digest,
        status=cast("object", status),  # type: ignore[arg-type]  -- the three literals of the result schema
        resources=tuple(
            InstallPackResultResourcesItem(
                kind=ResultKind(item.kind.value),
                key=item.key,
                version=str(item.version),
                digest=item.digest,
                verdict=cast("object", item.compat.verdict.value),  # type: ignore[arg-type]
                overrides=(item.kind, item.key) in overriding,
            )
            for item in candidate.resources
        ),
        quarantined=tuple(
            InstallPackResultQuarantinedItem(
                kind=ResultKind(item.kind.value), key=item.key, reasons=_failed_checks(item)
            )
            for item in candidate.resources
            if item.compat.verdict is CompatVerdict.QUARANTINE
        ),
        diagnostics=(),
    )


def _write(  # noqa: PLR0913 - persist the install metadata and resources in the caller's transaction
    uow: UnitOfWork,
    candidate: PackCandidate,
    *,
    installed_by: PrincipalId,
    now: datetime,
    ids: IdGenerator,
    pack_id: PackId,
    version_id: PackVersionId,
    origin: str,
    trust: PackTrust,
) -> None:
    """§7.1 step 15: pack version, new resource pairs, versions with their files, quarantine rows, events."""
    manifest = candidate.manifest
    uow.repo(PackRepository).add_version(
        PackVersion(
            id=version_id,
            pack_id=pack_id,
            version=manifest.version,
            digest=candidate.digest,
            manifest=manifest,
            state=PackState.ACTIVE,
            origin=origin,
            installed_at=now,
            installed_by=installed_by,
        )
    )
    resources, quarantine = uow.repo(ResourceRepository), uow.repo(QuarantineRepository)
    quarantined = 0
    for item in candidate.resources:
        existing = resources.find(item.kind, item.key)
        if existing is None:
            existing = Resource(ResourceId(ids.new_id()), item.kind, item.key, pack_id, now)
            resources.add(existing)
        rv_id = ResourceVersionId(ids.new_id())
        resources.add_version(
            ResourceVersion(
                id=rv_id,
                resource_id=existing.id,
                kind=item.kind,
                key=item.key,
                pack_version_id=version_id,
                version=item.version,
                digest=item.digest,
                manifest=item.manifest,
                files=item.files,
                tokens_estimate=item.tokens_estimate,
                compat=item.compat,
                created_at=now,
            ),
            item.bodies,
        )
        uow.record(
            ResourceVersionAdded(
                pack_id=pack_id,
                resource_version_id=rv_id,
                resource_id=existing.id,
                kind=item.kind.value,
                key=item.key,
                version=str(item.version),
                digest=item.digest,
                pack_version_id=version_id,
            )
        )
        if item.compat.verdict is CompatVerdict.QUARANTINE:
            quarantined += 1
            reasons = _failed_checks(item) or ("compat",)
            quarantine.add(
                QuarantineEntry(
                    version_id=rv_id,
                    reason="compat",
                    report={**compat_report_to_json(item.compat), "reasons": list(reasons)},
                    created_by=installed_by,
                    created_at=now,
                )
            )
            uow.record(
                ResourceQuarantined(
                    pack_id=pack_id,
                    resource_version_id=rv_id,
                    kind=item.kind.value,
                    key=item.key,
                    reason_kind="compat",
                    reasons=reasons,
                )
            )
    uow.record(
        PackInstalled(
            pack_id=pack_id,
            pack_version_id=version_id,
            slug=manifest.slug,
            version=str(manifest.version),
            digest=candidate.digest,
            trust=trust.value,
            resource_count=len(candidate.resources),
            quarantined_count=quarantined,
        )
    )


def install_candidate(  # noqa: PLR0913 - commands and facades pass the installation dependencies explicitly
    candidate: PackCandidate,
    *,
    origin: str,
    trust: PackTrust,
    installed_by: PrincipalId,
    clock: Clock,
    ids: IdGenerator,
    config: EffectiveConfig,
    uow: UnitOfWork,
    allow_quarantine: bool = True,
    dry_run: bool = False,
) -> InstallPackResult:
    manifest = candidate.manifest
    _check_trust(manifest, trust=trust, origin=origin)
    _check_requires_skm(manifest)
    packs = uow.repo(PackRepository)
    packs.lock_registry()
    pack = packs.find_by_slug(manifest.slug)
    if pack is not None:
        existing = packs.find_version(pack.id, manifest.version)
        if existing is not None:
            if existing.digest != candidate.digest:
                raise Conflict(
                    ErrorCode.EXTENSION_DIGEST_CONFLICT,
                    f"pack {manifest.slug} {manifest.version} is installed with another digest",
                    details={
                        "slug": manifest.slug,
                        "version": str(manifest.version),
                        "installed": existing.digest,
                        "offered": candidate.digest,
                    },
                )
            _require_compat_scan(candidate, trust)
            _check_replay(uow, candidate, existing)
            return _result(
                candidate,
                pack_id=pack.id,
                version_id=existing.id,
                status="already_installed",
                overriding=frozenset(),
            )
        if pack.trust is not trust:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "the trust of a pack never changes between versions",
                details={"reason": "trust_changed", "installed": pack.trust.value, "offered": trust.value},
            )
    overriding = _check_overrides(uow, candidate, pack=pack, trust=trust)
    _check_profiles(uow, config, candidate, trust=trust)
    _check_config_fragment(config, manifest, trust=trust)
    _require_compat_scan(candidate, trust)
    _check_digest_aliases(uow, candidate)
    pack_id = pack.id if pack is not None else PackId(ids.new_id())
    version_id = PackVersionId(ids.new_id())
    if dry_run:
        return _result(
            candidate, pack_id=pack_id, version_id=version_id, status="dry_run", overriding=overriding
        )
    refused = [item for item in candidate.resources if item.compat.verdict is CompatVerdict.QUARANTINE]
    if refused and not allow_quarantine:
        raise PreconditionFailed(
            ErrorCode.RESOURCE_QUARANTINED,
            "the pack has resources that fail compatibility",
            details={"resources": [{"kind": item.kind.value, "key": item.key} for item in refused]},
        )
    if pack is None:
        packs.add(Pack(pack_id, manifest.slug, manifest.title, manifest.publisher, trust, clock.now()))
    _write(
        uow,
        candidate,
        installed_by=installed_by,
        now=clock.now(),
        ids=ids,
        pack_id=pack_id,
        version_id=version_id,
        origin=origin,
        trust=trust,
    )
    return _result(
        candidate, pack_id=pack_id, version_id=version_id, status="installed", overriding=overriding
    )
