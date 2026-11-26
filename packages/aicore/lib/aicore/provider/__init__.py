"""Provider-model domain cluster.

There is no flat facade: import submodules directly (``aicore.provider.values``,
``aicore.provider.manifest``, ...). Artifact rendering and locking live in
:mod:`aicore.artifacts`.

Provider-health composition lives in :mod:`aicore.provider.health`; package
adapters pass owner-produced evidence to it and never write through this layer.
"""
