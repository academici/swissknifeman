"""Unit tests for ``skm.modules.extensions.domain.requires`` (extensions §4.11)."""

from skm.modules.extensions.domain.requires import (
    RequiresDiagnostic,
    RequiresNode,
    resolve_requires,
)


def test_resolve_requires_bfs_order_and_cycle_safety() -> None:
    nodes = {
        "a": RequiresNode(key="a", requires=("b", "c")),
        "b": RequiresNode(key="b", requires=("d", "a")),  # cycle back to "a"
        "c": RequiresNode(key="c", requires=("d", "e")),
        "d": RequiresNode(key="d", requires=()),
        "e": RequiresNode(key="e", requires=()),
    }
    resolved, updated_selected, diags = resolve_requires(
        [("a", "root")],
        nodes.get,
        frozenset(),
    )
    assert [(node.key, req) for node, req in resolved] == [
        ("a", "root"),
        ("b", "a"),
        ("c", "a"),
        ("d", "b"),
        ("e", "c"),
    ]
    assert updated_selected == frozenset({"a", "b", "c", "d", "e"})
    assert diags == ()


def test_resolve_requires_skips_already_selected() -> None:
    nodes = {
        "a": RequiresNode(key="a", requires=("b",)),
        "b": RequiresNode(key="b", requires=("c",)),
        "c": RequiresNode(key="c", requires=()),
    }
    resolved, updated_selected, diags = resolve_requires(
        [("a", "root")],
        nodes.get,
        frozenset({"b"}),
    )
    assert [(node.key, req) for node, req in resolved] == [("a", "root")]
    assert updated_selected == frozenset({"a", "b"})
    assert diags == ()


def test_resolve_requires_aggregates_unknown_and_excluded_diagnostics() -> None:
    nodes = {
        "a": RequiresNode(key="a", requires=("missing", "banned")),
        "b": RequiresNode(key="b", requires=("missing", "banned")),
        "banned": RequiresNode(
            key="banned", requires=("after-banned",), exclude_tokens=frozenset({"no-net"})
        ),
        "after-banned": RequiresNode(key="after-banned", requires=()),
    }
    resolved, updated_selected, diags = resolve_requires(
        [("a", "root"), ("b", "root")],
        nodes.get,
        frozenset(),
        frozenset({"no-net"}),
    )
    assert [(node.key, req) for node, req in resolved] == [("a", "root"), ("b", "root")]
    assert updated_selected == frozenset({"a", "b"})
    assert diags == (
        RequiresDiagnostic(
            code="SKILL_REQUIRED_EXCLUDED",
            required="banned",
            requesters=("a", "b"),
        ),
        RequiresDiagnostic(
            code="SKILL_REQUIRED_UNKNOWN",
            required="missing",
            requesters=("a", "b"),
        ),
    )
