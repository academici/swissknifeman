"""Portable workspace: identity of a project, the documents of the workspace, machine bindings and the one rule that
tells where the plans of a project live (contract ``knowledge/workspace-contract`` of PLAN6, ADR 0085).

Layering: ``workspace`` uses :mod:`aicore.state`, :mod:`aicore.util` and the standard library. stdlib only.
"""
from __future__ import annotations


class WorkspaceError(Exception):
    """A workspace refusal with a stable ``code`` (``PROJECT_MARKER_INVALID``, ``WORKSPACE_PROJECT_MISSING``, ...)."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


from .bindings import bind, bindings_path, read_bindings, set_paths, unbind  # noqa: E402
from .documents import (MARKER_RELPATH, project_dir, read_device, read_marker, read_project,  # noqa: E402
                        read_workspace, utc_now, validate_document, write_device, write_marker,
                        write_project, write_workspace)
from .localconfig import (CONFIG_FILE as LOCAL_CONFIG_FILE, LOCAL_DIRNAME, LOCAL_FOLDERS,  # noqa: E402
                          clear_repo_path, ensure_local, local_backups_dir, local_config_file,  # noqa: E402
                          local_dir, local_state_dir, local_stubs_dir, read_local_config, repo_path, set_repo_path)
from .ids import is_code, is_id, new_id  # noqa: E402
from .remotes import checkout_remotes, normalize_remote, redact_remote  # noqa: E402
from .resolve import PlansStore, legacy_plans_present, resolve_plans_store, source_root_of  # noqa: E402

__all__ = [
    "LOCAL_CONFIG_FILE", "LOCAL_DIRNAME", "LOCAL_FOLDERS", "MARKER_RELPATH", "PlansStore", "WorkspaceError", "bind", "bindings_path", "checkout_remotes", "clear_repo_path",
    "ensure_local", "is_code", "is_id", "legacy_plans_present", "local_backups_dir", "local_config_file", "local_dir",
    "local_state_dir", "local_stubs_dir", "new_id", "normalize_remote", "project_dir", "read_bindings", "read_device",
    "read_local_config", "read_marker", "read_project", "read_workspace", "redact_remote", "repo_path",
    "resolve_plans_store", "set_paths", "set_repo_path", "source_root_of", "unbind", "utc_now",
    "validate_document", "write_device", "write_marker", "write_project", "write_workspace",
]
