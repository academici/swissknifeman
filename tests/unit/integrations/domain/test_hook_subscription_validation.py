"""Hook subscription parser, §4.10 matrix validator (integrations §5.8.1) and the registry callback."""

import copy
from typing import Any, cast

import pytest

from skm.kernel.json_types import JsonValue
from skm.modules.integrations.domain.hook_subscriptions import (
    CommandTarget,
    EventSinkTarget,
    ExecutionLocation,
    FailurePolicy,
    HookSubscription,
    SubscriptionKind,
    WebhookTarget,
    parse_subscriptions,
    subscription_digest,
    subscription_json,
    validate_subscription,
)
from skm.modules.integrations.settings import validators_for

RUN_FINISHED = "urn:skm:execution:event:run-finished:v1"
PLAN_DONE = "urn:skm:planning:event:plan-completed:v1"
HOOKABLE = frozenset({RUN_FINISHED, PLAN_DONE})
SINKS = frozenset({"slack"})
SECRET = "secret://env/HOOK_SECRET"

WEBHOOK = {"url": "https://example.test/hook", "secret": SECRET}
COMMAND = {"argv": ["/usr/bin/audit", "--json"]}
SINK = {"sink_id": "slack", "config": {"channel": "ops"}}


def entry(
    cls: str, location: str, kind: str, events: list[str], target: dict[str, Any], **extra: Any
) -> dict[str, Any]:
    return {
        "class": cls,
        "kind": kind,
        "execution_location": location,
        "event_types": events,
        "target": copy.deepcopy(target),
        **extra,
    }


# one valid row of the matrix per (class, location); the first policy is the default
VALID = {
    "enforcement-host": entry(
        "enforcement", "host", "command", ["client:pre_shell", "client:permission_request"], COMMAND
    ),
    "workflow-webhook": entry("workflow", "control_plane", "webhook", [RUN_FINISHED], WEBHOOK),
    "workflow-sink": entry("workflow", "control_plane", "event_sink", ["urn:skm:execution:event:*"], SINK),
    "workflow-host": entry("workflow", "host", "command", ["client:session_start", "client:stop"], COMMAND),
    "observation-webhook": entry("observation", "control_plane", "webhook", [PLAN_DONE], WEBHOOK),
    "observation-host": entry("observation", "host", "command", ["client:*"], COMMAND),
}


def parsed(config: dict[str, Any], sub_id: str = "s1") -> HookSubscription:
    subs, violations = parse_subscriptions({sub_id: config}, {})
    assert violations == (), violations
    return subs[0]


def reasons(config: dict[str, Any], **kwargs: Any) -> set[str]:
    sub = parsed(config)
    found = validate_subscription(
        sub, hookable_types=kwargs.get("hookable", HOOKABLE), sink_ids=kwargs.get("sinks", SINKS)
    )
    assert all(item.key == "hooks.subscriptions.s1" for item in found)
    return {item.reason for item in found}


def changed(name: str, **changes: Any) -> dict[str, Any]:
    config = copy.deepcopy(VALID[name])
    for field, value in changes.items():
        config[field] = value
    return config


@pytest.mark.parametrize("name", sorted(VALID))
def test_every_matrix_row_has_a_valid_combination(name: str) -> None:
    assert reasons(VALID[name]) == set()


def test_defaults_follow_the_row() -> None:
    cases = {
        "enforcement-host": (1000, FailurePolicy.DENY),
        "workflow-webhook": (5000, FailurePolicy.DENY),
        "workflow-host": (1000, FailurePolicy.WARN),
        "observation-webhook": (5000, FailurePolicy.RETRY),
        "observation-host": (1000, FailurePolicy.WARN),
    }
    for name, (timeout, policy) in cases.items():
        sub = parsed(VALID[name])
        assert (sub.timeout_ms, sub.failure_policy, sub.enabled) == (timeout, policy, True), name
        assert (sub.retry.max_attempts, sub.retry.backoff.initial_ms) == (5, 1000)
        assert (sub.retry.backoff.factor, sub.retry.backoff.max_ms) == (2.0, 300_000)
        assert sub.defined_at == "instance"
        assert sub.digest.startswith("sha256:")


