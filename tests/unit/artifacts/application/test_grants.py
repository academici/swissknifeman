"""Access grants and the authorization of version reads (artifacts §4.2a, §8, §13; ARTIFACT-01/05, ACCESS-02).

A worker reads a file version only with an active ``assignment`` grant on exactly that version; the right of
an ordinary reader is decided on the scope of the *stored* file. Equal digests share neither blobs' rights
nor grants. The facade functions run in the caller's unit of work and are exercised the way an execution
handler calls them: in a unit that the caller commits (or drops).
"""

from collections.abc import Callable
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

import pytest

from skm.application_bus.context import CommandContext, QueryContext
from skm.kernel.actor import Actor
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, SkmError
from skm.kernel.ids import FileVersionId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access.public import Role
from skm.modules.artifacts import public
from skm.modules.artifacts.application.commands import add_file_version, restore_file, trash_file
from skm.modules.artifacts.application.queries import (
    get_file,
    get_file_version,
    list_file_versions,
    open_file_version_content,
)
from skm.modules.artifacts.domain.access_grant import GrantReason
from skm.modules.artifacts.generated.commands import AddFileVersion
from skm.modules.artifacts.public import (
    GetFile,
    GetFileVersion,
    ListFileVersions,
    OpenFileVersionContent,
    RestoreFile,
    TrashFile,
)
from unit.artifacts.application.test_commands import SOURCE_V, TEXT, Setup, World, build_world

CLAIM = "assignment-1"
TTL = timedelta(hours=4)


@pytest.fixture
def world() -> World:
    return build_world()


@pytest.fixture
def setup(world: World) -> Setup:
    return Setup(world)


class Files:
    """Two files with the same bytes in one workspace, a worker and a second claim."""

    def __init__(self, world: World, setup: Setup) -> None:
        self.world, self.setup = world, setup
        first = world.add_file(setup.ws, world.stage(setup.ws), title="a", project_id=setup.project)
        second = world.add_file(setup.ws, world.stage(setup.ws), title="b", project_id=setup.project)
        self.a, self.b = FileVersionId(first.file_version_id), FileVersionId(second.file_version_id)
        self.file_a, self.file_b = first.file_id, second.file_id
        self.worker = world.worker("w1", setup.ws)
        self.other_worker = world.worker("w2", setup.ws)

    def grant(
        self,
        versions: tuple[FileVersionId, ...],
        *,
        who: Actor | None = None,
        ref: str = CLAIM,
        ttl: timedelta = TTL,
    ) -> int:
        world = self.world
        with world.uow() as uow:
            added = public.grant_access(
                uow,
                principal_id=(who or self.worker).principal_id,
                version_ids=versions,
                reason=GrantReason.ASSIGNMENT,
                ref=ref,
                expires_at=world.clock.now() + ttl,
                ids=world.ids,
                now=world.clock.now(),
            )
            uow.commit()
        return added

    def revoke(self, ref: str = CLAIM) -> int:
        with self.world.uow() as uow:
            closed = public.revoke_grants(
                uow, reason=GrantReason.ASSIGNMENT, ref=ref, now=self.world.clock.now()
            )
            uow.commit()
        return closed

    def extend(self, ttl: timedelta, ref: str = CLAIM) -> int:
        world = self.world
        with world.uow() as uow:
            count = public.extend_grants(
                uow,
                reason=GrantReason.ASSIGNMENT,
                ref=ref,
                expires_at=world.clock.now() + ttl,
                now=world.clock.now(),
            )
            uow.commit()
        return count

    def read(self, version: FileVersionId, who: Actor | str | None = None) -> Any:
        return self.world.ask(GetFileVersion(file_version_id=version), who or self.worker)

    def open(self, version: FileVersionId, who: Actor | str | None = None) -> Any:
        return self.world.ask(OpenFileVersionContent(file_version_id=version), who or self.worker)

    def forbidden(self, fn: Any) -> SkmError:
        with pytest.raises(SkmError) as caught:
            fn()
        assert caught.value.code is ErrorCode.FORBIDDEN
        return caught.value

    def rows(self) -> dict[Any, Any]:
        return dict(self.world.tables().grants)


@pytest.fixture
def files(world: World, setup: Setup) -> Files:
    return Files(world, setup)


