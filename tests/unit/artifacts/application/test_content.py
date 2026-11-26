"""File and version reads, the read facades and ``register_file_version`` (artifacts §8, §13).

The facades run in the caller's unit of work and check no permission; the queries decide ``file.read`` on the
stored file. Foreign or consumed refs and the pin lookups (``require_ready_versions``,
``latest_ready_version``, ``read_text_content``) are proved on the memory backend.
"""

import base64
import inspect
import io
import json
from datetime import timedelta
from typing import Any, BinaryIO, cast
from uuid import UUID

import pytest

from skm.adapters.memory.artifacts.repositories import MemoryBlobContentReader
from skm.adapters.memory.artifacts.state import artifacts_state
from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import FileVersionId
from skm.modules.artifacts import public
from skm.modules.artifacts.application import reads
from skm.modules.artifacts.domain.blob import BlobAvailability, LocationState
from skm.modules.artifacts.domain.classification import Classification
from skm.modules.artifacts.domain.content_safety import SafetyReport
from skm.modules.artifacts.domain.file import FileOrigin
from skm.modules.artifacts.domain.file_version import VersionSource
from skm.modules.artifacts.generated import commands as wire
from skm.modules.artifacts.generated import queries
from skm.modules.artifacts.module import MODULE
from skm.modules.artifacts.ports import BlobContentReader, BlobRepository
from skm.modules.artifacts.public import (
    GetFile,
    GetFileVersion,
    ListFiles,
    ListFileVersions,
    OpenFileVersionContent,
    TrashFile,
)
from unit.artifacts.application.test_commands import TEXT, Setup, TrickleStore, World, build_world

EVIDENCE = VersionSource(kind="evidence", ref="attempt-1", captured_at=None)


@pytest.fixture
def world() -> World:
    return build_world()


@pytest.fixture
def setup(world: World) -> Setup:
    return Setup(world)


def code_of(fn: Any) -> SkmError:
    with pytest.raises(SkmError) as caught:
        fn()
    return caught.value


def read_in_uow(world: World, fn: Any) -> Any:
    with world.uow(readonly=True) as uow:
        return fn(uow)


def make_missing(world: World, version_id: Any) -> None:
    """The blob's only location is marked missing, as ``skm storage verify --repair-safe`` would."""
    with world.uow() as uow:
        blob_id = world.tables().versions[version_id].blob_id
        location = world.tables().locations[blob_id][0]
        uow.repo(BlobRepository).mark_location(
            blob_id, location.backend_id, LocationState.MISSING, world.clock.now()
        )
        uow.commit()


def storage_key(world: World, version_id: Any) -> str:
    return world.tables().locations[world.tables().versions[version_id].blob_id][0].storage_key


# ---------------------------------------------------------------------------------------------- queries
def test_get_file_returns_the_file_and_its_current_version(world: World, setup: Setup) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws), project_id=setup.project, title="  notes  ")
    second = world.add_version(first.file_id, world.stage(setup.ws, b"v2\n"), version=2, filename="n2.txt")
    view = world.ask(GetFile(file_id=first.file_id), "viewer")
    assert (view.title, view.state, view.project_id, view.workspace_id) == (
        "notes",
        "active",
        setup.project,
        setup.ws,
    )
    assert view.current_version.file_version_id == second.file_version_id
    assert (view.current_version.version_no, view.current_version.original_filename) == (2, "n2.txt")
    assert view.row_version == world.tables().files[first.file_id].row_version


def test_the_scope_of_a_file_read_is_the_stored_file_not_the_request(world: World, setup: Setup) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws))
    for dto in (
        GetFile(file_id=first.file_id),
        ListFileVersions(file_id=first.file_id),
    ):
        assert code_of(lambda dto=dto: world.ask(dto, "outsider")).code is ErrorCode.FORBIDDEN
    version = GetFileVersion(file_version_id=first.file_version_id)
    assert code_of(lambda: world.ask(version, "outsider")).code is ErrorCode.FORBIDDEN
    # an unknown id: whoever holds file.read on the instance learns it is unknown, everyone else is refused
    assert code_of(lambda: world.ask(GetFile(file_id=UUID(int=5)))).code is ErrorCode.NOT_FOUND
    assert code_of(lambda: world.ask(GetFile(file_id=UUID(int=5)), "viewer")).code is ErrorCode.FORBIDDEN


