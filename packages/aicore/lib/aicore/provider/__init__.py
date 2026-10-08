"""Provider-model domain cluster.

``core.__init__`` is the sole public facade; import submodules directly for deep
imports to avoid a duplicate export surface.

Provider-health composition lives in :mod:`core.provider.health`; package
adapters pass owner-produced evidence to it and never write through this layer.
"""
