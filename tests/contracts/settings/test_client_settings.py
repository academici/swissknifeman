"""Settings reads, versioned writes and a draft import on all client transports."""

from dataclasses import replace
from typing import Any

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.settings import public as settings
from support.backend import ClientBackend, client_backend
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "client_backend", "pg_session", "test_database"]

KEY = "execution.review.max_rounds"


def test_config_cas_explain_dry_run_and_lock(client_backend: ClientBackend) -> None:
    side = client_backend
    owner = side.client()
    workspace = {"level": "workspace", "scope_id": str(side.seed.workspace_id)}
    instance = {"level": "instance"}
    explain = settings.ExplainConfig.from_json({"scope": workspace, "keys": [KEY]})
    initial: Any = owner.ask(explain)
    write = settings.SetValue.from_json(
        {
            "scope": instance,
            "key": KEY,
            "value": 4,
            "expected_row_version": 0,
        }
    )
    result: Any = owner.dispatch(write, idempotency_key="config-set")
    assert result.entry.row_version == 1
    assert result.effective.value == 4
    assert owner.dispatch(write, idempotency_key="config-set") == result
    get_value = settings.GetValue.from_json({"scope": workspace, "key": KEY})
    stored: Any = owner.ask(get_value)
    assert stored.present
    assert stored.value == 4
    assert stored.winner.entry_id == result.entry.entry_id
    assert stored.winner.row_version == 1
    assert stored.locked_by is None
    current: Any = owner.ask(explain)
    assert current.to_json()["generation"] == initial.to_json()["generation"] + 1
    assert current.to_json()["keys"][0]["value"] == 4
    value: Any = owner.ask(replace(explain, detail="value"))
    assert value.to_json()["keys"][0]["value"] == 4

    with pytest.raises(SkmError) as stale:
        owner.dispatch(replace(write, value=3, expected_row_version=2))
    assert stale.value.code is ErrorCode.VERSION_CONFLICT
    assert owner.ask(explain) == current

    draft = settings.ImportConfig.from_json(
        {
            "scope": workspace,
            "format": "json",
            "document": {"execution": {"review": {"max_rounds": 2}}},
            "dry_run": True,
        }
    )
    preview: Any = owner.dispatch(draft)
    assert preview.dry_run
    assert not preview.applied
    assert not preview.problems
    assert len(preview.changes) == 1
    assert preview.entries_digest_before != preview.entries_digest_after
    assert owner.ask(explain) == current
    applied: Any = owner.dispatch(
        replace(draft, dry_run=False, expected_entries_digest=preview.entries_digest_before)
    )
    assert applied.applied
    assert applied.entries_digest_after == preview.entries_digest_after
    scoped: Any = owner.ask(explain)
    assert scoped.to_json()["keys"][0]["value"] == 2

    lock = settings.LockValue.from_json(
        {
            "scope": instance,
            "key": KEY,
            "expected_row_version": 1,
            "reason": "Lock review ceiling",
            "confirmed": True,
        }
    )
    locked: Any = owner.dispatch(lock)
    assert locked.entry.locked
    assert locked.entry.row_version == 2
    rejected = settings.SetValue.from_json(
        {
            "scope": workspace,
            "key": KEY,
            "value": 1,
            "expected_row_version": 1,
        }
    )
    with pytest.raises(SkmError) as shadowed:
        owner.dispatch(rejected)
    assert shadowed.value.code is ErrorCode.CONFIG_LOCKED
    effective: Any = owner.ask(get_value)
    assert effective.present
    assert effective.value == 4
    assert effective.winner == effective.locked_by
    assert effective.winner.entry_id == locked.entry.entry_id
    assert effective.winner.row_version == 2
    final: Any = owner.ask(explain)
    assert final.to_json()["keys"][0]["value"] == 4
