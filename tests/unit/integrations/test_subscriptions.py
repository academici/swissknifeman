"""Unit and registry-integration tests for ``integrations`` hook subscriptions (P10.08.a)."""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any, cast
from uuid import UUID

import pytest

from fakes.app import FakeScopeChain
from fakes.authorizer import FakeAuthorizer
from fakes.clock import FrozenClock
from fakes.entropy import DeterministicEntropy
from fakes.ids import SequentialIds
from skm.adapters.memory.config_store import MemoryConfigStore
from skm.adapters.memory.core import REPOSITORIES as CORE_REPOSITORIES
from skm.adapters.memory.settings import REPOSITORIES as SETTINGS_REPOSITORIES
from skm.adapters.memory.uow import InMemoryBackend
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.ports import Authorizer
from skm.application_bus.registry import BusRegistry
from skm.bootstrap.modules import MANIFESTS, MODULE_CATALOG
from skm.bootstrap.platform_module import PLATFORM_MANIFEST
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import PrincipalId, ProjectId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.access.permissions import PERMISSIONS as ACCESS_PERMISSIONS
from skm.modules.integrations.application.subscribers import default_hookable_event_types
from skm.modules.integrations.domain.hook_events import HookClass, HookSurfaceId
from skm.modules.integrations.domain.hook_outcomes import (
    HostCommandVerdict,
    HostHookOutcome,
    HostOutcomeStatus,
    combine_outcomes,
)
from skm.modules.integrations.domain.hook_rules import HookDecision, HookVerdict
from skm.modules.integrations.domain.hook_subscriptions import (
    Backoff,
    CommandTarget,
    ExecutionLocation,
    FailurePolicy,
    HookSubscription,
    RetrySpec,
    SubscriptionKind,
    WebhookTarget,
    effective_max_attempts,
    matches,
    next_attempt_at,
    subscription_digest,
    subscription_json,
)
from skm.modules.integrations.settings import validators_for
from skm.modules.settings.generated.commands import SetValue, SetValueDefsScopeRef
from skm.modules.settings.module import MODULE as SETTINGS_MODULE
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.registry import SettingsRegistry
from skm.platform.config.store import ConfigStore, EmptyPackConfigSource, PackConfigSource, ScopeTree
from skm.platform.config.validators import (
    SECTION_URNS as PLATFORM_SECTIONS,
)
from skm.platform.config.validators import (
    VALIDATORS as PLATFORM_VALIDATORS,
)
from skm.platform.config.validators import (
    VIEWS as PLATFORM_VIEWS,
)
from skm.platform.schema.registry import SchemaRegistry

HOOKABLE_EVENT = "urn:skm:policy:event:intent-proposed:v1"
HOOKABLE_PLAN_EVENT = "urn:skm:planning:event:plan-created:v1"
NOW = datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)
DEFAULT_BACKOFF = Backoff(initial_ms=1000, factor=2.0, max_ms=300_000)
DEFAULT_RETRY = RetrySpec(max_attempts=5, backoff=DEFAULT_BACKOFF)


def _webhook_sub(
    sub_id: str = "ci-notify",
    *,
    class_: HookClass = HookClass.OBSERVATION,
    event_types: tuple[str, ...] = (HOOKABLE_EVENT,),
    url: str = "https://hooks.example.com/skm",
    secret: str = "secret://env/SKM_HOOK_SECRET",
    headers: dict[str, str] | None = None,
    timeout_ms: int = 5000,
    retry: RetrySpec = DEFAULT_RETRY,
    failure_policy: FailurePolicy = FailurePolicy.RETRY,
    enabled: bool = True,
) -> HookSubscription:
    draft = HookSubscription(
        id=sub_id,
        enabled=enabled,
        hook_class=class_,
        kind=SubscriptionKind.WEBHOOK,
        execution_location=ExecutionLocation.CONTROL_PLANE,
        event_types=event_types,
        target=WebhookTarget(url=url, secret=secret, previous_secret=None, headers=headers or {}),
        timeout_ms=timeout_ms,
        retry=retry,
        failure_policy=failure_policy,
        defined_at="workspace",
        digest="",
    )
    return replace(draft, digest=subscription_digest(subscription_json(draft)))


