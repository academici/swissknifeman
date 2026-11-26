"""Checkout settings read by host operations, with defaults when the config view lacks them."""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, cast

from skm.modules.workspace.generated.settings import WorkspaceSettings

if TYPE_CHECKING:
    from skm.application_bus.host import HostContext

__all__: list[str] = []


def checkout_marker_relpath(ctx: HostContext) -> str:
    section_fn = getattr(ctx.config, "section", None)
    if callable(section_fn):
        with suppress(Exception):
            ws_settings = cast("WorkspaceSettings", section_fn(WorkspaceSettings))
            return ws_settings.checkout.marker_path
    getter = getattr(ctx.config, "get", None)
    if callable(getter):
        with suppress(Exception):
            value = getter("workspace.checkout.marker_path")
            if isinstance(value, str) and value:
                return value
    return ".skm/project.json"


def git_timeout_seconds(ctx: HostContext) -> float:
    getter = getattr(ctx.config, "get", None)
    if callable(getter):
        with suppress(Exception):
            value = getter("worker.git.timeout_seconds")
            if isinstance(value, (int, float)) and value > 0:
                return float(value)
    return 60.0