def test_parse_reads_targets_and_provenance() -> None:
    config = {
        "web": changed(
            "workflow-webhook",
            target={**WEBHOOK, "previous_secret": "secret://env/OLD", "headers": {"X-Team": "a"}},
        ),
        "cmd": changed(
            "workflow-host",
            target={"argv": ["x"], "cwd": "state_dir", "env_allow": ["HOME"], "env_refs": {"TOKEN": SECRET}},
        ),
        "snk": VALID["workflow-sink"],
    }
    subs, violations = parse_subscriptions(config, {"web": "workspace", "cmd": "project"})
    assert violations == ()
    assert [sub.id for sub in subs] == ["cmd", "snk", "web"]
    cmd, snk, web = subs
    assert isinstance(web.target, WebhookTarget)
    assert (web.target.previous_secret, dict(web.target.headers), web.defined_at) == (
        "secret://env/OLD",
        {"X-Team": "a"},
        "workspace",
    )
    assert isinstance(cmd.target, CommandTarget)
    assert (cmd.target.cwd, cmd.target.env_allow, dict(cmd.target.env_refs), cmd.defined_at) == (
        "state_dir",
        ("HOME",),
        {"TOKEN": SECRET},
        "project",
    )
    assert isinstance(snk.target, EventSinkTarget)
    assert (snk.kind, snk.execution_location, snk.target.sink_id) == (
        SubscriptionKind.EVENT_SINK,
        ExecutionLocation.CONTROL_PLANE,
        "slack",
    )


# one invalid value per matrix column
@pytest.mark.parametrize(
    ("name", "changes", "reason"),
    [
        ("enforcement-host", {"execution_location": "control_plane"}, "class_location_not_allowed"),
        ("enforcement-host", {"kind": "webhook", "target": WEBHOOK}, "location_kind_mismatch"),
        ("workflow-webhook", {"kind": "command", "target": COMMAND}, "location_kind_mismatch"),
        ("workflow-host", {"kind": "webhook", "target": WEBHOOK}, "kind_not_allowed"),
        ("enforcement-host", {"event_types": ["client:session_start"]}, "event_type_not_allowed"),
        ("enforcement-host", {"event_types": ["client:*"]}, "event_type_not_allowed"),
        ("workflow-host", {"event_types": ["client:pre_shell"]}, "event_type_not_allowed"),
        ("enforcement-host", {"failure_policy": "retry"}, "failure_policy_not_allowed"),
        ("workflow-host", {"failure_policy": "deny"}, "failure_policy_not_allowed"),
        ("workflow-host", {"failure_policy": "retry"}, "failure_policy_not_allowed"),
        ("observation-webhook", {"failure_policy": "deny"}, "failure_policy_not_allowed"),
        ("enforcement-host", {"timeout_ms": 49}, "timeout_out_of_range"),
        ("enforcement-host", {"timeout_ms": 10_001}, "timeout_out_of_range"),
        ("workflow-webhook", {"timeout_ms": 99}, "timeout_out_of_range"),
        ("workflow-webhook", {"timeout_ms": 30_001}, "timeout_out_of_range"),
        ("observation-host", {"timeout_ms": 10_001}, "timeout_out_of_range"),
    ],
)
def test_one_invalid_value_per_matrix_column(name: str, changes: dict[str, Any], reason: str) -> None:
    assert reason in reasons(changed(name, **changes))


@pytest.mark.parametrize(
    ("name", "changes"),
    [
        ("enforcement-host", {"timeout_ms": 50, "failure_policy": "warn"}),
        ("enforcement-host", {"timeout_ms": 10_000}),
        ("workflow-webhook", {"timeout_ms": 100, "failure_policy": "retry"}),
        ("workflow-webhook", {"timeout_ms": 30_000, "failure_policy": "warn"}),
        ("workflow-host", {"failure_policy": "warn"}),
        ("observation-webhook", {"failure_policy": "warn"}),
        ("observation-host", {"failure_policy": "retry"}),
    ],
)
def test_boundaries_and_alternate_policies_are_accepted(name: str, changes: dict[str, Any]) -> None:
    assert reasons(changed(name, **changes)) == set()