def _host_sub(
    sub_id: str = "audit-shell",
    *,
    class_: HookClass = HookClass.ENFORCEMENT,
    event_types: tuple[str, ...] = ("client:pre_shell",),
    argv: tuple[str, ...] = ("./scripts/audit.py",),
    failure_policy: FailurePolicy = FailurePolicy.DENY,
    enabled: bool = True,
) -> HookSubscription:
    draft = HookSubscription(
        id=sub_id,
        enabled=enabled,
        hook_class=class_,
        kind=SubscriptionKind.COMMAND,
        execution_location=ExecutionLocation.HOST,
        event_types=event_types,
        target=CommandTarget(argv=argv, cwd="checkout", env_allow=("CI",), env_refs={}),
        timeout_ms=1000,
        retry=DEFAULT_RETRY,
        failure_policy=failure_policy,
        defined_at="project",
        digest="",
    )
    return replace(draft, digest=subscription_digest(subscription_json(draft)))


def test_matches_exact_and_wildcard_domain_and_client_patterns() -> None:
    exact_domain = _webhook_sub(event_types=("urn:skm:policy:event:intent-proposed:v1",))
    assert matches(exact_domain, "urn:skm:policy:event:intent-proposed:v1") is True
    assert matches(exact_domain, "urn:skm:policy:event:intent-denied:v1") is False
    assert matches(exact_domain, "client:pre_shell") is False

    module_wild = _webhook_sub(event_types=("urn:skm:policy:event:*",))
    assert matches(module_wild, "urn:skm:policy:event:intent-proposed:v1") is True
    assert matches(module_wild, "urn:skm:policy:event:intent-approved:v2") is True
    assert matches(module_wild, "urn:skm:planning:event:plan-created:v1") is False
    assert matches(module_wild, "urn:skm:policy:command:propose-intent:v1") is False
    assert matches(module_wild, "urn:skm:policy:event:") is False

    exact_client = _host_sub(event_types=("client:pre_shell",))
    assert matches(exact_client, "client:pre_shell") is True
    assert matches(exact_client, "client:post_shell") is False
    assert matches(exact_client, "urn:skm:policy:event:intent-proposed:v1") is False

    client_wild = _host_sub(
        class_=HookClass.OBSERVATION, event_types=("client:*",), failure_policy=FailurePolicy.WARN
    )
    assert matches(client_wild, "client:pre_shell") is True
    assert matches(client_wild, "client:session_start") is True
    assert matches(client_wild, "client:") is False
    assert matches(client_wild, "urn:skm:policy:event:intent-proposed:v1") is False


def test_effective_max_attempts_respects_warn_vs_retry_and_deny() -> None:
    retry = RetrySpec(max_attempts=6, backoff=DEFAULT_BACKOFF)
    assert effective_max_attempts(_webhook_sub(retry=retry, failure_policy=FailurePolicy.WARN)) == 1
    assert effective_max_attempts(_webhook_sub(retry=retry, failure_policy=FailurePolicy.RETRY)) == 6
    assert (
        effective_max_attempts(
            _webhook_sub(class_=HookClass.WORKFLOW, retry=retry, failure_policy=FailurePolicy.DENY)
        )
        == 6
    )


