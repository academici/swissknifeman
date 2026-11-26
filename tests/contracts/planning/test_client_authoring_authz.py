"""Authorization is evaluated again for source-pinned reads and keyed publication receipts."""

from dataclasses import replace
from typing import Any

import pytest

from contracts.planning._authoring_support import BASE_GUIDE, BASE_TEXT, A, add_guide, base_draft
from contracts.planning.test_client_planning import preview, publication
from integration.artifacts.test_upload_flow import dispatch_new
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import FileVersionId
from skm.modules.access import public as access
from skm.modules.artifacts import public as artifacts
from skm.modules.planning import public as planning
from support.backend import ClientBackend, client_backend
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "client_backend", "pg_session", "test_database"]


def test_publish_replay_and_authoring_reads_recheck_current_permissions(
    client_backend: ClientBackend,
) -> None:
    side = client_backend
    owner = side.client()
    ws = side.seed.workspace_id
    principal = side.seed.principals["editor"]
    added = add_guide(side, owner)
    version = FileVersionId(added.file_version_id)
    plan, draft = base_draft(side, owner, version)
    permissions = {"plan.read", "plan.publish", "file.read"}

    def issue(name: str, allowed: set[str]) -> access.CreateTokenResult:
        token: Any = owner.dispatch(access.CreateToken(name, principal, ws, tuple(sorted(allowed))))
        return token

    original = issue("publisher", permissions)
    publisher = side.client(token=original.secret)
    candidate = preview(publisher, plan, draft)
    assert candidate.publishable
    assert candidate.pinned_materials[0].file_version_id == version
    command = publication(plan, draft, candidate)
    key = publisher.new_idempotency_key()
    receipt: Any = publisher.dispatch(command, idempotency_key=key)
    assert receipt.content_digest == candidate.content_digest

    fresh = dispatch_new(owner, planning.OpenDraft(plan, base="current"))
    file_query = artifacts.GetFileVersion(version)
    assert publisher.ask(file_query) == owner.ask(file_query)
    with publisher.open_file_version_content(version) as content:
        assert content.read() == BASE_GUIDE
    assert preview(publisher, plan, fresh).pinned_materials[0].file_version_id == version
    owner.dispatch(access.RevokeToken(original.token_id))
    for lost in ("plan.read", "plan.publish"):
        limited = side.client(token=issue(f"without-{lost}", permissions - {lost}).secret)
        with pytest.raises(SkmError) as denied:
            limited.dispatch(command, idempotency_key=key)
        assert denied.value.code is ErrorCode.FORBIDDEN

    limited = side.client(token=issue("without-file", permissions - {"file.read"}).secret)
    assert limited.dispatch(command, idempotency_key=key) == receipt
    with pytest.raises(SkmError) as metadata:
        limited.ask(file_query)
    assert metadata.value.code is ErrorCode.FORBIDDEN
    with pytest.raises(SkmError) as stream, limited.open_file_version_content(version):
        pytest.fail("protected file content opened")
    assert stream.value.code is ErrorCode.FORBIDDEN
    with pytest.raises(SkmError) as denied_preview:
        preview(limited, plan, fresh)
    assert denied_preview.value.code is ErrorCode.FORBIDDEN

    editor = side.client("editor")
    page = planning.ListEntities(plan, revision_id=receipt.revision_id, kinds=("item",), limit=1)
    first: Any = editor.ask(page)
    assert first.next_cursor
    continuation = replace(page, after=first.next_cursor)
    entity = planning.GetEntity(plan, A, revision_id=receipt.revision_id)
    text = planning.ReadText(plan, A, "/summary", revision_id=receipt.revision_id)
    assert editor.ask(entity) == owner.ask(entity)
    fragment: Any = editor.ask(text)
    assert fragment.text == BASE_TEXT
    owner.dispatch(access.RevokeMembership(ws, principal))
    for query in (continuation, entity, text):
        with pytest.raises(SkmError) as denied_read:
            editor.ask(query)
        assert denied_read.value.code is ErrorCode.FORBIDDEN
