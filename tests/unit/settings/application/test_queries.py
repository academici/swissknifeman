"""Settings queries through the bus (settings §A.8).

Explain is checked against the statuses of ``examples/config/explain-execution-review-max-rounds.json`` on the
same level fixture (default 2, pack 3, instance 4, workspace 3 locked, project 5, plan 1). The project and
plan entries are stale contributions no command would accept below the lock, so the fixture writes them
through the repository. Export is deterministic, ``portable_only`` drops non-portable keys and
import(export) is a no-op; the schema lists every section; entries and history page by their keysets.
"""

import base64
import json
import tomllib
from datetime import timedelta
from pathlib import Path
from runpy import run_path
from typing import Any, cast
from uuid import UUID

import pytest

from skm.application_bus.ports import AuthzDecision
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import PrincipalId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.settings.domain.entry import ConfigEntryId, EntryOp, new_entry
from skm.modules.settings.generated import queries
from skm.modules.settings.ports import ConfigEntryRepository, ConfigGenerationCounter
from skm.platform.config.sources.packs import PackFragment

h = run_path(str(Path(__file__).with_name("test_commands.py")))
harness, set_value, Packs, SCOPE_IDS = h["harness"], h["set_value"], h["Packs"], h["SCOPE_IDS"]
settings_registry = h["settings_registry"]

ROOT = Path(__file__).resolve().parents[4]
EXAMPLE = json.loads(
    (ROOT / "tests/fixtures/corpus/examples/config/explain-execution-review-max-rounds.json").read_text()
)
ROUNDS = "execution.review.max_rounds"


def ref(cls: type[Any], level: str) -> Any:
    return cls(level=level, scope_id=SCOPE_IDS[level])


def explain(level: str, **fields: Any) -> queries.ExplainConfig:
    return queries.ExplainConfig(scope=ref(queries.ExplainConfigDefsScopeRef, level), **fields)


def export(level: str, fmt: str = "toml", **fields: Any) -> queries.ExportConfig:
    return queries.ExportConfig(scope=ref(queries.ExportConfigDefsScopeRef, level), format=fmt, **fields)  # type: ignore[arg-type]


def stale_entries(made: Any, *rows: tuple[str, int, bool]) -> None:
    """Entries written past the command rules (data of an earlier ceiling)."""
    with made.uow() as uow:
        repo = uow.repo(ConfigEntryRepository)
        for level, value, locked in rows:
            repo.add(
                new_entry(
                    entry_id=ConfigEntryId(UUID(int=len(level) * 1000 + value)),
                    scope=ScopeRef(ScopeKind(level), SCOPE_IDS[level]),
                    key=ROUNDS,
                    op=EntryOp.SET,
                    value=value,
                    locked=locked,
                    reason="",
                    actor=PrincipalId(UUID(int=1)),
                    now=made.clock.now(),
                )
            )
        uow.repo(ConfigGenerationCounter).increment()
        uow.commit()


# ---------------------------------------------------------------------------------------------------------
# get_value / explain_config


def test_get_value_resolves_the_chain_without_invocation() -> None:
    made = harness()
    made.run(set_value("instance", ROUNDS, 4))
    view = made.ask(queries.GetValue(scope=ref(queries.GetValueDefsScopeRef, "plan"), key=ROUNDS))
    assert (view.present, view.value, view.winner.level, view.locked_by) == (True, 4, "instance", None)
    with pytest.raises(SkmError) as caught:
        made.ask(queries.GetValue(scope=ref(queries.GetValueDefsScopeRef, "plan"), key="logging.level"))
    assert caught.value.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED
    with pytest.raises(SkmError) as caught:
        made.ask(queries.GetValue(scope=ref(queries.GetValueDefsScopeRef, "plan"), key="nope.key"))
    assert caught.value.code is ErrorCode.CONFIG_UNKNOWN_KEY


