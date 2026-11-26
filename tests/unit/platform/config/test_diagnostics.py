"""Configured-state coverage, owner-port boundaries and value-free doctor findings."""

import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from runpy import run_path
from typing import Any, cast
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.kernel.generated.documents import CheckResult
from skm.kernel.json_types import JsonValue
from skm.kernel.outcomes import Diagnostic, Severity
from skm.kernel.scopes import ScopeKind, ScopeRecord, ScopeRegistry
from skm.platform.config.diagnostics import diagnose_config
from skm.platform.config.effective import EffectiveConfig
from skm.platform.config.keys import Chain, Level
from skm.platform.config.layers import Contribution, Layer, LayerRef
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.registry import SettingsRegistry
from skm.platform.config.scopes import ScopeChain
from skm.platform.config.sources.packs import PackFragment
from skm.platform.config.store import ConfigStore, EmptyPackConfigSource, PackConfigSource, ScopeTree

# Reuse the nearest tests' real memory UoW and real schema/registry builders.
_loader = run_path(str(Path(__file__).with_name("test_loader.py")))
_registry = run_path(str(Path(__file__).with_name("test_registry.py")))
Store = _loader["Store"]
Built, leaf, section = (_registry[name] for name in ("Built", "leaf", "section"))
IDS = _loader["LEVEL_IDS"]
ALL_IDS = (*IDS.values(), _loader["OTHER_HOST"])


def build(tmp_path: Path, *, validator: Any = None, invalid: bool = False) -> SettingsRegistry:
    def bounded(values: Mapping[str, JsonValue]) -> str | None:
        return (
            "private validator text"
            if cast("int", values["demo.size"]) > cast("int", values["demo.limit"])
            else None
        )

    def host_bounded(values: Mapping[str, JsonValue]) -> str | None:
        return (
            "private host text"
            if cast("int", values["demo.host_size"]) > cast("int", values["demo.host_limit"])
            else None
        )

    properties = {
        "size": leaf(levels=["instance", "workspace", "project", "plan", "run"], pack=True),
        "limit": leaf(default=5),
        "old": leaf(deprecated={"since": "2", "replacement": "demo.size"}, lockable=False),
        "local": leaf(levels=["instance"], lockable=False),
        "restart": leaf({"type": "string"}, default="startup", levels=["instance"], reload="restart"),
        "host_size": leaf(chain="host", levels=["instance", "host"]),
        "host_limit": leaf(chain="host", levels=["instance", "host"], default=5),
        "secret": leaf({"$ref": _registry["SECRET_REF"]}, default=None, nullable=True, sensitivity="secret"),
        "nested": leaf(
            {
                "type": "object",
                "properties": {"token": {"$ref": _registry["SECRET_REF"]}},
                "additionalProperties": False,
            },
            default={},
        ),
    }
    for index, node in enumerate(properties.values(), 1):
        node["x-skm"]["ui"]["order"] = index
    if invalid:
        properties["size"]["default"] = "REG-05 private rejected default"
        properties["local"]["x-skm"]["deprecated"] = {"since": "2", "replacement": "demo.absent"}
    return Built(
        tmp_path,
        [
            section(
                properties=properties,
                validators=[
                    {
                        "id": "demo.bounds",
                        "keys": ["demo.size", "demo.limit"],
                        "rule": "size <= limit",
                    },
                    {
                        "id": "demo.host_bounds",
                        "keys": ["demo.host_size", "demo.host_limit"],
                        "rule": "size <= limit",
                    },
                ],
            )
        ],
    ).build(validators={"demo.bounds": validator or bounded, "demo.host_bounds": host_bounded})


@pytest.fixture
def registry(tmp_path: Path) -> SettingsRegistry:
    return build(tmp_path)


@pytest.fixture
def store():
    return Store()


def inventory(uow) -> tuple[ScopeRecord, ...]:
    # Deliberately do not depend on the independently implemented list_scopes method.
    return tuple(uow.repo(ScopeRegistry).get(scope_id) for scope_id in ALL_IDS)


