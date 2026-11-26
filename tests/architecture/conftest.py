"""Session-scoped read-only snapshots shared across architecture test modules.

Each ``SourceFile`` still owns its own per-instance AST/fact caches (no global
path cache), so synthetic fixture trees in individual tests remain completely
isolated while full-repository checks parse ``src/skm`` and run ``tools.gen``
at most once per worker session.
"""

from __future__ import annotations

from collections.abc import Mapping
from importlib import import_module
from pathlib import Path

import pytest

from ._tree import SourceFile, collect

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def session_root_tree() -> tuple[SourceFile, ...]:
    return tuple(collect(ROOT))


@pytest.fixture(scope="session")
def session_generated_outputs() -> Mapping[Path, str]:
    gen = import_module("tools.gen")
    return dict(gen.outputs(ROOT))
