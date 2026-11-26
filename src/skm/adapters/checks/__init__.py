"""Check runners for execution stages: command, shell, manual and external checks plus their registry.

Every command check runs through the sandbox wrapper with bounded output capture; ``registry.py`` builds
the runners and decides when a previous result may be reused.
"""

__all__: list[str] = []
