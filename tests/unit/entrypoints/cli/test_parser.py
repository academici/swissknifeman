"""Parser, group discovery, ``main`` composition, references, editor and host context (cli §1, §2, §5, §8).

Business groups arrive with later cards, so ``main`` is exercised through fixture groups that are passed to it
explicitly; the one real group (``version``) is checked in ``test_version.py``. Backend groups run in one
``App`` built from explicit test ``CompositionOverrides`` with a fixture Actor; production without a backend
factory is checked to refuse. Nothing here promises persistence between processes.
"""

import argparse
import errno
import importlib
import json
import os
import re
import stat
import sys
import tempfile
import textwrap
from collections.abc import Callable, Generator, Sequence
from functools import cache
from io import StringIO
from pathlib import Path
from typing import IO, Any, override
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator

from fakes.app import FakeScopeChain
from fakes.authorizer import FakeAuthorizer
from skm.application_bus.host import HostServices
from skm.bootstrap.composition import App, CompositionOverrides, build_app
from skm.entrypoints.cli.commands import GROUPS, CommandGroup, GroupRegistryError, SubParsers, discover_groups
from skm.entrypoints.cli.context import CliOptions, CliSession
from skm.entrypoints.cli.editor import edit_document, resolve_editor
from skm.entrypoints.cli.host import build_host_context, host_context_factory
from skm.entrypoints.cli.main import Backend, app_backend, main
from skm.entrypoints.cli.output import ENVELOPE_SCHEMA, escape_terminal, render
from skm.entrypoints.cli.parser import (
    GLOBAL_FLAGS,
    build_parser,
    options_from,
    parse_command_line,
    secret_values,
)
from skm.entrypoints.cli.refs import (
    CliRef,
    RefForm,
    RefKind,
    ScopeSelector,
    default_scope_kind,
    parse_ref,
    parse_scope,
)
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import (
    BackendUnavailable,
    CapabilityUnavailable,
    NotFound,
    SkmError,
    Unauthenticated,
    ValidationFailed,
)
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId, PrincipalId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.settings.generated import commands, queries
from skm.platform.logging import setup
from skm.platform.logging.redaction import MASK, Redactor
from skm.platform.system_clock import SystemClock
from skm.platform.system_ids import Uuid7Generator

OWNER = Actor(PrincipalId(UUID("01900000-0000-7000-8000-0000000000b1")), PrincipalKind.HUMAN, "fixture-owner")
INSTANCE = ScopeId(UUID("01900000-0000-7000-8000-000000000001"))
WORKSPACE = ScopeId(UUID("01900000-0000-7000-8000-0000000000a1"))
ROUNDS = "execution.review.max_rounds"
SECRET = "sentinel-secret-9f3c1d7a"

# cli §3 as a JSON Schema: the shape every ``--json`` document of this card must have.
ENVELOPE = Draft202012Validator(
    {
        "type": "object",
        "required": ["schema", "ok", "command", "request_id"],
        "properties": {
            "schema": {"const": ENVELOPE_SCHEMA},
            "ok": {"type": "boolean"},
            "command": {"type": "string"},
            "request_id": {"type": "string", "pattern": "^cli-"},
        },
        "oneOf": [
            {
                "required": ["result", "diagnostics"],
                "properties": {"ok": {"const": True}, "diagnostics": {"type": "array"}},
            },
            {
                "required": ["outcome", "result"],
                "properties": {
                    "ok": {"const": True},
                    "result": {"type": "null"},
                    "outcome": {"type": "object", "required": ["kind", "code", "message"]},
                },
            },
            {
                "required": ["error"],
                "properties": {
                    "ok": {"const": False},
                    "error": {
                        "type": "object",
                        "required": ["code", "category", "message", "details", "retryable"],
                    },
                },
            },
        ],
    }
)


@pytest.fixture(autouse=True)
def isolated_logging() -> Generator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(setup._state, "settings", setup._state.settings)  # main() reconfigures logging
        yield


# ---------------------------------------------------------------------------------------------------------
# groups and discovery


def group(name: str, run: Callable[[argparse.Namespace, Any], int], **fields: Any) -> CommandGroup:
    def register(sub: SubParsers) -> None:
        parser = sub.add_parser(name, help=f"fixture group {name}")
        parser.add_argument("--key", default=ROUNDS)
        parser.set_defaults(run=run, command_name=f"test.{name}")

    return CommandGroup(name=name, help=f"fixture group {name}", register=register, **fields)


def walk_parsers(parser: argparse.ArgumentParser) -> Generator[argparse.ArgumentParser]:
    yield parser
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for child in action.choices.values():
                yield from walk_parsers(child)


def test_parser_has_every_registered_group(capsys: pytest.CaptureFixture[str]) -> None:
    assert GROUPS, "discovery must find the groups of the package"
    parser = build_parser()
    for registered in GROUPS:
        with pytest.raises(SystemExit) as stop:
            parser.parse_args([registered.name, "--help"])
        assert stop.value.code == 0
        assert registered.name in capsys.readouterr().out
    for child in walk_parsers(parser):
        assert child.format_help()  # --help of every verb renders


def make_package(root: Path, name: str, files: dict[str, str]) -> Any:
    package = root / name
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    for filename, body in files.items():
        (package / filename).write_text(textwrap.dedent(body), encoding="utf-8")
    sys.path.insert(0, str(root))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(root))


GROUP_TEMPLATE = """
from skm.entrypoints.cli.commands import CommandGroup
GROUP = CommandGroup(name={name!r}, help="h", register=lambda sub: None, order={order})
"""


def test_duplicate_group_name_stops_the_start(tmp_path: Path) -> None:
    package = make_package(
        tmp_path,
        "dup_groups",
        {
            "one.py": GROUP_TEMPLATE.format(name="same", order=1),
            "two.py": GROUP_TEMPLATE.format(name="same", order=2),
        },
    )
    with pytest.raises(GroupRegistryError, match=r"'same'.*dup_groups\.one.*dup_groups\.two"):
        discover_groups(package)


def test_discovery_sorts_by_order_then_name_and_ignores_private_modules(tmp_path: Path) -> None:
    package = make_package(
        tmp_path,
        "sorted_groups",
        {
            "zeta.py": GROUP_TEMPLATE.format(name="zeta", order=10),
            "alpha.py": GROUP_TEMPLATE.format(name="alpha", order=100),
            "beta.py": GROUP_TEMPLATE.format(name="beta", order=100),
            "_helpers.py": "VALUE = 1\n",
        },
    )
    assert [g.name for g in discover_groups(package)] == ["zeta", "alpha", "beta"]


def test_a_command_module_without_group_stops_the_start(tmp_path: Path) -> None:
    package = make_package(tmp_path, "headless_groups", {"loose.py": "VALUE = 1\n"})
    with pytest.raises(GroupRegistryError, match="must export GROUP"):
        discover_groups(package)


def test_the_real_registry_is_derived_not_listed() -> None:
    assert list(GROUPS) == sorted(GROUPS, key=lambda g: (g.order, g.name))
    assert len({g.name for g in GROUPS}) == len(GROUPS)