def test_event_type_patterns() -> None:
    web = "workflow-webhook"
    assert reasons(changed(web, event_types=["urn:skm:execution:event:unknown:v1"])) == {"unknown_event_type"}
    assert reasons(changed(web, event_types=["urn:skm:billing:event:*"])) == {"unknown_event_type"}
    assert reasons(changed(web, event_types=["urn:skm:execution:event:*", PLAN_DONE])) == set()
    for text in (
        "execution.run-finished",
        "urn:skm:execution:event:run-*",
        "*",
        "urn:skm:execution:event:*:v1",
    ):
        assert reasons(changed(web, event_types=[text])) == {"invalid_event_pattern"}, text
    assert reasons(changed(web, event_types=["client:pre_shell"])) == {"client_event_requires_host"}
    assert reasons(changed(web, event_types=["client:*"])) == {"client_event_requires_host"}
    host = "observation-host"
    assert reasons(changed(host, event_types=["client:not_a_kind"])) == {"unknown_client_event"}
    assert reasons(changed(host, event_types=[RUN_FINISHED])) == {"event_type_not_allowed"}
    assert reasons(changed(host, event_types=["client:post_shell", "client:permission_request"])) == set()
    assert reasons(changed(web, event_types=[RUN_FINISHED]), hookable=frozenset()) == {"unknown_event_type"}
    many = [f"urn:skm:execution:event:e{n}:v1" for n in range(33)]
    assert "event_types_count" in reasons(changed(web, event_types=many), hookable=frozenset(many))
    assert "event_types_count" in reasons(changed(web, event_types=[]))
    assert "event_types_count" not in reasons(changed(web, event_types=many[:32]), hookable=frozenset(many))


def test_event_sink_rules() -> None:
    sink = "workflow-sink"
    assert reasons(changed(sink, target={"sink_id": "pagerduty", "config": {}})) == {"sink_not_registered"}
    assert reasons(
        changed(sink, target={"sink_id": "webhook", "config": {}}), sinks=frozenset({"webhook"})
    ) == {"sink_id_webhook"}
    assert reasons(changed(sink, target={"sink_id": "slack", "config": {}}), sinks=frozenset()) == {
        "sink_not_registered"
    }


def test_webhook_target_rules() -> None:
    web = "workflow-webhook"

    def with_target(**fields: Any) -> set[str]:
        return reasons(changed(web, target={**WEBHOOK, **fields}))

    assert with_target(url="http://example.test/h") == {"webhook_url_scheme"}
    assert with_target(url="ftp://example.test/h") == {"webhook_url_scheme"}
    assert with_target(url="https://") == {"webhook_url_scheme"}
    assert (
        with_target(url="http://127.0.0.1:8080/h") == set()
    )  # loopback; the flag is checked where delivery happens
    assert with_target(url="http://localhost/h") == set()
    assert with_target(url="http://[::1]:9/h") == set()
    assert with_target(url="http://localhost.evil.test/h") == {"webhook_url_scheme"}
    assert with_target(url="http://user@evil.test/h") == {"webhook_url_scheme"}
    assert with_target(headers={f"X-H{n}": "v" for n in range(17)}) == {"headers_invalid"}
    assert with_target(headers={f"X-H{n}": "v" for n in range(16)}) == set()
    for name in ("Authorization", "host", "Content-Type", "content-length", "SKM-Signature", "Bad Name", ""):
        assert with_target(headers={name: "v"}) == {"headers_invalid"}, name


def test_command_target_rules() -> None:
    cmd = "workflow-host"

    def with_target(**fields: Any) -> set[str]:
        return reasons(changed(cmd, target={**COMMAND, **fields}))

    assert with_target(argv=[]) == {"argv_invalid"}
    assert with_target(argv=[""]) == {"argv_invalid"}
    assert with_target(argv=["x"] * 65) == {"argv_invalid"}
    assert with_target(argv=["x"] * 64) == set()
    assert with_target(env_allow=[f"V{n}" for n in range(33)]) == {"env_invalid"}
    assert with_target(env_allow=["1BAD"]) == {"env_invalid"}
    assert with_target(env_refs={"bad-name": SECRET}) == {"env_invalid"}
    assert with_target(env_allow=["HOME"], env_refs={"TOKEN": SECRET}, cwd="state_dir") == set()


HOST_ROWS = ["enforcement-host", "workflow-host", "observation-host"]


