"""HTTP layer of the backend: the only place of gui that imports third-party packages (Starlette, uvicorn, anyio).

Importing it puts the locked packages of ``requirements.lock`` on ``sys.path`` first (``gui.deps.activate``), so a
missing install fails with ``GUI_DEPS_UNAVAILABLE`` instead of an ``ImportError``.
"""
from .. import deps as _deps

try:
    import starlette  # noqa: F401
except ImportError:
    _deps.activate()
