"""Start a credential-bound MCP stdio session or show its published tools."""

import argparse
from collections.abc import Generator, Sequence
from contextlib import closing, contextmanager
from dataclasses import replace
from pathlib import Path
from uuid import UUID

from skm.application_bus.client import SkmClient
from skm.bootstrap.composition import App, build_app
from skm.bootstrap.instance_profiles import verified_config
from skm.bootstrap.instance_secrets import http_credential, open_http_client
from skm.bootstrap.local_memory import LocalEpisodicMemory, local_episodic_memory
from skm.bootstrap.stage_broker import request_stage_tools, run_stage_mcp_proxy
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.project import resolve_project_id
from skm.entrypoints.cli.context import CliSession
from skm.entrypoints.cli.output import render, render_error, render_table
from skm.entrypoints.mcp.registry import published_tools, tools_digest
from skm.entrypoints.mcp.server import serve
from skm.entrypoints.mcp.server import serve_stage as serve_stage
from skm.entrypoints.mcp.session import McpSession
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, Unauthenticated
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Surface
from skm.platform.config.bootstrap import BootstrapConfig
from skm.platform.config.secrets import SecretRef, SecretValue
from skm.platform.config.sources.bootstrap import ProfileCatalog
from skm.platform.schema.registry import SchemaRegistry

__all__ = ["GROUP", "register", "serve_stage"]

_HELP: dict[str, str] = {"": "serve MCP over stdio", "tools": "list the session's MCP tools and digest"}


def _missing_token(token_env: str) -> Unauthenticated:
    return Unauthenticated(ErrorCode.UNAUTHENTICATED, f"Set {token_env} or configure api.credential")


def _credential(bootstrap: BootstrapConfig, ctx: CliSession, token_env: str) -> SecretValue:
    try:
        return http_credential(bootstrap, ctx.environ, ctx.redactor.register_secret)
    except SkmError as error:
        if error.code is ErrorCode.SECRET_UNAVAILABLE or error.details.get("reason") == "secret_unresolved":
            raise _missing_token(token_env) from None
        raise


def _session(
    ctx: CliSession,
    client: SkmClient,
    project: str | None,
    *,
    local_memory: tuple[LocalEpisodicMemory, UUID] | None = None,
) -> McpSession:
    ctx.client_ = client
    project_id = None if project is None else resolve_project_id(ctx, project)
    return McpSession.open(
        client,
        project_id=project_id,
        cli_context_path=None if ctx.state_dir is None else ctx.state_dir / "cli-context.json",
        instance_id=ctx.instance_id,
        local_memory=local_memory,
    )


@contextmanager
def _remote_session(
    bootstrap: BootstrapConfig, credential: SecretValue, ctx: CliSession, project: str | None
) -> Generator[McpSession]:
    with closing(open_http_client(bootstrap, ctx.environ, credential=credential)) as discovery:
        session = _session(ctx, discovery, project)
        if session.run_id is None:
            yield session
            return
        # The guarded notes route needs the live assignment run in the URL. The server
        # verifies this path against the bearer on every note request.
        with closing(
            open_http_client(bootstrap, ctx.environ, credential=credential, run_scope_id=session.run_id)
        ) as scoped:
            yield replace(session, client=scoped)


