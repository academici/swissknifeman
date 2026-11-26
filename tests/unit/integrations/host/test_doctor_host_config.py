"""Doctor reads its settings from the host chain, which never resolves work keys."""

import json
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest

from skm.bootstrap.composition import _settings_registry
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.integrations.host import doctor
from skm.platform.config.keys import MISSING, Chain, Level
from skm.platform.config.layers import Contribution, Layer, LayerRef
from skm.platform.config.resolver import resolve
from skm.platform.config.scopes import ScopeChain, ScopeRef
from skm.platform.schema.registry import SchemaRegistry


@pytest.fixture(scope="module")
def host_ctx() -> Any:
    registry = _settings_registry(SchemaRegistry.load_default())
    at = LayerRef(Level.DEFAULT)
    defaults = Layer(
        at,
        {
            spec.key: Contribution(at, "default", cast("Any", spec.default))
            for spec in registry.keys(chain=Chain.HOST)
            if spec.default is not MISSING
        },
    )
    chain = ScopeChain(Chain.HOST, (ScopeRef(Level.INSTANCE, UUID(int=1)), ScopeRef(Level.HOST, UUID(int=2))))
    stored = [
        Layer(LayerRef(scope.level, scope.scope_id, label=scope.level.value), {}) for scope in chain.scopes
    ]
    config = resolve(registry, chain, [defaults, *stored], generation=1, pack_generation=0)
    return SimpleNamespace(config=config)


def test_work_chain_subscriptions_read_as_absent_on_the_host_chain(host_ctx: Any) -> None:
    # Before the fix every real ``skm integrations doctor`` failed with CONFIG_SCOPE_NOT_ALLOWED here.
    assert doctor._config(host_ctx, "hooks.subscriptions", {}) == {}
    assert doctor._config(host_ctx, "hooks.host.trusted", {}) in ({}, None)


def test_unknown_keys_still_fail(host_ctx: Any) -> None:
    with pytest.raises(SkmError) as refused:
        doctor._config(host_ctx, "hooks.no_such_key", {})
    assert refused.value.code is ErrorCode.CONFIG_UNKNOWN_KEY


class _Fs:
    def __init__(self, raw: bytes | None) -> None:
        self.raw = raw

    def read(self, path: str) -> bytes | None:
        assert path == ".skm/project.json"
        return self.raw


@pytest.mark.parametrize(
    ("raw", "state"),
    [
        (None, "missing"),
        (b"not json", "mismatch"),
        (b"[]", "mismatch"),
        (b'{"project_id": "other"}', "mismatch"),
        (b'{"project_id": "p1"}', "mismatch"),
    ],
)
def test_the_checkout_marker_is_observed_against_the_project(raw: bytes | None, state: str) -> None:
    observed = doctor._checkout_marker(
        cast("Any", _Fs(raw)),
        cast("Any", UUID(int=1)),
        cast("Any", UUID(int=2)),
        UUID(int=3),
        "main",
        UUID(int=4),
    )
    assert observed == state


def test_doctor_compares_the_full_marker_to_the_binding() -> None:
    from skm.modules.workspace.domain.checkout_marker import MARKER_SCHEMA

    marker = {
        "schema": MARKER_SCHEMA,
        "project_id": str(UUID(int=1)),
        "workspace_id": str(UUID(int=2)),
        "repository_id": str(UUID(int=3)),
        "instance_id": str(UUID(int=4)),
        "mount_name": "main",
    }

    def observe() -> str:
        return doctor._checkout_marker(
            cast("Any", _Fs(json.dumps(marker).encode())),
            cast("Any", UUID(int=1)),
            cast("Any", UUID(int=2)),
            UUID(int=3),
            "main",
            UUID(int=4),
        )

    assert observe() == "present"
    marker["repository_id"] = str(UUID(int=5))
    assert observe() == "mismatch"
