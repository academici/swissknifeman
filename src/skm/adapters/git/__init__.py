"""Git adapters: the safe subprocess runner, repository inspection, snapshots, task integration and hooks.

``runner.py`` runs ``git`` behind the repository trust boundary; ``environments/`` prepares the checkout an
attempt works in; ``integration*.py`` write accepted task deltas to the target branch.
"""

__all__: list[str] = []
