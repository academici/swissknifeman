"""Lazy embedded hook profile, shared by ``skm-hook`` and ``skm hook``."""

from __future__ import annotations

import io
import json
from collections.abc import Callable, Generator, Mapping
from contextlib import ExitStack, contextmanager, suppress
from dataclasses import replace
from importlib import import_module
from os.path import lexists
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Any, TextIO, cast

if TYPE_CHECKING:
    import argparse
    from datetime import datetime
    from uuid import UUID

    from skm.adapters.integrations.claude_code.session_summary import SessionSummarySpool
    from skm.application_bus.client import SkmClient
    from skm.bootstrap.composition import App
    from skm.kernel.json_types import JsonObject
    from skm.modules.integrations.domain.hook_rules import HookDecision
    from skm.platform.config.bootstrap import BootstrapConfig
    from skm.platform.config.secrets import SecretValue

__all__ = [
    "build_embedded_hook_app",
    "evaluate",
    "evaluate_native",
    "hook_bootstrap",
    "hook_context",
    "invoke",
    "is_enforcement",
    "read_bytes",
    "render_native",
    "unavailable_context",
    "with_hook_state",
    "write_output",
]


class _HookTargets:
    """Resolve only the requested native codec, without the projection registry."""

    def get(self, target: Any) -> Any:
        from skm.modules.integrations.domain.target import TargetId

        return _HookTarget(TargetId(target).value)

    def all(self) -> tuple[Any, ...]:
        from skm.modules.integrations.domain.target import TargetId

        return tuple(self.get(target) for target in TargetId)


class _HookTarget:
    def __init__(self, target: str) -> None:
        self.target = target

    def __getattr__(self, name: str) -> Any:
        if self.target in {"claude_code", "codex", "cursor", "grok"} and name in {
            "normalize_hook_payload",
            "render_hook_decision",
        }:
            if self.target == "claude_code":
                import skm.adapters.integrations.claude_code.hooks as codec
            elif self.target == "codex":
                import skm.adapters.integrations.codex.hooks as codec
            elif self.target == "cursor":
                import skm.adapters.integrations.cursor.hooks as codec
            else:
                import skm.adapters.integrations.grok.hooks as codec
            return getattr(codec, name)
        names = {
            "antigravity": "AntigravityTarget",
            "claude_code": "ClaudeCodeTarget",
            "codex": "CodexTarget",
            "cursor": "CursorTarget",
            "gemini_cli": "GeminiCliTarget",
            "grok": "GrokTarget",
        }
        module = import_module(f"skm.adapters.integrations.{self.target}.target")
        return getattr(getattr(module, names[self.target])(), name)


def unavailable_context() -> Any:
    """A context with target renderers and no backend: normal evaluation fails closed."""
    from uuid import UUID

    from skm.application_bus.host import HostContext
    from skm.kernel.cancel import CancelSource
    from skm.kernel.gateways import GatewayTable
    from skm.kernel.ids import HostId
    from skm.modules.integrations.ports import IntegrationTargetRegistry

    class UnavailableClient:
        def __getattr__(self, name: str) -> Any:
            raise ConnectionError("hook backend unavailable")

    return HostContext(
        client=cast("Any", UnavailableClient()),
        gateways=GatewayTable({IntegrationTargetRegistry: _HookTargets()}, "host_gateway"),
        host_id=HostId(UUID(int=0)),
        config={},
        log=None,
        cancel=CancelSource().token,
    )


def _inherited_home(environ: Mapping[str, str]) -> str | None:
    home = environ.get("HOME", "")
    return home if home and Path(home).is_absolute() else None


def with_hook_state(
    ctx: Any, state_dir: Path, *, instance_id: UUID | None = None, home: str | None = None
) -> Any:
    from skm.adapters.git.hook_state import LocalHookState
    from skm.kernel.gateways import GatewayTable
    from skm.modules.integrations.host.hook_state import HookState
    from skm.modules.integrations.ports import IntegrationTargetRegistry

    def query(name: str, payload: dict[str, Any]) -> object:
        module, query_name = name.split(".", 1)
        query_module = import_module(f"skm.modules.{module}.application.queries.{query_name}")
        return query_module.SPEC.dto.from_json(payload)

    entries: dict[type[object], object] = {}
    if isinstance(ctx.gateways, GatewayTable):
        entries.update(ctx.gateways.entries)
    entries[HookState] = LocalHookState(state_dir, query, instance_id=instance_id, home=home)
    entries[IntegrationTargetRegistry] = _HookTargets()
    return replace(ctx, gateways=GatewayTable(entries, kind="host_gateway"))