# ---------------------------------------------------------------------------------------------- issue
def test_grant_access_adds_one_row_per_exact_version_in_the_versions_workspace(files: Files) -> None:
    assert files.grant((files.a, files.b)) == 2
    rows = files.rows().values()
    assert {row.file_version_id for row in rows} == {files.a, files.b}
    assert {row.workspace_id for row in rows} == {files.setup.ws}
    assert {(row.principal_id, row.reason, row.ref, row.revoked_at) for row in rows} == {
        (files.worker.principal_id, GrantReason.ASSIGNMENT, CLAIM, None)
    }


def test_a_repeated_issue_of_the_same_claim_appends_nothing(files: Files) -> None:
    assert files.grant((files.a,)) == 1
    before = files.rows()
    assert files.grant((files.a,)) == 0
    assert files.rows() == before


def test_a_grant_must_expire_after_it_is_issued_and_names_a_known_version(files: Files) -> None:
    with pytest.raises(SkmError) as caught:
        files.grant((files.a,), ttl=timedelta(0))
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    with pytest.raises(SkmError) as unknown:
        files.grant((files.a, FileVersionId(UUID(int=99))))
    assert unknown.value.code is ErrorCode.NOT_FOUND
    assert files.rows() == {}  # nothing was added by either refusal


def test_a_dropped_unit_leaves_no_grant(files: Files) -> None:
    world = files.world
    with world.uow() as uow:
        public.grant_access(
            uow,
            principal_id=files.worker.principal_id,
            version_ids=(files.a,),
            reason=GrantReason.ASSIGNMENT,
            ref=CLAIM,
            expires_at=world.clock.now() + TTL,
            ids=world.ids,
            now=world.clock.now(),
        )
    assert files.rows() == {}


# ---------------------------------------------------------------------------------------------- reads
def test_a_worker_without_a_grant_reads_nothing(files: Files) -> None:
    error = files.forbidden(lambda: files.read(files.a))
    assert error.details["reason"] == "no_active_grant"
    files.forbidden(lambda: files.open(files.a))
    files.forbidden(lambda: files.world.ask(GetFile(file_id=files.file_a), files.worker))


def test_a_grant_on_one_version_opens_nothing_of_an_equal_digest_version(files: Files) -> None:
    files.grant((files.a,))
    granted = files.read(files.a)  # the granted version reads
    assert files.read(files.b, "owner").digest == granted.digest  # same bytes, same workspace
    files.forbidden(lambda: files.read(files.b))
    files.forbidden(lambda: files.open(files.b))
    assert {row.file_version_id for row in files.rows().values()} == {files.a}


def test_a_grant_belongs_to_its_principal(files: Files) -> None:
    files.grant((files.a,))
    files.forbidden(lambda: files.read(files.a, files.other_worker))


def test_a_grant_expires_with_the_clock(files: Files) -> None:
    files.grant((files.a,))
    files.world.clock.advance(TTL - timedelta(seconds=1))
    assert files.read(files.a).file_version_id == files.a
    files.world.clock.advance(timedelta(seconds=1))
    files.forbidden(lambda: files.read(files.a))
    files.forbidden(lambda: files.open(files.a))


def test_a_grant_never_widens_the_scope_of_the_file(files: Files) -> None:
    """The scope is the stored file's: a worker of another workspace holds no ``file.read`` here at all."""
    foreign = files.world.worker("foreign", files.setup.other_ws)
    files.grant((files.a,), who=foreign)
    files.forbidden(lambda: files.read(files.a, foreign))


def test_an_ordinary_reader_needs_no_grant_but_its_scope(files: Files) -> None:
    assert files.read(files.a, "viewer").file_version_id == files.a
    files.forbidden(lambda: files.read(files.a, "outsider"))
    files.forbidden(lambda: files.open(files.a, "outsider"))
    other = files.world.person("other_member", {ScopeId(files.setup.other_ws): Role.OWNER})
    files.forbidden(lambda: files.read(files.a, other))  # a role elsewhere is no right here