def test_list_files_pages_newest_first_and_filters(world: World, setup: Setup) -> None:
    for index, title in enumerate(("a", "b", "c")):
        data = f"file {index}\n".encode()
        project = (
            setup.project if index else None
        )  # "a" is workspace-level, "b" and "c" belong to the project
        world.add_file(setup.ws, world.stage(setup.ws, data), title=title, project_id=project)
        world.clock.advance(timedelta(seconds=1))
    first = world.ask(ListFiles(workspace_id=setup.ws, limit=2), "viewer")
    assert [item.title for item in first.items] == ["c", "b"]
    assert first.next is not None
    rest = world.ask(ListFiles(workspace_id=setup.ws, limit=2, after=first.next), "viewer")
    assert [item.title for item in rest.items] == ["a"]
    assert rest.next is None
    in_project = world.ask(ListFiles(workspace_id=setup.ws, project_id=setup.project), "viewer")
    assert sorted(item.title for item in in_project.items) == ["b", "c"]
    trashed = world.ask(ListFiles(workspace_id=setup.ws, state="trashed"), "viewer")
    assert trashed.items == ()
    evidence = world.ask(ListFiles(workspace_id=setup.ws, origin=queries.FileOrigin.EVIDENCE), "viewer")
    assert evidence.items == ()
    assert (
        code_of(lambda: world.ask(ListFiles(workspace_id=setup.ws), "outsider")).code is ErrorCode.FORBIDDEN
    )
    assert code_of(
        lambda: world.ask(ListFiles(workspace_id=setup.ws, after="not a cursor"), "viewer")
    ).code is (ErrorCode.SCHEMA_INVALID)


def test_list_file_versions_pages_highest_number_first(world: World, setup: Setup) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws))
    for number in (2, 3, 4):
        world.add_version(first.file_id, world.stage(setup.ws, f"v{number}\n".encode()), version=number)
    page = world.ask(ListFileVersions(file_id=first.file_id, limit=3), "viewer")
    assert [item.version_no for item in page.items] == [4, 3, 2]
    assert page.next is not None
    last = world.ask(
        ListFileVersions(file_id=first.file_id, limit=3, after=page.next),
        "viewer",
    )
    assert [item.version_no for item in last.items] == [1]
    assert last.next is None


def test_get_file_version_carries_file_classification_and_state(world: World, setup: Setup) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws), classification=wire.Classification.CONFIDENTIAL)
    world.run(TrashFile(file_id=first.file_id, expected_row_version=2, reason="x"))
    view = world.ask(GetFileVersion(file_version_id=first.file_version_id), "viewer")
    assert (view.file_id, view.classification.value, view.state) == (first.file_id, "confidential", "trashed")
    assert (view.size_bytes, view.version_no, view.safety_verdict) == (len(TEXT), 1, "ok")
    assert view.digest.startswith("sha256:")
    assert view.detected_media_type == "text/plain"


def test_open_content_names_the_location_and_serves_a_consistent_media_type(
    world: World, setup: Setup
) -> None:
    ok = world.add_file(setup.ws, world.stage(setup.ws), declared_media_type="text/plain")
    odd = world.add_file(
        setup.ws, world.stage(setup.ws, b"other text\n"), declared_media_type="image/png", title="odd"
    )
    plain = world.add_file(setup.ws, world.stage(setup.ws, b"third\n"), title="third")
    handles = {
        name: world.ask(
            OpenFileVersionContent(file_version_id=made.file_version_id),
            "viewer",
        )
        for name, made in (("ok", ok), ("odd", odd), ("plain", plain))
    }
    assert handles["ok"].media_type == "text/plain"
    assert handles["odd"].media_type == "application/octet-stream"  # declared type the bytes contradict
    assert handles["plain"].media_type == "application/octet-stream"  # nothing declared: opaque
    with world.blobs.open(handles["ok"].location) as stream:
        assert stream.read() == TEXT
    assert set(handles["ok"].location) == {"backend_id", "storage_key", "storage_version"}


def test_open_content_of_a_version_without_a_present_location_is_not_ready(
    world: World, setup: Setup
) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws))
    make_missing(world, first.file_version_id)
    error = code_of(lambda: world.ask(OpenFileVersionContent(file_version_id=first.file_version_id)))
    assert error.code is ErrorCode.FILE_VERSION_NOT_READY


def test_open_content_still_works_for_a_trashed_file(world: World, setup: Setup) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws))
    world.run(TrashFile(file_id=first.file_id, expected_row_version=2, reason="x"))
    handle = world.ask(
        OpenFileVersionContent(file_version_id=first.file_version_id),
        "viewer",
    )
    with world.blobs.open(handle.location) as stream:
        assert stream.read() == TEXT


