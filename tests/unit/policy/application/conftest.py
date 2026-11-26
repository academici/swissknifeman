"""Fixtures of the policy application tests: ``world`` is the real bus over memory (``harness``)."""

import pytest

from unit.policy.application.harness import World, build_world


@pytest.fixture
def world() -> World:
    return build_world()