def check(store, registry, *, records=None, packs=None) -> tuple[CheckResult, ...]:
    with store.uow(readonly=True) as uow:
        return diagnose_config(
            registry=registry,
            inventory=inventory(uow) if records is None else records,
            store=uow.repo(ConfigStore),
            scopes=uow.repo(ScopeTree),
            packs=packs or EmptyPackConfigSource(),
        )


def matching(findings, code, *, level=None, key=None):
    return [
        item
        for item in findings
        if item.id == f"config.{code}"
        and (level is None or item.details.target == f"{level.value}:{IDS[level]}")
        and (key is None or json.loads(item.details.detail).get("key") == key)
    ]


def test_all_kinds_empty_scopes_and_both_instance_chains_are_checked(registry, store) -> None:
    findings = check(store, registry)
    coverage = {
        (item.details.target, json.loads(item.details.detail)["chain"])
        for item in matching(findings, "configured_state")
    }
    expected = {
        (f"{level.value}:{scope_id}", "host" if level is Level.HOST else "work")
        for level, scope_id in IDS.items()
    }
    expected |= {(f"instance:{IDS[Level.INSTANCE]}", "host"), (f"host:{_loader['OTHER_HOST']}", "host")}
    assert coverage == expected
    assert not [item for item in findings if item.status == "fail"]
    restart = matching(findings, "restart_pending")
    assert len(restart) == 1
    assert restart[0].status == "warn"
    assert json.loads(restart[0].details.detail)["state"] == "unknown"
    for finding in findings:
        assert CheckResult.from_json(finding.to_json()) == finding


@pytest.mark.parametrize(
    ("key", "value", "reason"),
    [
        ("demo.size", 8, "validator"),
        ("demo.size", "bad schema", "schema"),
    ],
)
def test_empty_descendants_inherit_invalid_ancestor_configuration(
    registry, store, key, value, reason
) -> None:
    store.commit((Level.INSTANCE, key, value))
    findings = check(store, registry)
    for level in (Level.INSTANCE, Level.WORKSPACE, Level.PROJECT, Level.PLAN, Level.RUN):
        invalid = matching(findings, "CONFIG_INVALID", level=level, key=key)
        assert len(invalid) == 1
        assert invalid[0].status == "fail"
        assert json.loads(invalid[0].details.detail)["reason"] == reason
        contribution = json.loads(invalid[0].details.detail)["contributions"][-1]
        assert contribution["scope_id"] == str(IDS[Level.INSTANCE])
    if reason == "schema":
        blocked = matching(findings, "CONFIG_INVALID", level=Level.RUN, key="demo.limit")
        assert json.loads(blocked[0].details.detail)["blocked_by"] == ["demo.size"]


def test_instance_host_chain_is_validated_even_without_registered_hosts(registry, store) -> None:
    store.commit((Level.INSTANCE, "demo.host_size", "bad host value"))
    with store.uow(readonly=True) as uow:
        records = tuple(record for record in inventory(uow) if record.kind is not ScopeKind.HOST)
    findings = check(store, registry, records=records)
    invalid = matching(findings, "CONFIG_INVALID", level=Level.INSTANCE, key="demo.host_size")
    assert len(invalid) == 1
    assert json.loads(invalid[0].details.detail)["chain"] == "host"
    assert not matching(findings, "CONFIG_SCOPE_NOT_ALLOWED", key="demo.host_size")


