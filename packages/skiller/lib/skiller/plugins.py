"""plugins — first-turn visibility of marketplace plugins in Claude Code.

The implementation lives in ``aicore.delivery.claude``; these names stay importable here for
``skiller budget --with-plugins``.
"""
import core  # noqa: F401  (the first core import puts aicore on sys.path)

from aicore.delivery.claude import (PLUGIN_CALL_TIMEOUT, _details_cache,  # noqa: F401
                                    list_enabled_plugins, plugin_always_on_tokens,
                                    plugins_summary)
from aicore.delivery.claude import run_claude as _run_claude  # noqa: F401