def test_a_worker_lists_and_gets_only_what_it_holds_a_grant_on(files: Files) -> None:
    world = files.world
    second = world.add_version(files.file_a, world.stage(files.setup.ws, b"v2\n"), version=2)
    v2 = FileVersionId(second.file_version_id)
    files.grant((files.a,))
    listed = world.ask(ListFileVersions(file_id=files.file_a), files.worker)
    assert [item.file_version_id for item in listed.items] == [files.a]  # v2 is not granted
    files.forbidden(lambda: world.ask(GetFile(file_id=files.file_a), files.worker))  # current is v2
    files.grant((v2,))
    assert world.ask(GetFile(file_id=files.file_a), files.worker).current_version.file_version_id == v2
    both = world.ask(ListFileVersions(file_id=files.file_a), files.worker)
    assert [item.version_no for item in both.items] == [2, 1]


def test_a_grant_lets_a_worker_read_but_never_change_a_logical_file(files: Files) -> None:
    files.grant((files.a,))
    world = files.world
    staged = world.stage(files.setup.ws, b"v2\n")
    assert world.tables().files[files.file_a].row_version == 2
    for dto in (
        TrashFile(file_id=files.file_a, expected_row_version=2, reason="x"),
        RestoreFile(file_id=files.file_a, expected_row_version=2),
    ):
        files.forbidden(lambda dto=dto: world.run(dto, files.worker))
    files.forbidden(lambda: world.add_version(files.file_a, staged, version=2, actor=files.worker))
    files.forbidden(lambda: world.add_file(files.setup.ws, staged, actor=files.worker))
    assert world.tables().files[files.file_a].row_version == 2


# ---------------------------------------------------------------------------------------------- revoke
def test_revoke_closes_every_grant_of_the_claim_and_only_that_claim(files: Files) -> None:
    files.grant((files.a, files.b))
    files.grant((files.a,), ref="assignment-2", who=files.other_worker)
    assert files.revoke() == 2
    files.forbidden(lambda: files.read(files.a))
    files.forbidden(lambda: files.read(files.b))
    assert files.read(files.a, files.other_worker).file_version_id == files.a  # another claim is untouched
    assert files.revoke() == 0  # nothing left to close


def test_a_revoked_claim_can_be_issued_again(files: Files) -> None:
    files.grant((files.a,))
    files.revoke()
    assert files.grant((files.a,)) == 1
    assert files.read(files.a).file_version_id == files.a


def test_a_new_open_after_revoke_is_refused_while_an_open_stream_finishes(files: Files) -> None:
    files.grant((files.a,))
    handle = files.open(files.a)
    stream = files.world.blobs.open(handle.location)  # immutable bytes already being read
    files.revoke()
    files.forbidden(lambda: files.open(files.a))
    with stream:
        assert stream.read() == TEXT


def test_bytes_are_got_only_through_an_authorized_file_version(files: Files) -> None:
    files.grant((files.a,))
    handle = files.open(files.a)
    assert (handle.size_bytes, handle.filename) == (len(TEXT), "notes.txt")
    with files.world.blobs.open(handle.location) as stream:
        assert stream.read() == TEXT
    assert handle.digest not in str(files.rows())  # a digest is never an access token: no grant carries it
    files.forbidden(lambda: files.open(files.b))


# ---------------------------------------------------------------------------------------------- renew
def test_extend_moves_the_expiry_of_existing_grants_without_new_rows(files: Files) -> None:
    files.grant((files.a, files.b))
    before = files.rows()
    files.world.clock.advance(timedelta(hours=1))
    assert files.extend(timedelta(hours=8)) == 2
    after = files.rows()
    assert set(after) == set(before)  # the same rows: nothing was appended
    for grant_id, row in before.items():
        moved = after[grant_id]
        assert moved.expires_at == files.world.clock.now() + timedelta(hours=8)
        assert (moved.principal_id, moved.file_version_id, moved.reason, moved.ref, moved.created_at) == (
            row.principal_id,
            row.file_version_id,
            row.reason,
            row.ref,
            row.created_at,
        )


def test_repeated_renewals_never_grow_the_table(files: Files) -> None:
    files.grant((files.a,))
    for hour in range(1, 6):
        files.world.clock.advance(timedelta(minutes=30))
        files.extend(timedelta(hours=hour))
    assert len(files.rows()) == 1


def test_extend_never_shortens_an_expiry(files: Files) -> None:
    files.grant((files.a,), ttl=timedelta(hours=10))
    [row] = files.rows().values()
    files.extend(timedelta(hours=1))
    assert next(iter(files.rows().values())).expires_at == row.expires_at


