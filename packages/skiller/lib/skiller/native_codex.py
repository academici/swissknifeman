"""Explicit project plugin activation and read-only native Codex discovery.

The implementation lives in ``aicore.delivery.codex``; these names stay importable here for the
skiller callers (``connect``, ``hub``, ``update``, ``budget``) and their tests.
"""
import core  # noqa: F401  (the first core import puts aicore on sys.path)

from aicore.delivery.codex import (SUFFIX, _read, apply_selection, codex_home,  # noqa: F401
                                   native_inventory, plan_selection)