def test_explain_matches_the_example_statuses_on_the_same_levels() -> None:
    made = harness(packs=Packs(PackFragment("example-overlay", 10, {ROUNDS: 3}, frozenset())))
    stale_entries(
        made, ("instance", 4, False), ("workspace", 3, True), ("project", 5, False), ("plan", 1, False)
    )
    result = made.ask(explain("plan", keys=(ROUNDS, "storage.statement_timeout_ms")))
    report = cast("dict[str, Any]", result.to_json())
    assert report["schema"] == EXAMPLE["schema"]
    assert report["chain_kind"] == "work"
    assert [layer["level"] for layer in report["chain"]] == [layer["level"] for layer in EXAMPLE["chain"]]
    [key, timeout] = report["keys"]
    expected = next(item for item in EXAMPLE["keys"] if item["key"] == ROUNDS)
    for name in ("key", "present", "value", "merge", "reload", "sensitivity"):
        assert key[name] == expected[name], name
    assert key["winner"]["level"] == "workspace"
    assert key["locked_by"]["level"] == "workspace"
    statuses = [(item["layer"]["level"], item["status"], item.get("reason")) for item in key["contributions"]]
    assert statuses == [
        (item["layer"]["level"], item["status"], item.get("reason")) for item in expected["contributions"]
    ]
    assert [item["code"] for item in key["diagnostics"]] == ["CONFIG_LOCKED"]
    assert timeout["value"] == 30000
    assert timeout["contributions"][0]["status"] == "winner"


def test_explain_detail_defaults_section_and_other_chain() -> None:
    made = harness()
    made.run(set_value("project", ROUNDS, 1))
    brief = cast("dict[str, Any]", made.ask(explain("project", keys=(ROUNDS,), detail="value")).to_json())
    assert brief["keys"][0]["contributions"] == []
    assert "base" not in brief["keys"][0]
    assert brief["keys"][0]["winner"]["level"] == "project"
    changed = cast("dict[str, Any]", made.ask(explain("project", include_defaults_only=False)).to_json())
    assert [item["key"] for item in changed["keys"]] == [ROUNDS]
    section = cast("dict[str, Any]", made.ask(explain("project", section="storage")).to_json())
    assert section["keys"]
    assert {item["key"].split(".")[0] for item in section["keys"]} == {"storage"}
    with pytest.raises(SkmError) as caught:
        made.ask(explain("project", keys=("logging.level",)))
    assert caught.value.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED
    assert caught.value.details["hint"] == "host"
    host = cast("dict[str, Any]", made.ask(explain("host", keys=("logging.level",))).to_json())
    assert host["chain_kind"] == "host"
    assert host["keys"][0]["value"] == "info"


# ---------------------------------------------------------------------------------------------------------
# export_config


def test_export_is_deterministic_and_round_trips_as_a_no_op() -> None:
    made = harness()
    made.run(set_value("instance", ROUNDS, 4, locked=True))
    made.run(set_value("instance", "execution.workflow.profile", "quick-fix"))
    made.run(set_value("instance", "logging.level", "debug"))
    first = made.ask(export("instance"))
    assert first == made.ask(export("instance"))
    parsed = tomllib.loads(first.document)
    assert parsed["lock"] == [ROUNDS]
    assert parsed["logging"] == {"level": "debug"}
    assert [entry.key for entry in first.entries] == sorted(entry.key for entry in first.entries)
    portable = made.ask(export("instance", portable_only=True))
    assert "logging" not in tomllib.loads(portable.document)
    assert portable.digest == first.digest  # the CAS digest covers every entry of the scope
    as_json = made.ask(export("instance", "json"))
    assert as_json.to_json()["document"]["execution"]["review"] == {"max_rounds": 4}
    before = made.snapshot()
    again = made.run(
        h["commands"].ImportConfig(
            scope=h["commands"].ImportConfigDefsScopeRef(level="instance", scope_id=SCOPE_IDS["instance"]),
            format="toml",
            document=first.document,
            expected_entries_digest=first.digest,
        )
    )
    assert {item.change for item in again.changes} == {"unchanged"}
    assert made.snapshot() == before


# ---------------------------------------------------------------------------------------------------------
# get_schema, list_entries, get_history, get_generation


def test_schema_lists_every_section_and_project_key_metadata() -> None:
    made = harness()
    view = made.ask(queries.GetSchema())
    registry = settings_registry()
    assert view.registry_digest == registry.digest
    assert [section.id for section in view.sections] == [section.id for section in registry.sections()]
    keys = {key.key: key for section in view.sections for key in section.keys}
    machine_keys = {
        "runtimes.binaries",
        "runtimes.credentials.copy",
        "runtimes.codex.allow_full_access",
        "runtimes.claude_code.allow_skip_permissions",
    }
    registry_keys = {spec.key for spec in registry.keys()}  # noqa: SIM118 - a registry, not a dict
    assert set(keys) == registry_keys - machine_keys
    assert keys.keys() >= {"runtimes.allowed", "plugins.allowed"}
    rounds = keys[ROUNDS]
    assert (rounds.merge, rounds.default, rounds.narrow.direction, rounds.lockable) == (
        "narrow",
        2,
        "min",
        True,
    )
    assert keys["hooks.subscriptions"].confirm is True
    storage = made.ask(queries.GetSchema(section="storage"))
    assert [section.id for section in storage.sections] == ["storage"]
    assert storage.sections[0].schema["$id"] == storage.sections[0].schema_urn
    with pytest.raises(SkmError) as caught:
        made.ask(queries.GetSchema(section="nope"))
    assert caught.value.code is ErrorCode.CONFIG_UNKNOWN_KEY