def test_extend_does_not_revive_an_expired_or_a_revoked_grant(files: Files) -> None:
    files.grant((files.a,))
    files.world.clock.advance(TTL)
    assert files.extend(timedelta(hours=8)) == 0  # expired: not revived
    files.forbidden(lambda: files.read(files.a))
    files.grant((files.b,), ref="assignment-3")
    files.revoke("assignment-3")
    assert files.extend(timedelta(hours=8), ref="assignment-3") == 0
    files.forbidden(lambda: files.read(files.b))


def test_extend_touches_only_its_own_claim(files: Files) -> None:
    files.grant((files.a,))
    files.grant((files.b,), ref="assignment-2", who=files.other_worker)
    claim_two = {r.id: r.expires_at for r in files.rows().values() if r.ref == "assignment-2"}
    files.extend(timedelta(hours=9))
    assert {r.id: r.expires_at for r in files.rows().values() if r.ref == "assignment-2"} == claim_two


def test_a_renewed_grant_keeps_the_read_alive_past_the_first_expiry(files: Files) -> None:
    files.grant((files.a,))
    files.world.clock.advance(TTL - timedelta(minutes=1))
    files.extend(TTL)
    files.world.clock.advance(timedelta(minutes=30))  # past the original expiry
    assert files.read(files.a).file_version_id == files.a


# ---------------------------------------------------------------------------------------------- misc
def test_the_view_of_a_version_carries_the_verdict_but_no_instruction_trust(files: Files) -> None:
    """Safety ``ok`` is a scan result, not trust: the view has no trust field and the classification stays."""
    view = files.read(files.a, "owner")
    assert view.safety_verdict == "ok"
    assert view.classification.value == "internal"
    assert not any("trust" in name for name in type(view).__slots__)


# --------------------------------------------------------------------------------------- narrowed tokens
READ_ONLY = frozenset({"file.read"})


def test_a_file_read_only_token_reads_through_the_authorization_of_the_stored_file(files: Files) -> None:
    """The bus must not ask such a token for ``token.own``; the stored file decides the right."""
    world, ws = files.world, files.setup.ws
    token = world.token_actor("viewer", permissions=READ_ONLY, scope=ScopeId(ws))
    version = files.read(files.a, token)
    assert version.file_version_id == files.a
    assert world.ask(GetFile(file_id=files.file_a), token).file_id == files.file_a
    listed = world.ask(ListFileVersions(file_id=files.file_a), token)
    assert [item.file_version_id for item in listed.items] == [files.a]
    assert files.open(files.a, token).size_bytes == len(TEXT)


def test_a_token_without_file_read_or_outside_its_scope_reads_nothing(files: Files) -> None:
    world, ws = files.world, files.setup.ws
    no_read = world.token_actor("viewer", permissions=frozenset({"file.write"}), scope=ScopeId(ws), serial=2)
    files.forbidden(lambda: files.read(files.a, no_read))
    elsewhere = world.token_actor(
        "viewer", permissions=READ_ONLY, scope=ScopeId(files.setup.other_ws), serial=3
    )
    files.forbidden(lambda: files.read(files.a, elsewhere))  # a token of another workspace
    files.forbidden(lambda: files.open(files.a, elsewhere))
    files.forbidden(
        lambda: files.read(files.a, world.token_actor("outsider", permissions=READ_ONLY, serial=4))
    )
    assert files.read(files.a, "viewer").file_version_id == files.a  # the right itself is untouched


def test_a_token_that_cannot_write_gains_no_write_from_its_read_right(files: Files) -> None:
    world = files.world
    token = world.token_actor("viewer", permissions=READ_ONLY, scope=ScopeId(files.setup.ws), serial=5)
    staged = world.stage(files.setup.ws, b"v2\n")
    files.forbidden(lambda: world.add_version(files.file_a, staged, version=2, actor=token))
    files.forbidden(
        lambda: world.run(TrashFile(file_id=files.file_a, expected_row_version=2, reason="x"), token)
    )
    assert world.staged_row(staged).consumed_at is None