def _session_spool(
    state_dir: Path, environ: Mapping[str, str], wake: Callable[[], None]
) -> SessionSummarySpool:
    from skm.adapters.integrations.claude_code.session_summary import SessionSummarySpool
    from skm.platform.system_clock import SystemClock

    home = Path(environ.get("HOME") or Path.home())
    claude_dir = Path(environ.get("CLAUDE_CONFIG_DIR") or home / ".claude")
    return SessionSummarySpool(
        state_dir / "hooks" / "learning", claude_dir / "projects", wake=wake, now=SystemClock().now
    )


def _session_learning_enabled(client: SkmClient, project: str) -> bool:
    from uuid import UUID

    from skm.kernel.errors import Forbidden, NotFound
    from skm.modules.access.public import WhoAmI, WhoAmIView

    try:
        identity = cast("WhoAmIView", client.ask(WhoAmI(scope_id=UUID(project))))
    except (Forbidden, NotFound):
        return False
    # Learning also depends on knowledge. WhoAmI reports the configured flags for both modules.
    return (
        identity.modules.get("knowledge", False)
        and identity.modules.get("learning", False)
        and "lesson.read" in identity.effective_permissions
    )


def _with_session_spool(
    ctx: Any,
    state_dir: Path,
    environ: Mapping[str, str],
    wake: Callable[[], None],
    enabled: Callable[[str], bool],
) -> Any:
    from skm.kernel.gateways import GatewayTable
    from skm.modules.integrations.host.evaluate_hook import SessionEndObserver

    gateways = cast("GatewayTable", ctx.gateways)
    spool = _session_spool(state_dir, environ, wake)

    class LiveSessionObserver:
        def enqueue(self, project: str, checkout: str, session_id: str, transcript: str) -> None:
            if enabled(project):
                spool.enqueue(project, checkout, session_id, transcript)

    entries = {**gateways.entries, SessionEndObserver: LiveSessionObserver()}
    return replace(ctx, gateways=GatewayTable(entries, "host_gateway"))


def hook_bootstrap(environ: Mapping[str, str], path: str | None) -> BootstrapConfig:
    from skm.platform.config.bootstrap import validate_worker_host
    from skm.platform.config.sources.bootstrap import ProfileCatalog

    catalog = ProfileCatalog.read(path, environ, Path(environ.get("HOME", str(Path.home()))))
    # Native input does not choose where the daemon sends its credential.
    name = environ.get("SKM_INSTANCE", catalog.default)
    config = catalog.config(name)
    if (
        config.access_mode == "http"
        or config.installation_id is not None
        or config.machine_database_url is not None
    ):
        from skm.bootstrap.instance_profiles import verified_config

        config = verified_config(config, name, environ, lambda _: None)
    # Match restore_profile_root without importing storage on the cached hook path.
    roots = (Path(config.source).resolve().parent, config.state_dir.absolute())
    if any(
        lexists(root / name)
        for root in roots
        for name in ("restore-quarantine.json", "restore-activation.json")
    ):
        from skm.application_bus.middleware import require_restore_admission

        require_restore_admission(False, "hook")

    from skm.kernel.ports_uow import Surface

    return validate_worker_host(config, surface=Surface.HOOK)


_HOOK_PERMISSIONS = frozenset(
    {
        "workspace.read",
        "project.read",
        "checkout.read_locator",
        "integration.read",
        "run.read",
        "inbox.read",
        "lesson.read",
        "config.read",
        "policy.read",
    }
)


def hook_credential(config: BootstrapConfig) -> SecretValue:
    from skm.bootstrap.instance_secrets import check_private_dir, read_private
    from skm.kernel.error_codes import ErrorCode
    from skm.kernel.errors import PreconditionFailed
    from skm.platform.config.secrets import SecretRef, SecretValue

    path = config.state_dir / "secrets" / "hook.token"
    check_private_dir(path.parent)
    raw = read_private(path, 1025)
    if not raw or len(raw) > 1024:
        raise PreconditionFailed(ErrorCode.SECRET_UNAVAILABLE, "A dedicated hook credential is required")
    secret = raw.decode("ascii").strip()
    if not secret or any(ch.isspace() for ch in secret):
        raise PreconditionFailed(ErrorCode.SECRET_UNAVAILABLE, "Invalid dedicated hook credential")
    return SecretValue(SecretRef.parse(f"secret://file/{path}"), secret)