def test_next_attempt_at_backoff_jitter_cap_and_retry_after() -> None:
    retry = RetrySpec(max_attempts=5, backoff=Backoff(initial_ms=1000, factor=2.0, max_ms=5000))
    assert next_attempt_at(retry, attempt=1, now=NOW, jitter=1.0) == NOW + timedelta(milliseconds=1000)
    assert next_attempt_at(retry, attempt=2, now=NOW, jitter=1.0) == NOW + timedelta(milliseconds=2000)
    assert next_attempt_at(retry, attempt=3, now=NOW, jitter=0.8) == NOW + timedelta(milliseconds=3200)
    assert next_attempt_at(retry, attempt=4, now=NOW, jitter=1.2) == NOW + timedelta(milliseconds=5000)
    assert next_attempt_at(retry, attempt=1, now=NOW, jitter=1.0, retry_after_ms=3500) == NOW + timedelta(
        milliseconds=3500
    )
    assert next_attempt_at(retry, attempt=1, now=NOW, jitter=1.0, retry_after_ms=99_000) == NOW + timedelta(
        milliseconds=5000
    )

    with pytest.raises(ValueError, match="jitter"):
        next_attempt_at(retry, attempt=1, now=NOW, jitter=0.79)
    with pytest.raises(ValueError, match="jitter"):
        next_attempt_at(retry, attempt=1, now=NOW, jitter=1.21)
    with pytest.raises(ValueError, match="attempt"):
        next_attempt_at(retry, attempt=0, now=NOW, jitter=1.0)


def test_subscription_digest_ignores_enabled_and_changes_on_material_fields() -> None:
    enabled_sub = _webhook_sub(enabled=True)
    disabled_sub = _webhook_sub(enabled=False)
    digest = enabled_sub.digest
    assert digest.startswith("sha256:")
    assert len(digest) == 71
    assert disabled_sub.digest == digest

    assert _webhook_sub(url="https://hooks.example.com/other").digest != digest
    assert _webhook_sub(secret="secret://env/OTHER_SECRET").digest != digest
    assert _webhook_sub(timeout_ms=8000).digest != digest
    assert _host_sub(argv=("./a.py",)).digest != _host_sub(argv=("./b.py",)).digest


def _decision(
    verdict: HookVerdict,
    *,
    surface: HookSurfaceId = HookSurfaceId.GIT_GUARDRAILS,
    reason_code: str | None = None,
    message: str | None = None,
    context: str | None = None,
) -> HookDecision:
    return HookDecision(
        verdict=verdict,
        surface=surface,
        reason_code=reason_code,
        user_message=message,
        agent_message=message,
        additional_context=context,
    )


def _outcome(
    sub_id: str,
    *,
    class_: HookClass,
    policy: FailurePolicy = FailurePolicy.DENY,
    status: HostOutcomeStatus = HostOutcomeStatus.OK,
    verdict: HostCommandVerdict = HostCommandVerdict.NONE,
    reason: str | None = None,
    context: str | None = None,
) -> HostHookOutcome:
    return HostHookOutcome(
        subscription_id=sub_id,
        hook_class=class_,
        failure_policy=policy,
        status=status,
        verdict=verdict,
        reason=reason,
        additional_context=context,
        duration_ms=12,
    )