READ_BY_ID = (
    lambda files: GetFileVersion(file_version_id=files.a),
    lambda files: OpenFileVersionContent(file_version_id=files.a),
    lambda files: GetFile(file_id=files.file_a),
    lambda files: ListFileVersions(file_id=files.file_a),
)
UNKNOWN_BY_ID = (
    GetFileVersion(file_version_id=FileVersionId(UUID(int=77))),
    OpenFileVersionContent(file_version_id=FileVersionId(UUID(int=77))),
    GetFile(file_id=UUID(int=78)),
    ListFileVersions(file_id=UUID(int=78)),
)
OPAQUE = {"permission": "file.read", "scope": None, "reason_code": "ROLE_LACKS_PERMISSION"}


def test_an_unknown_id_fails_closed_and_a_denial_reveals_nothing_of_the_stored_file(files: Files) -> None:
    """The bus resolves the scope from the stored file; a refusal looks the same for a file the caller may
    not read and for an id that does not exist, and names neither the workspace nor the project."""
    world, project = files.world, files.setup.project
    world.person("neighbour", {ScopeId(files.setup.other_ws): Role.VIEWER})
    for dto in UNKNOWN_BY_ID:  # an instance-wide reader learns the id is unknown, the rest are refused
        with pytest.raises(SkmError) as unknown:
            world.ask(dto, "owner")
        assert unknown.value.code is ErrorCode.NOT_FOUND
        assert files.forbidden(lambda dto=dto: world.ask(dto, "viewer")).details == OPAQUE
    for dto in (*(make(files) for make in READ_BY_ID), *UNKNOWN_BY_ID):
        refused = files.forbidden(lambda dto=dto: world.ask(dto, "neighbour"))
        assert refused.details == OPAQUE
        assert str(files.setup.ws) not in str(refused) + repr(refused.details)
        assert str(project) not in str(refused) + repr(refused.details)
    denied = [row for row in world.backend.committed.core.audit if row.decision == "denied"]
    scopes = {cast("Any", row.target)["scope"]["id"] for row in denied}
    assert str(project) in scopes  # the audit row, unlike the reply, names the real scope
    assert str(world.instance) in scopes  # and the instance scope an unknown id was decided on


# --------------------------------------------------------------------------------- narrowed write tokens
WRITE_ONLY = frozenset({"file.write"})


def test_a_file_write_token_changes_a_file_through_the_authorization_of_the_stored_file(files: Files) -> None:
    world, ws = files.world, files.setup.ws
    world.person("member", {ScopeId(ws): Role.MEMBER})
    token = world.token_actor("member", permissions=WRITE_ONLY, scope=ScopeId(ws), serial=20)
    trashed = world.run(TrashFile(file_id=files.file_a, expected_row_version=2, reason="x"), token)
    assert trashed.state == "trashed"
    restored = world.run(RestoreFile(file_id=files.file_a, expected_row_version=trashed.row_version), token)
    assert restored.state == "active"
    added = world.add_version(
        files.file_a, world.stage(ws, b"v2\n"), version=restored.row_version, actor=token
    )
    assert added.version_no == 2
    project_token = world.token_actor(
        "member", permissions=WRITE_ONLY, scope=ScopeId(files.setup.project), serial=21
    )
    again = world.run(TrashFile(file_id=files.file_b, expected_row_version=2, reason="x"), project_token)
    assert again.state == "trashed"  # a token of the file's own project is enough


def test_a_file_write_token_gains_nothing_outside_its_scope_or_its_rights(files: Files) -> None:
    world, ws, other = files.world, files.setup.ws, files.setup.other_ws
    world.person("member", {ScopeId(ws): Role.MEMBER})
    trash = TrashFile(file_id=files.file_a, expected_row_version=2, reason="x")
    elsewhere = world.token_actor("member", permissions=WRITE_ONLY, scope=ScopeId(other), serial=22)
    read_only = world.token_actor("member", permissions=READ_ONLY, scope=ScopeId(ws), serial=23)
    viewer = world.token_actor("viewer", permissions=WRITE_ONLY, scope=ScopeId(ws), serial=24)  # no role
    outsider = world.token_actor("outsider", permissions=WRITE_ONLY, serial=25)
    staged = world.stage(ws, b"v2\n")
    for token in (elsewhere, read_only, viewer, outsider):
        world.refused(ErrorCode.FORBIDDEN, lambda token=token: world.run(trash, token))
        world.refused(
            ErrorCode.FORBIDDEN,
            lambda token=token: world.add_version(files.file_a, staged, version=2, actor=token),
        )
    assert world.staged_row(staged).consumed_at is None
    # a token of the project cannot reach a workspace-level file next to it
    loose = world.add_file(ws, world.stage(ws), title="loose")
    project_token = world.token_actor(
        "member", permissions=WRITE_ONLY, scope=ScopeId(files.setup.project), serial=26
    )
    world.refused(
        ErrorCode.FORBIDDEN,
        lambda: world.run(
            TrashFile(file_id=loose.file_id, expected_row_version=2, reason="x"), project_token
        ),
    )
    unknown = TrashFile(file_id=UUID(int=79), expected_row_version=1, reason="x")
    refused = world.refused(ErrorCode.FORBIDDEN, lambda: world.run(unknown, "member"))
    assert refused.details == {**OPAQUE, "permission": "file.write"}
    with pytest.raises(SkmError) as missing:
        world.run(unknown)  # the instance owner is told the id is unknown
    assert missing.value.code is ErrorCode.NOT_FOUND


