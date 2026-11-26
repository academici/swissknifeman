"""Platform catalog ownership, value contracts, views and plugins.subsets."""

from functools import cache

import pytest

from skm.bootstrap.modules import MODULE_CATALOG
from skm.kernel.json_types import JsonValue
from skm.platform.config.generated.settings import (
    ApiDocument,
    BackgroundSettings,
    LoggingDocument,
    StorageSettings,
)
from skm.platform.config.keys import MISSING, Chain, Level, MergeStrategy, Reload
from skm.platform.config.registry import SettingsRegistry
from skm.platform.config.validators import SECTION_URNS, VALIDATORS, VIEWS
from skm.platform.schema.registry import SchemaRegistry

PLATFORM_KEYS = {
    "modules": "knowledge.enabled learning.enabled exports.enabled",
    "plugins": "allowed required control_plane_allowed override_builtin",
    "logging": (
        "level format file component_levels redact_patterns retention_days detail file_max_bytes file_backups"
    ),
    "storage": (
        "statement_timeout_ms lock_timeout_ms idle_in_transaction_timeout_ms "
        "retry.max_attempts retry.backoff_ms idempotency.ttl_hours"
    ),
    "events": (
        "delivery.max_attempts delivery.timeout_seconds delivery.backoff_seconds "
        "delivery.backoff_max_seconds delivery.visibility_timeout_seconds outbox.delivered_retention_hours"
    ),
    "background": (
        "outbox_relay.interval_ms outbox_relay.batch_size outbox_relay.max_lag_seconds janitor.interval_ms "
        "scheduler.interval_ms lease_sweeper.interval_ms timeout_enforcer.interval_ms "
        "stall_detector.interval_ms autopilot.interval_ms memory_expirer.interval_ms"
    ),
    "api": (
        "bind allowed_hosts min_client_version max_response_bytes schema_check_interval_seconds "
        "proxy.trusted "
        "threadpool.size shutdown.grace_seconds cors.origins limits.max_body_bytes client.timeout_seconds "
        "page.default_limit page.max_limit sse.heartbeat_seconds sse.poll_ms sse.batch_size "
        "sse.max_streams_per_token sse.queue_size live.batch_ms live.buffer_events mcp.max_response_tokens "
        "worker.max_long_polls"
    ),
    "ui": "theme locale time_display open_browser stale_after_seconds plans.tree_depth runs.live_stream",
    "ecosystems": "ids hosts deny_patterns",
}


@cache
def platform_registry() -> SettingsRegistry:
    return SettingsRegistry.build(
        SchemaRegistry.load_default(),
        SECTION_URNS,
        views=VIEWS,
        validators=VALIDATORS,
        known_permissions=frozenset(),
    )


def test_all_platform_sections_have_one_owner_and_exact_catalog_keys() -> None:
    registry = platform_registry()
    assert set(VIEWS) == set(PLATFORM_KEYS)
    assert {info.schema_urn for info in registry.sections()} == set(SECTION_URNS)
    assert set(VALIDATORS) == {"plugins.subsets"}
    for section, names in PLATFORM_KEYS.items():
        info = registry.section(section)
        assert info.owner == "platform"
        assert info.view is VIEWS[section]
        assert set(info.keys) == {f"{section}.{name}" for name in names.split()}
        assert all(spec.owner == "platform" for spec in registry.keys(section=section))


def test_modules_flags_only_cover_optional_modules() -> None:
    registry = platform_registry()
    optional = {entry.id for entry in MODULE_CATALOG if entry.optional}
    assert {spec.key for spec in registry.keys(section="modules")} == {
        f"modules.{module}.enabled" for module in optional
    }
    for spec in registry.keys(section="modules"):
        assert spec.default is True
        assert spec.levels == {Level.INSTANCE}
        assert spec.reload is Reload.RESTART
        assert spec.merge is MergeStrategy.REPLACE
        assert not spec.pack
        assert not spec.override


def test_storage_has_no_pool_or_bootstrap_credentials() -> None:
    registry = platform_registry()
    assert not registry.section("storage").validators
    assert "bootstrap.pool_capacity" not in VALIDATORS
    for key in (
        "storage.pool.min_size",
        "storage.pool.max_size",
        "storage.pool.timeout_seconds",
        "database.url",
        "api.credential",
        "secrets.token_pepper",
    ):
        assert registry.find(key) is None
    for spec in registry.keys(section="storage"):
        assert spec.chain is Chain.WORK
        assert spec.levels == {Level.INSTANCE}
        assert spec.reload is Reload.LIVE