def test_schema_positional_argument_is_the_section_not_the_scope() -> None:
    positional = queries.GetSchema("storage")
    assert positional == queries.GetSchema(section="storage")
    assert (positional.section, positional.scope) == ("storage", None)
    assert positional.to_json() == {"section": "storage"}
    made = harness()
    storage = made.ask(positional)
    assert [section.id for section in storage.sections] == ["storage"]
    # an omitted scope is still the instance; the string never reaches the scope validation
    assert [(call.permission, call.scope_id) for call in made.authorizer.calls] == [
        ("config.read", SCOPE_IDS["instance"])
    ]
    made.authorizer.calls.clear()
    project = queries.GetSchema("storage", ref(queries.GetSchemaDefsScopeRef, "project"))
    assert made.ask(project) == storage
    [call] = made.authorizer.calls
    assert (call.permission, call.scope_id) == ("config.read", SCOPE_IDS["project"])
    denied = harness()
    read_only_at(denied, "project")
    assert denied.ask(project) == storage
    with pytest.raises(SkmError) as caught:
        denied.ask(positional)
    assert caught.value.code is ErrorCode.FORBIDDEN
    assert caught.value.details["permission"] == "config.read"


def schema_at(level: str, **fields: Any) -> queries.GetSchema:
    return queries.GetSchema(scope=ref(queries.GetSchemaDefsScopeRef, level), **fields)


def read_only_at(made: Any, level: str) -> None:
    """``config.read`` only in the scope ``level``; every other permission stays allowed."""
    decide = made.authorizer.authorize

    def authorize(uow: Any, actor: Any, permission: str, chain: Any) -> Any:
        decision = decide(uow, actor, permission, chain)
        if permission == "config.read" and chain[-1].id != SCOPE_IDS[level]:
            return AuthzDecision(allowed=False, reason_code="ROLE_LACKS_PERMISSION")
        return decision

    made.authorizer.authorize = authorize


def test_schema_checks_config_read_in_the_requested_scope() -> None:
    made = harness()
    instance = made.ask(queries.GetSchema())
    assert [(call.permission, call.scope_id) for call in made.authorizer.calls] == [
        ("config.read", SCOPE_IDS["instance"])
    ]
    for level in ("instance", "workspace", "project", "plan", "run", "host"):
        made.authorizer.calls.clear()
        assert made.ask(schema_at(level)) == instance  # one registry: the scope selects the right only
        # the bus decides once, in the query's read-only UoW; the handler asks nothing more
        [call] = made.authorizer.calls
        assert (call.permission, call.scope_id, call.readonly) == ("config.read", SCOPE_IDS[level], True)
    instance_only = queries.GetSchema(scope=queries.GetSchemaDefsScopeRef(level="instance"))
    assert made.ask(instance_only) == instance
    storage = made.ask(schema_at("project", section="storage"))
    assert [section.id for section in storage.sections] == ["storage"]


def test_schema_in_a_readable_scope_needs_no_instance_right() -> None:
    made = harness()
    read_only_at(made, "project")
    assert made.ask(schema_at("project")).sections
    for dto in (queries.GetSchema(), schema_at("instance"), schema_at("workspace"), schema_at("plan")):
        with pytest.raises(SkmError) as caught:
            made.ask(dto)
        assert caught.value.code is ErrorCode.FORBIDDEN
        assert caught.value.details["permission"] == "config.read"


@pytest.mark.parametrize("section", [None, "storage", "nope"])
def test_schema_refusal_precedes_any_metadata(section: str | None) -> None:
    made = harness()
    made.authorizer.deny_all()
    for dto in (queries.GetSchema(section=section), schema_at("project", section=section)):
        with pytest.raises(SkmError) as caught:
            made.ask(dto)
        # never CONFIG_UNKNOWN_KEY: whether a section exists is metadata too
        assert caught.value.code is ErrorCode.FORBIDDEN
        assert "registry_digest" not in str(caught.value.details)
        assert "storage" not in str(caught.value.details)