@contextmanager
def _open(args: argparse.Namespace, ctx: CliSession) -> Generator[tuple[App | None, McpSession]]:
    token = ctx.environ.get(args.token_env)
    if token:
        ctx.redactor.register_secret(token)
    # Bootstrap uses SKM_API_TOKEN for a literal credential. Apply the MCP-specific
    # environment precedence while retaining profile selection and validation.
    environ = {**ctx.environ, "SKM_API_TOKEN": token} if token else ctx.environ
    try:
        catalog = ProfileCatalog.read(ctx.options.bootstrap, environ, ctx.home)
    except SkmError as error:
        if error.code is ErrorCode.BOOTSTRAP_MISSING and not environ.get("SKM_API_TOKEN"):
            raise _missing_token(args.token_env) from None
        raise
    if catalog.source == "env" and not environ.get("SKM_API_TOKEN"):
        raise _missing_token(args.token_env)
    profile = catalog.select(ctx.options.instance, Path.cwd())
    bootstrap = catalog.config(profile)
    if bootstrap.access_mode == "http" and (
        bootstrap.installation_id is not None or bootstrap.machine_database_url is not None
    ):
        bootstrap = verified_config(bootstrap, profile, ctx.environ, ctx.redactor.register_secret)
    ctx.state_dir, ctx.instance_id = bootstrap.state_dir, bootstrap.instance_id
    local_memory = (
        (local_episodic_memory(bootstrap), args.local_memory_session) if args.local_memory_session else None
    )
    credential = (
        SecretValue(SecretRef.parse("secret://env/" + args.token_env), token)
        if token
        else _credential(bootstrap, ctx, args.token_env)
    )
    if bootstrap.access_mode == "http":
        with _remote_session(bootstrap, credential, ctx, args.project) as session:
            yield None, session
        return

    invocation: JsonObject = {"set": list(ctx.options.sets), "config": ctx.options.config or []}
    with closing(
        build_app(bootstrap, surface=Surface.MCP, environ=ctx.environ, invocation=invocation)
    ) as app:
        ctx.instance_id = app.instance_id
        client = app.client(actor=app.authenticate(credential.reveal()), surface=Surface.MCP)
        yield app, _session(ctx, client, args.project, local_memory=local_memory)


def _run(args: argparse.Namespace, ctx: CliSession) -> int:
    if args.verb == "tools" and args.tools_json:
        ctx.options = replace(ctx.options, json=True)
    try:
        socket = ctx.environ.get("SKM_STAGE_SOCKET")
        if socket:
            if args.verb != "tools":
                return run_stage_mcp_proxy(socket, ctx.stdin, ctx.stdout)
            tools = request_stage_tools(socket)
            return _render_tools(ctx, tools)
        with _open(args, ctx) as (app, session):
            if args.verb != "tools":
                session.refresh()
                return serve(app, session, ctx.stdin, ctx.stdout)
            tools = published_tools(session, app.schemas if app else SchemaRegistry.load_default())
            return _render_tools(ctx, tools)
    except SkmError as error:
        if args.verb != "tools" or error.code in {ErrorCode.UNAUTHENTICATED, ErrorCode.NO_PROJECT_SCOPE}:
            return render_error(replace(ctx, options=replace(ctx.options, json=False)), error, command="mcp")
        raise


def _render_tools(ctx: CliSession, tools: Sequence[JsonObject]) -> int:
    digest = tools_digest(tools)
    return render(
        ctx,
        {"tools": list(tools), "tools_digest": digest},
        human=lambda _: [
            f"tools_digest  {digest}",
            *render_table(ctx, ("Tool", "Description"), [(t["name"], t["description"]) for t in tools]),
        ],
        essential=lambda _: digest,
        command="mcp tools",
    )


def register(sub: SubParsers) -> None:
    group = sub.add_parser("mcp", help=_HELP[""])
    verbs = group.add_subparsers(dest="verb", metavar="{tools}")
    for verb in ("", "tools"):
        command = group if verb == "" else verbs.add_parser(verb, help=_HELP[verb])
        command.add_argument("--project", metavar="REF", default=argparse.SUPPRESS)
        command.add_argument("--token-env", metavar="NAME", default=argparse.SUPPRESS)
        command.add_argument(
            "--local-memory-session",
            type=UUID,
            metavar="UUID",
            default=argparse.SUPPRESS,
            help="serve HOST_PRIVATE episodic memory for a trusted local session",
        )
        if verb == "tools":
            command.add_argument("--json", action="store_true", dest="tools_json")
        command.set_defaults(run=_run, command_name="mcp tools" if verb else "mcp")
    group.set_defaults(project=None, token_env="SKM_TOKEN", local_memory_session=None)


GROUP = CommandGroup("mcp", _HELP[""], register, requires_backend=False)
