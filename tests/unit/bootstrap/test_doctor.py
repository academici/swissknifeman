import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import PurePosixPath
from typing import Any, ClassVar, cast
from uuid import UUID

import pytest

from skm.application_bus.ports import RegisteredCheckReport
from skm.bootstrap.doctor import (
    DoctorCheckCollector,
    DoctorCheckRegistry,
    DoctorCheckSpec,
    RestartPendingKey,
    ServingProcessObservation,
    ServingProcessObserver,
)
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.kernel.outcomes import Severity
from skm.modules.integrations.domain.reports import CheckResult
from skm.modules.integrations.domain.target import TargetId
from skm.platform.config.keys import Chain, Level
from skm.platform.config.layers import Contribution, Layer, LayerRef
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.registry import SectionValidatorFn, SettingsRegistry
from skm.platform.config.scopes import ScopeChain, ScopeRef
from skm.platform.config.store import EmptyPackConfigSource, StoredContribution
from skm.platform.logging.redaction import MASK, Redactor
from skm.platform.schema.registry import SchemaRegistry


def _finding(level: str, path: str | None = None, hint: str | None = None) -> CheckResult:
    return CheckResult("c.1", TargetId.CODEX, level, "Title", "detail", path, hint)


def test_normalizes_levels_and_details() -> None:
    reg = DoctorCheckRegistry(
        [
            DoctorCheckSpec(
                "a", lambda ctx: [_finding("info"), _finding("warning", "/p", "h"), _finding("error")]
            )
        ]
    )
    out = reg.run(object())
    assert [r["status"] for r in out] == ["ok", "warn", "fail"]
    assert out[1] == {
        "id": "c.1",
        "status": "warn",
        "message": "Title",
        "hint": "h",
        "details": {"target": "codex", "detail": "detail", "path": "/p"},
    }
    assert out[0]["details"]["path"] is None  # type: ignore[index]


def test_duplicate_id_rejected() -> None:
    with pytest.raises(ValidationFailed):
        DoctorCheckRegistry([DoctorCheckSpec("a", lambda c: []), DoctorCheckSpec("a", lambda c: [])])


def test_unknown_level_rejected() -> None:
    reg = DoctorCheckRegistry([DoctorCheckSpec("a", lambda c: [_finding("bogus")])])
    with pytest.raises(ValueError, match="bogus"):
        reg.run(None)


INSTANCE = ScopeRef(Level.INSTANCE, UUID(int=1))
HOST = ScopeRef(Level.HOST, UUID(int=2))
OTHER_HOST = ScopeRef(Level.HOST, UUID(int=3))
SECTION = "urn:skm:settings:probe:v1"
SECRET_REF = "urn:skm:config:secret-ref:v1"


class _View:
    SCHEMA_URN: ClassVar[str] = SECTION
    SCHEMA_DIGEST: ClassVar[str] = ""


class _TypedView:
    SCHEMA_URN: ClassVar[str] = SECTION
    SCHEMA_DIGEST: ClassVar[str] = ""


def _leaf(
    order: int,
    *,
    chain: str = "work",
    reload: str = "restart",
    secret: bool = False,
    schema: dict[str, Any] | None = None,
    default: JsonValue = "startup-private-value",
) -> dict[str, Any]:
    return {
        **({"$ref": SECRET_REF} if secret else schema or {"type": "string"}),
        "default": "secret://env/STARTUP" if secret else default,
        "description": "Probe value",
        "x-skm": {
            "chain": chain,
            "levels": ["instance", "host"] if chain == "host" else ["instance"],
            "merge": "replace",
            "reload": reload,
            "override": True,
            "sensitivity": "secret" if secret else "public",
            "portable": not secret,
            "lockable": True,
            "nullable": False,
            "pack": True,
            "confirm": False,
            "ui": {"group": "probe", "order": order, "widget": "json"},
        },
    }


