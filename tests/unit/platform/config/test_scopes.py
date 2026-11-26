"""Stored scopes and scope chains (settings §B.1): a stored level always has a UUID scope."""

from dataclasses import FrozenInstanceError
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from skm.platform.config.keys import STORED_LEVELS, Chain, Level
from skm.platform.config.scopes import ScopeChain, ScopeRef


def ref(level: Level, label: str = "") -> ScopeRef:
    return ScopeRef(level, uuid4(), label)


def work(*levels: Level) -> ScopeChain:
    return ScopeChain(Chain.WORK, tuple(ref(level) for level in levels))


@pytest.mark.parametrize("level", sorted(STORED_LEVELS))
def test_every_stored_level_makes_a_scope_ref(level: Level) -> None:
    scope = ScopeRef(level, uuid4())
    assert scope.level is level
    assert isinstance(scope.scope_id, UUID)


@pytest.mark.parametrize(
    "level", [Level.DEFAULT, Level.PACK, Level.INVOCATION, Level.RUN_BUNDLE, Level.PROCESS]
)
def test_non_stored_levels_are_rejected(level: Level) -> None:
    with pytest.raises(ValueError, match="stored level"):
        ScopeRef(level, uuid4())


@pytest.mark.parametrize("bad", [None, "0191e2a4-7c3f-7b21-8a54-3f6d2c1b9e07", 7, b"x" * 16])
def test_stored_scope_id_is_always_a_uuid(bad: object) -> None:
    with pytest.raises(TypeError, match="UUID"):
        ScopeRef(Level.WORKSPACE, cast(Any, bad))


def test_unknown_level_is_rejected() -> None:
    with pytest.raises(ValueError, match="galaxy"):
        ScopeRef(cast(Any, "galaxy"), uuid4())


def test_level_string_is_coerced_and_label_is_not_part_of_equality() -> None:
    scope_id = uuid4()
    first = ScopeRef(cast(Any, "workspace"), scope_id, "workspace:personal")
    assert first.level is Level.WORKSPACE
    assert first == ScopeRef(Level.WORKSPACE, scope_id, "renamed")
    assert hash(first) == hash(ScopeRef(Level.WORKSPACE, scope_id))
    assert first != ScopeRef(Level.PROJECT, scope_id)
    assert first != ScopeRef(Level.WORKSPACE, uuid4())


def test_scope_ref_is_immutable() -> None:
    scope = ref(Level.PLAN)
    with pytest.raises(FrozenInstanceError):
        cast(Any, scope).label = "x"
    assert not hasattr(scope, "__dict__")


@pytest.mark.parametrize(
    "levels",
    [
        (Level.INSTANCE,),
        (Level.INSTANCE, Level.WORKSPACE),
        (Level.INSTANCE, Level.WORKSPACE, Level.PROJECT),
        (Level.INSTANCE, Level.WORKSPACE, Level.PROJECT, Level.PLAN),
        (Level.INSTANCE, Level.WORKSPACE, Level.PROJECT, Level.PLAN, Level.RUN),
    ],
)
def test_work_chain_is_a_prefix_farthest_first(levels: tuple[Level, ...]) -> None:
    chain = work(*levels)
    assert chain.kind is Chain.WORK
    assert chain.target.level is levels[-1]
    assert chain.ids() == tuple(scope.scope_id for scope in chain.scopes)
    assert [scope.level for scope in chain.scopes] == list(levels)


def test_host_chain_is_instance_then_host() -> None:
    chain = ScopeChain(Chain.HOST, (ref(Level.INSTANCE), ref(Level.HOST, "host:laptop")))
    assert chain.target.label == "host:laptop"
    assert len(chain.ids()) == 2


def test_host_chain_of_the_instance_scope_is_just_the_instance() -> None:
    # settings §B.10: scope=instance with kind=host resolves to (instance)
    instance = ref(Level.INSTANCE, "instance")
    chain = ScopeChain(Chain.HOST, (instance,))
    assert chain.kind is Chain.HOST
    assert chain.target == instance
    assert chain.ids() == (instance.scope_id,)


@pytest.mark.parametrize(
    ("kind", "levels"),
    [
        (Chain.WORK, ()),
        (Chain.WORK, (Level.WORKSPACE,)),  # must start at instance
        (Chain.WORK, (Level.INSTANCE, Level.PROJECT)),  # skipped workspace
        (Chain.WORK, (Level.INSTANCE, Level.PLAN, Level.PROJECT)),  # wrong order
        (Chain.WORK, (Level.INSTANCE, Level.HOST)),  # host is not in the work chain
        (Chain.WORK, (Level.INSTANCE, Level.INSTANCE)),
        (Chain.HOST, ()),
        (Chain.HOST, (Level.INSTANCE, Level.WORKSPACE)),
        (Chain.HOST, (Level.HOST, Level.INSTANCE)),
        (Chain.HOST, (Level.INSTANCE, Level.HOST, Level.HOST)),
    ],
)
def test_malformed_chains_are_rejected(kind: Chain, levels: tuple[Level, ...]) -> None:
    with pytest.raises(ValueError, match="chain"):
        ScopeChain(kind, tuple(ref(level) for level in levels))


def test_a_scope_id_cannot_repeat_in_a_chain() -> None:
    scope_id = uuid4()
    with pytest.raises(ValueError, match="distinct"):
        ScopeChain(Chain.WORK, (ScopeRef(Level.INSTANCE, scope_id), ScopeRef(Level.WORKSPACE, scope_id)))


def test_chain_is_immutable_and_snapshots_its_scopes() -> None:
    scopes = [ref(Level.INSTANCE), ref(Level.WORKSPACE)]
    chain = ScopeChain(Chain.WORK, cast(Any, scopes))
    scopes.append(ref(Level.PROJECT))
    assert len(chain.scopes) == 2
    assert isinstance(chain.scopes, tuple)
    with pytest.raises(FrozenInstanceError):
        cast(Any, chain).kind = Chain.HOST
