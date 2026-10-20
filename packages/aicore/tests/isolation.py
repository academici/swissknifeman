"""Test helper: keep the project search of a fixture away from the host's ancestors (a sandbox /tmp/.git)."""
from pathlib import Path
from unittest import mock

from aicore.state import locations


def isolated_project_search(root):
    """Keep real markers inside the fixture; host ancestors are outside its synthetic filesystem."""
    ancestors = set(Path(root).resolve().parents)
    marker_found = locations._marker_found
    return mock.patch.object(locations, "_marker_found", side_effect=lambda candidate, marker:
                             candidate not in ancestors and marker_found(candidate, marker))