def test_combine_outcomes_enforces_precedence_shadow_mode_and_untrusted_message() -> None:
    builtin_none = _decision(HookVerdict.NONE)
    builtin_deny = _decision(HookVerdict.DENY, reason_code="POLICY_DENY", message="blocked")
    assert (
        combine_outcomes(
            builtin_deny,
            [_outcome("a", class_=HookClass.WORKFLOW, verdict=HostCommandVerdict.NONE, context="ctx")],
        )
        == builtin_deny
    )

    untrusted = combine_outcomes(
        builtin_none,
        [_outcome("guard-1", class_=HookClass.ENFORCEMENT, status=HostOutcomeStatus.UNTRUSTED)],
    )
    assert untrusted.verdict is HookVerdict.ASK
    assert untrusted.reason_code == "HOOK_SUBSCRIPTION_UNTRUSTED"
    expected_untrusted = (
        "hook subscription guard-1 is not trusted on this host; "
        'review it with "skm hooks show guard-1" and run "skm hooks trust guard-1"'
    )
    assert untrusted.user_message == expected_untrusted
    assert untrusted.agent_message == expected_untrusted

    for failure_status in (
        HostOutcomeStatus.FAILED,
        HostOutcomeStatus.TIMEOUT,
        HostOutcomeStatus.INVALID_OUTPUT,
        HostOutcomeStatus.SKIPPED_BUDGET,
    ):
        failed = combine_outcomes(
            builtin_none,
            [_outcome("guard-fail", class_=HookClass.ENFORCEMENT, status=failure_status, reason="boom")],
        )
        assert failed.verdict is HookVerdict.DENY
        assert failed.reason_code == "HOOK_SUBSCRIPTION_FAILED"

    shadow = combine_outcomes(
        builtin_none,
        [
            _outcome(
                "s1", class_=HookClass.ENFORCEMENT, policy=FailurePolicy.WARN, verdict=HostCommandVerdict.DENY
            ),
            _outcome(
                "s2",
                class_=HookClass.ENFORCEMENT,
                policy=FailurePolicy.WARN,
                status=HostOutcomeStatus.UNTRUSTED,
            ),
        ],
    )
    assert shadow == builtin_none

    long_b = "B" * 3995
    long_c = "C" * 50
    combined_ctx = combine_outcomes(
        builtin_none,
        [
            _outcome(
                "z-obs", class_=HookClass.OBSERVATION, verdict=HostCommandVerdict.DENY, reason="ignored"
            ),
            _outcome("c-wf", class_=HookClass.WORKFLOW, context=long_c),
            _outcome("b-wf", class_=HookClass.WORKFLOW, context=long_b),
            _outcome("a-wf", class_=HookClass.WORKFLOW, verdict=HostCommandVerdict.DENY, reason="wf no deny"),
        ],
    )
    assert combined_ctx.verdict is HookVerdict.CONTEXT
    assert combined_ctx.additional_context is not None
    assert len(combined_ctx.additional_context) == 4000
    assert combined_ctx.additional_context.startswith("B" * 10)

    precedence = combine_outcomes(
        _decision(HookVerdict.ASK, reason_code="BUILTIN_ASK", message="ask"),
        [
            _outcome("sub-z", class_=HookClass.ENFORCEMENT, verdict=HostCommandVerdict.DENY, reason="z deny"),
            _outcome("sub-a", class_=HookClass.ENFORCEMENT, verdict=HostCommandVerdict.DENY, reason="a deny"),
        ],
    )
    assert precedence.verdict is HookVerdict.DENY
    assert precedence.user_message == "a deny"
    assert precedence.agent_message == "a deny"


@cache
def _cached_bundle(
    sink_ids: tuple[str, ...],
) -> tuple[SchemaRegistry, SettingsRegistry, BusRegistry, frozenset[str]]:
    schemas = SchemaRegistry.load_default()
    hookable = default_hookable_event_types(schemas)
    all_perms = frozenset(ACCESS_PERMISSIONS).union(
        *(m.permissions for m in MANIFESTS), PLATFORM_MANIFEST.permissions
    )
    by_sec = {
        cast("Mapping[str, Any]", schemas.get(urn)["x-skm-section"])["id"]: urn
        for urn in schemas.urns()
        if "x-skm-section" in schemas.get(urn)
    }
    views, callbacks, urns = dict(PLATFORM_VIEWS), dict(PLATFORM_VALIDATORS), list(PLATFORM_SECTIONS)
    for entry in MODULE_CATALOG:
        if entry.settings_sections:
            mod = importlib.import_module(f"skm.modules.{entry.id}.settings")
            views.update(mod.VIEWS)
            callbacks.update(mod.VALIDATORS)
            urns.extend(by_sec[sec] for sec in entry.settings_sections)
    callbacks.update(validators_for(hookable_types=hookable, sink_ids=sink_ids))
    reg = SettingsRegistry.build(
        schemas, urns, views=views, validators=callbacks, known_permissions=all_perms
    )
    bus_reg = BusRegistry.build(
        (SETTINGS_MODULE,), schemas=schemas, permission_catalog=all_perms, disabled_modules=frozenset()
    )
    return schemas, reg, bus_reg, all_perms