def test_platform_security_and_host_metadata_match_catalog() -> None:
    registry = platform_registry()
    for spec in registry.keys(section="plugins"):
        assert spec.levels == {Level.INSTANCE}
        assert spec.reload is Reload.RESTART
        assert not spec.override
        assert not spec.pack
        assert spec.lockable
        assert spec.confirm is (spec.key != "plugins.required")
        if spec.key != "plugins.required":
            assert spec.merge is MergeStrategy.NARROW
            assert spec.narrow is not None
            assert spec.narrow.direction == "intersect"
    assert registry.spec("plugins.required").merge is MergeStrategy.REPLACE
    for spec in registry.keys(section="background"):
        assert spec.chain is Chain.HOST
        assert spec.levels == {Level.INSTANCE, Level.HOST}
        assert not spec.portable
        assert not spec.pack
        assert not spec.override
        assert (spec.reload is Reload.RESTART) is spec.key.endswith("interval_ms")
    assert registry.spec("api.cors.origins").merge is MergeStrategy.UNION
    assert registry.spec("logging.redact_patterns").merge is MergeStrategy.APPEND_UNIQUE
    assert registry.spec("logging.component_levels").merge is MergeStrategy.DEEP_MERGE
    log_file = registry.spec("logging.file")
    assert log_file.default is MISSING
    assert log_file.nullable
    assert log_file.path
    assert log_file.chain is Chain.HOST
    assert not log_file.portable


@pytest.mark.parametrize(
    ("allowed", "required", "control", "ok"),
    [
        ([], [], [], True),
        (["acme.kiro", "tools"], [], [], True),
        (["acme.kiro", "tools"], ["tools"], ["acme.kiro"], True),
        (["tools", "acme.kiro"], ["acme.kiro", "tools"], ["tools", "acme.kiro"], True),
        ([], ["tools"], [], False),
        ([], [], ["tools"], False),
        (["tools"], ["other"], [], False),
        (["tools"], [], ["other"], False),
        (["tools"], ["tools"], ["other"], False),
        (["tools"], ["other"], ["tools"], False),
    ],
)
def test_plugins_subsets(allowed: list[str], required: list[str], control: list[str], ok: bool) -> None:
    values: dict[str, JsonValue] = {
        "plugins.allowed": list(allowed),
        "plugins.required": list(required),
        "plugins.control_plane_allowed": list(control),
    }
    original = {key: list(value) for key, value in values.items() if isinstance(value, list)}
    validator = platform_registry().validator("plugins.subsets")
    message = validator(values)
    assert (message is None) is ok
    assert values == original
    if not ok:
        assert message is not None
        assert "plugins.allowed" in message


@pytest.mark.parametrize("key", ["allowed", "required", "control_plane_allowed"])
@pytest.mark.parametrize(
    ("value", "ok"),
    [
        ([], True),
        (["tools", "acme.kiro", "my_plugin.v2"], True),
        (["acme.kiro", "acme.kiro"], False),
        (["Acme.kiro"], False),
        (["acme-kiro"], False),
        (["acme.kiro.extra"], False),
        (["acme/kiro"], False),
        (["acme\\.kiro"], False),
        (["acme\\xkiro"], False),
    ],
)
def test_plugin_id_schema(key: str, value: JsonValue, ok: bool) -> None:
    assert (not platform_registry().value_issues(f"plugins.{key}", value)) is ok


@pytest.mark.parametrize(
    ("key", "good", "bad"),
    [
        ("api.bind", "[::1]:8765", "::1:8765"),
        ("api.bind", "localhost:8765", "localhost"),
        ("api.allowed_hosts", ["[::1]:8765", "localhost", "*.example.test"], ["https://example.test"]),
        ("api.min_client_version", "2.0.0", "2x0x0"),
        ("api.min_client_version", "2.0", "2\\.0\\.0"),
    ],
)
def test_api_patterns_follow_address_and_version_contracts(key: str, good: JsonValue, bad: JsonValue) -> None:
    registry = platform_registry()
    assert not registry.value_issues(key, good)
    assert registry.value_issues(key, bad)


def test_numeric_platform_boundaries_and_units() -> None:
    registry = platform_registry()
    for spec in registry.keys(chain=None):
        if spec.value_type != "integer":
            continue
        lower, upper = spec.value_schema["minimum"], spec.value_schema["maximum"]
        assert isinstance(lower, int)
        assert isinstance(upper, int)
        assert not registry.value_issues(spec.key, lower)
        assert not registry.value_issues(spec.key, upper)
        assert registry.value_issues(spec.key, lower - 1)
        assert registry.value_issues(spec.key, upper + 1)
        assert registry.value_issues(spec.key, True)
    defaults = {spec.key: spec.default for spec in registry.keys(chain=None) if spec.default is not MISSING}
    storage = StorageSettings.from_settings(defaults)
    background = BackgroundSettings.from_settings(defaults)
    api = ApiDocument.from_settings(defaults)
    logging = LoggingDocument.from_settings(defaults)
    assert storage.statement_timeout_ms == 30000
    assert storage.retry.backoff_ms == 50
    assert storage.idempotency.ttl_hours == 72
    assert background.outbox_relay.interval_ms == 500
    assert background.memory_expirer.interval_ms == 600000
    assert api.sse.poll_ms == 2000
    assert api.client.timeout_seconds == 30
    assert api.limits.max_body_bytes == 1048576
    assert logging.file_max_bytes == 52428800
    assert logging.file is None
