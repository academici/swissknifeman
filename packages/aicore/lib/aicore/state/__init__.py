"""Standard locations, legacy lookup, backups with rotation and the gitignore policy.

Layering: ``state`` uses only :mod:`aicore.util` and the standard library.
"""
from . import gitignore
from .backups import DEFAULT_KEEP, backup, list_backups
from .locations import (Locations, cache_dir, config_dir, data_dir, ensure_dir, find_project_root,
                        machine_config_file, machine_locations, project_backups_dir,
                        project_config_file, project_dir, project_state_dir, resolve_with_legacy,
                        state_dir)

__all__ = [
    "DEFAULT_KEEP", "Locations", "backup", "cache_dir", "config_dir", "data_dir", "ensure_dir",
    "find_project_root", "gitignore", "list_backups", "machine_config_file", "machine_locations",
    "project_backups_dir", "project_config_file", "project_dir", "project_state_dir",
    "resolve_with_legacy", "state_dir",
]