@pytest.mark.parametrize(
    ("scope", "code"),
    [
        ({"level": "project"}, ErrorCode.INVALID_REFERENCE),  # scope_id required below instance
        ({"level": "project", "scope_id": str(SCOPE_IDS["workspace"])}, ErrorCode.INVALID_REFERENCE),
        ({"level": "instance", "scope_id": str(SCOPE_IDS["project"])}, ErrorCode.INVALID_REFERENCE),
        ({"level": "project", "scope_id": str(UUID(int=7))}, ErrorCode.NOT_FOUND),
    ],
)
def test_schema_scope_must_name_the_scope_whose_right_is_checked(
    scope: dict[str, str], code: ErrorCode
) -> None:
    made = harness()
    with pytest.raises(SkmError) as caught:
        made.ask(queries.GetSchema.from_json({"scope": scope, "section": "nope"}))
    assert caught.value.code is code


def test_entries_and_history_page_by_their_keysets() -> None:
    made = harness()
    for level in ("instance", "workspace", "project"):
        made.run(set_value(level, ROUNDS, 2))
    made.run(set_value("project", "execution.workflow.profile", "quick-fix"))
    first = made.ask(queries.ListEntries(limit=2))
    second = made.ask(queries.ListEntries(after=first.next, limit=2))
    listed = [(item.key, item.scope.level) for item in (*first.items, *second.items)]
    assert listed == sorted(listed, key=lambda item: (item[0], str(SCOPE_IDS[item[1]])))
    assert len(listed) == 4
    assert second.next is None
    project = made.ask(queries.ListEntries(scope=ref(queries.ListEntriesDefsScopeRef, "project")))
    assert {item.key for item in project.items} == {ROUNDS, "execution.workflow.profile"}
    by_level = made.ask(queries.ListEntries(level="workspace", key_prefix="execution."))
    assert [item.scope.level for item in by_level.items] == ["workspace"]

    made.clock.advance(timedelta(seconds=1))
    made.run(set_value("project", ROUNDS, 1))
    page = made.ask(queries.GetHistory(limit=2))
    rest = made.ask(queries.GetHistory(after=page.next, limit=10))
    records = [*page.items, *rest.items]
    assert len(records) == 5
    assert rest.next is None
    assert [record.changed_at for record in records] == sorted((r.changed_at for r in records), reverse=True)
    assert records[0].change_kind == "updated"
    assert records[0].old_value == 2
    assert records[0].new_value == 1
    for_key = made.ask(queries.GetHistory(scope=ref(queries.GetHistoryDefsScopeRef, "project"), key=ROUNDS))
    assert [record.change_kind for record in for_key.items] == ["updated", "created"]
    assert made.ask(queries.GetGeneration()).generation == 5 == made.generation


def _history_cursor(changed_at: str, record_id: str = "00000000-0000-0000-0000-000000000000") -> str:
    raw = json.dumps([changed_at, record_id], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode("ascii")


@pytest.mark.parametrize("changed_at", ["2026-10-28", "2026-10-28T09:00:00", "not a time"])
def test_history_cursor_without_a_timezone_is_refused_on_empty_and_filled_history(changed_at: str) -> None:
    made = harness()
    for filled in (False, True):
        if filled:
            made.run(set_value("project", ROUNDS, 1))
        with pytest.raises(SkmError) as caught:
            made.ask(queries.GetHistory(after=_history_cursor(changed_at)))
        assert caught.value.code is ErrorCode.SCHEMA_INVALID
        assert caught.value.details == {"field": "after"}


def test_history_next_cursor_continues_the_pages() -> None:
    made = harness()
    for value in (1, 2, 1):
        made.clock.advance(timedelta(seconds=1))
        made.run(set_value("project", ROUNDS, value))
    page = made.ask(queries.GetHistory(limit=1))
    seen = list(page.items)
    while page.next is not None:
        page = made.ask(queries.GetHistory(after=page.next, limit=1))
        seen.extend(page.items)
    assert [record.change_kind for record in seen] == ["updated", "updated", "created"]
    aware = made.ask(queries.GetHistory(after=_history_cursor("2999-01-01T00:00:00+00:00", "f" * 36)))
    assert len(aware.items) == 3