def test_every_stored_row_keeps_scope_entry_and_lock_provenance(registry, store) -> None:
    store.commit(
        (Level.INSTANCE, "removed.secret", {"password": "unknown raw payload"}),
        (Level.WORKSPACE, "demo.old", 2),
        (Level.INSTANCE, "demo.size", 3, "set", True),
        (Level.PROJECT, "demo.size", 4),
        (Level.PLAN, "demo.size", None, "unset"),
        (Level.RUN, "demo.size", 5),
        (Level.PROJECT, "demo.local", 9),
        (Level.RUN, "demo.limit", 4, "set", True),
        (Level.HOST, "demo.size", 2),
        (Level.PROJECT, "demo.host_size", 3),
    )
    findings = check(store, registry)
    assert matching(findings, "CONFIG_UNKNOWN_KEY", key="removed.secret")
    assert matching(findings, "CONFIG_DEPRECATED_KEY", key="demo.old")
    for level, key in (
        (Level.PROJECT, "demo.local"),
        (Level.RUN, "demo.limit"),
        (Level.HOST, "demo.size"),
        (Level.PROJECT, "demo.host_size"),
    ):
        assert matching(findings, "CONFIG_SCOPE_NOT_ALLOWED", level=level, key=key)
    locked = matching(findings, "CONFIG_LOCKED", level=Level.RUN, key="demo.size")
    metadata = json.loads(locked[0].details.detail)
    assert metadata["locked_by"]["scope_id"] == str(IDS[Level.INSTANCE])
    assert UUID(metadata["locked_by"]["entry_id"])
    assert {item["scope_id"] for item in metadata["contributions"]} >= {
        str(IDS[level]) for level in (Level.WORKSPACE, Level.PROJECT, Level.PLAN, Level.RUN)
    }
    assert all(UUID(item["entry_id"]) for item in metadata["contributions"])
    assert "unknown raw payload" not in json.dumps([item.to_json() for item in findings])


def test_shared_instance_other_chain_rows_are_legitimate(registry, store) -> None:
    store.commit((Level.INSTANCE, "demo.host_size", 2), (Level.INSTANCE, "demo.size", 2))
    assert not matching(check(store, registry), "CONFIG_SCOPE_NOT_ALLOWED")


@pytest.mark.parametrize(
    ("level", "key"),
    [
        (Level.INSTANCE, "demo.local"),
        (Level.INSTANCE, "demo.old"),
        (Level.WORKSPACE, "demo.old"),
    ],
)
@pytest.mark.parametrize("locked", [False, True])
def test_non_lockable_stored_keys_and_deprecated_aliases_are_diagnosed(registry, store, level, key, locked):
    store.commit((level, key, 2, "set", locked))
    findings = [
        item
        for item in matching(check(store, registry), "CONFIG_SCOPE_NOT_ALLOWED", level=level, key=key)
        if json.loads(item.details.detail).get("reason") == "key_not_lockable"
    ]
    assert len(findings) == int(locked)
    if locked:
        assert findings[0].status == "warn"
        contribution = json.loads(findings[0].details.detail)["contributions"][0]
        assert contribution["scope_id"] == str(IDS[level])
        assert UUID(contribution["entry_id"])
        assert "value" not in contribution


@pytest.mark.parametrize("raises", [False, True])
def test_validator_messages_exceptions_and_secret_values_never_escape(tmp_path, store, raises) -> None:
    def untrusted(values):
        if raises:
            raise RuntimeError("secret exception content")
        return "secret validator output " + str(dict(values))

    registry = build(tmp_path, validator=untrusted)
    store.commit(
        (Level.INSTANCE, "demo.secret", "literal secret password"),
        (Level.INSTANCE, "demo.nested", {"token": "nested literal password"}),
        (Level.INSTANCE, "removed.secret", {"token": "removed password"}),
    )
    findings = check(store, registry)
    assert matching(findings, "CONFIG_INVALID", key="demo.size")
    assert matching(findings, "CONFIG_INVALID", key="demo.secret")
    assert matching(findings, "CONFIG_INVALID", key="demo.nested")
    text = json.dumps([item.to_json() for item in findings])
    for forbidden in (
        "secret exception content",
        "secret validator output",
        "literal secret password",
        "nested literal password",
        "removed password",
    ):
        assert forbidden not in text


def test_valid_secret_references_are_not_resolved_or_included(registry, store) -> None:
    store.commit(
        (Level.INSTANCE, "demo.secret", "secret://env/DOCTOR_TEST_MUST_NOT_RESOLVE"),
        (Level.INSTANCE, "demo.nested", {"token": "secret://file/nonexistent-doctor-secret"}),
    )
    findings = check(store, registry)
    assert not matching(findings, "CONFIG_INVALID")
    assert "secret://" not in json.dumps([item.to_json() for item in findings])