@pytest.fixture(scope="module")
def schemas() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def _build(
    schemas: SchemaRegistry,
    properties: dict[str, Any],
    view: type[_View] | type[_TypedView],
    rules: Mapping[str, tuple[tuple[str, ...], SectionValidatorFn]] | None = None,
) -> SettingsRegistry:
    rules = rules or {}
    section: dict[str, Any] = {"id": "probe", "owner": "probe", "title": "Probe"}
    if rules:
        section["validators"] = [
            {"id": rule, "keys": list(keys), "rule": "r"} for rule, (keys, _) in rules.items()
        ]
        for rule, (keys, _fn) in rules.items():
            for key in keys:
                properties[key.removeprefix("probe.")]["x-skm"].setdefault("validators", []).append(rule)
    document: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SECTION,
        "type": "object",
        "additionalProperties": False,
        "x-skm-section": section,
        "x-skm-codegen": {"python": {"module": "m", "class": "V", "kind": "settings_view"}},
        "properties": properties,
    }
    closure: dict[str, Any] = {SECTION: document}
    if any(leaf.get("$ref") == SECRET_REF for leaf in properties.values()):
        closure[SECRET_REF] = dict(schemas.get(SECRET_REF))
    canonical = json.dumps(closure, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    view.SCHEMA_DIGEST = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    combined = SchemaRegistry(
        {**{urn: schemas.get(urn) for urn in schemas.urns()}, SECTION: document}, schemas.registry
    )
    return SettingsRegistry.build(
        combined,
        [SECTION],
        views={"probe": view},
        validators={rule: fn for rule, (_keys, fn) in rules.items()},
        known_permissions=frozenset(),
    )


@pytest.fixture(scope="module")
def registry(schemas: SchemaRegistry) -> SettingsRegistry:
    properties = {
        "restart": _leaf(1),
        "host_restart": _leaf(2, chain="host"),
        "live": _leaf(3, reload="live"),
        "frozen": _leaf(4, reload="run_frozen"),
        "secret": _leaf(5, secret=True),
    }
    return _build(schemas, properties, _View)


@pytest.fixture(scope="module")
def typed_registry(schemas: SchemaRegistry) -> SettingsRegistry:
    """JSON restart objects/arrays on both chains and a ``restart <= live`` section validator."""
    properties = {
        "shape": _leaf(1, schema={"type": "object"}, default={}),
        "host_shape": _leaf(2, chain="host", schema={"type": "object"}, default={}),
        "list": _leaf(3, schema={"type": "array"}, default=[]),
        "host_list": _leaf(4, chain="host", schema={"type": "array"}, default=[]),
        "restart": _leaf(5, schema={"type": "integer"}, default=2),
        "live": _leaf(6, reload="live", schema={"type": "integer"}, default=10),
    }
    bounds = (
        ("probe.restart", "probe.live"),
        lambda values: "restart exceeds live" if values["probe.restart"] > values["probe.live"] else None,
    )
    return _build(schemas, properties, _TypedView, {"probe.bounds": bounds})


class _Store:
    """Committed port data by default; the observer must not write or capture a new process."""

    def __init__(self) -> None:
        self.rows: dict[UUID, dict[str, StoredContribution]] = {}
        self.version = 7
        self.uncommitted = False
        self.reads = 0

    def generation(self) -> int:
        return self.version

    def pending_writes(self) -> bool:
        return self.uncommitted

    def entries_for(self, scope_ids: Sequence[UUID]) -> Mapping[UUID, Mapping[str, StoredContribution]]:
        self.reads += 1
        return {scope_id: self.rows[scope_id] for scope_id in scope_ids if scope_id in self.rows}

    def put(self, scope: ScopeRef, key: str, value: JsonValue) -> None:
        self.version += 1
        self.rows.setdefault(scope.scope_id, {})[key] = StoredContribution(
            UUID(int=self.version), key, "set", value, False, self.version
        )


class _Scopes:
    def __init__(self, instance: ScopeRef = INSTANCE) -> None:
        self.instance = instance
        self.requested: list[tuple[ScopeRef, Chain]] = []

    def instance_scope(self) -> ScopeRef:
        return self.instance

    def chain_for(self, scope: ScopeRef, kind: Chain) -> ScopeChain:
        self.requested.append((scope, kind))
        if scope == self.instance:
            return ScopeChain(kind, (self.instance,))
        assert kind is Chain.HOST
        assert scope in (HOST, OTHER_HOST)
        return ScopeChain(kind, (self.instance, scope))

    def label(self, scope: ScopeRef) -> str:
        return scope.label


@pytest.fixture
def store() -> _Store:
    return _Store()


@pytest.fixture
def scopes() -> _Scopes:
    return _Scopes()


def test_missing_snapshot_is_unknown_without_reading_configuration(
    registry: SettingsRegistry, store: _Store, scopes: _Scopes, monkeypatch: pytest.MonkeyPatch
) -> None:
    loader = ConfigLoader(registry, EmptyPackConfigSource())

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("doctor must never capture a baseline or resolve without one")

    monkeypatch.setattr(loader, "start_process", forbidden)
    monkeypatch.setattr(loader, "effective", forbidden)
    observer = ServingProcessObserver(loader)
    observation = observer.observe(store, scopes)
    assert observation.state == "snapshot_missing"
    assert observation.process_generation is None
    assert observation.pending == ()
    assert loader.process is None
    assert scopes.requested == []
    assert store.reads == 0
    (check,) = observation.to_checks()
    assert check.status == "warn"
    assert "unknown" in check.message
    assert "reason=snapshot_missing" in check.details.detail


@pytest.mark.parametrize("host", [None, INSTANCE, HOST])
def test_no_change_observes_only_the_captured_chains(
    registry: SettingsRegistry, store: _Store, scopes: _Scopes, host: ScopeRef | None
) -> None:
    loader = ConfigLoader(registry, EmptyPackConfigSource())
    snapshot = loader.start_process(store, scopes, host)
    scopes.requested.clear()
    observation = ServingProcessObserver(loader).observe(store, scopes)
    assert observation.state == "observed"
    assert observation.instance_scope_id == INSTANCE.scope_id
    assert observation.host_target == host
    assert observation.process_generation == 7
    assert observation.pending == ()
    assert loader.process is snapshot
    expected = [(INSTANCE, Chain.WORK)]
    if host is not None:
        expected.append((host, Chain.HOST))
    assert scopes.requested == expected
    (check,) = observation.to_checks()
    assert check.status == "ok"
    assert "serving-process chains" in check.message
    if host is None:
        assert "host=not_captured" in check.details.detail


@pytest.mark.parametrize(("work_changed", "host_changed"), [(True, False), (False, True), (True, True)])
def test_restart_findings_preserve_key_scope_and_original_process_generation(
    registry: SettingsRegistry,
    schemas: SchemaRegistry,
    store: _Store,
    scopes: _Scopes,
    work_changed: bool,
    host_changed: bool,
) -> None:
    loader = ConfigLoader(registry, EmptyPackConfigSource())
    snapshot = loader.start_process(store, scopes, HOST)
    if work_changed:
        store.put(INSTANCE, "probe.restart", "changed-work-private-value")
    if host_changed:
        store.put(HOST, "probe.host_restart", "changed-host-private-value")
    observation = ServingProcessObserver(loader).observe(store, scopes)
    expected = []
    if work_changed:
        expected.append(("probe.restart", Chain.WORK, INSTANCE))
    if host_changed:
        expected.append(("probe.host_restart", Chain.HOST, HOST))
    assert [(p.key, p.chain, p.target) for p in observation.pending] == expected
    assert observation.process_generation == snapshot.generation == 7
    assert loader.process is snapshot
    for check, (key, chain, target) in zip(observation.to_checks(), expected, strict=True):
        assert check.id == "config.restart_pending"
        assert check.status == "ok"  # settings §B.7 info, kernel-platform §5.2a info → ok
        assert check.message == "A configured value is pending serving-process restart"
        assert check.hint is not None
        assert check.details.detail.startswith("CONFIG_RESTART_PENDING; ")
        assert check.details.target == f"{target.level.value}:{target.scope_id}"
        assert f"key={key}; chain={chain.value}" in check.details.detail
        assert "process_generation=7" in check.details.detail
        assert schemas.validator("urn:skm:kernel:check-result:v1").issues(check.to_json()) == ()
    assert "private-value" not in str(observation)
    assert "private-value" not in str(observation.to_checks())


@pytest.mark.parametrize("captured_host", [None, HOST])
def test_another_hosts_changes_do_not_claim_this_process_needs_restart(
    registry: SettingsRegistry, store: _Store, scopes: _Scopes, captured_host: ScopeRef | None
) -> None:
    loader = ConfigLoader(registry, EmptyPackConfigSource())
    loader.start_process(store, scopes, captured_host)
    store.put(OTHER_HOST, "probe.host_restart", "other-host-private-value")
    scopes.requested.clear()
    observation = ServingProcessObserver(loader).observe(store, scopes)
    assert observation.state == "observed"
    assert observation.pending == ()
    assert all(target != OTHER_HOST for target, _kind in scopes.requested)
    assert observation.host_target == captured_host


def test_another_instance_is_unknown_without_using_process_values(
    registry: SettingsRegistry, store: _Store, scopes: _Scopes
) -> None:
    loader = ConfigLoader(registry, EmptyPackConfigSource())
    snapshot = loader.start_process(store, scopes, HOST)
    reads = store.reads
    foreign = _Scopes(ScopeRef(Level.INSTANCE, UUID(int=99)))
    observation = ServingProcessObserver(loader).observe(store, foreign)
    assert observation.state == "instance_mismatch"
    assert observation.pending == ()
    assert foreign.requested == []
    assert store.reads == reads
    assert loader.process is snapshot
    (check,) = observation.to_checks()
    assert check.status == "warn"
    assert "unknown" in check.message
    assert "reason=instance_mismatch" in check.details.detail


@pytest.mark.parametrize(("target", "key"), [(INSTANCE, "probe.restart"), (HOST, "probe.host_restart")])
@pytest.mark.parametrize("value", [42, {"bad": "invalid-private-value"}])
def test_invalid_changed_restart_value_still_requires_restart(
    registry: SettingsRegistry,
    store: _Store,
    scopes: _Scopes,
    target: ScopeRef,
    key: str,
    value: JsonValue,
) -> None:
    loader = ConfigLoader(registry, EmptyPackConfigSource())
    loader.start_process(store, scopes, HOST)
    store.put(target, key, value)
    observation = ServingProcessObserver(loader).observe(store, scopes)
    # Process overrides remove the invalid key; testing invalid_keys() here would miss this change.
    effective = loader.effective(store, scopes, target, Chain.HOST if target == HOST else Chain.WORK)
    assert key not in effective.invalid_keys()
    assert effective.get(key) == "startup-private-value"
    assert [item.key for item in observation.pending] == [key]
    assert observation.to_checks()[0].status == "ok"
    assert "pending" in observation.to_checks()[0].message
    assert "invalid-private-value" not in str(observation.to_checks())


def test_live_frozen_and_non_restart_diagnostics_do_not_become_restart_findings(
    registry: SettingsRegistry, store: _Store, scopes: _Scopes
) -> None:
    loader = ConfigLoader(registry, EmptyPackConfigSource())
    loader.start_process(store, scopes, None)
    store.put(INSTANCE, "probe.live", 42)  # A CONFIG_INVALID diagnostic is not CONFIG_RESTART_PENDING.
    store.put(INSTANCE, "probe.frozen", "new-frozen-private-value")
    assert loader.effective(store, scopes, None).diagnostics
    observation = ServingProcessObserver(loader).observe(store, scopes)
    assert observation.state == "observed"
    assert observation.pending == ()


def test_observer_tracks_reverted_values_against_the_same_baseline(
    registry: SettingsRegistry, store: _Store, scopes: _Scopes
) -> None:
    loader = ConfigLoader(registry, EmptyPackConfigSource())
    snapshot = loader.start_process(store, scopes, None)
    observer = ServingProcessObserver(loader)
    store.put(INSTANCE, "probe.restart", "new-private-value")
    assert observer.observe(store, scopes).pending
    store.put(INSTANCE, "probe.restart", "startup-private-value")
    assert observer.observe(store, scopes).pending == ()
    assert loader.process is snapshot


@pytest.mark.parametrize("value", ["secret://env/CHANGED_PRIVATE_REF", "literal-private-secret"])
def test_secret_changes_are_reported_without_references_or_literals(
    registry: SettingsRegistry, store: _Store, scopes: _Scopes, value: str
) -> None:
    loader = ConfigLoader(registry, EmptyPackConfigSource())
    loader.start_process(store, scopes, None)
    store.put(INSTANCE, "probe.secret", value)
    observation = ServingProcessObserver(loader).observe(store, scopes)
    assert [item.key for item in observation.pending] == ["probe.secret"]
    rendered = repr(observation) + repr(observation.to_checks())
    assert value not in rendered
    assert "secret://" not in rendered
    assert "startup-private-value" not in rendered


def test_invocation_is_observed_from_the_existing_loader(
    registry: SettingsRegistry, store: _Store, scopes: _Scopes
) -> None:
    invocation = LayerRef(Level.INVOCATION, source="cli")
    loader = ConfigLoader(
        registry,
        EmptyPackConfigSource(),
        [Layer(invocation, {"probe.restart": Contribution(invocation, "set", "invocation-private-value")})],
    )
    loader.start_process(store, scopes, None)
    store.put(INSTANCE, "probe.restart", "changed-stored-private-value")
    observation = ServingProcessObserver(loader).observe(store, scopes)
    # The existing invocation still wins. A fresh loader would falsely compare stored state instead.
    assert observation.state == "observed"
    assert observation.pending == ()


def test_uncommitted_state_cannot_be_reported_as_serving_process_status(
    registry: SettingsRegistry, store: _Store, scopes: _Scopes
) -> None:
    loader = ConfigLoader(registry, EmptyPackConfigSource())
    loader.start_process(store, scopes, HOST)
    store.put(INSTANCE, "probe.restart", "uncommitted-private-value")
    store.uncommitted = True
    scopes.requested.clear()
    observation = ServingProcessObserver(loader).observe(store, scopes)
    assert observation.state == "uncommitted"
    assert observation.pending == ()
    assert scopes.requested == []
    (check,) = observation.to_checks()
    assert check.status == "warn"
    assert "unknown" in check.message


@pytest.mark.parametrize("captured", [False, True])
def test_summary_findings_use_the_unchanged_check_result_schema(
    registry: SettingsRegistry, schemas: SchemaRegistry, store: _Store, scopes: _Scopes, captured: bool
) -> None:
    loader = ConfigLoader(registry, EmptyPackConfigSource())
    if captured:
        loader.start_process(store, scopes, None)
    checks = ServingProcessObserver(loader).observe(store, scopes).to_checks()
    for check in checks:
        document = check.to_json()
        assert schemas.validator("urn:skm:kernel:check-result:v1").issues(document) == ()
        assert set(document) == {"id", "status", "message", "hint", "details"}
        assert set(document["details"]) == {"target", "detail", "path"}
        assert document["details"]["path"] is None


_KIND_CHANGES: list[tuple[JsonValue, JsonValue]] = [
    ({"x": True}, {"x": 1}),
    ([False], [0]),
    ({"x": 1}, {"x": 1.0}),
    ([1], [1.0]),
    ({"a": [{"b": True}]}, {"a": [{"b": 1}]}),
    ([[{"c": 3}]], [[{"c": 3.0}]]),
]
_ORDINARY_CHANGES: list[tuple[JsonValue, JsonValue]] = [({"x": 1}, {"x": 2}), ([1, 2], [2, 1])]


def _json_key(target: ScopeRef, value: JsonValue) -> str:
    return f"probe.{'host_' if target == HOST else ''}{'shape' if isinstance(value, dict) else 'list'}"


@pytest.mark.parametrize("target", [INSTANCE, HOST])
@pytest.mark.parametrize(("before", "after"), _KIND_CHANGES + _ORDINARY_CHANGES)
def test_nested_json_changes_are_never_certified_as_unchanged(
    typed_registry: SettingsRegistry,
    store: _Store,
    scopes: _Scopes,
    target: ScopeRef,
    before: JsonValue,
    after: JsonValue,
) -> None:
    key = _json_key(target, before)
    assert not typed_registry.value_issues(key, before)
    assert not typed_registry.value_issues(key, after)
    store.put(target, key, before)
    loader = ConfigLoader(typed_registry, EmptyPackConfigSource())
    snapshot = loader.start_process(store, scopes, HOST)
    store.put(target, key, after)
    observation = ServingProcessObserver(loader).observe(store, scopes)
    chain = Chain.HOST if target == HOST else Chain.WORK
    assert observation.state == "observed"
    assert [(p.key, p.chain, p.target) for p in observation.pending] == [(key, chain, target)]
    assert loader.process is snapshot
    (check,) = observation.to_checks()
    assert check.message == "A configured value is pending serving-process restart"
    assert f"CONFIG_RESTART_PENDING; key={key}; chain={chain.value}" in check.details.detail
    # Restoring the captured value is an observed empty comparison again.
    store.put(target, key, before)
    assert ServingProcessObserver(loader).observe(store, scopes).pending == ()


@pytest.mark.parametrize("target", [INSTANCE, HOST])
@pytest.mark.parametrize("value", [{"x": True, "y": [0, 1.0, None]}, [False, {"z": 1}]])
def test_rewriting_the_same_json_value_is_not_pending(
    typed_registry: SettingsRegistry, store: _Store, scopes: _Scopes, target: ScopeRef, value: JsonValue
) -> None:
    key = _json_key(target, value)
    store.put(target, key, value)
    loader = ConfigLoader(typed_registry, EmptyPackConfigSource())
    loader.start_process(store, scopes, HOST)
    store.put(target, key, json.loads(json.dumps(value)))
    observation = ServingProcessObserver(loader).observe(store, scopes)
    assert observation.state == "observed"
    assert observation.pending == ()
    (check,) = observation.to_checks()
    assert check.status == "ok"
    assert check.message == "No restart-pending changes in the observed serving-process chains"


def test_live_only_validator_failure_does_not_imply_a_restart_change(
    typed_registry: SettingsRegistry, store: _Store, scopes: _Scopes
) -> None:
    loader = ConfigLoader(typed_registry, EmptyPackConfigSource())
    loader.start_process(store, scopes, None)
    observer = ServingProcessObserver(loader)
    store.put(INSTANCE, "probe.live", 1)  # restart=2 now exceeds live=1; restart itself is unchanged
    effective = loader.effective(store, scopes, None)
    assert effective.invalid_keys()["probe.restart"].reason == "validator"
    assert observer.observe(store, scopes).pending == ()
    store.put(INSTANCE, "probe.live", 10)  # restoration
    assert observer.observe(store, scopes).pending == ()
    store.put(INSTANCE, "probe.restart", 5)
    store.put(INSTANCE, "probe.live", 3)  # a changed restart input that fails the validator
    assert [item.key for item in observer.observe(store, scopes).pending] == ["probe.restart"]
    store.put(INSTANCE, "probe.live", 10)  # the same changed restart input, now valid
    assert [item.key for item in observer.observe(store, scopes).pending] == ["probe.restart"]


@pytest.mark.parametrize(("severity", "status"), [("info", "ok"), ("warning", "warn"), ("error", "fail")])
def test_pending_findings_use_the_declared_severity_mapping(severity: str, status: str) -> None:
    item = RestartPendingKey("probe.restart", Chain.WORK, INSTANCE, Severity(severity))
    observation = ServingProcessObservation("observed", INSTANCE.scope_id, None, 7, (item,))
    (check,) = observation.to_checks()
    assert check.status == status
    assert check.message == "A configured value is pending serving-process restart"
    assert "CONFIG_RESTART_PENDING; key=probe.restart; chain=work" in check.details.detail


@pytest.mark.parametrize("state", ["snapshot_missing", "instance_mismatch", "uncommitted"])
def test_unknown_states_remain_warnings_even_with_informational_pending(state: Any) -> None:
    item = RestartPendingKey("probe.restart", Chain.WORK, INSTANCE)
    observation = ServingProcessObservation(state, None, None, None, (item,))
    (check,) = observation.to_checks()
    assert check.status == "warn"
    assert f"reason={state}" in check.details.detail


def _bad(**changes: Any) -> CheckResult:
    return replace(_finding("info"), **changes)


@pytest.mark.parametrize(
    "finding",
    [
        _bad(check_id=cast("Any", 7)),
        _bad(check_id=""),
        _bad(title=cast("Any", 7)),
        _bad(hint=cast("Any", {"h": 1})),
        _bad(detail=cast("Any", {"d": 1})),
        _bad(target=cast("Any", "codex")),
        _bad(path=cast("Any", 7)),
        _bad(level=cast("Any", ["info"])),
        cast("Any", object()),
    ],
)
def test_a_malformed_field_fails_its_check_inside_isolation(finding: CheckResult) -> None:
    reg = DoctorCheckRegistry(
        [
            DoctorCheckSpec("bad", lambda c: [_finding("warning"), finding]),
            DoctorCheckSpec("fine", lambda c: [_finding("info")]),
        ]
    )
    assert reg.reports(object()) == (
        RegisteredCheckReport("bad", "failed"),  # buffered: the valid first finding is not reported
        RegisteredCheckReport("fine", "collected", reg.run_isolated(object(), frozenset({"fine"}))),
    )
    assert [(r.id, r.status) for r in reg.run_isolated(object())] == [("bad", "warn"), ("c.1", "ok")]


def test_a_path_object_is_projected_as_its_string() -> None:
    reg = DoctorCheckRegistry(
        [DoctorCheckSpec("a", lambda c: [_bad(path=cast("Any", PurePosixPath("/p/q")))])]
    )
    (report,) = reg.reports(object())
    assert report.findings[0].details.path == "/p/q"


def _collector(*specs: DoctorCheckSpec, in_uow: bool = False) -> DoctorCheckCollector:
    return DoctorCheckCollector(DoctorCheckRegistry(specs), in_unit_of_work=lambda: in_uow)


def test_reports_never_execute_and_collection_records_per_check() -> None:
    calls: list[str] = []

    def check(name: str, level: str) -> Callable[[object], list[CheckResult]]:
        def run(context: object) -> list[CheckResult]:
            calls.append(name)
            return [replace(_finding(level), check_id=name)]

        return run

    collector = _collector(
        DoctorCheckSpec("a", check("a", "info")), DoctorCheckSpec("b", check("b", "error"))
    )
    assert collector.ids() == {"a", "b"}
    assert collector.reports() == ()  # nothing collected yet: no report, nothing executed
    assert calls == []
    collector.collect(redactor=Redactor(), only=frozenset({"b"}))
    assert calls == ["b"]
    assert [(r.check_id, r.state) for r in collector.reports()] == [("b", "collected")]
    collector.collect(redactor=Redactor())
    assert calls == ["b", "a", "b"]
    assert [r.check_id for r in collector.reports()] == ["a", "b"]  # registration order
    assert [r.check_id for r in collector.reports(frozenset({"a"}))] == ["a"]
    assert calls == ["b", "a", "b"]
    with pytest.raises(ValueError, match="not registered"):
        collector.collect(redactor=Redactor(), only=frozenset({"z"}))


def test_collection_refuses_inside_a_unit_of_work() -> None:
    calls: list[object] = []
    collector = _collector(DoctorCheckSpec("a", lambda c: calls.append(c) or []), in_uow=True)
    with pytest.raises(RuntimeError, match="outside every unit of work"):
        collector.collect(redactor=Redactor())
    assert calls == []
    assert collector.reports() == ()


def test_collection_redacts_every_string_of_every_finding() -> None:
    secret = "Hunter2-Quartz-Lantern!"
    leaky = CheckResult(
        "c.1", TargetId.CODEX, "error", f"t {secret}", f"d {secret}", f"/{secret}", f"h {secret}"
    )
    collector = _collector(DoctorCheckSpec("a", lambda c: [leaky]))
    redactor = Redactor()
    redactor.register_secret(secret)
    collector.collect(redactor=redactor)
    ((finding,),) = [r.findings for r in collector.reports()]
    assert (finding.id, finding.status, finding.details.target) == ("c.1", "fail", "codex")
    assert (finding.message, finding.hint, finding.details.detail, finding.details.path) == (
        f"t {MASK}",
        f"h {MASK}",
        f"d {MASK}",
        f"/{MASK}",
    )
    assert secret not in repr(collector.reports())


class _StubPostgresUow:
    """Replaces ``PostgresUnitOfWork`` behaviour: no pool; ``failures`` simulate a failing enter or exit."""

    failures: ClassVar[dict[str, Exception | None]] = {"enter": None, "exit": None}

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def __enter__(self) -> "_StubPostgresUow":
        if (error := _StubPostgresUow.failures["enter"]) is not None:
            raise error
        return self

    def __exit__(self, *exc: object) -> None:
        if (error := _StubPostgresUow.failures["exit"]) is not None:
            raise error


def _tracked(monkeypatch: pytest.MonkeyPatch, tracker: Any) -> Any:
    from skm.adapters.postgres.uow import PostgresUnitOfWork
    from skm.bootstrap.composition import _TrackedUow

    for name in ("__init__", "__enter__", "__exit__"):
        monkeypatch.setattr(PostgresUnitOfWork, name, getattr(_StubPostgresUow, name))
    unused = cast("Any", None)
    return _TrackedUow(tracker, unused, unused, unused, unused, unused, readonly=True, isolation=unused)


def test_tracker_holds_exactly_while_a_postgres_unit_of_work_is_open(monkeypatch: pytest.MonkeyPatch) -> None:
    from skm.adapters.postgres.extensions.pack_config_source import PackConnectionSlot

    tracker = PackConnectionSlot()
    collector = DoctorCheckCollector(DoctorCheckRegistry([]), in_unit_of_work=tracker.holds)
    uow = _tracked(monkeypatch, tracker)
    assert not tracker.holds()
    collector.collect(redactor=Redactor())  # outside every unit of work
    with uow:
        assert tracker.holds()
        with pytest.raises(RuntimeError, match="outside every unit of work"):
            collector.collect(redactor=Redactor())
    assert not tracker.holds()
    collector.collect(redactor=Redactor())


def test_tracker_is_per_thread_and_survives_failed_enter_and_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    import threading

    from skm.adapters.postgres.extensions.pack_config_source import PackConnectionSlot

    tracker = PackConnectionSlot()
    uow = _tracked(monkeypatch, tracker)
    seen: list[bool] = []
    with uow:
        thread = threading.Thread(target=lambda: seen.append(tracker.holds()))
        thread.start()
        thread.join()
    assert seen == [False]  # another thread's open unit of work does not block this one
    monkeypatch.setitem(_StubPostgresUow.failures, "enter", RuntimeError("no connection"))
    with pytest.raises(RuntimeError, match="no connection"), uow:
        raise AssertionError("not entered")
    assert not tracker.holds()  # a unit of work that never opened is not counted
    monkeypatch.setitem(_StubPostgresUow.failures, "enter", None)
    monkeypatch.setitem(_StubPostgresUow.failures, "exit", RuntimeError("rollback failed"))
    with pytest.raises(RuntimeError, match="rollback failed"), uow:
        assert tracker.holds()
    assert not tracker.holds()  # a failing exit still releases the guard