def hook_principal(client: SkmClient) -> UUID:
    from skm.bootstrap.machine_access import require_human_identity
    from skm.kernel.error_codes import ErrorCode
    from skm.kernel.errors import Forbidden
    from skm.modules.access.public import WhoAmI, WhoAmIView

    identity = client.ask(WhoAmI())
    principal, _ = require_human_identity(identity)
    assert isinstance(identity, WhoAmIView)  # noqa: S101
    assert identity.token is not None  # noqa: S101
    token = identity.token
    if token.scope_grants is not None:
        bounded = bool(token.scope_grants) and all(
            set(grant.permissions) <= _HOOK_PERMISSIONS for grant in token.scope_grants
        )
    else:
        bounded = (
            token.scope_id is not None
            and token.permissions is not None
            and (set(token.permissions) <= _HOOK_PERMISSIONS)
        )
    if not bounded:
        raise Forbidden(ErrorCode.FORBIDDEN, "Native hooks require a dedicated scoped credential")
    return principal


def _hook_state_dir(config: BootstrapConfig, credential: SecretValue | None = None) -> Path:
    from hashlib import sha256

    if config.installation_id is None or config.instance_id is None:
        return config.state_dir
    secret = credential if credential is not None else hook_credential(config)
    identity = sha256(secret.reveal().encode("ascii")).hexdigest()
    return (
        config.state_dir / "hook-profiles" / str(config.installation_id) / str(config.instance_id) / identity
    )


def build_embedded_hook_app(config: BootstrapConfig, environ: Mapping[str, str]) -> App:
    from skm.bootstrap.composition import build_app
    from skm.kernel.ports_uow import Surface

    return cast(
        "App",
        build_app(config, surface=Surface.HOOK, environ=environ, invocation={}, load_project_plugins=False),
    )


@contextmanager
def hook_context(
    environ: Mapping[str, str],
    bootstrap_path: str | None = None,
    *,
    subscriptions: bool = False,
    started: float | None = None,
    session_wake: Callable[[], None] | None = None,
    session_drain: bool = False,
    embedded_app: Callable[[BootstrapConfig], App] | None = None,
) -> Generator[Any]:
    from uuid import UUID

    bootstrap = hook_bootstrap(environ, bootstrap_path)
    credential = hook_credential(bootstrap)

    from skm.application_bus.client import new_request_id
    from skm.application_bus.host import HostContext
    from skm.kernel.cancel import CancelSource
    from skm.kernel.gateways import GatewayTable
    from skm.kernel.ids import HostId, ScopeId
    from skm.kernel.ports_uow import RequestMeta, Surface
    from skm.kernel.scopes import ScopeKind, ScopeRef
    from skm.platform.config import ConfigStore, ScopeTree
    from skm.platform.logging.logger import get_logger
    from skm.platform.system_clock import SystemClock
    from skm.platform.system_ids import Uuid7Generator

    with ExitStack() as resources:
        if bootstrap.access_mode == "http":
            from skm.bootstrap._http_mode import build_http_hook_app

            remote = build_http_hook_app(bootstrap, environ, credential, started=started, drain=session_drain)
            resources.callback(remote.close)
            config, client, host_id = remote.config, remote.client, remote.host_id
            principal = remote.principal
        else:
            if embedded_app is None:
                app = build_embedded_hook_app(bootstrap, environ)
                resources.callback(app.close)
            else:
                app = embedded_app(bootstrap)
            host_id = HostId(UUID(str(bootstrap.host_id)))
            actor = app.authenticate(credential.reveal())
            clock = SystemClock()
            ids = Uuid7Generator(clock)
            meta = RequestMeta(new_request_id(ids), Surface.HOOK, None, clock.now())
            with app.uow_factory(meta, readonly=True) as unit:
                config = app.config.effective_host(
                    unit.repo(ConfigStore),
                    unit.repo(ScopeTree),
                    ScopeRef(ScopeKind.HOST, ScopeId(host_id)),
                )
            client = app.client(actor=actor, surface=Surface.HOOK)
            principal = hook_principal(client)
        context = HostContext(
            client=client,
            gateways=GatewayTable({}, kind="host_gateway"),
            host_id=host_id,
            config=config,
            log=get_logger("entrypoints.hook"),
            cancel=CancelSource().token,
        )
        if bootstrap.installation_id is not None and bootstrap.instance_id is not None:
            from skm.bootstrap.machine import open_machine_store
            from skm.bootstrap.projection_wiring import bind_managed_projections
            from skm.platform.machine import MachinePrincipal

            scope = MachinePrincipal(bootstrap.installation_id, bootstrap.instance_id, principal)
            store = open_machine_store(bootstrap, environ, on_secret=lambda _: None)
            context = bind_managed_projections(context, store, lambda: scope, bootstrap.state_dir)
        state_dir = _hook_state_dir(bootstrap, credential)
        context = with_hook_state(
            context, state_dir, instance_id=bootstrap.instance_id, home=_inherited_home(environ)
        )
        if session_wake is not None:
            context = _with_session_spool(
                context,
                state_dir,
                environ,
                session_wake,
                lambda project: _session_learning_enabled(client, project),
            )
        if subscriptions:
            from skm.bootstrap.hook_subscriptions import with_subscription_gateways

            context = with_subscription_gateways(
                context, state_dir, _hook_process_environment(environ), native_drain=True
            )
        yield context


