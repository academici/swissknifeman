"""``extensions.uninstall_pack_version`` (extensions §7.5): soft, ``state = retired``; history stays readable.

A retired version takes no part in new resolution and a run that pinned it gets ``pinned_pack_missing``. The
last active version of ``core`` cannot go: the system would lose its role profiles. The registry lock comes
before the first read, so two retirements cannot both count the same active versions.
"""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, PreconditionFailed
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.extensions.domain.events import PackVersionUninstalled
from skm.modules.extensions.domain.keys import PackVersionId
from skm.modules.extensions.domain.pack import CORE_PACK, PackState
from skm.modules.extensions.generated.commands import UninstallPackVersion
from skm.modules.extensions.generated.results import UninstallPackVersionResult
from skm.modules.extensions.ports import PackRepository

__all__ = ["SPEC", "handle"]


def handle(cmd: UninstallPackVersion, ctx: CommandContext, uow: UnitOfWork) -> UninstallPackVersionResult:
    del ctx
    packs = uow.repo(PackRepository)
    packs.lock_registry()
    version_id = PackVersionId(cmd.pack_version_id)
    version = packs.get_version(version_id)
    if version.state is PackState.RETIRED:
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            "the pack version is already retired",
            details={"pack_version_id": str(version_id), "state": version.state.value},
        )
    if (
        version.manifest.slug == CORE_PACK
        and len(packs.list_versions(version.pack_id, state=PackState.ACTIVE)) == 1
    ):
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "the only active version of core cannot be retired",
            details={"reason": "last_core_version"},
        )
    packs.set_version_state(version_id, PackState.RETIRED)
    uow.record(
        PackVersionUninstalled(
            pack_id=version.pack_id,
            pack_version_id=version_id,
            slug=version.manifest.slug,
            version=str(version.version),
        )
    )
    return UninstallPackVersionResult(pack_version_id=version_id, state="retired")


SPEC = CommandSpec(
    name="extensions.uninstall_pack_version",
    dto=UninstallPackVersion,
    result=UninstallPackVersionResult,
    permission="ext.install",
    scope_of=None,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
