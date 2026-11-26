"""ComponentSpec accepts only a non-empty key and a callable factory."""

from typing import cast

import pytest

from skm.plugin_api import ComponentKind, ComponentSpec, Side


def _factory(_context: object) -> object:
    return object()


def test_component_spec_rejects_an_empty_key() -> None:
    with pytest.raises(ValueError, match="a component key is a non-empty string"):
        ComponentSpec(kind=ComponentKind.RUNTIME, key="", side=Side.HOST, factory=_factory)


def test_component_spec_rejects_a_non_callable_factory() -> None:
    with pytest.raises(TypeError, match="a component factory must be callable"):
        ComponentSpec(kind=ComponentKind.RUNTIME, key="acme.run", side=Side.HOST, factory="not-a-factory")  # type: ignore[arg-type]


def test_component_spec_coerces_kind_side_and_schemas() -> None:
    # Strings and a list are the published constructor contract; the fields stay typed as enums/tuple.
    spec = ComponentSpec(
        cast(ComponentKind, "runtime"),
        "acme.run",
        cast(Side, "host"),
        _factory,
        schemas=cast(tuple[str, ...], ["schema.json"]),
    )
    assert spec.kind is ComponentKind.RUNTIME
    assert spec.side is Side.HOST
    assert spec.schemas == ("schema.json",)
    assert spec.factory is _factory