# ---------------------------------------------------------------------------------------------- require_ready
def test_require_ready_versions_returns_views_in_order_without_repeats(world: World, setup: Setup) -> None:
    a = world.add_file(setup.ws, world.stage(setup.ws), title="a")
    b = world.add_file(setup.ws, world.stage(setup.ws, b"b\n"), title="b")
    ids = [
        FileVersionId(b.file_version_id),
        FileVersionId(a.file_version_id),
        FileVersionId(b.file_version_id),
    ]
    views = read_in_uow(world, lambda uow: public.require_ready_versions(uow, setup.ws, ids))
    assert [view.file_version_id for view in views] == [b.file_version_id, a.file_version_id]
    assert views[1].digest.startswith("sha256:")


def test_require_ready_versions_refuses_unknown_and_foreign_versions_alike(
    world: World, setup: Setup
) -> None:
    foreign = world.add_file(setup.other_ws, world.stage(setup.other_ws), title="f")
    mine = world.add_file(setup.ws, world.stage(setup.ws), title="m")
    for bad in (FileVersionId(UUID(int=3)), FileVersionId(foreign.file_version_id)):
        ids = [FileVersionId(mine.file_version_id), bad]
        error = code_of(
            lambda ids=ids: read_in_uow(world, lambda uow: public.require_ready_versions(uow, setup.ws, ids))
        )
        assert error.code is ErrorCode.NOT_FOUND
        assert error.details["ids"] == [str(bad)]


def test_require_ready_versions_names_the_trashed_and_the_missing_ones(world: World, setup: Setup) -> None:
    a = world.add_file(setup.ws, world.stage(setup.ws), title="a")
    b = world.add_file(setup.ws, world.stage(setup.ws, b"b\n"), title="b")
    c = world.add_file(setup.ws, world.stage(setup.ws, b"c\n"), title="c")
    world.run(TrashFile(file_id=a.file_id, expected_row_version=2, reason="x"))
    make_missing(world, b.file_version_id)
    ids = [FileVersionId(x.file_version_id) for x in (a, b, c)]
    error = code_of(lambda: read_in_uow(world, lambda uow: public.require_ready_versions(uow, setup.ws, ids)))
    assert error.code is ErrorCode.FILE_VERSION_NOT_READY
    assert error.details["ids"] == [str(a.file_version_id), str(b.file_version_id)]


def test_get_file_version_facade_reads_without_a_permission_check(world: World, setup: Setup) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws))
    view = read_in_uow(world, lambda uow: public.get_file_version(uow, FileVersionId(first.file_version_id)))
    assert (view.version_no, view.original_filename) == (1, "notes.txt")
    assert code_of(
        lambda: read_in_uow(world, lambda uow: public.get_file_version(uow, FileVersionId(UUID(int=4))))
    ).code is (ErrorCode.NOT_FOUND)


# ---------------------------------------------------------------------------------------------- latest ready
def test_latest_ready_version_is_the_newest_available_one(world: World, setup: Setup) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws))
    second = world.add_version(first.file_id, world.stage(setup.ws, b"v2\n"), version=2)
    third = world.add_version(first.file_id, world.stage(setup.ws, b"v3\n"), version=3)
    latest = read_in_uow(world, lambda uow: public.latest_ready_version(uow, first.file_id))
    assert latest.file_version_id == third.file_version_id
    make_missing(world, third.file_version_id)
    latest = read_in_uow(world, lambda uow: public.latest_ready_version(uow, first.file_id))
    assert latest.file_version_id == second.file_version_id  # the newest *available* one
    make_missing(world, second.file_version_id)
    make_missing(world, first.file_version_id)
    assert read_in_uow(world, lambda uow: public.latest_ready_version(uow, first.file_id)) is None


def test_latest_ready_version_skips_a_trashed_file_and_an_unknown_one(world: World, setup: Setup) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws))
    world.run(TrashFile(file_id=first.file_id, expected_row_version=2, reason="x"))
    assert read_in_uow(world, lambda uow: public.latest_ready_version(uow, first.file_id)) is None
    missing = code_of(lambda: read_in_uow(world, lambda uow: public.latest_ready_version(uow, UUID(int=8))))  # type: ignore[arg-type]
    assert missing.code is ErrorCode.NOT_FOUND


# ---------------------------------------------------------------------------------------------- read_text
def read_text(world: World, version_id: Any, max_bytes: int = 1000) -> Any:
    return read_in_uow(
        world,
        lambda uow: public.read_text_content(uow, FileVersionId(version_id), max_bytes=max_bytes),
    )