def read_bytes(stdin: Any) -> bytes:
    raw = getattr(stdin, "buffer", stdin).read(1_048_577)
    return raw.encode("utf-8") if isinstance(raw, str) else raw


def evaluate(args: argparse.Namespace, stdin: Any, context: Any, *, live: bool = False) -> dict[str, Any]:
    from skm.modules.integrations.host.evaluate_hook import run

    raw = read_bytes(stdin)
    try:
        payload = json.loads(raw.decode("utf-8")) if len(raw) <= 1_048_576 else None
    except (ValueError, RecursionError, UnicodeError):
        payload = None
    return cast(
        "dict[str, Any]",
        run(
            context,
            {
                "target": args.target,
                "surface": args.surface,
                "project_id": args.project,
                "event_name": args.event_name,
                "payload": payload,
                **({"class": args.hook_class} if getattr(args, "hook_class", None) is not None else {}),
            },
            payload_size=len(raw),
            live=live,
        ),
    )


def write_output(result: dict[str, Any], stdout: TextIO, stderr: TextIO) -> int:
    output = result["client_output"]
    rendered = output["stdout"]
    if rendered:
        stdout.write(
            (json.dumps(rendered, ensure_ascii=False) if isinstance(rendered, dict) else rendered) + "\n"
        )
    stdout.flush()
    if result.get("verdict") == "none" and result.get("reason_code"):
        stderr.write("skm hook: " + str(result["reason_code"]) + "\n")
    if output.get("stderr"):
        stderr.write(output["stderr"] + "\n")
    return int(output["exit_code"])


def is_enforcement(args: argparse.Namespace) -> bool:
    from skm.modules.integrations.domain.hook_events import HookSurfaceId
    from skm.modules.integrations.domain.hook_rules import ENFORCEMENT

    return (
        args.surface in ENFORCEMENT
        or (
            args.surface == HookSurfaceId.REVIEW_GATE
            and args.event_name not in {"SubagentStop", "subagentStop"}
        )
        or (
            args.surface == HookSurfaceId.SUBSCRIPTIONS
            and getattr(args, "hook_class", None) not in {"workflow", "observation"}
        )
        or getattr(args, "hook_class", None) == "enforcement"
    )


def invoke(
    args: argparse.Namespace,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
    environ: Mapping[str, str],
    bootstrap_path: str | None = None,
) -> int:
    """One native protocol for both commands, with daemon-only enforcement."""
    if is_enforcement(args):
        from skm.bootstrap.hookd import protected_result

        return write_output(protected_result(args, stdin, environ), stdout, stderr)
    drains: list[Callable[[], None]] = []
    result = evaluate_native(args, read_bytes(stdin), environ, bootstrap_path, after_output=drains)
    code = write_output(result, stdout, stderr)
    for drain in drains:
        drain()
    return code


def render_native(args: argparse.Namespace, decision: HookDecision) -> dict[str, Any]:
    from skm.modules.integrations.domain.hook_events import HookEventKind, NormalizedHookEvent
    from skm.modules.integrations.domain.target import TargetId

    target = TargetId(args.target)
    event = NormalizedHookEvent(
        target, HookEventKind.PRE_TOOL, None, "", None, None, (), None, None, args.event_name
    )
    return cast("dict[str, Any]", _HookTargets().get(target).render_hook_decision(event, decision))


