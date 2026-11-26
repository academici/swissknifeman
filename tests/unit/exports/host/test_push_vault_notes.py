"""Writer selection, bounded drain, and recovery at filesystem/receipt boundaries."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal, cast
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest

from skm.adapters.exports.obsidian.vault_fs import LocalVaultFs
from skm.application_bus.client import SkmClient
from skm.application_bus.host import HostContext
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, SkmError
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId
from skm.kernel.json_types import JsonObject
from skm.modules.exports.domain.markdown import digest
from skm.modules.exports.host import locate_vault, push_vault_notes
from skm.modules.exports.ports import VaultFs
from skm.modules.exports.public import (
    ListPendingNotes,
    PendingNotesView,
    PendingNoteView,
    RecordNoteWritten,
    RecordNoteWrittenResult,
)
from skm.modules.exports.settings import SECTION_URNS, VALIDATORS, VIEWS
from skm.modules.workspace.public import GetProject, ProjectView
from skm.platform.config.keys import MISSING
from skm.platform.config.registry import SettingsRegistry
from skm.platform.schema.registry import SchemaRegistry


def _config(**overrides: object) -> dict[str, object]:
    registry = SettingsRegistry.build(
        SchemaRegistry.load_default(),
        SECTION_URNS,
        validators=VALIDATORS,
        views=VIEWS,
        known_permissions=frozenset(),
    )
    keys = registry.keys()
    return {
        **{key.key: key.default for key in keys if key.default is not MISSING},
        **overrides,
    }


_WORKSPACE = uuid4()
_PROJECT = uuid4()
type VaultFixture = tuple[HostContext, Mock, LocalVaultFs]
_REQUEST: JsonObject = {"workspace_id": str(_WORKSPACE)}


def _note(
    kind: Literal["plan_archived", "run_finished"] = "plan_archived",
    *,
    name: str = "note.md",
    body: str | None = None,
) -> PendingNoteView:
    event_id = uuid4()
    header = "skm-run" if kind == "run_finished" else "plan-archived"
    content = body if body is not None else f"---\ntype: {header}\nevent_id: {event_id}\n---\nbody\n"
    return PendingNoteView(
        uuid4(),
        _PROJECT,
        uuid4(),
        kind,
        name,
        "plans",
        content,
        digest(content),
        event_id,
        1,
        "restricted",
        (),
    )


@pytest.fixture
def vault(tmp_path: Path) -> tuple[HostContext, Mock, LocalVaultFs]:
    root = tmp_path / "vault"
    root.mkdir()
    fs = LocalVaultFs(root, tmp_path)
    host_id = HostId(uuid4())
    fs.update_identity(host_id, fork=False, deadline_seconds=1)
    client = Mock(spec=SkmClient)
    client.new_idempotency_key.side_effect = lambda: uuid4().hex

    def record(cmd: RecordNoteWritten, *, idempotency_key: str) -> RecordNoteWrittenResult:
        assert idempotency_key
        return RecordNoteWrittenResult(True, cmd.note_id, cmd.vault_id, cmd.generation)

    client.dispatch.side_effect = record
    return (
        HostContext(
            client,
            GatewayTable({VaultFs: fs}, "host_gateway"),
            host_id,
            _config(**{"exports.vault.path": str(root)}),
            Mock(),
            CancelSource().token,
        ),
        client,
        fs,
    )


def _page(client: Mock, *notes: PendingNoteView, after: str | None = None) -> None:
    def answer(query: object) -> object:
        if isinstance(query, ListPendingNotes):
            return PendingNotesView(notes, after, after is not None)
        assert isinstance(query, GetProject)
        return ProjectView(_PROJECT, _WORKSPACE, "sample", "Sample", "", "active", 1, ())

    client.ask.side_effect = answer


def _rows(report: JsonObject, key: str) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", report[key])


def _journal(fs: LocalVaultFs) -> dict[str, Any]:
    (path,) = fs.state().root.glob("*.journal")
    return json.loads(path.read_bytes())


def test_read_only_discovery_and_no_fallback_for_explicit_path(vault: VaultFixture) -> None:
    ctx, client, fs = vault
    candidate = fs.root / "candidate"
    (candidate / ".obsidian").mkdir(parents=True)
    settings = _config(**{"exports.vault.candidates": [str(fs.root / "absent"), str(candidate)]})
    assert locate_vault.run(replace(ctx, config=settings), {})["source"] == "candidate"
    assert not (candidate / ".skm-vault.json").exists()
    with pytest.raises(SkmError) as err:
        locate_vault.run(
            replace(ctx, config={**settings, "exports.vault.path": str(fs.root / "missing")}), {}
        )
    assert err.value.code == ErrorCode.EXPORT_VAULT_MISSING
    client.ask.assert_not_called()


def test_foreign_suffix_exact_digest_and_modified_run_note(vault: VaultFixture) -> None:
    ctx, client, fs = vault
    exact = _note(body="Exact bytes with an unparseable header")
    altered = _note("run_finished", name="run.md")
    _page(client, exact, altered)
    assert fs.create_new("SKM/Unsorted/note.md", b"foreign")
    assert fs.create_new("SKM/Unsorted/note (2).md", exact.body.encode())
    assert fs.create_new("SKM/Unsorted/run.md", altered.body.replace("body\n", "edited\n").encode())

    report = push_vault_notes.run(ctx, _REQUEST)
    assert report["partial"] is True
    assert report["created"] == []
    assert len(_rows(report, "verified_existing")) == len(_rows(report, "modified_existing")) == 1
    assert not (fs.root / "SKM/Unsorted/run (2).md").exists()
    assert (fs.root / "SKM/Unsorted/note.md").read_bytes() == b"foreign"
    assert b"edited" in (fs.root / "SKM/Unsorted/run.md").read_bytes()


@pytest.mark.parametrize("invalid", [False, True])
def test_ambiguous_or_invalid_mapping_never_falls_back(vault: VaultFixture, invalid: bool) -> None:
    ctx, client, fs = vault
    _page(client, _note())
    if invalid:
        assert fs.create_new(".projects.json", b"x" * ((1 << 20) + 1))
    else:
        for folder in ("one", "two"):
            assert fs.create_new(f"Projects/{folder}/control.md", b"---\nskm_project: sample\n---\n")
    report = push_vault_notes.run(ctx, _REQUEST)
    assert report["partial"] is True
    (failure,) = _rows(report, "blocked")
    assert failure["code"] == "EXPORT_VAULT_PROJECT_UNKNOWN"
    assert not (fs.root / "SKM").exists()
    client.dispatch.assert_not_called()


def test_dry_run_reports_source_paths_without_state_or_fs_mutations(vault: VaultFixture) -> None:
    ctx, client, fs = vault
    _page(client, _note())
    before = {path.name for path in fs.state().root.iterdir()}
    report = push_vault_notes.run(ctx, {**_REQUEST, "dry_run": True})
    (preview,) = _rows(report, "preview")
    assert preview["relative_path"] == "SKM/Unsorted/note.md"
    assert preview["classification"] == "restricted"
    assert before == {path.name for path in fs.state().root.iterdir()}
    assert not (fs.root / "SKM").exists()
    client.dispatch.assert_not_called()


def test_link_outcome_unknown_keeps_frozen_path_and_backoff(
    vault: VaultFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, client, fs = vault
    note = _note()
    _page(client, note)
    original = LocalVaultFs.create_new
    now = 1000.0
    monkeypatch.setattr(LocalVaultFs, "retry_time", lambda self: now)
    monkeypatch.setattr(LocalVaultFs, "retry_jitter", lambda self: 1.0)

    def fail_after_publish(target: LocalVaultFs, rel: str, data: bytes) -> bool:
        (entry,) = _journal(fs)["entries"].values()
        assert entry["frozen_path"] == rel
        assert entry["body_digest"] == note.body_digest
        assert entry["outcome_unknown"]
        assert original(target, rel, data)
        raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "injected after link")

    with monkeypatch.context() as fault:
        fault.setattr(LocalVaultFs, "create_new", fail_after_publish)
        assert push_vault_notes.run(ctx, _REQUEST)["errors"]
    client.dispatch.assert_not_called()
    assert _rows(push_vault_notes.run(ctx, _REQUEST), "blocked")[0]["reason"] == "retry_not_due"
    assert fs.create_new(".projects.json", b"broken")
    now += 31
    (receipt,) = _rows(push_vault_notes.run(ctx, _REQUEST), "verified_existing")
    assert receipt["relative_path"] == "SKM/Unsorted/note.md"
    assert not (fs.root / "Elsewhere").exists()
    assert _journal(fs)["entries"] == {}


@pytest.mark.parametrize(
    "invalid",
    [
        b"broken",
        b'{"projects":[{"skm_project":"sample","vault_path":"A"},{"skm_project":"sample","vault_path":"B"}]}',
    ],
)
def test_frozen_retry_requires_a_valid_mapping_before_publication(
    vault: VaultFixture, monkeypatch: pytest.MonkeyPatch, invalid: bytes
) -> None:
    ctx, client, fs = vault
    note = _note()
    _page(client, note)
    now = 1000.0
    monkeypatch.setattr(LocalVaultFs, "retry_time", lambda self: now)
    monkeypatch.setattr(LocalVaultFs, "retry_jitter", lambda self: 1.0)

    with monkeypatch.context() as fault:
        publish = Mock(
            side_effect=BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE, "before link", details={"outcome": "failed_without_effect"}
            )
        )
        fault.setattr(LocalVaultFs, "create_new", publish)
        assert push_vault_notes.run(ctx, _REQUEST)["errors"]
        publish.assert_called_once_with("SKM/Unsorted/note.md", note.body.encode())

    now += 31
    catalog = fs.root / ".projects.json"
    catalog.write_bytes(invalid)
    with monkeypatch.context() as fault:
        publish = Mock()
        fault.setattr(LocalVaultFs, "create_new", publish)
        for _ in range(2):
            (blocked,) = _rows(push_vault_notes.run(ctx, _REQUEST), "blocked")
            assert blocked["code"] == "EXPORT_VAULT_PROJECT_UNKNOWN"
        publish.assert_not_called()
    client.dispatch.assert_not_called()
    assert set(fs.root.iterdir()) == {catalog, fs.root / ".skm-vault.json"}
    (entry,) = _journal(fs)["entries"].values()
    assert entry["attempts"] == 2
    assert entry["frozen_path"] == "SKM/Unsorted/note.md"

    catalog.write_bytes(b'{"projects":[{"skm_project":"sample","vault_path":"Elsewhere"}]}')
    (created,) = _rows(push_vault_notes.run(ctx, _REQUEST), "created")
    assert created["relative_path"] == entry["frozen_path"]
    assert (fs.root / created["relative_path"]).read_bytes() == note.body.encode()
    assert not (fs.root / "Elsewhere").exists()


def test_eexist_collision_can_continue_before_own_publication(
    vault: VaultFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, client, fs = vault
    _page(client, _note())
    original = LocalVaultFs.create_new

    def raced(target: LocalVaultFs, rel: str, data: bytes) -> bool:
        if rel == "SKM/Unsorted/note.md":
            assert original(target, rel, b"racer")
        return original(target, rel, data)

    monkeypatch.setattr(LocalVaultFs, "create_new", raced)
    (receipt,) = _rows(push_vault_notes.run(ctx, _REQUEST), "created")
    assert receipt["relative_path"].endswith("note (2).md")
    assert (fs.root / "SKM/Unsorted/note.md").read_bytes() == b"racer"


def test_permanent_poison_does_not_starve_the_next_page(vault: VaultFixture) -> None:
    ctx, client, _ = vault
    _page(client, *(_note(name="../refused.md") for _ in range(100)), after="next")
    first = push_vault_notes.run(ctx, _REQUEST)
    assert first["partial"] is True
    assert len(_rows(first, "blocked")) == 100
    _page(client, _note())
    assert push_vault_notes.run(ctx, _REQUEST)["created"]
    assert isinstance(query := client.ask.call_args_list[-2].args[0], ListPendingNotes)
    assert query.after == "next"


def test_unbound_replica_refuses_before_requesting_any_body(vault: VaultFixture, tmp_path: Path) -> None:
    ctx, client, fs = vault
    copy = tmp_path / "replica"
    copy.mkdir()
    (copy / ".skm-vault.json").write_bytes((fs.root / ".skm-vault.json").read_bytes())
    for host in (ctx.host_id, HostId(UUID(int=1))):
        copy_ctx = replace(ctx, host_id=host, config=_config(**{"exports.vault.path": str(copy)}))
        with pytest.raises(SkmError, match="current local writer binding"):
            push_vault_notes.run(copy_ctx, _REQUEST)
    client.ask.assert_not_called()
    client.dispatch.assert_not_called()


def test_full_journal_blocks_before_publication(vault: VaultFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx, client, fs = vault
    _page(client, _note())
    monkeypatch.setattr(push_vault_notes, "_JOURNAL_MAX_ROWS", 0)
    report = push_vault_notes.run(ctx, _REQUEST)
    assert report["partial"] is True
    assert _rows(report, "blocked")[0]["reason"] == "journal_full"
    assert not (fs.root / "SKM").exists()
    client.dispatch.assert_not_called()


@pytest.mark.parametrize("byte_limit", [False, True])
def test_saturated_journal_preserves_frozen_evidence_and_advances_cursor(
    vault: VaultFixture, monkeypatch: pytest.MonkeyPatch, byte_limit: bool
) -> None:
    ctx, client, fs = vault
    pending = _note()
    _page(client, pending)
    publish = LocalVaultFs.create_new

    def lose_outcome(target: LocalVaultFs, path: str, body: bytes) -> bool:
        assert publish(target, path, body)
        raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "after link")

    with monkeypatch.context() as fault:
        fault.setattr(LocalVaultFs, "create_new", lose_outcome)
        assert push_vault_notes.run(ctx, _REQUEST)["errors"]
    (journal,) = fs.state().root.glob("*.journal")
    evidence = journal.read_bytes()
    assert json.loads(evidence)["entries"][f"{pending.note_id}:1"]["outcome_unknown"]

    if byte_limit:
        monkeypatch.setattr(push_vault_notes, "_JOURNAL_MAX_BYTES", len(evidence))
    else:
        monkeypatch.setattr(push_vault_notes, "_JOURNAL_MAX_ROWS", 1)
    _page(client, _note(name="../refused.md"), after="next")
    report = push_vault_notes.run(ctx, _REQUEST)
    assert report["partial"] is report["has_more"] is True
    assert report["reason"] == "journal_full"
    assert _rows(report, "blocked")[0]["retry"] == "journal_full"

    _page(client)
    assert push_vault_notes.run(ctx, _REQUEST)["has_more"] is False
    assert isinstance(query := client.ask.call_args.args[0], ListPendingNotes)
    assert query.after == "next"
    assert journal.read_bytes() == evidence
    client.dispatch.assert_not_called()


def test_permanent_failure_waits_for_a_new_delivery_generation(
    vault: VaultFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, client, fs = vault
    note = _note(name="../refused.md")
    validate = Mock(wraps=push_vault_notes.validate_component)
    monkeypatch.setattr(push_vault_notes, "validate_component", validate)
    _page(client, note)
    assert push_vault_notes.run(ctx, _REQUEST)["blocked"]
    assert push_vault_notes.run(ctx, _REQUEST)["blocked"]
    validate.assert_called_once()
    assert _journal(fs)["entries"][f"{note.note_id}:1"]["attempts"] == 1
    _page(client, replace(note, generation=2))
    assert push_vault_notes.run(ctx, _REQUEST)["blocked"]
    assert validate.call_count == 2


def test_blocked_suffix_range_reopens_when_existing_bytes_change(vault: VaultFixture) -> None:
    ctx, client, fs = vault
    ctx = replace(ctx, config=_config(**{"exports.vault.path": str(fs.root), "exports.notes.max_suffix": 1}))
    note = _note()
    _page(client, note)
    path = "SKM/Unsorted/note.md"
    assert fs.create_new(path, b"foreign")
    for _ in range(2):
        (blocked,) = _rows(push_vault_notes.run(ctx, _REQUEST), "blocked")
        assert blocked["code"] == "EXPORT_NOTE_NO_FREE_NAME"
    assert _journal(fs)["entries"][f"{note.note_id}:1"]["attempts"] == 1

    edited = note.body.replace("body", "edited").encode()
    (fs.root / path).write_bytes(edited)
    assert push_vault_notes.run(ctx, _REQUEST)["modified_existing"]
    assert (fs.root / path).read_bytes() == edited


@pytest.mark.parametrize("line_ending", ["", "\n"])
def test_truncated_header_with_intact_identity_is_modified(vault: VaultFixture, line_ending: str) -> None:
    ctx, client, fs = vault
    note = _note()
    _page(client, note)
    path = "SKM/Unsorted/note.md"
    truncated = f"---\ntype: plan-archived\nevent_id: {note.event_id}{line_ending}".encode()
    assert fs.create_new(path, truncated)
    assert push_vault_notes.run(ctx, _REQUEST)["modified_existing"]
    assert fs.read_bounded(path, max_bytes=256) == truncated
    assert not (fs.root / "SKM/Unsorted/note (2).md").exists()


def test_explicit_vault_path_to_a_regular_file_is_missing(vault: VaultFixture) -> None:
    ctx, _, fs = vault
    assert fs.create_new("regular-file", b"file")
    with pytest.raises(SkmError) as error:
        locate_vault.run(
            replace(ctx, config=_config(**{"exports.vault.path": str(fs.root / "regular-file")})), {}
        )
    assert error.value.code == ErrorCode.EXPORT_VAULT_MISSING