def test_read_text_content_returns_text_and_none_for_everything_else(world: World, setup: Setup) -> None:
    text = world.add_file(setup.ws, world.stage(setup.ws, "привет\n".encode()), title="t")
    binary = world.add_file(setup.ws, world.stage(setup.ws, b"a\x00b"), title="b")
    latin = world.add_file(setup.ws, world.stage(setup.ws, b"\xff\xfe broken"), title="l")
    big = world.add_file(setup.ws, world.stage(setup.ws, b"x" * 50), title="x")
    assert read_text(world, text.file_version_id) == "привет\n"
    assert read_text(world, binary.file_version_id) is None  # a NUL byte
    assert read_text(world, latin.file_version_id) is None  # not UTF-8
    assert read_text(world, big.file_version_id, max_bytes=49) is None  # over the limit
    assert read_text(world, big.file_version_id, max_bytes=50) == "x" * 50  # exactly at the limit


def test_read_text_content_refuses_a_missing_version_or_missing_bytes(world: World, setup: Setup) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws))
    assert code_of(lambda: read_text(world, UUID(int=6))).code is ErrorCode.NOT_FOUND
    world.blobs.delete_unreferenced(
        {"backend_id": "local-primary", "storage_key": storage_key(world, first.file_version_id)}
    )
    assert code_of(lambda: read_text(world, first.file_version_id)).code is ErrorCode.FILE_VERSION_NOT_READY
    other = world.add_file(setup.ws, world.stage(setup.ws, b"other\n"), title="o")
    make_missing(world, other.file_version_id)
    assert code_of(lambda: read_text(world, other.file_version_id)).code is ErrorCode.FILE_VERSION_NOT_READY


# ---------------------------------------------------------------------------------------------- facade writes
def register(world: World, setup: Setup, staged: Any, **changes: Any) -> Any:
    """``consume_staged_blob`` then ``register_file_version`` in one unit, as an execution handler does."""
    fields: dict[str, Any] = {
        "workspace_id": setup.ws,
        "project_id": setup.project,
        "title": "stdout of check",
        "origin": FileOrigin.EVIDENCE,
        "original_filename": "check.log",
        "media_type": None,
        "source": EVIDENCE,
        "classification": Classification.INTERNAL,
        "safety": SafetyReport((), (), False),
        "created_by": world.people["owner"].principal_id,
    }
    fields.update(changes)
    now = world.clock.now()
    with world.uow() as uow:
        view = public.consume_staged_blob(
            uow, ref=staged.ref().to_json(), workspace_id=staged.workspace_id, request_id="req-exec", now=now
        )
        made = public.register_file_version(uow, staged=view, ids=world.ids, now=now, **fields)
        uow.commit()
    return made


def test_register_file_version_creates_the_file_and_version_one(world: World, setup: Setup) -> None:
    staged = world.stage(setup.ws, b"all green\n")
    ref = register(world, setup, staged, classification=Classification.RESTRICTED)
    tables = world.tables()
    [file] = tables.files.values()
    [version] = tables.versions.values()
    assert ref == {"file_id": str(file.id), "file_version_id": str(version.id), "version_no": 1}
    assert (file.origin, file.classification, file.current_version_id) == (
        FileOrigin.EVIDENCE,
        Classification.RESTRICTED,
        version.id,
    )
    assert (version.source, version.safety.findings, version.created_by) == (
        EVIDENCE,
        (),
        world.people["owner"].principal_id,
    )
    assert world.staged_row(staged).consumed_request_id == "req-exec"
    assert len(world.events("file-added")) == 1
    assert len(world.events("file-version-added")) == 1


def test_register_file_version_refuses_a_foreign_workspace_and_a_bad_filename(
    world: World, setup: Setup
) -> None:
    staged = world.stage(setup.other_ws)
    good = world.stage(setup.ws)
    before = world.snapshot()
    error = code_of(lambda: _register_foreign(world, setup, staged))
    assert error.code is ErrorCode.FORBIDDEN
    assert error.details["reason"] == "other_workspace"
    assert world.snapshot() == before
    bad_name = code_of(lambda: register(world, setup, good, original_filename="a/b"))
    assert bad_name.code is ErrorCode.SCHEMA_INVALID
    assert world.snapshot() == before
    assert world.staged_row(good).consumed_at is None