# ---------------------------------------------------------------------------------------------------------
# global flags and usage errors


def test_every_global_flag_is_parsed_before_the_group() -> None:
    parser = build_parser()
    args = parse_command_line(
        parser,
        [
            "--json",
            "-q",
            "-vv",
            "--bootstrap",
            "/b.toml",
            "--instance",
            "work",
            "--scope",
            "project:x",
            "--set",
            "a=1",
            "--set",
            "b=2",
            "--config",
            "/c.toml",
            "--as-token",
            "tok",
            "-y",
            "--no-color",
            "version",
        ],
    )
    assert options_from(args) == CliOptions(
        json=True,
        quiet=True,
        verbosity=2,
        assume_yes=True,
        no_color=True,
        actor_hint="tok",
        scope="project:x",
        instance="work",
        bootstrap="/b.toml",
        sets=("a=1", "b=2"),
        config="/c.toml",
    )
    assert {flag for names, _ in GLOBAL_FLAGS for flag in names} >= {
        "--json",
        "--quiet",
        "--verbose",
        "--bootstrap",
        "--instance",
        "--scope",
        "--set",
        "--config",
        "--as-token",
        "--yes",
        "--no-color",
    }


def run_main(
    argv: Sequence[str],
    *groups: CommandGroup,
    backend: Callable[[CliOptions, Any], Backend] | None = None,
    environ: dict[str, str] | None = None,
    disabled: frozenset[str] = frozenset(),
) -> tuple[int, str, str]:
    out, err = StringIO(), StringIO()
    code = main(
        list(argv),
        environ=environ if environ is not None else {},
        stdout=out,
        stderr=err,
        backend=backend,
        groups=groups,
        disabled_modules=disabled,
    )
    return code, out.getvalue(), err.getvalue()


def ok_group(name: str = "ok") -> CommandGroup:
    return group(
        name,
        lambda args, ctx: render(
            ctx, {"n": 1}, human=lambda value: f"n={value['n']}", command=f"test.{name}"
        ),
        requires_backend=False,
    )