@pytest.mark.parametrize("name", HOST_ROWS)
@pytest.mark.parametrize(
    ("argv", "valid"),
    [
        (["./hooks/check"], False),
        (["hooks/check"], False),
        (["../check"], False),
        ([""], False),
        ([], False),
        (["x"] * 65, False),
        (["/usr/bin/check"], True),
        (["check"], True),
        (["/usr/bin/printf", "%s", ""], True),
        (["check", ""], True),
        (["x"] * 64, True),
    ],
)
def test_host_command_executable_and_empty_arguments(name: str, argv: list[str], valid: bool) -> None:
    config = changed(name, target={**COMMAND, "argv": argv})
    assert reasons(config) == (set() if valid else {"argv_invalid"})
    callback = validators_for(hookable_types=HOOKABLE, sink_ids=SINKS)["integrations.hook_subscriptions"]
    result = callback({"hooks.subscriptions": {"s1": config}})
    assert (result is None) == valid


def test_retry_ranges() -> None:
    web = "workflow-webhook"

    def with_retry(
        attempts: int = 5, initial: int = 1000, factor: float = 2.0, maximum: int = 300_000
    ) -> set[str]:
        retry = {
            "max_attempts": attempts,
            "backoff": {"initial_ms": initial, "factor": factor, "max_ms": maximum},
        }
        return reasons(changed(web, retry=retry))

    assert with_retry() == set()
    assert with_retry(attempts=1, initial=100, factor=1.0, maximum=100) == set()
    assert with_retry(attempts=20, initial=600_000, factor=10, maximum=86_400_000) == set()
    for kwargs in cast(
        "list[dict[str, Any]]",
        [
            {"attempts": 0},
            {"attempts": 21},
            {"initial": 99},
            {"initial": 600_001, "maximum": 700_000},
            {"factor": 0.9},
            {"factor": 10.1},
            {"maximum": 999},
            {"maximum": 86_400_001},
        ],
    ):
        assert with_retry(**kwargs) == {"retry_out_of_range"}, kwargs


@pytest.mark.parametrize(
    ("config", "reason"),
    [
        (
            changed("workflow-webhook", target={"url": "https://x.test/", "secret": "literal-secret"}),
            "secret_ref_required",
        ),
        (changed("workflow-webhook", target={"url": "https://x.test/"}), "secret_ref_required"),
        (changed("workflow-webhook", target={**WEBHOOK, "previous_secret": "plain"}), "secret_ref_required"),
        (changed("workflow-host", target={**COMMAND, "env_refs": {"TOKEN": "plain"}}), "secret_ref_required"),
        (changed("workflow-webhook", target={**WEBHOOK, "headers": {"X": 1}}), "invalid_shape"),
        (changed("workflow-webhook", target={**WEBHOOK, "extra": 1}), "invalid_shape"),
        (changed("workflow-host", target={"argv": "run"}), "invalid_shape"),
        (changed("workflow-host", target={}), "invalid_shape"),
        (changed("workflow-host", target={**COMMAND, "cwd": "elsewhere"}), "invalid_cwd"),
        (changed("workflow-sink", target={"sink_id": 3}), "invalid_shape"),
        (changed("workflow-webhook", surprise=1), "invalid_shape"),
        (changed("workflow-webhook", enabled="yes"), "invalid_shape"),
        (changed("workflow-webhook", timeout_ms="5"), "invalid_shape"),
        (changed("workflow-webhook", timeout_ms=True), "invalid_shape"),
        (changed("workflow-webhook", event_types="a"), "invalid_shape"),
        (changed("workflow-webhook", retry={"max_attempts": "5"}), "invalid_shape"),
        (changed("workflow-webhook", retry={"nope": 1}), "invalid_shape"),
        (changed("workflow-webhook", **{"class": "other"}), "invalid_class"),
        (changed("workflow-webhook", kind="smoke"), "invalid_kind"),
        (changed("workflow-webhook", execution_location="moon"), "invalid_execution_location"),
        (changed("workflow-webhook", failure_policy="ignore"), "invalid_failure_policy"),
        ("not an object", "invalid_shape"),
    ],
)
def test_malformed_entries_are_reported_and_left_out(config: Any, reason: str) -> None:
    subs, violations = parse_subscriptions({"s1": config, "ok": VALID["workflow-webhook"]}, {})
    assert [sub.id for sub in subs] == ["ok"]
    assert [(v.key, v.reason) for v in violations] == [("hooks.subscriptions.s1", reason)]