# ------------------------------------------------------------------------------------- bound handlers
def query_context(files: Files, scope: ScopeRef, who: str = "owner") -> QueryContext:
    world = files.world
    return QueryContext(
        actor=world.actor(who),
        meta=world.meta(),
        scope=scope,
        scope_chain=(),
        clock=world.clock,
        config=cast("Any", None),
        log=cast("Any", None),
        gateways=cast("Any", None),
    )


def command_context(files: Files, scope: ScopeRef, who: str = "owner") -> CommandContext:
    world = files.world
    return CommandContext(
        actor=world.actor(who),
        meta=world.meta(),
        scope=scope,
        scope_chain=(),
        clock=world.clock,
        ids=world.ids,
        entropy=cast("Any", None),
        config=cast("Any", None),
        log=cast("Any", None),
        gateways=cast("Any", None),
    )


def test_a_query_handler_refuses_a_file_outside_the_scope_the_bus_authorised(files: Files) -> None:
    """A race (or a defective resolver) must fail closed: nothing of the file is returned."""
    world, setup = files.world, files.setup
    right = ScopeRef(ScopeKind.PROJECT, ScopeId(setup.project))
    wrong = (
        ScopeRef(ScopeKind.WORKSPACE, ScopeId(setup.ws)),  # an ancestor is not the file's own scope
        ScopeRef(ScopeKind.WORKSPACE, ScopeId(setup.other_ws)),
        ScopeRef(ScopeKind.INSTANCE, world.instance),
    )
    handlers = (
        (get_file.handle, GetFile(file_id=files.file_a)),
        (list_file_versions.handle, ListFileVersions(file_id=files.file_a)),
        (get_file_version.handle, GetFileVersion(file_version_id=files.a)),
        (open_file_version_content.handle, OpenFileVersionContent(file_version_id=files.a)),
    )
    for typed, dto in handlers:
        handle = cast("Callable[[Any, Any, Any], object]", typed)
        for scope in wrong:
            with world.uow(readonly=True) as uow, pytest.raises(Forbidden) as caught:
                handle(dto, query_context(files, scope), uow)
            assert caught.value.details == {"reason": "scope_changed"}
        with world.uow(readonly=True) as uow:
            assert handle(dto, query_context(files, right), uow) is not None


def test_a_command_handler_refuses_a_file_outside_the_scope_the_bus_authorised(files: Files) -> None:
    world, setup = files.world, files.setup
    wrong = ScopeRef(ScopeKind.WORKSPACE, ScopeId(setup.ws))
    version = AddFileVersion(
        file_id=files.file_a,
        expected_row_version=2,
        blob=world.stage(setup.ws, b"v2\n").version_ref(),
        original_filename="n.txt",
        declared_media_type=None,
        source=SOURCE_V,
    )
    handlers = (
        (trash_file.handle, TrashFile(file_id=files.file_a, expected_row_version=2, reason="x")),
        (restore_file.handle, RestoreFile(file_id=files.file_a, expected_row_version=2)),
        (add_file_version.handle, version),
    )
    for typed, dto in handlers:
        handle = cast("Callable[[Any, Any, Any], object]", typed)
        before = world.snapshot()
        with world.uow() as uow, pytest.raises(Forbidden) as caught:
            handle(dto, command_context(files, wrong), uow)
        assert caught.value.details == {"reason": "scope_changed"}
        assert world.snapshot() == before