def test_registry_failure_reports_all_reg_codes_without_reading_ports(tmp_path) -> None:
    with pytest.raises(InternalError) as caught:
        build(tmp_path, invalid=True)
    assert caught.value.code is ErrorCode.CONFIG_REGISTRY_INVALID

    class Unreadable:
        def __getattr__(self, name):
            pytest.fail(f"registry failure must not read {name}")

    unreadable_store = cast("ConfigStore", Unreadable())
    unreadable_scopes = cast("ScopeTree", Unreadable())
    unreadable_packs = cast("PackConfigSource", Unreadable())
    findings = diagnose_config(
        registry=caught.value,
        inventory=(),
        store=unreadable_store,
        scopes=unreadable_scopes,
        packs=unreadable_packs,
    )
    assert all(item.status == "fail" for item in findings)
    codes = {json.loads(item.details.detail)["code"] for item in findings}
    assert {"CONFIG_REGISTRY_INVALID", "REG-05", "REG-09"} <= codes
    assert "private rejected default" not in json.dumps([item.to_json() for item in findings])
    assert not matching(findings, "configured_state")
    error = InternalError(ErrorCode.INTERNAL_ERROR, "unrelated failure")
    with pytest.raises(InternalError) as unrelated:
        diagnose_config(
            registry=error,
            inventory=(),
            store=unreadable_store,
            scopes=unreadable_scopes,
            packs=unreadable_packs,
        )
    assert unrelated.value is error


def test_configured_restart_values_are_checked_without_startup_or_invocation_overrides(
    registry, store
) -> None:
    at = LayerRef(Level.INVOCATION, source="cli")
    serving_loader = ConfigLoader(
        registry,
        EmptyPackConfigSource(),
        [
            Layer(at, {"demo.restart": Contribution(at, "set", "invocation")}),
        ],
    )
    with store.uow(readonly=True) as uow:
        serving_loader.start_process(uow.repo(ConfigStore), uow.repo(ScopeTree), None)
    store.commit((Level.INSTANCE, "demo.restart", 123))
    findings = check(store, registry)
    assert matching(findings, "CONFIG_INVALID", key="demo.restart")
    assert not matching(findings, "CONFIG_RESTART_PENDING")
    assert matching(findings, "restart_pending")[0].status == "warn"
    assert serving_loader.process is not None
    assert serving_loader.process.work["demo.restart"] == "startup"


def test_pack_port_and_generation_are_preserved(registry, store) -> None:
    class Packs:
        current = 1

        def __init__(self):
            self.seen: list[ScopeChain] = []

        def generation(self):
            return self.current

        def fragments(self, chain):
            self.seen.append(chain)
            return (PackFragment("test", 1, {"demo.size": 8 if self.current == 1 else 2}),)

    packs = Packs()
    findings = check(store, registry, packs=packs)
    assert matching(findings, "CONFIG_INVALID", level=Level.RUN, key="demo.size")
    assert {chain.kind for chain in packs.seen} == {Chain.WORK, Chain.HOST}
    assert json.loads(matching(findings, "CONFIG_INVALID")[0].details.detail)["pack_generation"] == 1
    packs.current = 2
    assert not matching(check(store, registry, packs=packs), "CONFIG_INVALID")


class RejectingPacks:
    """Two real pack fragments, each contributing the same rejected keys."""

    ids = ("pack.alpha", "pack.beta")

    def generation(self):
        return 1

    def fragments(self, chain):
        return tuple(
            PackFragment(
                pack_id,
                1,
                {
                    "demo.size": "malformed pack value",
                    "demo.limit": 3,
                    "removed.pack_key": {"password": "pack raw payload"},
                },
            )
            for pack_id in self.ids
        )


def work_findings(findings, code, level, key):
    return [
        item
        for item in matching(findings, code, level=level, key=key)
        if json.loads(item.details.detail)["chain"] == "work"
    ]


def pack_sources(findings) -> list[str]:
    sources = []
    for item in findings:
        [contribution] = json.loads(item.details.detail)["contributions"]
        assert set(contribution) == {"level", "pack_id"}
        assert contribution["level"] == "pack"
        sources.append(contribution["pack_id"])
    return sorted(sources)


