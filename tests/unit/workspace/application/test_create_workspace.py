"""``workspace.create_workspace`` (workspace §7): scope, first owner, event and result in one transaction."""

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access.domain.roles import Role
from skm.modules.access.ports import MembershipRepository
from skm.modules.workspace.public import CreateWorkspace


def test_creates_the_scope_the_row_the_owner_and_the_event(world) -> None:
    result = world.run(CreateWorkspace(slug="personal", title="  Personal  "))
    assert (result.slug, result.row_version) == ("personal", 1)
    with world.uow(readonly=True) as uow:
        scope = uow.repo(ScopeRegistry).get(ScopeId(result.workspace_id))
        owner = uow.repo(MembershipRepository).get(
            ScopeId(result.workspace_id), world.actor("owner").principal_id
        )
    assert (scope.kind, scope.parent_id, scope.workspace_id) == (
        ScopeKind.WORKSPACE,
        world.instance,
        result.workspace_id,
    )
    assert owner is not None
    assert owner.role is Role.OWNER
    assert world.tables().workspaces[result.workspace_id].title == "Personal"  # trimmed
    [event] = world.events("workspace-created")
    assert (event.stream_kind, event.stream_id, event.workspace_id) == (
        "workspace",
        result.workspace_id,
        result.workspace_id,
    )
    assert event.payload == {
        "workspace_id": str(result.workspace_id),
        "slug": "personal",
        "title": "Personal",
    }


def test_a_taken_slug_conflicts_and_writes_nothing(world) -> None:
    world.workspace("personal")
    before = world.snapshot()
    with pytest.raises(SkmError) as caught:
        world.run(CreateWorkspace(slug="personal", title="Other"))
    assert caught.value.code is ErrorCode.ALREADY_EXISTS
    assert world.snapshot() == before


@pytest.mark.parametrize("slug", ["A", "a", "two--hyphens", "trailing-", "has space"])
def test_an_invalid_slug_is_refused(world, slug: str) -> None:
    with pytest.raises(SkmError) as caught:
        world.run(CreateWorkspace(slug=slug, title="T"))
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    assert world.events("workspace-created") == []


def test_a_person_without_the_instance_right_is_forbidden(world) -> None:
    stranger = world.person("stranger")
    before = world.snapshot()
    with pytest.raises(SkmError) as caught:
        world.run(CreateWorkspace(slug="mine", title="Mine"), stranger)
    assert caught.value.code is ErrorCode.FORBIDDEN
    assert world.snapshot() == before


def test_the_same_idempotency_key_returns_the_same_result_once(world) -> None:
    first = world.run(CreateWorkspace(slug="personal", title="P"), key="k1")
    again = world.run(CreateWorkspace(slug="personal", title="P"), key="k1")
    assert again == first
    assert len(world.events("workspace-created")) == 1