@pytest.mark.parametrize(
    "argv",
    [
        ["--unknown", "ok"],
        ["nonexistent"],
        ["--js", "ok"],  # no abbreviations
        ["ok", "--json"],  # global flags go before the group
        ["ok", "--bogus"],
        [],
        ["--set"],
    ],
)
def test_usage_errors_exit_2_with_a_message_on_stderr(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = run_main(argv, ok_group())
    assert code == 2
    assert out == ""
    assert "skm" in err.splitlines()[0]  # the usage line
    assert err.splitlines()[-1].startswith("skm")
    assert ": error: " in err.splitlines()[-1]
    assert capsys.readouterr() == ("", "")  # main's own stderr, not the process stream


def test_an_unknown_group_is_reported_like_any_unrecognized_argument() -> None:
    code, _, err = run_main(["plan"], ok_group())
    assert code == 2
    assert err.splitlines()[-1] == "skm: error: unrecognized arguments: plan"


def test_a_usage_error_without_streams_goes_to_the_process_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--bogus"], environ={}, groups=[ok_group()]) == 2
    captured = capsys.readouterr()
    assert (captured.out, captured.err.splitlines()[-1]) == (
        "",
        "skm: error: unrecognized arguments: --bogus",
    )


TOKEN = "tok_SENTINEL_0123456789abcdef"
OTHER_TOKEN = "tok_OTHER_fedcba9876543210"
OSC52 = "\x1b]52;c;SGVsbG8=\x07"
RLO = chr(0x202E)  # bidi right-to-left override


def inert(text: str) -> bool:
    """Nothing in ``text`` (newlines aside) would still be escaped: it cannot act on a terminal."""
    flat = text.replace("\n", "")
    return escape_terminal(flat) == flat


@pytest.mark.parametrize(
    "argv",
    [
        ["ok", "--as-token", TOKEN],  # a global flag after the group: misplaced
        [f"--as-token={TOKEN}", "ok", f"--as-token={TOKEN}"],  # equals syntax, misplaced repetition
        ["--as-token", TOKEN, "ok", TOKEN],  # correctly placed, then repeated as a stray argument
        ["--as-token", TOKEN, TOKEN],  # the repeated value in the group position (invalid choice)
        ["--as-token", OTHER_TOKEN, f"--as-token={TOKEN}", "ok", "--bogus", OTHER_TOKEN],  # the shadowed one
        ["--as-tok", TOKEN, "ok"],  # an abbreviation is refused, its value still hidden
        ["--json", "--as-token", TOKEN],  # missing group
        ["--as-token", TOKEN, "--json=" + TOKEN, "ok"],  # argparse quotes the ignored explicit argument
        ["ok", "--as-token", "tok\\with'quote"],  # argparse's repr spelling of the value
    ],
)
def test_usage_errors_never_echo_a_token_value(argv: list[str]) -> None:
    code, out, err = run_main(argv, ok_group())
    assert (code, out) == (2, "")
    error_line = err.splitlines()[-1]
    assert ": error: " in error_line
    for secret in (TOKEN, OTHER_TOKEN, "tok\\with'quote", "tok\\\\with'quote", "with'quote"):
        assert secret not in err
    assert MASK in error_line or "required" in error_line


def test_a_short_token_is_masked_in_the_usage_error_too() -> None:
    code, _, err = run_main(["ok", "--as-token", "abc"], ok_group())
    assert code == 2
    assert "abc" not in err.splitlines()[-1]


def test_the_real_version_group_does_not_echo_a_misplaced_token() -> None:
    out, err = StringIO(), StringIO()
    assert main(["version", "--as-token", TOKEN], environ={}, stdout=out, stderr=err) == 2
    assert (out.getvalue(), TOKEN in err.getvalue()) == ("", False)
    assert err.getvalue().splitlines()[-1] == f"skm: error: unrecognized arguments: --as-token {MASK}"


def test_usage_error_text_cannot_drive_the_terminal() -> None:
    hostile = f"{OSC52}x\rerror: FORGED: injected\n{RLO}hint"
    code, out, err = run_main(["ok", hostile], ok_group())
    assert (code, out) == (2, "")
    assert inert(err)
    assert "\x1b" not in err
    assert not any(line.startswith("error: FORGED") for line in err.splitlines())
    assert err.splitlines()[-1] == (
        "skm: error: unrecognized arguments: "
        "\\x1b]52;c;SGVsbG8=\\x07x\\rerror: FORGED: injected\\n\\u202ehint"
    )


def test_help_and_version_still_exit_0_with_a_token_on_the_line(capsys: pytest.CaptureFixture[str]) -> None:
    for help_args in (["--help"], ["ok", "--help"]):
        code, out, err = run_main(["--as-token", TOKEN, *help_args], ok_group())
        assert (code, err) == (0, "")
        assert out.startswith("usage: skm")
        assert TOKEN not in out
    assert capsys.readouterr() == ("", "")
    assert main(["--as-token", TOKEN, "--version"], environ={}, groups=[ok_group()]) == 0
    assert capsys.readouterr().out.strip() != ""


def test_secret_values_finds_every_spelling_and_position() -> None:
    argv = ["--as-token", "a1", "--as-token=b2", "grp", "--as-token", "c3", "--as=d4", "--as-token="]
    assert secret_values(argv) == ("a1", "b2", "c3", "d4")
    assert secret_values(["--as-token"]) == ()
    assert secret_values(["--a", "x", "--json", "y"]) == ()


def test_a_known_group_runs_and_help_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_main(["ok"], ok_group()) == (0, "n=1\n", "")
    code, out, err = run_main(["--help"], ok_group())
    assert (code, err) == (0, "")
    assert "ok" in out
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("selected", [False, True])
@pytest.mark.parametrize("token", ["Z9SECRET", "x1b", 'ab"cd', "☃X"])
def test_help_protects_program_and_group_names_on_the_selected_stdout(
    selected: bool, token: str, capsys: pytest.CaptureFixture[str]
) -> None:
    spelling = json.dumps(token, ensure_ascii=True)[1:-1]
    name = f"pre{token}{spelling}post{OSC52}"
    code, out, err = run_main(["--as-token", token, *([name] if selected else []), "--help"], ok_group(name))
    assert (code, err) == (0, "")
    assert out.startswith("usage: skm")
    assert token not in out
    assert spelling not in out
    assert MASK in out
    assert inert(out)
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("supplied_stdout", [False, True])
def test_parse_command_line_protects_automatic_help_and_restores_its_sink(
    supplied_stdout: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    parser = build_parser([ok_group()])
    parser.prog = f"tool-Z9SECRET{OSC52}"
    out, err = StringIO(), StringIO()
    with pytest.raises(SystemExit) as stop:
        parse_command_line(
            parser,
            ["--as-token", "Z9SECRET", "--help"],
            stdout=out if supplied_stdout else None,
            stderr=err,
        )
    assert stop.value.code == 0
    process = capsys.readouterr()
    shown = out.getvalue() if supplied_stdout else process.out
    assert shown.startswith(f"usage: tool-{MASK}\\x1b")
    assert "Z9SECRET" not in shown
    assert inert(shown)
    assert err.getvalue() == process.err == ""
    assert (process.out if supplied_stdout else out.getvalue()) == ""
    with pytest.raises(SystemExit) as next_stop:
        parse_command_line(build_parser([ok_group()]), ["--help"])
    assert next_stop.value.code == 0
    assert capsys.readouterr().out.startswith("usage: skm")


@pytest.mark.parametrize("json_mode", [False, True])
def test_nested_group_help_uses_the_invocations_protected_stdout(
    json_mode: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    def register(sub: SubParsers) -> None:
        parent = sub.add_parser("nested")
        verbs = parent.add_subparsers(dest="verb")
        verbs.add_parser(f"preZ9SECRETpost{OSC52}")

    nested = CommandGroup("nested", "fixture", register, requires_backend=False)
    code, out, err = run_main(
        [
            *(["--json"] if json_mode else []),
            "--as-token=Z9SECRET",
            "nested",
            f"preZ9SECRETpost{OSC52}",
            "-h",
        ],
        nested,
    )
    assert (code, err) == (0, "")
    assert out.startswith(f"usage: skm nested pre{MASK}post\\x1b")
    assert "Z9SECRET" not in out
    assert inert(out)
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("json_flag", [False, True])
@pytest.mark.parametrize(
    ("token", "component", "event"),
    [
        ('review.component","event":"review.event', MASK, MASK),
        ('component","event":"review', f"review.{MASK}", f"{MASK}.event"),
        ('component","event":', f"review.{MASK}", "review.event"),
        ('","event":"review.event', "review.component", MASK),
    ],
)
def test_main_seals_json_logs_across_projected_metadata_and_fixed_members(
    json_flag: bool, token: str, component: str, event: str, capsys: pytest.CaptureFixture[str]
) -> None:
    class Private:
        @override
        def __str__(self) -> str:
            raise AssertionError("private log fields must never be inspected")

    def log(args: argparse.Namespace, ctx: Any) -> int:
        setup.emit(
            "review.component",
            "info",
            "review.event",
            {"message": "private prose", "payload": Private(), "token": token, "duration_ms": 12},
        )
        return 0

    code, out, err = run_main(
        [*(["--json"] if json_flag else []), "--as-token", token, "log"],
        group("log", log, requires_backend=False),
    )
    assert (code, out) == (0, "")
    assert token not in err
    assert inert(err)
    assert err.count("\n") == 1
    record = json.loads(err)
    assert set(record) == {"ts", "level", "component", "event", "pid", "host"}
    assert (record["component"], record["event"]) == (component, event)
    assert record["level"] == "info"
    assert record["host"] == "localhost"
    assert type(record["pid"]) is int
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("tty", [False, True])
@pytest.mark.parametrize("json_flag", [False, True])
def test_cli_logs_keep_projected_keys_and_filter_private_data_on_both_stream_formats(
    tty: bool, json_flag: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    def log(args: argparse.Namespace, ctx: Any) -> int:
        setup.emit(
            "review.component",
            "info",
            "bus.command.started",
            {
                "operation": "settings.get_host_config",
                "schema_urn": "urn:skm:settings:query:get-host-config:v1",
                "duration_ms": 12,
                "payload": "private fixture text",
            },
        )
        return 0

    out, err = StringIO(), Tty() if tty else StringIO()
    assert (
        main(
            [*(["--json"] if json_flag else []), "-vv", "--as-token", "component", "log"],
            environ={},
            stdout=out,
            stderr=err,
            groups=[group("log", log, requires_backend=False)],
        )
        == 0
    )
    shown = err.getvalue()
    assert "private fixture text" not in shown
    assert out.getvalue() == ""
    assert inert(shown)
    if json_flag or not tty:
        record = json.loads(shown)
        assert set(record) == {
            "ts",
            "level",
            "component",
            "event",
            "pid",
            "host",
            "operation",
            "schema_urn",
            "duration_ms",
        }
        assert record["component"] == f"review.{MASK}"
        assert record["operation"] == "settings.get_host_config"
        assert record["schema_urn"] == "urn:skm:settings:query:get-host-config:v1"
        assert record["duration_ms"] == 12
    else:
        assert f"info review.{MASK} bus.command.started" in shown
        assert 'operation="settings.get_host_config"' in shown
    assert capsys.readouterr() == ("", "")


def test_main_seals_log_credentials_touching_numeric_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup.os, "getpid", lambda: 1234)
    token = '1234,"host":"localhost'

    def log(args: argparse.Namespace, ctx: Any) -> int:
        setup.emit("review.component", "info", "review.event", {})
        return 0

    code, out, err = run_main(["--as-token", token, "log"], group("log", log, requires_backend=False))
    assert (code, out) == (0, "")
    assert token not in err
    record = json.loads(err)
    assert set(record) == {"ts", "level", "component", "event", "pid", "host"}
    # Masking the whole numeric scalar breaks the credential at the join.
    assert record["pid"] == MASK
    assert record["host"] == "localhost"
    assert (record["component"], record["event"]) == ("review.component", "review.event")


# ---------------------------------------------------------------------------------------------------------
# error mapping through main


def raising(error: BaseException) -> CommandGroup:
    def run(args: argparse.Namespace, ctx: Any) -> int:
        raise error

    return group("boom", run, requires_backend=False)


@pytest.mark.parametrize(
    ("error", "exit_code", "category"),
    [
        (
            ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "draft document does not match urn:skm:planning:specification:v1",
                details={"issues": [{"pointer": "/items/1", "code": "enum", "message": "bad"}]},
            ),
            1,
            "validation",
        ),
        (NotFound(ErrorCode.NOT_FOUND, "no such plan"), 1, "not_found"),
        (Unauthenticated(ErrorCode.UNAUTHENTICATED, "token expired"), 5, "unauthenticated"),
        (BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "database is not reachable"), 3, "backend"),
        (CapabilityUnavailable(ErrorCode.CAPABILITY_UNAVAILABLE, "no runtime"), 6, "capability"),
    ],
)
def test_structured_errors_exit_by_category_in_human_and_json(
    error: SkmError, exit_code: int, category: str
) -> None:
    code, out, err = run_main(["boom"], raising(error))
    assert (code, out) == (exit_code, "")
    assert err.startswith(f"error: {error.code.value}: ")
    code, out, err = run_main(["--json", "boom"], raising(error))
    assert (code, err) == (exit_code, "")
    document = json.loads(out)
    ENVELOPE.validate(document)
    assert (document["ok"], document["command"], document["error"]["category"]) == (
        False,
        "test.boom",
        category,
    )
    assert document["error"]["code"] == error.code.value


def test_interrupt_is_130_and_an_unexpected_exception_is_70() -> None:
    assert run_main(["boom"], raising(KeyboardInterrupt()))[0] == 130
    code, _, err = run_main(["boom"], raising(RuntimeError(f"password={SECRET}1234")))
    assert code == 70
    assert SECRET not in err
    assert "Traceback" not in err
    code, _, err = run_main(["-vv", "boom"], raising(RuntimeError(f"password={SECRET}1234")))
    assert (code, "Traceback" in err, SECRET in err) == (70, True, False)


def test_the_as_token_value_is_masked_everywhere() -> None:
    token = "tok_0123456789abcdef0123"
    code, out, err = run_main(
        ["--as-token", token, "--json", "boom"],
        raising(ValidationFailed(ErrorCode.CONFIG_INVALID, f"bad value {token}")),
    )
    assert code == 1
    assert token not in out + err


def test_every_repeated_as_token_value_is_masked_after_parsing() -> None:
    error = ValidationFailed(ErrorCode.CONFIG_INVALID, f"bad values {TOKEN} {OTHER_TOKEN}")
    for flags in ([], ["--json"]):
        code, out, err = run_main(
            [*flags, "--as-token", TOKEN, f"--as-token={OTHER_TOKEN}", "boom"], raising(error)
        )
        assert code == 1
        assert TOKEN not in out + err
        assert OTHER_TOKEN not in out + err


SHORT_TOKENS = ("Q", "q7", "Zq7", "k3Y9", "Wp2xK", "aB3dE5", "Xy7Qp2Z")  # 1..7 characters


def short_spellings(token: str) -> list[list[str]]:
    other = token[::-1] + "9"
    return [
        ["--as-token", token],  # split
        [f"--as-token={token}"],  # equals
        ["--as-token", other, f"--as-token={token}"],  # repeated: argparse keeps the last one
        [f"--as-token={token}", "--as-token", other],  # repeated: the shadowed one is the token
    ]


@pytest.mark.parametrize("token", SHORT_TOKENS)
def test_a_short_as_token_is_masked_in_post_parse_errors_text_and_json(token: str) -> None:
    other = token[::-1] + "9"
    error = ValidationFailed(
        ErrorCode.CONFIG_INVALID, f"bad token '{token}' or {other}", details={"token": token}
    )
    for flags in short_spellings(token):
        masked_other = MASK if other in " ".join(flags) else (f"{MASK}9" if len(token) == 1 else other)
        expected = f"bad token '{MASK}' or {masked_other}"
        code, out, err = run_main([*flags, "boom"], raising(error))
        assert (code, out) == (1, "")
        assert err == f"error: CONFIG_INVALID: {expected}\n"
        code, out, err = run_main([*flags, "--json", "boom"], raising(error))
        document = json.loads(out)
        ENVELOPE.validate(document)
        assert (code, err) == (1, "")
        assert document["error"]["message"] == expected
        assert document["error"]["details"] == {"token": MASK}


@pytest.mark.parametrize("token", SHORT_TOKENS)
def test_a_short_as_token_is_masked_in_cleanup_failures_and_keeps_normal_output(token: str) -> None:
    backend = failing_close(RuntimeError(f"close failed for x{token}y"))
    ok = group("done", lambda args, ctx: render(ctx, {"n": 1}, human=lambda _: "done", command="test.done"))
    for flags in short_spellings(token):
        code, out, err = run_main([*flags, "-vv", "done"], ok, backend=backend)
        assert (code, out) == (70, "done\n")
        assert INTERNAL_LINE.match(err.splitlines()[0])
        assert f"RuntimeError: close failed for x{MASK}y" in err.splitlines()
        assert token not in out + err
        code, out, err = run_main([*flags, "--json", "-vv", "done"], ok, backend=backend)
        document = json.loads(out)
        ENVELOPE.validate(document)
        assert (code, document["ok"], document["result"]) == (70, True, {"n": 1})
        assert f"RuntimeError: close failed for x{MASK}y" in err.splitlines()
        assert token not in out + err
        assert run_main([*flags, "ok"], ok_group()) == (0, "n=1\n", "")


def test_a_short_as_token_never_corrupts_the_envelope_framing() -> None:
    for token in ("ok", "cli", "skm", "v1", "error", "boom"):
        error = NotFound(ErrorCode.NOT_FOUND, f"no {token} here")
        code, out, _ = run_main(["--as-token", token, "--json", "boom"], raising(error))
        document = json.loads(out)
        ENVELOPE.validate(document)
        assert (code, document["command"], document["error"]["message"]) == (
            1,
            f"test.{MASK}" if token == "boom" else "test.boom",
            f"no {MASK} here",
        )


@pytest.mark.parametrize("token", SHORT_TOKENS)
def test_a_short_as_token_is_hidden_inside_alphanumeric_usage_errors(token: str) -> None:
    for flags in short_spellings(token):
        code, out, err = run_main([*flags, "ok", f"x{token}y"], ok_group())
        assert (code, out) == (2, "")
        assert token not in err
        assert f"x{MASK}y" in err


def test_usage_masks_overlaps_and_secrets_created_by_terminal_escaping() -> None:
    code, _, err = run_main(["--as-token", "ab", "--as-token", "bc", "ok", "zabcx"], ok_group())
    assert code == 2
    assert err.splitlines()[-1].endswith(f"z{MASK}x")
    code, _, err = run_main(["--as-token", "x1b", "ok", "\x1b"], ok_group())
    assert code == 2
    assert "x1b" not in err


def test_usage_and_error_program_names_are_untrusted_after_the_executable() -> None:
    code, out, err = run_main(["--as-token", "Q", "preQpost", "--key"], ok_group("preQpost"))
    assert (code, out) == (2, "")
    assert "Q" not in err
    assert err.startswith(f"usage: skm pre{MASK}post ")
    assert err.splitlines()[-1].startswith(f"skm pre{MASK}post: error: ")


def test_short_tokens_inside_post_parse_error_keys_and_values_are_hidden() -> None:
    code, out, err = run_main(
        ["--as-token", "Q", "--json", "boom"],
        raising(ValidationFailed(ErrorCode.CONFIG_INVALID, "xQy", details={"zQ0": ["xQy"]})),
    )
    assert (code, err) == (1, "")
    assert "Q" not in out
    document = json.loads(out)
    ENVELOPE.validate(document)
    assert document["error"]["message"] == f"x{MASK}y"
    assert document["error"]["details"] == {f"z{MASK}0": [f"x{MASK}y"]}


# ---------------------------------------------------------------------------------------------------------
# optional modules


def test_a_group_of_a_disabled_module_is_hidden_and_answers_module_disabled(
    capsys: pytest.CaptureFixture[str],
) -> None:
    hidden = group("lessons", lambda args, ctx: 0, module="knowledge", requires_backend=False)
    parser = build_parser([ok_group(), hidden], disabled_modules=frozenset({"knowledge"}))
    assert "lessons" not in parser.format_help()
    assert "lessons" in build_parser([ok_group(), hidden]).format_help()
    code, out, err = run_main(
        ["lessons", "anything", "--at-all"], ok_group(), hidden, disabled=frozenset({"knowledge"})
    )
    assert (code, out) == (6, "")
    assert err.startswith("error: MODULE_DISABLED: ")
    assert run_main(["lessons"], ok_group(), hidden)[0] == 0  # enabled: the real group runs


# ---------------------------------------------------------------------------------------------------------
# backend composition


def test_production_without_bootstrap_says_so_with_a_hint(tmp_path: Path) -> None:
    needs_backend = group("needs", lambda args, ctx: 0)
    code, out, err = run_main(["needs"], needs_backend, environ={"HOME": str(tmp_path)})
    assert (code, out) == (6, "")
    assert err.splitlines()[0].startswith("error: BOOTSTRAP_MISSING: ")
    assert "hint: skm init" in err.splitlines()


def test_production_with_a_bootstrap_composes_for_real_and_has_no_fallback(tmp_path: Path) -> None:
    """The default backend composes the production application: a bootstrap without a token pepper stops
    with SECRET_UNAVAILABLE before any connection, and the command never runs as a fallback actor."""
    ran: list[str] = []

    def run(args: argparse.Namespace, ctx: Any) -> int:
        ran.append("ran")
        return 0

    needs_backend = group("needs", run)
    env = {"HOME": str(tmp_path), "SKM_DATABASE_URL": "postgresql://unused"}
    code, out, err = run_main(["--json", "needs"], needs_backend, environ=env)
    assert code == 6
    document = json.loads(out)
    ENVELOPE.validate(document)
    assert document["error"]["code"] == "SECRET_UNAVAILABLE"
    assert document["error"]["details"]["field"] == "secrets.token_pepper"
    assert (ran, err) == ([], "")


@cache
def shared_app() -> tuple[App, FakeAuthorizer]:
    authorizer = FakeAuthorizer()
    app = build_app(
        load_bootstrap_for_tests(),
        surface=Surface.CLI,
        environ={},
        invocation={},
        overrides=CompositionOverrides(authorizer=authorizer, scopes=FakeScopeChain()),
    )
    with app.uow_factory(RequestMeta("req_" + "0" * 26, Surface.CLI, None, SystemClock().now())) as uow:
        scopes = uow.repo(ScopeRegistry)
        scopes.create(INSTANCE, ScopeKind.INSTANCE, parent=None, workspace_id=None)
        scopes.create(WORKSPACE, ScopeKind.WORKSPACE, parent=INSTANCE, workspace_id=WorkspaceId(WORKSPACE))
        uow.commit()
    return app, authorizer


def load_bootstrap_for_tests() -> Any:
    from skm.platform.config.bootstrap import load_bootstrap

    return load_bootstrap(None, {"SKM_DATABASE_URL": "postgresql://unused"}, Path("/nonexistent-home"))


def get_value_group() -> CommandGroup:
    def run(args: argparse.Namespace, ctx: Any) -> int:
        view = ctx.client.ask(
            queries.GetValue(
                scope=queries.GetValueDefsScopeRef(
                    level="workspace", scope_id=ctx.resolve_scope(f"workspace:{WORKSPACE}").id
                ),
                key=args.key,
            )
        )
        return render(ctx, view, human=lambda v: f"{args.key} = {v.value}", command="settings.get_value")

    return group("cfg-get", run)


def embedded(app: App) -> Callable[[CliOptions, Any], Backend]:
    return lambda options, environ: app_backend(app, OWNER)


def test_a_backend_group_runs_in_one_app_with_a_fixture_actor() -> None:
    app, authorizer = shared_app()
    authorizer.allow_all()
    app.client(actor=OWNER, surface=Surface.CLI).dispatch(
        commands.SetValue(
            scope=commands.SetValueDefsScopeRef(level="workspace", scope_id=WORKSPACE),
            key=ROUNDS,
            value=3,
            reason="fixture",
        )
    )
    code, out, err = run_main(["cfg-get"], get_value_group(), backend=embedded(app))
    assert (code, out, err) == (0, f"{ROUNDS} = 3\n", "")
    code, out, _ = run_main(["--json", "cfg-get"], get_value_group(), backend=embedded(app))
    document = json.loads(out)
    ENVELOPE.validate(document)
    assert (code, document["result"]["value"], document["command"]) == (0, 3, "settings.get_value")


def test_unknown_key_is_a_validation_exit_1_and_forbidden_is_exit_5() -> None:
    app, authorizer = shared_app()
    authorizer.allow_all()
    code, out, err = run_main(
        ["--json", "cfg-get", "--key", "nope.key"], get_value_group(), backend=embedded(app)
    )
    assert (code, err) == (1, "")
    assert json.loads(out)["error"]["code"] == "CONFIG_UNKNOWN_KEY"
    authorizer.deny_all()
    try:
        code, out, err = run_main(["cfg-get"], get_value_group(), backend=embedded(app))
        assert (code, out) == (5, "")
        assert err.startswith("error: FORBIDDEN: ")
        code, out, _ = run_main(["--json", "cfg-get"], get_value_group(), backend=embedded(app))
        document = json.loads(out)
        ENVELOPE.validate(document)
        assert (code, document["error"]["category"]) == (5, "forbidden")
    finally:
        authorizer.allow_all()


def test_the_backend_is_closed_after_the_command() -> None:
    closed: list[bool] = []

    def factory(options: CliOptions, environ: Any) -> Backend:
        app, _ = shared_app()
        return Backend(client=app.client(actor=OWNER, surface=Surface.CLI), close=lambda: closed.append(True))

    run_main(["boom"], group("boom", lambda args, ctx: 0), backend=factory)
    assert closed == [True]


def failing_close(error: BaseException) -> Callable[[CliOptions, Any], Backend]:
    def close() -> None:
        raise error

    def factory(options: CliOptions, environ: Any) -> Backend:
        app, _ = shared_app()
        return Backend(client=app.client(actor=OWNER, surface=Surface.CLI), close=close)

    return factory


INTERNAL_LINE = re.compile(
    r"^error: INTERNAL_ERROR: unexpected failure \(request cli-[0-9a-f-]+\); see logs$"
)


def test_a_failing_cleanup_after_success_is_an_internal_error_not_an_escaped_exception() -> None:
    backend = failing_close(RuntimeError(f"close failed password={SECRET}1234 {OSC52}"))
    ok = group("done", lambda args, ctx: render(ctx, {"n": 1}, human=lambda _: "done", command="test.done"))
    code, out, err = run_main(["done"], ok, backend=backend)
    assert (code, out) == (70, "done\n")
    assert INTERNAL_LINE.match(err.splitlines()[0])
    assert SECRET not in err
    code, out, err = run_main(["--json", "done"], ok, backend=backend)
    assert code == 70
    document = json.loads(out)  # still exactly one envelope on stdout
    ENVELOPE.validate(document)
    assert document["ok"] is True
    assert INTERNAL_LINE.match(err.splitlines()[0])
    code, _, err = run_main(["-vv", "done"], ok, backend=backend)
    assert (code, "Traceback" in err, SECRET in err, "\x1b" in err) == (70, True, False, False)


def test_a_failing_cleanup_never_replaces_the_command_error() -> None:
    backend = failing_close(RuntimeError(f"close failed {SECRET}"))

    def run(args: argparse.Namespace, ctx: Any) -> int:
        _ = ctx.client  # the backend is attached
        raise NotFound(ErrorCode.NOT_FOUND, "no plan")

    failed = group("boom", run)
    code, out, err = run_main(["boom"], failed, backend=backend)
    assert (code, out) == (1, "")
    assert err.splitlines()[0] == "error: NOT_FOUND: no plan"
    assert INTERNAL_LINE.match(err.splitlines()[1])
    code, out, err = run_main(["--json", "boom"], failed, backend=backend)
    assert code == 1
    assert json.loads(out)["error"]["code"] == "NOT_FOUND"
    assert SECRET not in out + err


def test_an_interrupted_cleanup_is_130() -> None:
    ok = group("done", lambda args, ctx: 0)
    assert run_main(["done"], ok, backend=failing_close(KeyboardInterrupt()))[0] == 130


def test_a_group_without_backend_never_calls_the_factory() -> None:
    def refuse(options: CliOptions, environ: Any) -> Backend:
        raise AssertionError("no backend expected")

    assert run_main(["ok"], ok_group(), backend=refuse)[0] == 0


# ---------------------------------------------------------------------------------------------------------
# references and scopes


def session(tmp_path: Path | None = None, **fields: Any) -> tuple[CliSession, StringIO, StringIO]:
    out, err = StringIO(), StringIO()
    ids = Uuid7Generator(SystemClock())
    options = fields.pop("options", CliOptions())
    return (
        CliSession(
            options=options,
            stdout=out,
            stderr=err,
            redactor=Redactor(),
            ids=ids,
            request_id="cli-test",
            state_dir=tmp_path,
            **fields,
        ),
        out,
        err,
    )


U = "0192f5c5-0b33-7c44-9a00-2b3c4d5e6f70"


@pytest.mark.parametrize(
    ("kind", "text", "form"),
    [
        (RefKind.WORKSPACE, "personal", RefForm.SLUG),
        (RefKind.WORKSPACE, f"workspace:{U}", RefForm.UUID),
        (RefKind.PROJECT, "skm", RefForm.SLUG),
        (RefKind.PROJECT, "personal/skm", RefForm.QUALIFIED_SLUG),
        (RefKind.PROJECT, f"project:{U}", RefForm.UUID),
        (RefKind.PLAN, "PLAN7", RefForm.ALIAS),
        (RefKind.PLAN, f"plan:{U}", RefForm.UUID),
        (RefKind.PLAN, "0192f5c50b33", RefForm.PREFIX),
        (RefKind.REVISION, "3", RefForm.NUMBER),
        (RefKind.REVISION, "r3", RefForm.NUMBER),
        (RefKind.REVISION, f"revision:{U}", RefForm.UUID),
        (RefKind.DRAFT, f"draft:{U}", RefForm.UUID),
        (RefKind.ENTITY, "P2", RefForm.DISPLAY_KEY),
        (RefKind.ENTITY, "P2.4/U1", RefForm.DISPLAY_KEY),
        (RefKind.ENTITY, "V1@P2.4", RefForm.DISPLAY_KEY),
        (RefKind.ENTITY, f"entity:{U}", RefForm.UUID),
        (RefKind.RUN, "last", RefForm.LAST),
        (RefKind.RUN, "0192f5c70b33", RefForm.PREFIX),  # cli §5.1: a run prefix has ≥ 12 hex
        (RefKind.RUN, "0192F5C7-0B33", RefForm.PREFIX),
        (RefKind.ATTEMPT, "0192f5c7", RefForm.PREFIX),  # other kinds keep their own minimum
        (RefKind.RUN, f"run:{U}", RefForm.UUID),
        (RefKind.TASK, "P2.4/U1", RefForm.DISPLAY_KEY),
        (RefKind.TASK, f"task:{U}", RefForm.UUID),
        (RefKind.REQUEST, f"req:{U}", RefForm.UUID),
        (RefKind.FILE_VERSION, f"fv:{U}", RefForm.UUID),
        (RefKind.FILE, "0192f5c50b33", RefForm.PREFIX),
        (RefKind.HOST, "laptop", RefForm.SLUG),
        (RefKind.TOKEN, "local-owner-cli", RefForm.SLUG),
        (RefKind.TOKEN, f"token:{U}", RefForm.UUID),
    ],
)
def test_parse_ref_accepts_the_documented_forms(kind: RefKind, text: str, form: RefForm) -> None:
    ref = parse_ref(kind, text)
    assert (ref.kind, ref.form, ref.text) == (kind, form, text.lower() if form is RefForm.PREFIX else text)
    assert (ref.uuid == UUID(U)) is (form is RefForm.UUID)


@pytest.mark.parametrize(
    ("kind", "text"),
    [
        (RefKind.PLAN, "PLAN"),  # example 09
        (RefKind.PLAN, "PLAN0"),
        (RefKind.PLAN, "0192f5c5"),  # a plan prefix needs ≥ 12 hex
        (RefKind.PLAN, "plan:not-a-uuid"),
        (RefKind.PROJECT, "a/b/c"),
        (RefKind.PROJECT, "Bad Slug"),
        (RefKind.REVISION, "0"),
        (RefKind.REVISION, "latest"),
        (RefKind.DRAFT, "open"),
        (RefKind.ENTITY, "p2"),
        (RefKind.RUN, "nothex!"),
        (RefKind.RUN, "abc"),
        (RefKind.RUN, "0192f5c7"),  # 8 hex: example 09's spelling, below the explicit run minimum
        (RefKind.RUN, "0192f5c70"),
        (RefKind.RUN, "0192f5c70b"),
        (RefKind.RUN, "0192f5c70b3"),
        (RefKind.RUN, "0192f5c7-0b3"),  # 11 hex digits with a hyphen
        (RefKind.TASK, "u1"),
        (RefKind.WORKSPACE, ""),
        (RefKind.WORKSPACE, f"project:{U}"),  # another kind's prefix
    ],
)
def test_parse_ref_rejects_everything_else_as_invalid_reference(kind: RefKind, text: str) -> None:
    with pytest.raises(ValidationFailed) as caught:
        parse_ref(kind, text)
    assert caught.value.code is ErrorCode.INVALID_REFERENCE
    assert caught.value.details["kind"] == kind.value
    assert caught.value.details["ref"] == text


def test_the_invalid_plan_message_matches_example_09() -> None:
    with pytest.raises(ValidationFailed) as caught:
        parse_ref(RefKind.PLAN, "PLAN")
    assert caught.value.message == (
        '"PLAN" is not a plan reference (expected PLAN<n>, plan:<uuid> or a uuid prefix of ≥ 12 hex)'
    )


def test_the_invalid_run_message_names_the_12_hex_minimum() -> None:
    with pytest.raises(ValidationFailed) as caught:
        parse_ref(RefKind.RUN, "0192f5c7")
    assert caught.value.message == (
        '"0192f5c7" is not a run reference (expected run:<uuid>, a uuid prefix of ≥ 12 hex or last)'
    )


def test_an_absent_reference_is_the_current_form() -> None:
    assert parse_ref(RefKind.REVISION, None) == CliRef(RefKind.REVISION, RefForm.CURRENT, "")


@pytest.mark.parametrize(
    ("text", "kind", "ref"),
    [
        ("instance", ScopeKind.INSTANCE, None),
        ("workspace", ScopeKind.WORKSPACE, None),
        ("workspace:personal", ScopeKind.WORKSPACE, "personal"),
        ("project", ScopeKind.PROJECT, None),
        ("project:skm", ScopeKind.PROJECT, "skm"),
        ("plan:PLAN7", ScopeKind.PLAN, "PLAN7"),
        ("run:last", ScopeKind.RUN, "last"),
        ("host", ScopeKind.HOST, None),
        ("host:laptop", ScopeKind.HOST, "laptop"),
    ],
)
def test_parse_scope_accepts_the_selector_grammar(text: str, kind: ScopeKind, ref: str | None) -> None:
    assert parse_scope(text) == ScopeSelector(kind, ref)


@pytest.mark.parametrize("text", ["", "global", "instance:x", "plan", "run", "project:", "Workspace:x"])
def test_parse_scope_rejects_bad_selectors(text: str) -> None:
    with pytest.raises(ValidationFailed) as caught:
        parse_scope(text)
    assert caught.value.code is ErrorCode.INVALID_REFERENCE


def test_default_scope_is_project_then_workspace_then_instance() -> None:
    assert default_scope_kind(project=True, workspace=True) is ScopeKind.PROJECT
    assert default_scope_kind(project=False, workspace=True) is ScopeKind.WORKSPACE
    assert default_scope_kind(project=False, workspace=False) is ScopeKind.INSTANCE


def test_explicit_uuid_references_resolve_without_a_lookup() -> None:
    ctx, _, _ = session()
    assert ctx.resolve_workspace(f"workspace:{U}") == WorkspaceId(UUID(U))
    assert ctx.resolve_scope(f"project:{U}") == ScopeRef(ScopeKind.PROJECT, ScopeId(UUID(U)))
    assert ctx.resolve_host(f"host:{U}") == HostId(UUID(U))


def test_references_that_need_a_query_say_so_instead_of_guessing() -> None:
    ctx, _, _ = session()
    with pytest.raises(CapabilityUnavailable) as caught:
        ctx.resolve_workspace("personal")
    assert caught.value.details == {
        "kind": "workspace",
        "form": "slug",
        "hint": "pass workspace:<uuid> or the bare uuid",
    }
    with pytest.raises(ValidationFailed):
        ctx.resolve_plan("PLAN")
    with pytest.raises(ValidationFailed, match="needs a run"):
        ctx.resolve_task(None, "P2.4/U1")


def test_cli_context_file_is_the_default_and_is_written_privately(tmp_path: Path) -> None:
    instance = UUID("0192f5c4-6e1a-7c3b-9a52-1f0d2c3b4a59")
    ctx, _, _ = session(tmp_path, instance_id=instance)
    with pytest.raises(NotFound) as caught:
        ctx.resolve_workspace(None)
    assert caught.value.details["hint"] == "skm use"
    ctx.save_context(workspace_id=U, workspace_slug="personal")
    path = tmp_path / "cli-context.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    saved = json.loads(path.read_text())
    assert saved == {
        "schema": "urn:skm:cli:context:v1",
        "instance_id": str(instance),
        "workspace_id": U,
        "workspace_slug": "personal",
    }
    fresh, _, _ = session(tmp_path, instance_id=instance)
    assert fresh.resolve_workspace(None) == WorkspaceId(UUID(U))
    assert fresh.resolve_scope(None).kind is ScopeKind.WORKSPACE  # no project saved: workspace
    fresh.save_context(workspace_id=None)
    with pytest.raises(NotFound):
        session(tmp_path, instance_id=instance)[0].resolve_workspace(None)


def test_cli_context_of_another_instance_is_ignored_with_a_warning(tmp_path: Path) -> None:
    writer, _, _ = session(tmp_path, instance_id=UUID(int=1))
    writer.save_context(workspace_id=U)
    reader, _, err = session(tmp_path, instance_id=UUID(int=2))
    with pytest.raises(NotFound):
        reader.resolve_workspace(None)
    assert "another instance" in err.getvalue()


@pytest.mark.parametrize("text", ["{not json", "[]", '"workspace"', "null"])
def test_an_unreadable_cli_context_is_ignored_with_a_warning(tmp_path: Path, text: str) -> None:
    (tmp_path / "cli-context.json").write_text(text, encoding="utf-8")
    reader, _, err = session(tmp_path, instance_id=UUID(int=1))
    with pytest.raises(NotFound):
        reader.resolve_workspace(None)
    assert "cli-context.json is unreadable" in err.getvalue()


def test_context_cannot_be_saved_without_a_state_dir_or_with_unknown_keys(tmp_path: Path) -> None:
    with pytest.raises(ValidationFailed):
        session()[0].save_context(workspace_id=U)
    with pytest.raises(ValidationFailed):
        session(tmp_path)[0].save_context(token="x")


def test_idempotency_keys_are_cli_prefixed_and_unique() -> None:
    ctx, _, _ = session()
    keys = {ctx.new_idempotency_key() for _ in range(5)}
    assert len(keys) == 5
    assert all(key.startswith("cli-") and UUID(key.removeprefix("cli-")).version == 7 for key in keys)


def test_confirm_follows_yes_and_the_terminal() -> None:
    assert session(options=CliOptions(assume_yes=True))[0].confirm("really?") is True
    assert session()[0].confirm("really?") is False  # StringIO stdin is not a terminal

    class Tty(StringIO):
        @override
        def isatty(self) -> bool:
            return True

    for answer, expected in (("y\n", True), ("no\n", False), ("\n", False)):
        ctx, _, err = session(stdin=Tty(answer))
        assert ctx.confirm("drop it?") is expected
        assert "drop it? [y/N]" in err.getvalue()


class Tty(StringIO):
    @override
    def isatty(self) -> bool:
        return True


@pytest.mark.parametrize("no_color", [False, True])
def test_a_confirmation_prompt_is_redacted_and_escaped_before_the_suffix(no_color: bool) -> None:
    ctx, out, err = session(stdin=Tty("n\n"), options=CliOptions(no_color=no_color))
    ctx.redactor.register_secret(SECRET)
    hostile = f"drop {OSC52}plan\nerror: FORGED: approved\r{RLO}txt.exe {SECRET}?"
    assert ctx.confirm(hostile) is False
    shown = err.getvalue()
    expected = "drop \\x1b]52;c;SGVsbG8=\\x07plan\\nerror: FORGED: approved\\r\\u202etxt.exe "
    assert shown == f"{expected}{MASK}? [y/N] "
    assert inert(shown)
    assert out.getvalue() == ""


@pytest.mark.parametrize("options", [CliOptions(), CliOptions(assume_yes=True)])
def test_a_hostile_prompt_is_not_shown_without_a_terminal_or_with_yes(options: CliOptions) -> None:
    ctx, _, err = session(options=options)
    ctx.confirm(f"{OSC52}?")
    assert err.getvalue() == ""


# ---------------------------------------------------------------------------------------------------------
# editor


def test_editor_round_trip_returns_the_edited_object_and_removes_the_file() -> None:
    seen: list[Path] = []

    def editor(argv: Sequence[str]) -> int:
        path = Path(argv[-1])
        seen.append(path)
        assert argv[:-1] == ["vim", "-n"]
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        document = json.loads(path.read_text())
        document["title"] = "edited"
        path.write_text(json.dumps(document))
        return 0

    result = edit_document({"title": "old", "n": 1}, environ={"EDITOR": "vim -n"}, run=editor)
    assert result == {"title": "edited", "n": 1}
    assert not seen[0].exists()
    assert not seen[0].parent.exists()


def test_editor_backup_files_do_not_fail_a_good_edit_or_stay_behind() -> None:
    # Emacs leaves document.json~ by default: the private edit copy must still be removed.
    seen: list[Path] = []

    def editor(argv: Sequence[str]) -> int:
        path = Path(argv[-1])
        seen.append(path)
        path.with_name(path.name + "~").write_text(path.read_text())
        path.write_text(json.dumps({"title": "edited"}))
        return 0

    assert edit_document({"title": "old"}, environ={"EDITOR": "emacs"}, run=editor) == {"title": "edited"}
    assert not seen[0].parent.exists()


def test_a_failed_copy_of_the_document_leaves_no_edit_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    real_fdopen = os.fdopen

    def full_disk(fd: int, *args: Any, **kwargs: Any) -> IO[Any]:
        real_fdopen(fd).close()
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(os, "fdopen", full_disk)
    with pytest.raises(OSError, match="No space left"):
        edit_document({"title": "old"}, environ={"EDITOR": "ed"}, run=lambda argv: 0)
    assert list(tmp_path.iterdir()) == []


def test_invalid_json_keeps_the_file_and_names_it() -> None:
    kept: list[Path] = []

    def editor(argv: Sequence[str]) -> int:
        kept.append(Path(argv[-1]))
        kept[0].write_text('{"title": ')
        return 0

    with pytest.raises(ValidationFailed) as caught:
        edit_document({"title": "old"}, environ={"VISUAL": "ed"}, run=editor)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    assert kept[0].exists()
    assert caught.value.details["path"] == str(kept[0])
    assert str(kept[0]) in str(caught.value.details["hint"])
    assert kept[0].read_text() == '{"title": '
    kept[0].unlink()
    kept[0].parent.rmdir()


def test_a_non_object_document_is_rejected_and_kept() -> None:
    kept: list[Path] = []

    def editor(argv: Sequence[str]) -> int:
        kept.append(Path(argv[-1]))
        kept[0].write_text("[1, 2]")
        return 0

    with pytest.raises(ValidationFailed, match="JSON object"):
        edit_document({}, environ={"EDITOR": "ed"}, run=editor)
    assert kept[0].exists()
    kept[0].unlink()
    kept[0].parent.rmdir()


def test_a_failing_editor_keeps_the_file() -> None:
    kept: list[Path] = []

    def editor(argv: Sequence[str]) -> int:
        kept.append(Path(argv[-1]))
        return 3

    with pytest.raises(CapabilityUnavailable, match="status 3"):
        edit_document({"a": 1}, environ={"EDITOR": "ed"}, run=editor)
    assert json.loads(kept[0].read_text()) == {"a": 1}
    kept[0].unlink()
    kept[0].parent.rmdir()


def test_editor_resolution_prefers_visual_and_demands_one() -> None:
    assert resolve_editor({"VISUAL": "code -w", "EDITOR": "vi"}) == ["code", "-w"]
    assert resolve_editor({"EDITOR": "vi"}) == ["vi"]
    with pytest.raises(CapabilityUnavailable, match="EDITOR"):
        resolve_editor({})
    with pytest.raises(CapabilityUnavailable):
        resolve_editor({"EDITOR": "   "})
    with pytest.raises(ValueError, match="json"):
        edit_document({}, suffix=".toml", environ={"EDITOR": "ed"})


# ---------------------------------------------------------------------------------------------------------
# host context


def test_host_context_comes_from_host_services_and_the_invocation_client() -> None:
    app, _ = shared_app()
    client = app.client(actor=OWNER, surface=Surface.CLI)
    services = HostServices(
        host_id=HostId(UUID(int=7)),
        surface=Surface.CLI,
        gateways=GatewayTable({}, "host_gateway"),
        host_config=lambda: {"host": "chain"},
        operations={},
    )
    ctx, _, _ = session(host_factory=host_context_factory(services, client))
    host = build_host_context(ctx)
    assert host.client is client
    assert host.host_id == HostId(UUID(int=7))
    assert host.config == {"host": "chain"}


def test_host_context_is_refused_without_host_services() -> None:
    app, _ = shared_app()
    client = app.client(actor=OWNER, surface=Surface.CLI)
    for ctx in (session()[0], session(host_factory=host_context_factory(None, client))[0]):
        with pytest.raises(CapabilityUnavailable) as caught:
            build_host_context(ctx)
        assert caught.value.details == {"reason": "no_host_services"}


def test_the_session_environment_alone_decides_colour() -> None:
    assert session(environ={})[0].color is True
    assert session(environ={"NO_COLOR": "1"})[0].color is False
    assert session(options=CliOptions(no_color=True))[0].color is False


def test_a_session_without_a_backend_has_no_client() -> None:
    with pytest.raises(CapabilityUnavailable) as caught:
        _ = session()[0].client
    assert caught.value.details == {"reason": "no_backend"}