@pytest.mark.parametrize(
    ("code", "key"),
    [
        ("CONFIG_INVALID", "demo.size"),
        ("CONFIG_UNKNOWN_KEY", "removed.pack_key"),
        ("CONFIG_PACK_NOT_ALLOWED", "demo.limit"),
    ],
)
def test_rejected_pack_contributions_keep_their_pack_identity(registry, store, code, key) -> None:
    findings = check(store, registry, packs=RejectingPacks())
    for level in (Level.INSTANCE, Level.RUN):
        rejected = work_findings(findings, code, level, key)
        assert len(rejected) == 2
        assert {item.status for item in rejected} == {"warn"}
        assert pack_sources(rejected) == list(RejectingPacks.ids)
        metadata = [json.loads(item.details.detail) for item in rejected]
        assert not {"reason", "validator", "blocked_by"} & {name for item in metadata for name in item}
    text = json.dumps([item.to_json() for item in findings])
    assert "malformed pack value" not in text
    assert "pack raw payload" not in text


@pytest.mark.parametrize(("value", "reason"), [("malformed stored value", "schema"), (8, "validator")])
def test_rejected_pack_values_stay_warnings_beside_an_invalid_effective_key(
    registry, store, value, reason
) -> None:
    store.commit((Level.INSTANCE, "demo.size", value))
    findings = check(store, registry, packs=RejectingPacks())
    for level in (Level.INSTANCE, Level.WORKSPACE, Level.RUN):
        invalid = work_findings(findings, "CONFIG_INVALID", level, "demo.size")
        assert len(invalid) == 3
        rejected = [item for item in invalid if item.status == "warn"]
        failed = [item for item in invalid if item.status == "fail"]
        assert pack_sources(rejected) == list(RejectingPacks.ids)
        assert all("reason" not in json.loads(item.details.detail) for item in rejected)
        assert len(failed) == 1
        metadata = json.loads(failed[0].details.detail)
        assert metadata["reason"] == reason
        assert metadata.get("validator") == ("demo.bounds" if reason == "validator" else None)
        assert metadata["contributions"][-1]["scope_id"] == str(IDS[Level.INSTANCE])
        assert all(item["level"] != "pack" for item in metadata["contributions"])
    text = json.dumps([item.to_json() for item in findings])
    assert "malformed stored value" not in text
    assert "malformed pack value" not in text


@pytest.mark.parametrize("change", ["empty", "duplicate", "missing_parent", "wrong_instance", "wrong_parent"])
def test_inconsistent_inventory_is_rejected(registry, store, change) -> None:
    with store.uow(readonly=True) as uow:
        records = inventory(uow)
    if change == "empty":
        records = ()
    elif change == "duplicate":
        records += (records[0],)
    elif change == "missing_parent":
        records = tuple(record for record in records if record.kind is not ScopeKind.PROJECT)
    elif change == "wrong_instance":
        records = (replace(records[0], id=UUID(int=999)),)
    else:
        records = tuple(
            replace(record, parent_id=IDS[Level.PROJECT]) if record.kind is ScopeKind.HOST else record
            for record in records
        )
    with pytest.raises(ValueError, match="diagnostic"):
        check(store, registry, records=records)


def test_output_is_deterministic_for_inventory_order(registry, store) -> None:
    with store.uow(readonly=True) as uow:
        records = inventory(uow)
    assert check(store, registry, records=records) == check(store, registry, records=reversed(records))


@pytest.mark.parametrize("value", [8, "malformed"])
def test_host_validator_failures_and_blocked_inputs_reach_both_hosts(registry, store, value) -> None:
    store.commit((Level.INSTANCE, "demo.host_size", value))
    findings = check(store, registry)
    for target in (
        f"instance:{IDS[Level.INSTANCE]}",
        f"host:{IDS[Level.HOST]}",
        f"host:{_loader['OTHER_HOST']}",
    ):
        failures = [
            item
            for item in matching(findings, "CONFIG_INVALID", key="demo.host_limit")
            if item.details.target == target
        ]
        assert len(failures) == 1
        metadata = json.loads(failures[0].details.detail)
        assert metadata["validator"] == "demo.host_bounds"
        assert metadata.get("blocked_by", []) == (["demo.host_size"] if value == "malformed" else [])
    assert "private host text" not in json.dumps([item.to_json() for item in findings])


