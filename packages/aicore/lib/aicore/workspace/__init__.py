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
from .ids import is_code, is_id, new_id  # noqa: E402
from .remotes import checkout_remotes, normalize_remote, redact_remote  # noqa: E402
from .resolve import PlansStore, legacy_plans_present, resolve_plans_store, source_root_of  # noqa: E402

__all__ = [
    "MARKER_RELPATH", "PlansStore", "WorkspaceError", "bind", "bindings_path", "checkout_remotes", "is_code", "is_id",
    "legacy_plans_present", "new_id", "normalize_remote", "project_dir", "read_bindings", "read_device",
    "read_marker", "read_project", "read_workspace", "redact_remote", "resolve_plans_store", "set_paths",
    "source_root_of", "unbind", "utc_now", "validate_document", "write_device", "write_marker", "write_project",
    "write_workspace",
]