def evaluate_native(
    args: argparse.Namespace,
    raw: bytes,
    environ: Mapping[str, str],
    bootstrap_path: str | None,
    *,
    live: bool = False,
    after_output: list[Callable[[], None]] | None = None,
    embedded_app: Callable[[BootstrapConfig], App] | None = None,
) -> dict[str, Any]:
    started = monotonic()
    drain_context = None
    session_queued = False

    def wake() -> None:
        nonlocal session_queued
        session_queued = True

    session_wake = (
        wake
        if (args.target, args.surface, args.event_name)
        == ("claude_code", "lifecycle.run_report", "SessionEnd")
        else None
    )
    try:
        cached = (
            None
            if live
            else _cached_context(
                args, raw, environ, bootstrap_path, session_wake=session_wake, started=started
            )
        )
        if cached is not None:
            result = evaluate(args, io.BytesIO(raw), cached)
        else:
            with hook_context(
                environ,
                bootstrap_path,
                subscriptions=args.surface == "custom.subscriptions",
                started=started,
                session_wake=session_wake,
                embedded_app=embedded_app,
            ) as context:
                result = evaluate(args, io.BytesIO(raw), context, live=live)
                if args.surface == "custom.subscriptions":
                    drain_context = context
    except Exception:
        if live:
            raise
        result = evaluate(args, io.BytesIO(raw), unavailable_context())
    if after_output is not None and session_queued:

        def start_sessions() -> None:
            with suppress(OSError):
                _start_session_drain(environ, bootstrap_path)

        after_output.append(start_sessions)
    if after_output is not None and drain_context is not None:

        def start_subscriptions() -> None:
            from skm.modules.integrations.host.host_subscriptions import SubscriptionState

            with suppress(Exception):
                drain_context.gateways.get(SubscriptionState).start_drain(bootstrap_path)

        after_output.append(start_subscriptions)
    return result


def _cached_context(
    args: argparse.Namespace,
    raw: bytes,
    environ: Mapping[str, str],
    bootstrap_path: str | None,
    *,
    session_wake: Callable[[], None] | None = None,
    started: float | None = None,
) -> Any:
    # Project policy can be cached; executable authority must use this host's current config.
    if args.surface == "custom.subscriptions":
        return None
    from uuid import UUID

    bootstrap = hook_bootstrap(environ, bootstrap_path)
    state_dir = _hook_state_dir(bootstrap)

    from skm.adapters.git.hook_state import LocalHookState
    from skm.kernel.gateways import GatewayTable
    from skm.kernel.ids import HostId
    from skm.modules.integrations.host.hook_state import HookState

    state = LocalHookState(
        state_dir,
        lambda _name, _payload: (_ for _ in ()).throw(ConnectionError("live query required")),
        instance_id=bootstrap.instance_id,
        home=_inherited_home(environ),
    )
    policy, snapshot = state.load_with_snapshot(args.project, args.target)
    if policy is None or snapshot is None or str(bootstrap.host_id) != snapshot["host_id"]:
        return None
    context = unavailable_context()
    if args.surface == "lifecycle.review_gate" and policy["hook_modes"].get("review_gate", "strict") != "off":
        from skm.modules.integrations.domain.hook_rules import commit_message
        from skm.modules.integrations.domain.target import TargetId
        from skm.modules.integrations.ports import IntegrationTargetRegistry

        adapter = context.gateways.get(IntegrationTargetRegistry).get(TargetId(args.target))
        event = adapter.normalize_hook_payload(args.event_name, json.loads(raw.decode("utf-8")))
        if commit_message(event.command or "") is not None:
            return None  # receipts are always live, even with a valid policy cache

    class CachedClient:
        offline = True
        cached_snapshot = snapshot

        def ask(self, query: Any) -> Any:
            from skm.modules.workspace.generated.views import CheckoutLocationView, ProjectView

            urn = query.SCHEMA_URN
            if urn == "urn:skm:workspace:query:get-project:v1":
                return ProjectView.from_json(snapshot["project"])
            if (
                urn == "urn:skm:workspace:query:resolve-checkout:v1"
                and query.mount_name == snapshot["mount"]
                and str(query.host_id) == snapshot["host_id"]
            ):
                return CheckoutLocationView.from_json(snapshot["checkout"])
            raise ConnectionError("live query required")

    context = replace(
        context,
        client=cast("Any", CachedClient()),
        host_id=HostId(UUID(snapshot["host_id"])),
        gateways=GatewayTable({**context.gateways.entries, HookState: state}, kind="host_gateway"),
    )
    if session_wake is not None:

        def enabled(project: str) -> bool:
            # Reuse cached policy and checkout facts. Module availability must come from the live backend.
            with hook_context(environ, bootstrap_path, started=started, session_drain=True) as live:
                return _session_learning_enabled(live.client, project)

        context = _with_session_spool(context, state_dir, environ, session_wake, enabled)
    return context


