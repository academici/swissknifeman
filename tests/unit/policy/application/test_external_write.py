"""External file writes through the real intent bus and trusted host path."""

import os
from pathlib import Path
from uuid import UUID

import pytest

from skm.application_bus.host import HostContext
from skm.bootstrap.host_services import build_host_services
from skm.kernel.actor import PrincipalKind
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, ValidationFailed
from skm.kernel.ids import HostId, ToolIntentId
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import Role
from skm.modules.policy.domain.approval import ApprovalRequired
from skm.modules.policy.generated.commands import (
    EffectKind,
    ProposeIntent,
    RecordIntentOutcome,
    StartIntentExecution,
)
from skm.modules.policy.host.external_write import write_external
from skm.modules.policy.public import EnforcementMode
from skm.platform.fs import atomic_write
from skm.platform.jsonc.digest import digest_bytes
from unit.policy.application.harness import World
from unit.policy.application.test_lifecycle import approve, view
from unit.policy.domain.layout import ROOTS

HOST_ID = HostId(UUID(int=11))
CONTENT = b"approved content"


class Client:
    def __init__(self, world: World) -> None:
        self.world = world

    def dispatch(self, command: object, *, idempotency_key: str | None = None) -> object:
        return self.world.run(command, key=idempotency_key)


def host(world: World) -> HostContext:
    client = Client(world)
    services = build_host_services(
        {},
        client=client,  # pyright: ignore[reportArgumentType] -- unused in host composition
        plugins=(),
        environ={},
        surface=Surface.CLI,
        host_config=dict,
        recorded_host_id=HOST_ID,
    )
    return HostContext(
        client,  # pyright: ignore[reportArgumentType] -- only dispatch is used by this host operation
        services.gateways,
        HOST_ID,
        None,
        None,
        CancelSource().token,
    )


def write_request(world: World, path: Path) -> ProposeIntent:
    return ProposeIntent(
        scope_id=world.scope_id,
        subject_ref="manual:external-write",
        kind=EffectKind.FS_WRITE_EXTERNAL,
        args={"host_id": str(HOST_ID), "path": str(path), "content_digest": digest_bytes(CONTENT)},
        reason="export requested file",
    )


def proposal(world: World, path: Path) -> ToolIntentId:
    world.allow_effects("fs_write_external")
    result = world.run(write_request(world, path))
    assert result.state == "proposed"
    return ToolIntentId(result.intent_id)


def test_host_write_requires_exact_human_approval(world: World, tmp_path: Path) -> None:
    path = tmp_path.resolve() / "export"
    ctx = host(world)
    intent = proposal(world, path)
    with pytest.raises(ApprovalRequired):
        write_external(ctx, intent, str(path), CONTENT, roots=ROOTS, mode=EnforcementMode.INTERACTIVE)
    approve(world, intent)
    with pytest.raises(Forbidden) as changed:
        write_external(
            ctx, intent, str(path), b"changed content", roots=ROOTS, mode=EnforcementMode.INTERACTIVE
        )
    assert changed.value.code is ErrorCode.APPROVAL_MISMATCH
    with pytest.raises(Forbidden):
        write_external(ctx, intent, str(path), CONTENT, roots=ROOTS, mode=EnforcementMode.AGENT_UNATTENDED)
    assert not path.exists()

    assert write_external(
        ctx, intent, str(path), CONTENT, roots=ROOTS, mode=EnforcementMode.INTERACTIVE
    ) == digest_bytes(CONTENT)
    assert path.read_bytes() == CONTENT
    assert view(world, intent).state == "succeeded"


def test_worker_cannot_request_or_consume_external_write_approval(world: World, tmp_path: Path) -> None:
    path = tmp_path.resolve() / "export"
    world.person("worker", {world.workspace_id: Role.WORKER}, kind=PrincipalKind.WORKER)
    intent = proposal(world, path)
    approve(world, intent)
    worker_proposal = world.run(write_request(world, path), "worker")
    assert worker_proposal.state == "denied"
    approved = view(world, intent)
    with pytest.raises(Forbidden) as caught:
        world.run(StartIntentExecution(intent_id=intent, args_digest=approved.args_digest), "worker")
    assert caught.value.code is ErrorCode.FORBIDDEN
    assert view(world, intent).state == "approved"

    world.run(StartIntentExecution(intent_id=intent, args_digest=approved.args_digest))
    with pytest.raises(Forbidden) as outcome:
        world.run(RecordIntentOutcome(intent_id=intent, outcome="succeeded", receipt={}), "worker")
    assert outcome.value.code is ErrorCode.FORBIDDEN
    assert view(world, intent).state == "executing"


@pytest.mark.parametrize("swap", ["parent", "leaf"])
def test_host_write_rejects_symlink_swapped_during_staging(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, swap: str
) -> None:
    root = tmp_path.resolve()
    parent, outside = root / "approved", root / "outside"
    parent.mkdir()
    outside.mkdir()
    target, victim = parent / "file", outside / "file"
    target.write_bytes(b"initial")
    victim.write_bytes(b"untouched")
    intent = proposal(world, target)
    approve(world, intent)
    staging_write = atomic_write._write_temp

    def swap_after_write(fd: int, data: bytes) -> None:
        staging_write(fd, data)
        if swap == "parent":
            parent.rename(root / "moved")
            os.symlink(outside, parent, target_is_directory=True)
        else:
            target.unlink()
            os.symlink(victim, target)

    monkeypatch.setattr(atomic_write, "_write_temp", swap_after_write)
    with pytest.raises(ValidationFailed) as caught:
        write_external(
            host(world), intent, str(target), CONTENT, roots=ROOTS, mode=EnforcementMode.INTERACTIVE
        )
    assert caught.value.code is ErrorCode.INVALID_REFERENCE
    assert victim.read_bytes() == b"untouched"
    if swap == "parent":
        assert (root / "moved" / "file").read_bytes() == b"initial"
    assert view(world, intent).state == "failed"