class _WriteHarness:
    def __init__(self, *, sink_ids: tuple[str, ...] = ("jira-sink",)) -> None:
        self.schemas, self.registry, bus_reg, all_perms = _cached_bundle(sink_ids)
        pack_source = EmptyPackConfigSource()
        authorizer = FakeAuthorizer(all_perms)
        self.clock = FrozenClock(NOW)
        self.ids = SequentialIds()
        self.backend = InMemoryBackend(
            factories={
                **CORE_REPOSITORIES,
                **SETTINGS_REPOSITORIES,
                ConfigStore: MemoryConfigStore,
                PackConfigSource: lambda _state: pack_source,
                Authorizer: lambda _state: authorizer,
            },
            schemas=self.schemas,
            subscriptions=bus_reg.subscription_index(),
            ids=self.ids,
            clock=self.clock,
        )
        self.loader = ConfigLoader(self.registry, pack_source)
        self.bus = Bus(
            registry=bus_reg,
            schemas=self.schemas,
            uow_factory=self.backend.uow_factory(),
            authorizer=authorizer,
            scopes=FakeScopeChain(),
            config=self.loader,
            clock=self.clock,
            ids=self.ids,
            entropy=DeterministicEntropy(),
            gateways=GatewayTable({}, "control_plane_gateway"),
            retry=RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
            idempotency_ttl=timedelta(hours=1),
        )
        self.actor = Actor(PrincipalId(UUID(int=10)), PrincipalKind.HUMAN, "tester")
        self.ws_id = WorkspaceId(UUID(int=1))
        self.proj_id = ProjectId(UUID(int=2))
        self._req = 0
        with self.uow() as uow:
            scopes = uow.repo(ScopeRegistry)
            inst = ScopeId(UUID(int=99))
            scopes.create(inst, ScopeKind.INSTANCE, parent=None, workspace_id=None)
            scopes.create(ScopeId(self.ws_id), ScopeKind.WORKSPACE, parent=inst, workspace_id=self.ws_id)
            scopes.create(
                ScopeId(self.proj_id),
                ScopeKind.PROJECT,
                parent=ScopeId(self.ws_id),
                workspace_id=self.ws_id,
            )
            uow.commit()

    def _meta(self) -> RequestMeta:
        self._req += 1
        return RequestMeta(f"req_{self._req:026d}", Surface.TEST, None, self.clock.now())

    def uow(self, *, readonly: bool = False) -> Any:
        return self.backend.uow_factory()(self._meta(), readonly=readonly)

    def write(self, key: str, value: Any) -> None:
        self.bus.dispatch(
            SetValue(
                scope=SetValueDefsScopeRef(level=cast("Any", "workspace"), scope_id=self.ws_id),
                key=key,
                value=value,
                reason="test",
                confirmed=True,
            ),
            actor=self.actor,
            meta=self._meta(),
        )

    def effective_subscriptions(self) -> Any:
        with self.uow(readonly=True) as uow:
            cfg = self.loader.effective(
                uow.repo(ConfigStore), uow.repo(ScopeTree), ScopeRef(ScopeKind.WORKSPACE, ScopeId(self.ws_id))
            )
            return cfg.get("hooks.subscriptions")


def _valid_webhook_raw(
    event_type: str = HOOKABLE_EVENT, *, url: str = "https://ci.example.com/skm"
) -> dict[str, Any]:
    return {
        "class": "observation",
        "kind": "webhook",
        "execution_location": "control_plane",
        "event_types": [event_type],
        "target": {
            "url": url,
            "secret": "secret://env/SKM_CI_SECRET",
            "headers": {"X-Team": "platform"},
        },
        "timeout_ms": 5000,
        "retry": {"max_attempts": 4, "backoff": {"initial_ms": 1000, "factor": 2.0, "max_ms": 60000}},
        "failure_policy": "retry",
        "enabled": True,
    }