def _register_foreign(world: World, setup: Setup, staged: Any) -> None:
    """Bytes consumed in their own workspace, registered into a project of another one."""
    now = world.clock.now()
    with world.uow() as uow:
        view = public.consume_staged_blob(
            uow, ref=staged.ref().to_json(), workspace_id=staged.workspace_id, request_id="r", now=now
        )
        public.register_file_version(
            uow,
            workspace_id=setup.ws,
            project_id=setup.project,
            title="t",
            origin=FileOrigin.EVIDENCE,
            staged=view,
            original_filename="x.log",
            media_type=None,
            source=EVIDENCE,
            classification=Classification.INTERNAL,
            safety=SafetyReport((), (), False),
            created_by=world.people["owner"].principal_id,
            ids=world.ids,
            now=now,
        )
        uow.commit()


def test_consume_staged_blob_marks_it_consumed_and_rollback_leaves_it_staged(
    world: World, setup: Setup
) -> None:
    staged = world.stage(setup.ws)
    now = world.clock.now()
    with world.uow() as uow:  # dropped: the calling transaction rolled back
        view = public.consume_staged_blob(
            uow, ref=staged.ref().to_json(), workspace_id=setup.ws, request_id="r1", now=now
        )
        assert (view.storage_key, view.workspace_id) == (staged.storage_key, setup.ws)
    assert world.staged_row(staged).consumed_at is None
    with world.uow() as uow:
        public.consume_staged_blob(
            uow, ref=staged.ref().to_json(), workspace_id=setup.ws, request_id="r2", now=now
        )
        uow.commit()
    assert world.staged_row(staged).consumed_request_id == "r2"
    again = code_of(
        lambda: read_in_uow(
            world,
            lambda uow: public.consume_staged_blob(
                uow, ref=staged.ref().to_json(), workspace_id=setup.ws, request_id="r3", now=now
            ),
        )
    )
    assert again.code is ErrorCode.STAGED_BLOB_CONSUMED


def test_consume_staged_blob_refuses_a_malformed_or_foreign_ref(world: World, setup: Setup) -> None:
    staged = world.stage(setup.ws)
    now = world.clock.now()
    malformed = {**staged.ref().to_json(), "staged_blob_id": "nope"}
    assert (
        code_of(
            lambda: read_in_uow(
                world,
                lambda uow: public.consume_staged_blob(
                    uow, ref=malformed, workspace_id=setup.ws, request_id="r", now=now
                ),
            )
        ).code
        is ErrorCode.SCHEMA_INVALID
    )
    assert (
        code_of(
            lambda: read_in_uow(
                world,
                lambda uow: public.consume_staged_blob(
                    uow, ref=staged.ref().to_json(), workspace_id=setup.other_ws, request_id="r", now=now
                ),
            )
        ).code
        is ErrorCode.FORBIDDEN
    )


def test_blob_availability_and_location_state_are_what_ready_means(world: World, setup: Setup) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws))
    blob = next(iter(world.tables().blobs.values()))
    assert blob.availability is BlobAvailability.AVAILABLE
    make_missing(world, first.file_version_id)
    [location] = world.tables().locations[blob.id]
    assert location.state is LocationState.MISSING
    assert location.verified_at == world.clock.now()


def test_read_text_content_has_the_documented_signature_and_no_store_parameter() -> None:
    parameters = inspect.signature(public.read_text_content).parameters
    assert list(parameters) == ["uow", "file_version_id", "max_bytes"]
    assert parameters["max_bytes"].kind is inspect.Parameter.KEYWORD_ONLY


def test_the_unit_of_work_hands_the_facade_the_store_the_host_bound(world: World, setup: Setup) -> None:
    assert BlobContentReader in MODULE.repository_ports
    first = world.add_file(setup.ws, world.stage(setup.ws, "один\n".encode()))
    with world.uow() as rolled:
        reader = rolled.repo(BlobContentReader)
        assert isinstance(reader, MemoryBlobContentReader)
        rolled.rollback()
    assert read_text(world, first.file_version_id) == "один\n"  # a dropped unit of work does not unbind it
    state = artifacts_state(world.backend.committed)
    state.store.store = None  # a host that bound nothing
    error = code_of(lambda: read_text(world, first.file_version_id))
    assert error.code is ErrorCode.CAPABILITY_UNAVAILABLE
    state.store.bind(world.blobs)
    assert read_text(world, first.file_version_id) == "один\n"


