"""Compose local interactive sessions with the project checkout and runtime settings."""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

from skm.adapters.runtimes.grok.runtime import grok_account_available
from skm.adapters.runtimes.interactive import (
    NATIVE_ACCOUNT_FILES,
    InteractiveLauncher,
    InteractiveSession,
    interactive_argv,
)
from skm.adapters.secrets.file import FileSecretResolver
from skm.application_bus.host import HostContext
from skm.bootstrap._quarantine import pinned_profile
from skm.bootstrap.runtimes import WorkerRuntimeSettings, runtime_environment
from skm.bootstrap.worker_runtimes import runtime_auth, worker_redactor
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, Conflict, PreconditionFailed, SkmError
from skm.kernel.ids import ProjectId
from skm.kernel.json_types import JsonObject
from skm.modules.integrations.ports import LocalCheckoutProjections
from skm.modules.runtimes import public as runtimes
from skm.platform.config.bootstrap import BootstrapConfig
from skm.platform.config.secrets import SecretRef
from skm.platform.config.sources.bootstrap import ProfileCatalog
from skm.platform.machine import MachineStore

__all__ = ["InteractiveLauncher", "InteractiveSession", "local_launcher", "start_session"]


def local_launcher(
    *,
    state_dir: Path | None,
    bootstrap: str | None,
    instance: str | None,
    environ: Mapping[str, str],
    home: Path,
) -> InteractiveLauncher:
    if state_dir is None:
        catalog = ProfileCatalog.read(bootstrap, environ, home)
        state_dir = pinned_profile(catalog.config(catalog.select(instance, Path.cwd()))).state_dir
    return InteractiveLauncher(state_dir / "sessions")


def _route(
    ctx: HostContext, project_id: ProjectId, role: str, runtime: str | None, model: str | None
) -> tuple[str, str]:
    payload: JsonObject = {
        "scope": {"kind": "project", "id": str(project_id)},
        "host_id": str(ctx.host_id),
        "role": role,
    }
    if runtime is not None:
        payload["explicit_runtime"] = runtime
    if model is not None:
        payload["explicit_model"] = model
    view = ctx.client.ask(runtimes.ExplainRouting.from_json(payload))
    assert isinstance(view, runtimes.RouteExplainView)  # noqa: S101 - verified by the bus
    decision = view.decision
    if decision is not None:
        selected_runtime, selected_model = decision.get("runtime_id"), decision.get("model")
        if isinstance(selected_runtime, str) and isinstance(selected_model, str):
            return selected_runtime, selected_model
    raise CapabilityUnavailable(
        ErrorCode.MODEL_UNAVAILABLE,
        view.error.message if view.error else "No runtime and model route for this interactive session",
    )


def _native_account(
    machine: WorkerRuntimeSettings, runtime: str, environ: Mapping[str, str]
) -> runtimes.SecretStr | None:
    copies = machine.get("runtimes.credentials.copy")
    relative = NATIVE_ACCOUNT_FILES.get(runtime)
    home = environ.get("HOME")
    if relative is None or not home or not isinstance(copies, dict) or copies.get(runtime) is not True:
        return None
    source = Path(home) / relative
    if source.is_symlink():
        return None
    try:
        value = FileSecretResolver().resolve(SecretRef.parse(f"secret://file/{source}"))
    except SkmError:
        return None
    return runtimes.SecretStr(value) if value else None


def start_session(  # noqa: PLR0913 -- interactive selection and its local process inputs
    launcher: InteractiveLauncher,
    ctx: HostContext,
    project_id: ProjectId,
    *,
    mount: str,
    role: str,
    runtime: str | None,
    model: str | None,
    bootstrap: BootstrapConfig,
    machine_store: MachineStore,
    environ: Mapping[str, str],
    on_secret: Callable[[str], None],
) -> InteractiveSession:
    local = ctx.gateways.get(LocalCheckoutProjections)
    checkout = local.resolve(project_id, mount)
    runtime, model = _route(ctx, project_id, role, runtime, model)
    machine = WorkerRuntimeSettings.read(machine_store)
    if not machine.allows_model(runtime, model, None):
        raise CapabilityUnavailable(
            ErrorCode.MODEL_UNAVAILABLE, "Interactive model is unavailable on this machine"
        )
    redactor, remember = worker_redactor(bootstrap, environ, on_secret)
    launch_env = runtime_environment(environ, redactor)
    account = runtime_auth(machine.accounts.get(runtime, {}), bootstrap, environ, redactor, remember)
    launch_env.update(account)
    account_home = None
    native_auth = None
    if runtime == "grok":
        if not grok_account_available(machine.grok_account_home):
            raise CapabilityUnavailable(ErrorCode.RUNTIME_AUTH_EXPIRED, "Local Grok account is unavailable")
        account_home = machine.grok_account_home
    elif runtime in {"antigravity", "claude_code", "codex", "gemini_cli"} and not account:
        native_auth = _native_account(machine, runtime, environ)
        if native_auth is None:
            raise CapabilityUnavailable(
                ErrorCode.RUNTIME_AUTH_EXPIRED, "Local runtime account is unavailable"
            )
        remember(native_auth.reveal())
    binaries = machine.get("runtimes.binaries")
    argv = interactive_argv(runtime, model, binaries if isinstance(binaries, dict) else {}, launch_env)
    checkouts = cast("list[JsonObject]", local.sync(project_id)["checkouts"])
    for item in checkouts:
        for outcome in cast("list[JsonObject]", item["outcomes"]):
            if outcome["state"] in ("drifted", "failed") or outcome["conflicts"] or outcome["failed"]:
                raise Conflict(
                    ErrorCode.PROJECTION_CONFLICT,
                    "Resolve project projection conflicts before starting an interactive session",
                    details={"mount": item["mount"], "target": outcome["target"]},
                )
    confirmed = local.resolve(project_id, mount)
    if not any(item["mount"] == mount for item in checkouts) or confirmed != checkout:
        raise PreconditionFailed(ErrorCode.CHECKOUT_MISMATCH, "Checkout changed during projection sync")
    return launcher.start(
        argv,
        project_id=str(project_id),
        runtime=runtime,
        model=model,
        checkout=confirmed[1],
        environ=launch_env,
        account_home=account_home,
        native_auth=native_auth,
    )
