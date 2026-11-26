"""``extensions.sync_builtin_packs`` (extensions §7.2): every packaged pack in one transaction.

The only caller of ``install_candidate`` with the builtin origin. A failure of any pack rolls all of them
back: built-in packs must be valid, an invalid one is a build defect.
"""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.tokens import TokenEstimator
from skm.modules.extensions.application.candidate import DEFAULT_ALLOWED_LICENSES, build_candidate
from skm.modules.extensions.application.install import install_candidate
from skm.modules.extensions.domain.keys import PackVersionId
from skm.modules.extensions.domain.kinds import ResourceKind
from skm.modules.extensions.domain.pack import BUILTIN_ORIGIN, CORE_PACK, PackTrust
from skm.modules.extensions.generated.commands import SyncBuiltinPacks
from skm.modules.extensions.generated.results import (
    SyncBuiltinPacksResult,
    SyncBuiltinPacksResultAlreadyInstalledItem,
    SyncBuiltinPacksResultInstalledItem,
)
from skm.modules.extensions.ports import (
    BuiltinPacks,
    QuarantineRepository,
    ResourceRepository,
    RuntimeCatalogSeeder,
)

__all__ = ["SPEC", "handle"]


def _config_set(ctx: CommandContext, key: str, default: frozenset[str]) -> frozenset[str]:
    if ctx.config.registry.find(key) is None:
        return default
    raw = ctx.config.get(key)
    return frozenset(str(item) for item in raw) if isinstance(raw, (list, tuple, set, frozenset)) else default


def _config_int(ctx: CommandContext, key: str, default: int) -> int:
    if ctx.config.registry.find(key) is None:
        return default
    raw = ctx.config.get(key)
    return raw if isinstance(raw, int) and not isinstance(raw, bool) else default


def handle(cmd: SyncBuiltinPacks, ctx: CommandContext, uow: UnitOfWork) -> SyncBuiltinPacksResult:
    del cmd
    estimator = ctx.gateways.get(TokenEstimator)
    allowed_licenses = _config_set(ctx, "extensions.compat.allowed_licenses", DEFAULT_ALLOWED_LICENSES)
    max_skill_tokens = _config_int(ctx, "extensions.compat.max_skill_tokens", 8000)
    max_steering_tokens = _config_int(ctx, "extensions.compat.max_steering_tokens", 2000)
    extra_known_tools = _config_set(ctx, "extensions.compat.extra_known_tools", frozenset())
    installed: list[SyncBuiltinPacksResultInstalledItem] = []
    already: list[SyncBuiltinPacksResultAlreadyInstalledItem] = []
    for payload in ctx.gateways.get(BuiltinPacks).payloads():
        candidate = build_candidate(
            payload,
            estimator=estimator,
            scan=True,
            allowed_licenses=allowed_licenses,
            max_skill_tokens=max_skill_tokens,
            max_steering_tokens=max_steering_tokens,
            extra_known_tools=extra_known_tools,
        )
        trust = (
            PackTrust.THIRD_PARTY if candidate.manifest.trust is PackTrust.THIRD_PARTY else PackTrust.BUILTIN
        )
        result = install_candidate(
            candidate,
            origin=BUILTIN_ORIGIN,
            trust=trust,
            installed_by=ctx.actor.principal_id,
            clock=ctx.clock,
            ids=ctx.ids,
            config=ctx.config,
            uow=uow,
        )
        if result.slug == CORE_PACK and ctx.gateways.has(RuntimeCatalogSeeder):
            resources = uow.repo(ResourceRepository)
            pack_version_id = PackVersionId(result.pack_version_id)
            models = resources.versions_of(ResourceKind.RUNTIME_CATALOG, "models", (pack_version_id,))
            if models and not uow.repo(QuarantineRepository).quarantined_ids((models[0].id,)):
                version = resources.get_version(models[0].id).version
                ctx.gateways.get(RuntimeCatalogSeeder)(uow, version.id, version.manifest)
        if result.status == "installed":
            installed.append(SyncBuiltinPacksResultInstalledItem(slug=result.slug, version=result.version))
        else:
            already.append(
                SyncBuiltinPacksResultAlreadyInstalledItem(slug=result.slug, version=result.version)
            )
    return SyncBuiltinPacksResult(installed=tuple(installed), already_installed=tuple(already))


SPEC = CommandSpec(
    name="extensions.sync_builtin_packs",
    dto=SyncBuiltinPacks,
    result=SyncBuiltinPacksResult,
    permission="ext.install",
    scope_of=None,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