def _start_session_drain(environ: Mapping[str, str], bootstrap_path: str | None) -> None:
    import subprocess
    import sys

    argv = [sys.executable, "-I", "-m", "skm.bootstrap.hook"]
    if bootstrap_path is not None:
        argv.append(bootstrap_path)
    subprocess.Popen(  # noqa: TID251 - detached observation drain with independent lifetime
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
        env=_hook_process_environment(environ),
    )


def _hook_process_environment(environ: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value for key, value in environ.items() if key not in {"SKM_API_TOKEN", "SKM_API_CREDENTIAL"}
    }


def _drain_sessions(environ: Mapping[str, str], bootstrap_path: str | None) -> None:
    from uuid import UUID

    from skm.adapters.checkout_fs.local import LocalCheckoutFs
    from skm.adapters.integrations.claude_code.target import ClaudeCodeTarget
    from skm.kernel.error_codes import ErrorCode
    from skm.kernel.errors import Forbidden, NotFound, PreconditionFailed, SkmError
    from skm.kernel.ids import ProjectId
    from skm.modules.integrations.ports import LocalCheckoutProjections
    from skm.modules.learning import public as learning
    from skm.modules.workspace.public import GetProject, ProjectView

    bootstrap = hook_bootstrap(environ, bootstrap_path)
    spool = _session_spool(_hook_state_dir(bootstrap), environ, lambda: None)
    target = ClaudeCodeTarget()

    def summarize(path: Path, session_id: str, checkout: Path, observed_at: datetime) -> JsonObject | None:
        return target.summarize_session(
            {"transcript_path": str(path), "session_id": session_id, "observed_at": observed_at.isoformat()},
            LocalCheckoutFs(checkout, state_dir=bootstrap.state_dir),
        )

    with hook_context(environ, bootstrap_path, session_drain=True) as context:

        def checkout_allowed(project: str, checkout: Path) -> bool:
            if not context.gateways.has(LocalCheckoutProjections):
                return True
            project_id = ProjectId(UUID(project))
            try:
                view = context.client.ask(GetProject(project_id))
            except (Forbidden, NotFound):
                return False
            if not isinstance(view, ProjectView):
                return False
            local = context.gateways.get(LocalCheckoutProjections)
            for mount in view.mounts:
                try:
                    _, root = local.resolve(project_id, mount.mount_name)
                except (Forbidden, NotFound):
                    continue
                except PreconditionFailed as exc:
                    if exc.code not in {ErrorCode.CHECKOUT_UNBOUND, ErrorCode.CHECKOUT_MISMATCH}:
                        raise
                    continue
                if checkout == root:
                    return True
            return False

        def dispatch(project: str, summary: JsonObject) -> None:
            command = learning.RecordActivity.from_json({"project_id": project, "summary": summary})
            # Intake resolves the project source toggle in the command transaction.
            try:
                context.client.dispatch(command)
            except SkmError as exc:
                if exc.code is not ErrorCode.MODULE_DISABLED:
                    raise

        spool.drain(
            enabled=lambda project: _session_learning_enabled(context.client, project),
            dispatch=dispatch,
            summarize=summarize,
            checkout_allowed=checkout_allowed,
        )


def _drain_subscriptions(environ: Mapping[str, str], bootstrap_path: str | None) -> None:
    from skm.modules.integrations.host.drain_hook_spool import run

    with hook_context(environ, bootstrap_path, subscriptions=True) as context:
        run(context, {})


if __name__ == "__main__":
    import os
    import sys

    args = sys.argv[1:]
    if args[:1] == ["--subscriptions"]:
        _drain_subscriptions(os.environ, args[1] if len(args) > 1 else None)
    else:
        _drain_sessions(os.environ, args[0] if args else None)
