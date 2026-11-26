"""Composition for protected live hook requests and their native client responses."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from collections.abc import Callable, Mapping
from contextlib import suppress
from importlib import import_module
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Any, TextIO, cast

from skm.adapters.integrations.hookd import capability_proven, exchange, listen, remember_capability, serve
from skm.bootstrap.hook import (
    build_embedded_hook_app,
    evaluate_native,
    hook_bootstrap,
    is_enforcement,
    read_bytes,
    render_native,
)
from skm.modules.integrations.domain.hook_events import HookSurfaceId
from skm.modules.integrations.domain.hook_rules import HookDecision, HookMode, HookVerdict
from skm.platform.process.runner import run

if TYPE_CHECKING:
    from skm.bootstrap.composition import App
    from skm.platform.config.bootstrap import BootstrapConfig

__all__ = ["is_enforcement", "protected_result", "run_daemon"]

_DECISION_SCHEMA = "urn:skm:integrations:host:hook-decision:v1"
_BACKEND_UNAVAILABLE = "HOOK_BACKEND_UNAVAILABLE"
_CLAUDE_MINIMUM = (2, 1, 295)
_CAPABILITY_SECONDS = 60.0
_BLOCKING_EVENTS = {
    "claude_code": frozenset({"PreToolUse", "UserPromptSubmit"}),
    "codex": frozenset({"PreToolUse", "UserPromptSubmit", "PermissionRequest"}),
    "cursor": frozenset({"beforeShellExecution", "preToolUse"}),
    "grok": frozenset({"PreToolUse", "UserPromptSubmit"}),
}


def _claude_can_block(environ: Mapping[str, str], timeout: float) -> bool:
    # Probe the host executable without consulting relative PATH entries or the checkout cwd.
    path = os.pathsep.join(
        directory
        for directory in environ.get("PATH", os.defpath).split(os.pathsep)
        if os.path.isabs(directory)
    )
    binary = shutil.which("claude", path=path) if path else None
    if binary is None:
        return False
    # A proven binary is trusted again for a minute unless it was replaced (identity and size and mtime).
    # Only success is remembered, so a failed or slow probe is retried by the next hook.
    entry = os.stat(binary)
    identity = (*_CLAUDE_MINIMUM, os.path.realpath(binary), entry.st_dev, entry.st_ino)
    key = "|".join(map(str, (*identity, entry.st_size, entry.st_mtime_ns, entry.st_ctime_ns)))
    if capability_proven(environ, key, _CAPABILITY_SECONDS):
        return True
    if timeout <= 0:
        return False
    result = run(
        [binary, "--version"],
        cwd=Path("/"),
        env={"PATH": path, "HOME": str(Path.home()), "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"},
        timeout_seconds=min(timeout, 1.0),
        max_stdout_bytes=256,
        max_stderr_bytes=256,
    )
    match = re.fullmatch(rb"(\d{1,6})\.(\d{1,6})\.(\d{1,6})(?: \(Claude Code\))?\s*", result.stdout)
    capable = (
        result.exit_code == 0 and match is not None and tuple(map(int, match.groups())) >= _CLAUDE_MINIMUM
    )
    if capable:
        remember_capability(environ, key)
    return capable


def _deny(args: argparse.Namespace, reason: str) -> dict[str, Any]:
    surface = HookSurfaceId(args.surface) if args.surface in HookSurfaceId else HookSurfaceId.SUBSCRIPTIONS
    message = f"skm hook: {reason}"
    return _native_result(args, HookDecision(HookVerdict.DENY, surface, reason, message, message, None))


def _native_result(args: argparse.Namespace, decision: HookDecision) -> dict[str, Any]:
    return {
        "verdict": decision.verdict.value,
        "reason_code": decision.reason_code,
        "client_output": render_native(args, decision),
    }


def _refusal(message: str) -> dict[str, Any]:
    return {"client_output": {"exit_code": 2, "stdout": "", "stderr": f"skm hook: {message}"}}


def _decision(reply: bytes, surface: str) -> HookDecision:
    decoded = json.loads(reply)
    if not isinstance(decoded, dict):
        raise ValueError("invalid hookd reply")
    result = cast("dict[str, Any]", decoded)
    text_fields = ("reason_code", "user_message", "agent_message", "additional_context")
    if (
        result.keys() != {"schema", "surface", "mode", "verdict", *text_fields}
        or result["schema"] != _DECISION_SCHEMA
    ):
        raise ValueError("invalid hookd reply")
    if result["surface"] != surface:
        raise ValueError("hookd replied for a different surface")
    HookMode(result["mode"])
    verdict = result["verdict"]
    if verdict not in {"none", "allow", "deny", "ask", "warn"}:
        raise ValueError("invalid hookd verdict")
    text = [result[field] for field in text_fields]
    for value in text:
        if value is not None:
            if not isinstance(value, str):
                raise ValueError("invalid hookd decision text")
            value.encode("utf-8")
    if result["reason_code"] in {_BACKEND_UNAVAILABLE, "HOOK_PAYLOAD_INVALID"}:
        verdict = "deny"
    return HookDecision(
        HookVerdict.CONTEXT if verdict == "warn" else HookVerdict(verdict), HookSurfaceId(surface), *text
    )


def protected_result(args: argparse.Namespace, stdin: TextIO, environ: Mapping[str, str]) -> dict[str, Any]:
    if args.event_name not in _BLOCKING_EVENTS.get(args.target, ()):
        return _refusal("HOOK_BLOCKING_UNAVAILABLE for this client event")
    try:
        timeout_ms = int(environ.get("SKM__INTEGRATIONS__HOOK__TIMEOUT_MS", "2000"))
        deadline = monotonic() + max(1, min(timeout_ms, 10_000)) / 1000
        if args.target == "claude_code":
            try:
                capable = _claude_can_block(environ, deadline - monotonic())
            except (OSError, TimeoutError, ValueError):
                capable = False
            if not capable:
                return _refusal("HOOK_BLOCKING_UNAVAILABLE (Claude Code >= 2.1.295 required)")
        raw = read_bytes(stdin)
        header = json.dumps(
            [args.target, args.surface, args.project, args.event_name, getattr(args, "hook_class", None)]
        ).encode("utf-8")
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("hookd deadline exceeded")
        reply = exchange(environ, header + b"\n" + raw, timeout=remaining)
        return _native_result(args, _decision(reply, args.surface))
    except Exception:  # noqa: BLE001 - untrusted protocol and backend details never reach the client
        return _deny(args, _BACKEND_UNAVAILABLE)


def _reply(
    data: bytes,
    environ: Mapping[str, str],
    bootstrap_path: str | None,
    embedded_app: Callable[[BootstrapConfig], App] | None = None,
) -> bytes:
    try:
        header, separator, raw = data.partition(b"\n")
        if not separator or len(header) > 4095:
            raise ValueError("invalid hookd request header")
        call = json.loads(header)
        if not isinstance(call, list) or len(cast("list[Any]", call)) != 5:
            raise ValueError("invalid hookd request header")
        target, surface, project, event_name, hook_class = cast("list[Any]", call)
        if any(not isinstance(value, str) for value in (target, surface, project, event_name)):
            raise ValueError("invalid hookd request fields")
        if hook_class not in {None, "enforcement", "workflow", "observation"}:
            raise ValueError("invalid hookd class")
        args = argparse.Namespace(
            target=target, surface=surface, project=project, event_name=event_name, hook_class=hook_class
        )
        if not is_enforcement(args) or event_name not in _BLOCKING_EVENTS.get(target, ()):
            raise ValueError("hookd only serves blocking hooks")
        result = evaluate_native(args, raw, environ, bootstrap_path, live=True, embedded_app=embedded_app)
        del result["client_output"]  # The installed hook client renders the logical decision.
        return json.dumps(result, ensure_ascii=True, allow_nan=False).encode("utf-8")
    except Exception:  # noqa: BLE001 - an unavailable evaluator yields an invalid/empty reply and a deny
        return b""


class _EmbeddedHookBackend:
    def __init__(self, environ: Mapping[str, str]) -> None:
        self._environ = environ
        self._app: App | None = None
        self._config: BootstrapConfig | None = None

    def open(self, config: BootstrapConfig) -> App:
        if self._app is not None and self._config == config:
            return self._app
        app = build_embedded_hook_app(config, self._environ)
        self.close()
        self._app, self._config = app, config
        return app

    def close(self) -> None:
        if self._app is not None:
            self._app.close()
            self._app = None


def run_daemon(
    bootstrap_path: str | None, stopped: Callable[[], bool], *, environ: Mapping[str, str] | None = None
) -> None:
    from skm.platform.schema.registry import SchemaRegistry

    environ = os.environ if environ is None else environ
    # Parse installed schemas and load the evaluator before declaring the socket ready.
    # Profile, credentials and project policy are read live within the request.
    SchemaRegistry.load_default()
    import_module("skm.bootstrap.composition")
    import_module("skm.modules.integrations.host.evaluate_hook")
    embedded = _EmbeddedHookBackend(environ)
    try:
        # Warm the local pool before serving, and let unavailable backends recover on later requests.
        # No project credential is read until a verified request opens its own actor client.
        with suppress(Exception):
            config = hook_bootstrap(environ, bootstrap_path)
            if config.access_mode == "embedded":
                embedded.open(config)
        with listen(environ) as listener:
            serve(listener, lambda data: _reply(data, environ, bootstrap_path, embedded.open), stopped)
    finally:
        embedded.close()