def test_all_stored_rows_are_checked_beyond_the_default_page_size(registry, store) -> None:
    store.commit(
        *[(Level.RUN, f"removed.key_{index}", {"password": "hidden payload"}) for index in range(127)]
    )
    findings = matching(check(store, registry), "CONFIG_UNKNOWN_KEY", level=Level.RUN)
    assert {json.loads(item.details.detail)["key"] for item in findings} == {
        f"removed.key_{index}" for index in range(127)
    }


def test_stale_inventory_is_rejected_before_reading_unauthorized_ancestors(registry, store) -> None:
    with store.uow(readonly=True) as uow:
        records = inventory(uow)
    workspace = next(record for record in records if record.kind is ScopeKind.WORKSPACE)
    extra = replace(workspace, id=UUID(int=123456))
    records = (
        *tuple(
            replace(record, parent_id=extra.id) if record.kind is ScopeKind.PROJECT else record
            for record in records
            if record.kind is not ScopeKind.WORKSPACE
        ),
        extra,
    )
    with store.uow(readonly=True) as uow:
        delegate = uow.repo(ConfigStore)

        class GuardedStore:
            def generation(self):
                return delegate.generation()

            def pending_writes(self):
                return delegate.pending_writes()

            def entries_for(self, scope_ids):
                assert workspace.id not in scope_ids, "read outside the supplied inventory"
                return delegate.entries_for(scope_ids)

        with pytest.raises(ValueError, match="different ancestry"):
            diagnose_config(
                registry=registry,
                inventory=records,
                store=GuardedStore(),
                scopes=uow.repo(ScopeTree),
                packs=EmptyPackConfigSource(),
            )


@pytest.mark.parametrize("code", ["CONFIG_NARROWING_VIOLATION", "UNRECOGNIZED_DIAGNOSTIC"])
def test_public_entrypoint_projects_only_allowlisted_diagnostic_metadata(registry, store, monkeypatch, code):
    original = ConfigLoader.effective

    def with_untrusted_details(self, *args, **kwargs):
        config = original(self, *args, **kwargs)
        diagnostic = Diagnostic(
            code,
            "untrusted diagnostic message",
            Severity.ERROR,
            target="demo.size",
            details={
                "layers": [
                    {
                        "level": "instance",
                        "scope_id": str(IDS[Level.INSTANCE]),
                        "entry_id": "malformed uuid private text",
                        "value": "hidden value",
                        "label": "private label",
                    }
                ],
                "violations": [{"value": "private rejected value", "ceiling": "private ceiling"}],
                "anything": "untrusted private detail",
            },
        )
        return EffectiveConfig(
            registry=config.registry,
            chain=config.chain,
            resolutions={key: config.resolution(key) for key in config.resolved_keys()},
            invalid=config.invalid_keys(),
            diagnostics=(diagnostic,),
            generation=config.generation,
            pack_generation=config.pack_generation,
            digest=config.digest,
        )

    monkeypatch.setattr(ConfigLoader, "effective", with_untrusted_details)
    findings = check(store, registry)
    output_code = code if code == "CONFIG_NARROWING_VIOLATION" else "CONFIG_DIAGNOSTIC_UNKNOWN"
    projected = matching(findings, output_code)
    assert projected
    assert {item.status for item in projected} == (
        {"warn"} if code == "CONFIG_NARROWING_VIOLATION" else {"fail"}
    )
    assert json.loads(projected[0].details.detail)["contributions"] == [
        {"level": "instance", "scope_id": str(IDS[Level.INSTANCE])},
    ]
    text = json.dumps([item.to_json() for item in findings])
    assert "private" not in text
    assert "untrusted" not in text
    assert "hidden value" not in text