def test_secret_literal_never_appears_in_the_message() -> None:
    _, violations = parse_subscriptions(
        {"s1": changed("workflow-webhook", target={"url": "https://x.test/", "secret": "hunter2-literal"})},
        {},
    )
    assert "hunter2-literal" not in violations[0].message


@pytest.mark.parametrize("bad_id", ["", "Upper", "-lead", "a" * 65, "has space", "ünï"])
def test_subscription_id_pattern(bad_id: str) -> None:
    subs, violations = parse_subscriptions({bad_id: VALID["workflow-webhook"]}, {})
    assert subs == ()
    assert [v.reason for v in violations] == ["invalid_id"]


def test_good_ids_are_accepted() -> None:
    ids = {"a", "0", "a.b-c_d", "a" * 64}
    subs, violations = parse_subscriptions(dict.fromkeys(ids, VALID["workflow-webhook"]), {})
    assert violations == ()
    assert {sub.id for sub in subs} == ids


def test_all_defects_of_one_subscription_are_listed_together() -> None:
    config = changed("enforcement-host", timeout_ms=5, failure_policy="retry", event_types=["client:stop"])
    assert reasons(config) == {"timeout_out_of_range", "failure_policy_not_allowed", "event_type_not_allowed"}


def test_digest_ignores_enabled_and_tracks_everything_else() -> None:
    base = parsed(VALID["workflow-webhook"])
    off = parsed(changed("workflow-webhook", enabled=False))
    assert base.digest == off.digest
    assert subscription_digest(subscription_json(base)) == base.digest
    argv = parsed(changed("workflow-host", target={"argv": ["a"]}))
    argv2 = parsed(changed("workflow-host", target={"argv": ["b"]}))
    assert argv.digest != argv2.digest
    assert parsed(changed("workflow-webhook", timeout_ms=6000)).digest != base.digest
    other_ref = parsed(changed("workflow-webhook", target={**WEBHOOK, "secret": "secret://env/OTHER"}))
    assert other_ref.digest != base.digest
    explicit = parsed(changed("workflow-webhook", timeout_ms=5000, failure_policy="deny"))
    assert explicit.digest == base.digest  # defaults are part of the normalized form
    assert "enabled" in subscription_json(base)


def test_registry_callback_reports_every_problem_and_closes_over_its_sets() -> None:
    callback = validators_for(hookable_types=HOOKABLE, sink_ids=SINKS)["integrations.hook_subscriptions"]
    assert callback({"hooks.subscriptions": {}}) is None
    assert callback({"hooks.subscriptions": None}) is None
    assert callback({"hooks.subscriptions": {name: VALID[name] for name in VALID}}) is None
    message = callback(
        {
            "hooks.subscriptions": {
                "bad-timeout": changed("enforcement-host", timeout_ms=1),
                "bad-secret": changed(
                    "workflow-webhook", target={"url": "https://x.test/", "secret": "plain"}
                ),
                "good": VALID["workflow-webhook"],
            }
        }
    )
    assert message is not None
    assert "hooks.subscriptions.bad-timeout: timeout_out_of_range" in message
    assert "hooks.subscriptions.bad-secret: secret_ref_required" in message
    assert "good" not in message
    assert (
        callback(cast("dict[str, JsonValue]", {"hooks.subscriptions": [1]}))
        == "hooks.subscriptions must be an object"
    )
    # the sets are fixed when the callback is built: a different set gives a different verdict
    strict = validators_for(hookable_types=frozenset(), sink_ids=frozenset())[
        "integrations.hook_subscriptions"
    ]
    assert strict({"hooks.subscriptions": {"s": VALID["workflow-webhook"]}}) is not None
    assert strict({"hooks.subscriptions": {"s": VALID["workflow-sink"]}}) is not None
    assert strict({"hooks.subscriptions": {"s": VALID["enforcement-host"]}}) is None


def test_validators_for_adds_the_hook_callback_to_the_static_ones() -> None:
    from skm.modules.integrations.settings import VALIDATORS

    full = validators_for(hookable_types=(), sink_ids=())
    assert set(full) == {"integrations.budget_order", "integrations.hook_subscriptions"}
    assert set(VALIDATORS) == {"integrations.budget_order"}  # no permissive default for the hook callback