# --------------------------------------------------------------------------------------- assignment binding
def assignment_token(files: Files, assignment: UUID, *, who: Actor | None = None, serial: int = 10) -> Actor:
    setup = files.setup
    run = files.world.run_scope(setup.ws, setup.project, serial=serial)
    return files.world.token_actor(
        who or files.worker, permissions=READ_ONLY, scope=run, assignment=assignment, serial=serial
    )


def test_an_assignment_token_reads_only_with_the_grant_of_its_own_assignment(files: Files) -> None:
    mine, theirs = UUID(int=0xA1), UUID(int=0xA2)
    files.grant((files.a,), ref=str(theirs))  # a grant of another assignment of the same principal
    token = assignment_token(files, mine)
    error = files.forbidden(lambda: files.read(files.a, token))
    assert error.details["reason"] == "no_active_grant"
    files.forbidden(lambda: files.open(files.a, token))
    files.grant((files.a,), ref=str(mine), ttl=TTL / 2)  # its own claim, expiring *earlier* than the other
    assert files.read(files.a, token).file_version_id == files.a
    assert files.open(files.a, token).size_bytes == len(TEXT)
    files.forbidden(lambda: files.read(files.b, token))  # equal bytes, other version: no grant


def test_an_assignment_token_does_not_inherit_the_grant_of_a_sibling_assignment(files: Files) -> None:
    first, second = UUID(int=0xA3), UUID(int=0xA4)
    files.grant((files.a,), ref=str(first))
    token_first = assignment_token(files, first, serial=11)
    token_second = assignment_token(files, second, serial=12)
    assert files.read(files.a, token_first).file_version_id == files.a
    files.forbidden(lambda: files.read(files.a, token_second))
    files.revoke(str(first))
    files.forbidden(lambda: files.read(files.a, token_first))  # revoked: closed for its own token as well


def test_an_assignment_grant_of_another_principal_is_no_grant_for_this_token(files: Files) -> None:
    assignment = UUID(int=0xA5)
    files.grant((files.a,), ref=str(assignment), who=files.other_worker)
    files.forbidden(lambda: files.read(files.a, assignment_token(files, assignment, serial=13)))


# ---------------------------------------------------------------------------------------------- exact claims
def test_a_repeated_issue_of_a_claim_is_a_no_op_even_when_another_claim_expires_later(files: Files) -> None:
    assert files.grant((files.a,), ref="claim-long", ttl=timedelta(hours=8)) == 1
    assert files.grant((files.a,), ref="claim-short", ttl=timedelta(hours=1)) == 1
    before = files.rows()
    # the latest-expiring grant of the version is "claim-long"; "claim-short" is still held exactly
    assert files.grant((files.a,), ref="claim-short", ttl=timedelta(hours=1)) == 0
    assert files.grant((files.a,), ref="claim-long", ttl=timedelta(hours=2)) == 0
    assert files.grant((files.a, files.b), ref="claim-short", ttl=timedelta(hours=1)) == 1  # only b is new
    assert len(files.rows()) == len(before) + 1
    assert {row.ref for row in files.rows().values() if row.file_version_id == files.a} == {
        "claim-long",
        "claim-short",
    }


def test_a_claim_is_issued_again_after_it_expired_or_was_revoked(files: Files) -> None:
    files.grant((files.a,))
    files.world.clock.advance(TTL)  # expired, never revoked
    assert files.grant((files.a,)) == 1
    files.revoke()
    assert files.grant((files.a,)) == 1
    assert files.read(files.a).file_version_id == files.a
    assert len(files.rows()) == 3


def test_a_grant_issue_that_is_rolled_back_leaves_no_row_and_no_claim(files: Files) -> None:
    world = files.world
    with world.uow() as uow:
        public.grant_access(
            uow,
            principal_id=files.worker.principal_id,
            version_ids=(files.a, files.b),
            reason=GrantReason.ASSIGNMENT,
            ref=CLAIM,
            expires_at=world.clock.now() + TTL,
            ids=world.ids,
            now=world.clock.now(),
        )
        uow.rollback()
    assert files.rows() == {}
    files.forbidden(lambda: files.read(files.a))
    assert files.grant((files.a, files.b)) == 2  # the claim was never recorded
