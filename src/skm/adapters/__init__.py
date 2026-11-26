"""Port implementations grouped by technology; only ``bootstrap`` chooses and wires them.

Each subpackage implements kernel or module ports (repositories, gateways, runtimes, sandboxes, stores).
Modules never import adapters; a concrete adapter class is exported through ``__all__`` and listed in the
architecture adapter inventory.
"""

__all__: list[str] = []