def test_the_facade_neither_checks_nor_grants_a_permission(world: World, setup: Setup) -> None:
    """It reads for an authorised handler; it is no query: a trashed file's pinned version stays readable and
    nothing in it names an actor, a grant or a scope."""
    first = world.add_file(setup.ws, world.stage(setup.ws))
    world.run(TrashFile(file_id=first.file_id, expected_row_version=2, reason="x"))
    assert read_text(world, first.file_version_id) == TEXT.decode()
    assert "actor" not in inspect.signature(public.read_text_content).parameters
    # the same bytes through the bus still need the stored file's right
    query = GetFileVersion(file_version_id=first.file_version_id)
    assert code_of(lambda: world.ask(query, "outsider")).code is ErrorCode.FORBIDDEN


def test_read_text_content_is_exact_when_the_store_returns_short_reads(world: World, setup: Setup) -> None:
    long_text = world.add_file(setup.ws, world.stage(setup.ws, b"x" * 50), title="x")
    artifacts_state(world.backend.committed).store.bind(TrickleStore(world.blobs, chunk=4))  # type: ignore[arg-type]
    assert read_text(world, long_text.file_version_id, max_bytes=50) == "x" * 50
    assert read_text(world, long_text.file_version_id, max_bytes=49) is None  # over the limit, not truncated
    assert read_text(world, long_text.file_version_id, max_bytes=10) is None


def test_read_up_to_loops_until_the_limit_or_the_end() -> None:
    class Dribble:
        """Two bytes per ``read`` call, whatever is asked."""

        def __init__(self, data: bytes) -> None:
            self._data = io.BytesIO(data)

        def read(self, size: int = -1) -> bytes:
            return self._data.read(min(size, 2) if size >= 0 else 2)

    def stream(data: bytes) -> BinaryIO:
        return cast("BinaryIO", Dribble(data))

    assert reads.read_up_to(stream(b"abcdefg"), 5) == b"abcde"
    assert reads.read_up_to(stream(b"abc"), 10) == b"abc"
    assert reads.read_up_to(stream(b"abc"), 0) == b""
    assert reads.read_up_to(stream(b""), 4) == b""


# ---------------------------------------------------------------------------------------------- cursors
def cursor(*parts: str) -> str:
    raw = json.dumps(list(parts), separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode("ascii")


def test_a_cursor_with_a_naive_timestamp_is_an_invalid_cursor_not_a_crash(world: World, setup: Setup) -> None:
    for number in range(3):
        world.add_file(setup.ws, world.stage(setup.ws, f"{number}\n".encode()), title=f"f{number}")
    aware = cursor(world.clock.now().isoformat(), str(UUID(int=0)))
    assert world.ask(ListFiles(workspace_id=setup.ws, after=aware)).items == ()  # nothing is older than it
    for bad in ("2026-10-29T12:00:00", "2026-10-29", "2026-10-29T12:00:00+25:00", "not a date"):
        error = code_of(lambda bad=bad: world.ask(ListFiles(workspace_id=setup.ws, after=cursor(bad, "x"))))
        assert error.code is ErrorCode.SCHEMA_INVALID, bad
        assert error.details["field"] == "after"
    assert len(world.ask(ListFiles(workspace_id=setup.ws)).items) == 3  # the refusals changed nothing


def test_a_naive_cursor_is_refused_by_the_repository_itself(world: World, setup: Setup) -> None:
    from skm.modules.artifacts.ports import FileRepository

    with world.uow(readonly=True) as uow, pytest.raises(SkmError) as caught:
        uow.repo(FileRepository).list(
            setup.ws,
            project_id=None,
            state=None,
            origin=None,
            after=cursor("2026-10-29T12:00:00", "x"),
            limit=10,
        )
    assert caught.value.code is ErrorCode.SCHEMA_INVALID


def test_the_by_id_queries_keep_their_wire_contract_and_resolve_the_scope_on_the_server() -> None:
    import dataclasses

    from skm.modules.artifacts.application.registry import QUERIES

    wire_fields = {
        "get_file": ["file_id"],
        "list_file_versions": ["file_id", "after", "limit"],
        "get_file_version": ["file_version_id"],
        "open_file_version_content": ["file_version_id"],
    }
    by_name = {spec.name: spec for spec in QUERIES if isinstance(spec, QuerySpec)}
    for name, expected in wire_fields.items():
        spec = by_name[f"artifacts.{name}"]
        assert [field.name for field in dataclasses.fields(spec.dto)] == expected  # no owner claim
        assert spec.permission == "file.read"  # a token narrowed to file.read passes the bus
        assert spec.scope_of is None  # the request names no scope ...
        assert spec.scope_resolver is not None  # ... the stored file does