def test_real_settings_registry_accepts_valid_webhook_command_and_sink_subscriptions() -> None:
    harness = _WriteHarness(sink_ids=("jira-sink",))
    payload = {
        "ci-webhook": _valid_webhook_raw(HOOKABLE_PLAN_EVENT),
        "host-guard": {
            "class": "enforcement",
            "kind": "command",
            "execution_location": "host",
            "event_types": ["client:pre_shell"],
            "target": {
                "argv": ["/opt/skm/scripts/guard.py"],
                "cwd": "checkout",
                "env_allow": ["CI"],
                "env_refs": {"API_TOKEN": "secret://env/SKM_GUARD_TOKEN"},
            },
            "timeout_ms": 1200,
            "failure_policy": "deny",
        },
        "jira-audit": {
            "class": "observation",
            "kind": "event_sink",
            "execution_location": "control_plane",
            "event_types": ["urn:skm:policy:event:*"],
            "target": {
                "sink_id": "jira-sink",
                "config": {"token": "secret://env/JIRA_TOKEN", "project": "OPS"},
            },
            "failure_policy": "warn",
        },
    }
    harness.write("hooks.subscriptions", payload)
    stored = harness.effective_subscriptions()
    assert isinstance(stored, dict)
    assert set(stored) == {"ci-webhook", "host-guard", "jira-audit"}


@pytest.mark.parametrize(
    ("case_name", "bad_entry"),
    [
        (
            "host_command_on_domain_event",
            {
                "class": "enforcement",
                "kind": "command",
                "execution_location": "host",
                "event_types": [HOOKABLE_EVENT],
                "target": {"argv": ["/opt/skm/guard.py"], "cwd": "checkout"},
                "failure_policy": "deny",
            },
        ),
        ("client_event_on_control_plane", {**_valid_webhook_raw(), "event_types": ["client:pre_shell"]}),
        (
            "enforcement_on_control_plane",
            {**_valid_webhook_raw(), "class": "enforcement", "failure_policy": "deny"},
        ),
        ("unknown_hookable_event_type", _valid_webhook_raw("urn:skm:unknown:event:missing:v1")),
        ("malformed_webhook_url", _valid_webhook_raw(url="https://[bad")),
        (
            "non_hookable_recursion_event_hook_delivery_failed",
            _valid_webhook_raw("urn:skm:integrations:event:hook-delivery-failed:v1"),
        ),
        (
            "raw_literal_webhook_secret",
            {
                **_valid_webhook_raw(),
                "target": {"url": "https://ci.example.com/skm", "secret": "plain-secret-value"},
            },
        ),
        (
            "unregistered_event_sink",
            {
                "class": "observation",
                "kind": "event_sink",
                "execution_location": "control_plane",
                "event_types": [HOOKABLE_EVENT],
                "target": {"sink_id": "missing-sink", "config": {}},
                "failure_policy": "warn",
            },
        ),
        (
            "reserved_webhook_sink_id",
            {
                "class": "observation",
                "kind": "event_sink",
                "execution_location": "control_plane",
                "event_types": [HOOKABLE_EVENT],
                "target": {"sink_id": "webhook", "config": {}},
                "failure_policy": "warn",
            },
        ),
        (
            "retry_max_attempts_out_of_bounds",
            {
                **_valid_webhook_raw(),
                "retry": {
                    "max_attempts": 99,
                    "backoff": {"initial_ms": 1000, "factor": 2.0, "max_ms": 60000},
                },
            },
        ),
        (
            "event_types_exceeds_32_patterns",
            {
                **_valid_webhook_raw(),
                "event_types": [f"urn:skm:policy:event:intent-{i}:v1" for i in range(33)],
            },
        ),
    ],
)
def test_invalid_subscription_write_is_completely_rejected_without_partial_persistence(
    case_name: str,
    bad_entry: dict[str, Any],
) -> None:
    harness = _WriteHarness(sink_ids=("jira-sink",))
    gen_before = harness.backend.committed.core.config_generation
    events_before = len(harness.backend.committed.core.events)
    combined = {"valid-sub": _valid_webhook_raw(), "broken-sub": bad_entry}
    with pytest.raises(ValidationFailed) as exc_info:
        harness.write("hooks.subscriptions", combined)
    assert exc_info.value.code is ErrorCode.CONFIG_INVALID, case_name
    assert harness.effective_subscriptions() == {}
    assert harness.backend.committed.core.config_generation == gen_before
    assert len(harness.backend.committed.core.events) == events_before
