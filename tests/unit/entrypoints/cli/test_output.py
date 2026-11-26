"""Shared CLI renderer: safe terminal text, redaction, envelope, tables, exit codes (cli §3, §4, SURFACE-03).

One renderer serves success and failure. Hostile values (OSC 52 clipboard writes, a forged newline prefix, a
carriage return, bidi URLs and paths, a sentinel secret) must not drive the terminal or survive unmasked in
human or JSON output; ``--no-color`` is not what protects them.
"""

import json
import re
from dataclasses import dataclass
from enum import Enum, IntEnum
from io import StringIO
from typing import Any, cast, override

import pytest

from skm.entrypoints.cli.context import CliOptions, CliRedactor, CliSession
from skm.entrypoints.cli.errors import EXIT_INTERRUPTED, run_guarded
from skm.entrypoints.cli.output import (
    CLI_EXIT,
    ENVELOPE_SCHEMA,
    Column,
    escape_terminal,
    kv_lines,
    render,
    render_error,
    render_findings,
    render_page,
    render_table,
    render_waiting,
    safe_text,
    to_jsonable,
)
from skm.kernel.error_codes import CATALOG, ErrorCategory, ErrorCode
from skm.kernel.errors import (
    Forbidden,
    NotFound,
    PreconditionFailed,
    SkmError,
    ValidationFailed,
    error_for,
)
from skm.kernel.outcomes import Diagnostic, Severity, Waiting
from skm.kernel.pagination import Cursor, Page
from skm.platform.logging.redaction import MASK, Redactor
from skm.platform.system_clock import SystemClock
from skm.platform.system_ids import Uuid7Generator

SECRET = "sentinel-secret-9f3c1d7a"
OSC52 = "\x1b]52;c;SGVsbG8=\x07"
FORGED = "ok\nerror: FORGED: injected line\nhint: run rm -rf"
BIDI_PATH = "/srv/\u202egpj.exe\u2069/report"
RAW_CONTROLS = re.compile(
    "[\x00-\x09\x0b-\x1f\x7f-\x9f\u061c\u200e\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069]"
)


class Terminal(StringIO):
    def __init__(self, *, tty: bool = False) -> None:
        super().__init__()
        self._tty = tty

    @override
    def isatty(self) -> bool:
        return self._tty


def make_ctx(*, tty: bool = False, **flags: Any) -> tuple[CliSession, Terminal, Terminal]:
    out, err = Terminal(tty=tty), Terminal(tty=tty)
    redactor = Redactor()
    redactor.register_secret(SECRET)
    ids = Uuid7Generator(SystemClock())
    ctx = CliSession(
        options=CliOptions(**flags),
        stdout=out,
        stderr=err,
        redactor=redactor,
        ids=ids,
        request_id="cli-test",
    )
    return ctx, out, err


def single_clean_line(text: str) -> None:
    assert text.endswith("\n")
    assert text.count("\n") == 1, text
    assert not RAW_CONTROLS.search(text.removesuffix("\n")), repr(text)


# ---------------------------------------------------------------------------------------------------------
# escape_terminal


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        ("\x1b[31mred\x1b[0m", "\\x1b[31mred\\x1b[0m"),
        (OSC52, "\\x1b]52;c;SGVsbG8=\\x07"),
        ("a\rb", "a\\rb"),
        ("a\nb", "a\\nb"),
        ("a\tb", "a\\tb"),
        ("del\x7f", "del\\x7f"),
        ("c1\x9b31m\x9d52;c;", "c1\\x9b31m\\x9d52;c;"),
        ("nul\x00", "nul\\x00"),
        (BIDI_PATH, "/srv/\\u202egpj.exe\\u2069/report"),
        ("https://\u202eexample.com", "https://\\u202eexample.com"),
        ("lrm\u200erlm\u200f", "lrm\\u200erlm\\u200f"),
        ("sep\u2028para\u2029", "sep\\u2028para\\u2029"),
        ("\ud800", "\\ud800"),
        ("Привет, мир ✓ 日本語", "Привет, мир ✓ 日本語"),
        ("plain text", "plain text"),
    ],
)
def test_escape_terminal(raw: str, shown: str) -> None:
    assert escape_terminal(raw) == shown
    assert not RAW_CONTROLS.search(shown)


def test_escape_is_not_a_no_color_feature() -> None:
    for flags in ({}, {"no_color": True}):
        ctx, _, _ = make_ctx(**flags)
        assert safe_text(ctx, OSC52) == "\\x1b]52;c;SGVsbG8=\\x07"


def test_redaction_runs_before_escaping() -> None:
    ctx, _, _ = make_ctx()
    assert safe_text(ctx, f"token={SECRET}\n") == f"token={MASK}\\n"


# ---------------------------------------------------------------------------------------------------------
# success path: human


def test_hostile_values_stay_on_one_line_in_human_success() -> None:
    ctx, out, err = make_ctx()
    hostile = f"{OSC52}{FORGED}\r{BIDI_PATH} {SECRET}"
    assert render(ctx, hostile, human=lambda value: f"created {value}", command="x.create") == 0
    single_clean_line(out.getvalue())
    assert SECRET not in out.getvalue()
    assert out.getvalue().startswith("created \\x1b]52;c;SGVsbG8=\\x07ok\\nerror: FORGED")
    assert err.getvalue() == ""


def test_a_block_is_escaped_line_by_line_and_cannot_be_forged() -> None:
    ctx, out, _ = make_ctx()
    render(ctx, None, human=lambda _: ["TITLE  first", f"TITLE  {FORGED}"], command="x.show")
    lines = out.getvalue().splitlines()
    assert len(lines) == 2
    assert lines[1].startswith("TITLE  ok\\nerror: FORGED")


def test_quiet_prints_only_the_essential_part() -> None:
    ctx, out, _ = make_ctx(quiet=True)
    render(
        ctx,
        {"id": "abc"},
        human=lambda value: "long summary",
        command="x.create",
        essential=lambda v: v["id"],
    )
    assert out.getvalue() == "abc\n"
    silent, out2, _ = make_ctx(quiet=True)
    render(silent, {"id": "abc"}, human=lambda value: "long summary", command="x.create")
    assert out2.getvalue() == ""


def test_diagnostics_go_to_stderr_in_human_mode_and_are_escaped() -> None:
    ctx, out, err = make_ctx()
    warn = Diagnostic("CONFIG_DEPRECATED", f"old key {OSC52}", Severity.WARNING, target="a.b")
    render(ctx, 1, human=lambda _: "ok", command="x", diagnostics=[warn])
    assert out.getvalue() == "ok\n"
    assert err.getvalue() == "warning: CONFIG_DEPRECATED: old key \\x1b]52;c;SGVsbG8=\\x07\n"


# ---------------------------------------------------------------------------------------------------------
# success path: json


def envelope_ok(document: dict[str, Any]) -> None:
    """The ``urn:skm:cli:envelope:v1`` shape of cli §3 (the packaged schema file is not part of this card)."""
    assert document["schema"] == ENVELOPE_SCHEMA
    assert isinstance(document["ok"], bool)
    assert isinstance(document["command"], str)
    assert isinstance(document["request_id"], str)
    if document["ok"] and "outcome" not in document:
        assert "result" in document
        assert isinstance(document["diagnostics"], list)
    elif document["ok"]:
        assert document["result"] is None
        assert {"kind", "code", "message"} <= set(document["outcome"])
    else:
        assert {"code", "category", "message", "details", "retryable"} == set(document["error"])


def test_json_success_keeps_values_in_valid_strings_with_controls_escaped() -> None:
    ctx, out, err = make_ctx(json=True)
    hostile = {
        "title": f"{OSC52}{FORGED}\r{BIDI_PATH}",
        "token": f"Bearer {SECRET}",
        "ссылка": "https://\u202eevil",
    }
    assert render(ctx, hostile, human=lambda _: "never", command="planning.publish_revision") == 0
    raw = out.getvalue()
    single_clean_line(raw)
    assert "\x1b" not in raw
    assert SECRET not in raw
    assert "\\u202e" in raw
    document = json.loads(raw)
    envelope_ok(document)
    assert document["command"] == "planning.publish_revision"
    assert document["request_id"] == "cli-test"
    assert document["result"]["title"].startswith(OSC52)  # the value round-trips, only its encoding is safe
    assert err.getvalue() == ""


def test_json_has_no_ansi_decoration_even_on_a_tty() -> None:
    ctx, out, _ = make_ctx(tty=True, json=True)
    render(ctx, {"a": 1}, human=lambda _: "x", command="x")
    assert "\x1b[" not in out.getvalue()


def test_json_carries_diagnostics() -> None:
    ctx, out, _ = make_ctx(json=True)
    warn = Diagnostic("CONFIG_DEPRECATED", "old", Severity.WARNING, target="a.b")
    render(ctx, {}, human=lambda _: "x", command="x", diagnostics=[warn])
    assert json.loads(out.getvalue())["diagnostics"] == [
        {"code": "CONFIG_DEPRECATED", "severity": "warning", "message": "old", "target": "a.b"}
    ]


def test_to_jsonable_covers_result_shapes() -> None:
    from datetime import UTC, datetime
    from pathlib import PurePosixPath
    from uuid import UUID

    class Color(Enum):
        RED = "red"

    @dataclass
    class Row:
        id: UUID
        at: datetime
        color: Color
        path: PurePosixPath
        tags: tuple[str, ...]

    row = Row(UUID(int=1), datetime(2026, 1, 2, tzinfo=UTC), Color.RED, PurePosixPath("/a"), ("x", "y"))
    assert to_jsonable(row) == {
        "id": str(UUID(int=1)),
        "at": "2026-01-02T00:00:00+00:00",
        "color": "red",
        "path": "/a",
        "tags": ["x", "y"],
    }
    with pytest.raises(TypeError):
        to_jsonable(float("nan"))
    with pytest.raises(TypeError):
        to_jsonable(b"bytes")


class Level(IntEnum):
    HIGH = 2


class Shade(Enum):
    DARK = "dark"


@dataclass(frozen=True)
class Graded:
    severity: Severity  # a StrEnum of the project
    level: Level
    shade: Shade
    by_level: dict[Level, ErrorCode]


GRADED = Graded(Severity.WARNING, Level.HIGH, Shade.DARK, {Level.HIGH: ErrorCode.MODULE_DISABLED})
GRADED_JSON = {"severity": "warning", "level": 2, "shade": "dark", "by_level": {"2": "MODULE_DISABLED"}}


@pytest.mark.parametrize(
    ("value", "expected"),
    [(Severity.WARNING, "warning"), (ErrorCode.MODULE_DISABLED, "MODULE_DISABLED"), (Level.HIGH, 2)],
)
def test_to_jsonable_turns_str_and_int_enums_into_exact_primitives(value: object, expected: object) -> None:
    converted = to_jsonable(value)
    assert converted == expected
    assert type(converted) is type(expected)


@pytest.mark.parametrize(
    "result", [Severity.WARNING, Level.HIGH, Shade.DARK, GRADED, [GRADED], {"nested": {"x": GRADED}}]
)
def test_json_render_of_enum_results_succeeds_through_the_guard(result: object) -> None:
    ctx, out, err = make_ctx(json=True)
    assert run_guarded(lambda: render(ctx, result, human=str, command="x.show"), ctx, "x.show") == 0
    document = json.loads(out.getvalue())
    envelope_ok(document)
    assert document["result"] == to_jsonable(result)
    assert err.getvalue() == ""


def test_json_diagnostics_with_an_error_code_member_render() -> None:
    ctx, out, _ = make_ctx(json=True)
    diagnostics = [
        Diagnostic(
            ErrorCode.MODULE_DISABLED, "learning is disabled", Severity.WARNING, "modules.learning.enabled"
        ),
        Diagnostic("CONFIG_DEPRECATED", "old", Severity.INFO),
    ]
    command = "x"

    def show() -> int:
        return render(ctx, GRADED, human=str, command=command, diagnostics=diagnostics)

    assert run_guarded(show, ctx, command) == 0
    document = json.loads(out.getvalue())
    assert document["result"] == GRADED_JSON
    assert [item["code"] for item in document["diagnostics"]] == ["MODULE_DISABLED", "CONFIG_DEPRECATED"]
    human, _, human_err = make_ctx()
    assert (
        run_guarded(lambda: render(human, 1, human=str, command="x", diagnostics=diagnostics), human, "x")
        == 0
    )
    assert human_err.getvalue().splitlines()[0] == "warning: MODULE_DISABLED: learning is disabled"


def test_json_page_of_enum_items_renders() -> None:
    ctx, out, _ = make_ctx(json=True)
    page = Page(items=[GRADED], next=None)
    columns = [Column[Graded]("severity", lambda row: row.severity)]
    assert run_guarded(lambda: render_page(ctx, page, columns=columns, command="x.list"), ctx, "x.list") == 0
    assert json.loads(out.getvalue())["result"] == {"items": [GRADED_JSON], "next": None}


# ---------------------------------------------------------------------------------------------------------
# errors


def hostile_error() -> SkmError:
    return Forbidden(
        ErrorCode.FORBIDDEN,
        f"permission plan.publish is required at {BIDI_PATH}{OSC52}{FORGED} {SECRET}",
        details={"permission": "plan.publish", "hint": ["skm use", f"{FORGED}"], "note": SECRET},
    )


def test_human_error_is_one_error_line_plus_only_declared_hints() -> None:
    ctx, out, err = make_ctx()
    assert render_error(ctx, hostile_error(), command="planning.publish_revision") == 5
    assert out.getvalue() == ""
    lines = err.getvalue().splitlines()
    assert [line.split(":")[0] for line in lines] == ["error", "hint", "hint"]
    assert lines[0].startswith("error: FORBIDDEN: permission plan.publish is required at /srv/\\u202e")
    assert "\\x1b]52;c;SGVsbG8=\\x07" in lines[0]
    assert SECRET not in err.getvalue()
    assert not RAW_CONTROLS.search(err.getvalue().replace("\n", ""))


def test_json_error_is_the_catalog_envelope_with_redaction_and_escaping() -> None:
    ctx, out, err = make_ctx(json=True)
    assert render_error(ctx, hostile_error(), command="planning.publish_revision") == 5
    raw = out.getvalue()
    single_clean_line(raw)
    assert SECRET not in raw
    assert "\\u202e" in raw
    assert err.getvalue() == ""
    document = json.loads(raw)
    envelope_ok(document)
    assert (document["ok"], document["error"]["code"], document["error"]["category"]) == (
        False,
        "FORBIDDEN",
        "forbidden",
    )
    assert document["error"]["details"]["permission"] == "plan.publish"
    assert document["error"]["retryable"] is False


def test_error_with_candidates_and_schema_issues_prints_the_example_09_blocks() -> None:
    ctx, _, err = make_ctx()
    ambiguous = ValidationFailed(
        ErrorCode.AMBIGUOUS_REFERENCE,
        '"0192f5c7" matches 3 runs; use at least 12 hex characters',
        details={"candidates": ["0192f5c7-2100  PLAN7 r2  succeeded", f"0192f5c7-2a00 {OSC52}"]},
    )
    assert render_error(ctx, ambiguous, command="execution.get_run") == 1
    assert err.getvalue().splitlines()[1:] == [
        "candidates:",
        "  0192f5c7-2100  PLAN7 r2  succeeded",
        "  0192f5c7-2a00 \\x1b]52;c;SGVsbG8=\\x07",
    ]
    ctx, _, err = make_ctx()
    invalid = ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        "draft document does not match urn:skm:planning:specification:v1",
        details={
            "issues": [
                {"pointer": "/items/1/review/mode", "code": "enum", "message": '"none" is not one of x'}
            ]
        },
    )
    render_error(ctx, invalid, command="planning.save_draft")
    assert err.getvalue().splitlines()[1] == '  /items/1/review/mode   enum   "none" is not one of x'


def test_human_error_names_a_reason_code_but_not_free_text() -> None:
    ctx, _, err = make_ctx()
    shared = "Backup or recovery precondition failed"
    coded = PreconditionFailed(
        ErrorCode.INVALID_TRANSITION, shared, details={"reason": "backup_path_already_exists"}
    )
    render_error(ctx, coded, command="backup.create")
    assert err.getvalue().splitlines() == [
        f"error: INVALID_TRANSITION: {shared} (reason: backup_path_already_exists)"
    ]
    ctx, _, err = make_ctx()
    prose = PreconditionFailed(
        ErrorCode.INVALID_TRANSITION, shared, details={"reason": f"stderr said {SECRET}"}
    )
    render_error(ctx, prose, command="backup.create")
    assert err.getvalue().splitlines() == [f"error: INVALID_TRANSITION: {shared}"]


def test_error_prefix_is_coloured_only_on_a_tty_with_colour_on_and_text_stays_escaped() -> None:
    ctx, _, err = make_ctx(tty=True)
    render_error(ctx, Forbidden(ErrorCode.FORBIDDEN, f"x {OSC52}"), command="x")
    assert err.getvalue().startswith("\x1b[1;31merror:\x1b[0m FORBIDDEN: x \\x1b]52;c;")
    assert err.getvalue().count("\x1b") == 2  # only the CLI's own decoration
    for flags in ({"no_color": True}, {}):
        ctx, _, err = make_ctx(tty=flags == {"no_color": True}, **flags) if flags else make_ctx()
        render_error(ctx, Forbidden(ErrorCode.FORBIDDEN, "x"), command="x")
        assert "\x1b" not in err.getvalue()


# ---------------------------------------------------------------------------------------------------------
# exit codes


def test_every_catalog_code_exits_by_its_category() -> None:
    assert set(CLI_EXIT) == set(ErrorCategory)
    for info in CATALOG.values():
        assert CLI_EXIT[info.category] == info.cli_exit, info.code


@pytest.mark.parametrize(
    ("code", "exit_code"),
    [
        (ErrorCode.NOT_FOUND, 1),
        (ErrorCode.SCHEMA_INVALID, 1),
        (ErrorCode.FORBIDDEN, 5),
        (ErrorCode.UNAUTHENTICATED, 5),
        (ErrorCode.BACKEND_UNAVAILABLE, 3),
        (ErrorCode.VERSION_CONFLICT, 6),
        (ErrorCode.BOOTSTRAP_MISSING, 6),
        (ErrorCode.CAPABILITY_UNAVAILABLE, 6),
        (ErrorCode.OUTCOME_UNKNOWN, 6),
        (ErrorCode.INTERNAL_ERROR, 70),
    ],
)
def test_run_guarded_maps_structured_errors(code: ErrorCode, exit_code: int) -> None:
    ctx, _, err = make_ctx()

    def fail() -> int:
        raise error_for(code, "boom")

    assert run_guarded(fail, ctx, "x.y") == exit_code
    assert err.getvalue().startswith(f"error: {code.value}: boom")


def test_waiting_is_exit_4_and_not_an_error() -> None:
    ctx, out, err = make_ctx(json=True)
    waiting = Waiting(ErrorCode.NOTHING_TO_CLAIM, "no work available")
    assert render_waiting(ctx, waiting, command="execution.claim_assignment") == 4
    document = json.loads(out.getvalue())
    envelope_ok(document)
    assert document["outcome"] == {
        "kind": "waiting",
        "code": "NOTHING_TO_CLAIM",
        "message": "no work available",
    }
    assert err.getvalue() == ""
    human, human_out, _ = make_ctx()
    assert render_waiting(human, waiting, command="x") == 4
    assert human_out.getvalue() == "waiting: NOTHING_TO_CLAIM: no work available\n"


def test_keyboard_interrupt_is_130_and_prints_nothing() -> None:
    ctx, out, err = make_ctx()

    def interrupted() -> int:
        raise KeyboardInterrupt

    assert run_guarded(interrupted, ctx, "x") == EXIT_INTERRUPTED == 130
    assert (out.getvalue(), err.getvalue()) == ("", "")


def test_unexpected_exceptions_are_internal_errors_without_a_traceback_by_default() -> None:
    ctx, _, err = make_ctx()

    def crash() -> int:
        raise RuntimeError(f"db password={SECRET}1234")

    assert run_guarded(crash, ctx, "x") == 70
    assert err.getvalue() == (
        "error: INTERNAL_ERROR: unexpected failure (request cli-test); see logs\n"
        "hint: rerun with -vv to print the traceback\n"
    )


def test_traceback_appears_at_vv_redacted_and_escaped() -> None:
    ctx, _, err = make_ctx(verbosity=2)

    def crash() -> int:
        raise RuntimeError(f"password={SECRET}1234 {OSC52}")

    assert run_guarded(crash, ctx, "x") == 70
    text = err.getvalue()
    assert "Traceback (most recent call last):" in text
    assert SECRET not in text
    assert "\x1b" not in text
    assert "\\x1b]52;c;SGVsbG8=\\x07" in text


def test_a_single_v_does_not_print_the_traceback() -> None:
    ctx, _, err = make_ctx(verbosity=1)

    def crash() -> int:
        raise RuntimeError("x")

    run_guarded(crash, ctx, "x")
    assert "Traceback" not in err.getvalue()


def test_the_traceback_hint_is_offered_only_where_vv_would_print_one() -> None:
    def crash() -> int:
        raise RuntimeError("x")

    for verbosity, json_output, hinted in ((0, False, True), (2, False, False), (0, True, False)):
        ctx, out, err = make_ctx(verbosity=verbosity, json=json_output)
        run_guarded(crash, ctx, "x")
        assert ("-vv" in out.getvalue() + err.getvalue()) is hinted, (verbosity, json_output)


def test_json_internal_error_has_no_traceback_even_at_vv() -> None:
    ctx, out, err = make_ctx(json=True, verbosity=2)

    def crash() -> int:
        raise RuntimeError("x")

    assert run_guarded(crash, ctx, "x") == 70
    assert json.loads(out.getvalue())["error"]["code"] == "INTERNAL_ERROR"
    assert "Traceback" not in out.getvalue() + err.getvalue()


def test_run_guarded_without_a_context_still_maps_errors(capsys: pytest.CaptureFixture[str]) -> None:
    def fail() -> int:
        raise NotFound(ErrorCode.NOT_FOUND, "missing")

    assert run_guarded(fail, None, "x") == 1
    assert capsys.readouterr().err == "error: NOT_FOUND: missing\n"


# ---------------------------------------------------------------------------------------------------------
# tables, pages, findings


def test_table_cells_cannot_start_a_new_row_or_leak_controls() -> None:
    ctx, _, _ = make_ctx()
    rows = [["PLAN7", f"title {FORGED}"], ["PLAN8", f"{OSC52}{BIDI_PATH}"], ["PLAN9", None]]
    lines = render_table(ctx, ["alias", "title"], rows)
    assert len(lines) == 4
    assert lines[0] == "alias  title"
    assert all(not RAW_CONTROLS.search(line) for line in lines)
    assert lines[1].startswith("PLAN7  title ok\\nerror: FORGED")
    assert lines[3] == "PLAN9"


def test_table_aligns_columns_without_borders_or_trailing_blanks() -> None:
    ctx, _, _ = make_ctx()
    lines = render_table(ctx, ["a", "bb"], [["xxx", "1"], ["y", "22"]])
    assert lines == ["a    bb", "xxx  1", "y    22"]


def test_kv_lines_escape_keys_and_values() -> None:
    ctx, _, _ = make_ctx()
    lines = kv_lines(ctx, [("ID", "1"), ("TITLE\n", f"{OSC52}{SECRET}"), ("EMPTY", None)])
    assert lines == ["ID       1", f"TITLE\\n  \\x1b]52;c;SGVsbG8=\\x07{MASK}", "EMPTY"]


def test_render_page_json_has_items_and_cursor_and_human_has_a_table() -> None:
    page: Page[dict[str, str]] = Page(items=[{"slug": "skm", "title": OSC52}], next=None)
    columns = [
        Column[dict[str, str]]("slug", lambda row: row["slug"]),
        Column[dict[str, str]]("title", lambda row: row["title"]),
    ]
    ctx, out, _ = make_ctx(json=True)
    assert render_page(ctx, page, columns=columns, command="workspace.list_projects") == 0
    document = json.loads(out.getvalue())
    envelope_ok(document)
    assert document["result"] == {"items": [{"slug": "skm", "title": OSC52}], "next": None}
    ctx, out, err = make_ctx()
    more = Page(items=page.items, next=Cursor("cursor-1"))
    render_page(ctx, more, columns=columns, command="workspace.list_projects")
    assert out.getvalue().splitlines() == ["slug  title", "skm   \\x1b]52;c;SGVsbG8=\\x07"]
    assert "more results" in err.getvalue()


def test_an_empty_human_page_prints_only_the_header() -> None:
    columns = [
        Column[dict[str, str]]("slug", lambda row: row["slug"]),
        Column[dict[str, str]]("title", lambda row: row["title"]),
    ]
    empty: Page[dict[str, str]] = Page(items=[], next=None)
    ctx, out, err = make_ctx()
    assert run_guarded(lambda: render_page(ctx, empty, columns=columns, command="x.list"), ctx, "x.list") == 0
    assert (out.getvalue(), err.getvalue()) == ("slug  title\n", "")
    assert render_table(ctx, ["a", f"b{OSC52}"], []) == ["a  b\\x1b]52;c;SGVsbG8=\\x07"]
    as_json, json_out, _ = make_ctx(json=True)
    assert render_page(as_json, empty, columns=columns, command="x.list") == 0
    assert json.loads(json_out.getvalue())["result"] == {"items": [], "next": None}
    quiet, quiet_out, _ = make_ctx(quiet=True)
    assert render_page(quiet, empty, columns=columns, command="x.list") == 0
    assert quiet_out.getvalue() == ""


def test_findings_table_is_escaped_and_silent_in_json() -> None:
    class Finding:
        code = "PLAN_NOT_READY"
        severity = "error"
        entity = "P2.4"
        message = f"bad {OSC52}"

    ctx, _, err = make_ctx()
    render_findings(ctx, [Finding()])
    assert err.getvalue().splitlines() == [
        "code            severity  entity  message",
        "PLAN_NOT_READY  error     P2.4    bad \\x1b]52;c;SGVsbG8=\\x07",
    ]
    quiet_ctx, _, quiet_err = make_ctx(json=True)
    render_findings(quiet_ctx, [Finding()])
    assert quiet_err.getvalue() == ""


# ---------------------------------------------------------------------------------------------------------
# credentials shorter than the shared Redactor's minimum (CliRedactor)

SHORT_TOKENS = ("Q", "q7", "Zq7", "k3Y9", "Wp2xK", "aB3dE5", "Xy7Qp2Z")


def short_ctx(token: str, **flags: Any) -> tuple[CliSession, Terminal, Terminal]:
    ctx, out, err = make_ctx(**flags)
    redactor = CliRedactor()
    redactor.register_secret(SECRET)
    redactor.register_secret(token)
    ctx.redactor = redactor
    return ctx, out, err


@pytest.mark.parametrize("token", SHORT_TOKENS)
def test_the_shared_redactor_alone_keeps_a_short_token(token: str) -> None:
    shared = Redactor()
    shared.register_secret(token)
    assert shared.text(f"token {token}") == f"token {token}"  # why the CLI needs its own registry


@pytest.mark.parametrize("token", SHORT_TOKENS)
def test_a_short_token_is_masked_in_text_and_documents(token: str) -> None:
    redactor = CliRedactor()
    redactor.register_secret(token)
    shown = f"token '{token}', token={token}; tok_{token} {token}.\n{token}"
    assert redactor.text(shown) == f"token '{MASK}', token={MASK}; tok_{MASK} {MASK}.\n{MASK}"
    assert redactor.document({"actor": token, token: [f"bad {token}"], "n": 1}) == {
        "actor": MASK,
        MASK: [f"bad {MASK}"],
        "n": 1,
    }


def test_short_tokens_are_masked_inside_ordinary_words_too() -> None:
    redactor = CliRedactor()
    for token in ("a", "ok", "id"):
        redactor.register_secret(token)
    assert redactor.text("a group of okapis; request_id took a look") == (
        f"{MASK} group of {MASK}pis; request_{MASK} to{MASK} {MASK} lo{MASK}"
    )
    assert redactor.text("the label is broken") == f"the l{MASK}bel is br{MASK}en"


def test_a_short_token_inside_a_scalar_masks_the_whole_scalar() -> None:
    redactor = CliRedactor()
    redactor.register_secret("1")
    redactor.register_secret("true")
    assert redactor.document([1, 10, 21, True, False, None]) == [MASK, MASK, MASK, MASK, False, None]


def test_a_short_token_never_splits_the_mask_of_a_longer_secret() -> None:
    redactor = CliRedactor()
    redactor.register_secret("abc-12345678")
    redactor.register_secret("abc")
    assert redactor.text("x abc-12345678 abc") == f"x {MASK} {MASK}"
    assert redactor.text(MASK) == MASK
    redactor.register_secret("red")  # a word inside the mask itself
    assert redactor.text("red abc-12345678") == f"{MASK} {MASK}"


def test_the_repr_spelling_and_punctuation_edges_of_a_short_token_are_masked() -> None:
    redactor = CliRedactor()
    redactor.register_secret("a'\\b")
    redactor.register_secret("-+")
    assert redactor.text("seen \"a'\\\\b\" and a'\\b") == f'seen "{MASK}" and {MASK}'
    assert redactor.text("x-+y") == f"x{MASK}y"
    with pytest.raises(TypeError):
        redactor.register_secret(cast("str", b"abc"))


@pytest.mark.parametrize("token", ['ab"cd', r"ab\cd", "☃X", 'long☃"quote\\token', "ab\x1bcd", "emoji😀X"])
@pytest.mark.parametrize("ensure_ascii", [False, True])
def test_json_string_spellings_are_masked_at_registration_and_in_rendered_data(
    token: str, ensure_ascii: bool
) -> None:
    spelling = json.dumps(token, ensure_ascii=ensure_ascii)[1:-1]
    assert json.loads(f'"{spelling}"') == token  # the review's reversible exposure
    ctx, out, err = short_ctx(token, json=True)
    assert ctx.redactor.text(spelling) == MASK
    assert ctx.redactor.document({spelling: [spelling]}) == {MASK: [MASK]}
    render(
        ctx,
        {"nested": [{spelling: spelling}]},
        human=str,
        command="show",
        diagnostics=[Diagnostic("NOTE", spelling, Severity.WARNING, target=spelling)],
    )
    render_error(
        ctx,
        NotFound(ErrorCode.NOT_FOUND, spelling, details={"nested": [{spelling: spelling}]}),
        command="show",
    )
    render_page(ctx, Page(items=[{spelling: spelling}], next=None), columns=[], command="list")
    render_waiting(ctx, Waiting(ErrorCode.NOTHING_TO_CLAIM, spelling), command="claim")
    success, error, page, waiting = (json.loads(line) for line in out.getvalue().splitlines())
    for document in (success, error, page, waiting):
        envelope_ok(document)
    assert success["result"] == {"nested": [{MASK: MASK}]}
    assert success["diagnostics"][0]["message"] == success["diagnostics"][0]["target"] == MASK
    assert error["error"]["message"] == MASK
    assert error["error"]["details"] == {"nested": [{MASK: MASK}]}
    assert page["result"]["items"] == [{MASK: MASK}]
    assert waiting["outcome"]["message"] == MASK
    assert err.getvalue() == ""
    human, human_out, human_err = short_ctx(token)
    render(
        human,
        spelling,
        human=str,
        command="show",
        diagnostics=[Diagnostic("NOTE", spelling, Severity.WARNING)],
    )
    render_error(human, NotFound(ErrorCode.NOT_FOUND, spelling), command="show")
    assert human_out.getvalue() == f"{MASK}\n"
    assert human_err.getvalue() == f"warning: NOTE: {MASK}\nerror: NOT_FOUND: {MASK}\n"


@pytest.mark.parametrize("token", ['snow☃"double', "snow☃'single", 'emoji😀"quote', "雪\\path"])
def test_ascii_repr_spellings_of_unicode_credentials_are_also_masked(token: str) -> None:
    spelling = ascii(token)[1:-1]
    ctx, out, _ = short_ctx(token, json=True)
    assert ctx.redactor.text(spelling) == MASK
    render(ctx, {spelling: [spelling]}, human=str, command="show")
    assert json.loads(out.getvalue())["result"] == {MASK: [MASK]}
    human, human_out, _ = short_ctx(token)
    render(human, spelling, human=str, command="show")
    assert human_out.getvalue() == f"{MASK}\n"


@pytest.mark.parametrize(
    ("token", "label"),
    [("Z9SECRET", "Z9SECRET"), ("x1b", "\x1b"), (r"\n", "\n"), ('ab"cd', r"ab\"cd"), ("☃X", r"\u2603X")],
)
def test_caller_labels_are_data_in_tables_key_value_blocks_and_pages(token: str, label: str) -> None:
    ctx, out, _ = short_ctx(token)
    assert render_table(ctx, [label], []) == [MASK]
    assert kv_lines(ctx, [(label, "value")]) == [f"{MASK}  value"]
    assert render_page(ctx, Page(items=[], next=None), columns=[Column[str](label, str)], command="list") == 0
    assert out.getvalue() == f"{MASK}\n"


def test_label_and_value_joins_are_sealed_and_fixed_finding_headers_stay_intact() -> None:
    ctx, _, err = short_ctx("A  B")
    assert render_table(ctx, ["A", "B"], []) == [f"{MASK}  {MASK}"]
    assert kv_lines(ctx, [("A", "B")]) == [f"{MASK}  {MASK}"]
    ctx.redactor.register_secret("code")

    class Finding:
        code = "code"
        severity = "warning"
        entity = "-"
        message = "text"

    render_findings(ctx, [Finding()])
    assert err.getvalue().splitlines()[0].startswith("code")
    assert err.getvalue().splitlines()[1].startswith(MASK)


@pytest.mark.parametrize("token", SHORT_TOKENS)
def test_short_tokens_are_masked_in_every_rendered_form(token: str) -> None:
    error = ValidationFailed(ErrorCode.CONFIG_INVALID, f"bad token '{token}'", details={"token": token})
    ctx, out, err = short_ctx(token)
    assert render(ctx, {"actor": token}, human=lambda r: f"actor {r['actor']}", command="x.show") == 0
    render_error(ctx, error, command="x.show", extra=[f"cause {token}"])
    assert out.getvalue() == f"actor {MASK}\n"
    assert err.getvalue() == f"error: CONFIG_INVALID: bad token '{MASK}'\ncause {MASK}\n"
    jctx, jout, _ = short_ctx(token, json=True)
    render(jctx, {"actor": token}, human=lambda _: "", command="x.show")
    render_error(jctx, error, command="x.show")
    success, failure = (json.loads(line) for line in jout.getvalue().splitlines())
    assert success["result"] == {"actor": MASK}
    assert (failure["error"]["message"], failure["error"]["details"]) == (
        f"bad token '{MASK}'",
        {"token": MASK},
    )


@pytest.mark.parametrize("token", ["ok", "cli", "skm", "v1", "x", "error", "result"])
def test_a_short_token_that_equals_a_framing_word_keeps_the_envelope_valid(token: str) -> None:
    ctx, out, _ = short_ctx(token, json=True)
    ctx.request_id = "cli-0190"
    render(ctx, {"value": 3}, human=lambda _: "", command="x.show")
    render_error(ctx, NotFound(ErrorCode.NOT_FOUND, f"no {token}"), command="x.show")
    for line in out.getvalue().splitlines():
        document = json.loads(line)
        assert (document["schema"], document["command"], document["request_id"]) == (
            ENVELOPE_SCHEMA,
            f"{MASK}.show" if token == "x" else "x.show",
            "cli-0190",
        )
        assert set(document) >= {"schema", "ok", "command", "request_id"}
    assert json.loads(out.getvalue().splitlines()[-1])["error"]["message"] == f"no {MASK}"


@pytest.mark.parametrize("token", SHORT_TOKENS)
def test_short_tokens_are_hidden_inside_alphanumeric_json_keys_and_values(token: str) -> None:
    ctx, out, _ = short_ctx(token, json=True)
    render(ctx, {f"x{token}y": [f"x{token}y", {"nested": f"z{token}0"}]}, human=str, command="show")
    assert token not in out.getvalue()
    assert json.loads(out.getvalue())["result"] == {f"x{MASK}y": [f"x{MASK}y", {"nested": f"z{MASK}0"}]}


@pytest.mark.parametrize(
    ("tokens", "value", "expected"),
    [
        (("ab", "bc"), "zabcx", f"z{MASK}x"),
        (("aba", "bab"), "abab", MASK),
        (("ab", "bc", "cd"), "abcde", f"{MASK}e"),
        (("abcdefghi", "ijk"), "abcdefghijk", MASK),
        (("Q", "d\u203ax"), "Qx", MASK),
    ],
)
def test_all_overlapping_tokens_are_hidden_in_either_registration_order(
    tokens: tuple[str, ...], value: str, expected: str
) -> None:
    for order in (tokens, tokens[::-1]):
        redactor = CliRedactor()
        for token in order:
            redactor.register_secret(token)
        assert redactor.text(value) == expected
        assert redactor.document({value: [value]}) == {expected: [expected]}


@pytest.mark.parametrize(
    ("token", "value"),
    [("x1b", "\x1b"), (r"\n", "\n"), ("u202e", "\u202e"), ("ud800", "\ud800")],
)
def test_escaping_cannot_recreate_a_token_in_human_output(token: str, value: str) -> None:
    ctx, out, _ = short_ctx(token)
    assert safe_text(ctx, value) == MASK
    render(ctx, value, human=str, command="show")
    assert out.getvalue() == f"{MASK}\n"


@pytest.mark.parametrize(
    ("token", "value"),
    [("u0000", "\x00"), (r"\n", "\n"), ("u202e", "\u202e"), ("ud800", "\ud800")],
)
def test_escaping_cannot_recreate_a_token_in_json_strings_or_keys(token: str, value: str) -> None:
    ctx, out, _ = short_ctx(token, json=True)
    render(ctx, {value: value}, human=str, command="show")
    assert token not in out.getvalue()
    assert json.loads(out.getvalue())["result"] == {MASK: MASK}
    out.getvalue().encode("utf-8")


@pytest.mark.parametrize(
    ("token", "result", "expected"),
    [
        ('A","B', ["A", "B"], [MASK, MASK]),
        ('A":1', {"A": 1}, {MASK: MASK}),
        ("1,2", [1, 2], [MASK, MASK]),
        ('A":null', {"A": None}, {MASK: MASK}),
    ],
)
def test_json_joins_mask_only_data_and_preserve_syntax(token: str, result: object, expected: object) -> None:
    ctx, out, _ = short_ctx(token, json=True)
    render(ctx, result, human=str, command="show")
    assert token not in out.getvalue()
    document = json.loads(out.getvalue())
    envelope_ok(document)
    assert document["result"] == expected


@pytest.mark.parametrize("token", ["null", "tru", "1"])
def test_untrusted_json_scalars_are_redacted_in_results_pages_and_errors(token: str) -> None:
    payload = [None, True, 21]
    expected = [MASK if token in json.dumps(value) else value for value in payload]
    ctx, out, _ = short_ctx(token, json=True)
    render(ctx, payload, human=str, command="show")
    render_page(ctx, Page(items=payload, next=None), columns=[], command="list")
    render_error(ctx, NotFound(ErrorCode.NOT_FOUND, "absent", details={"payload": payload}), command="show")
    success, page, error = (json.loads(line) for line in out.getvalue().splitlines())
    assert success["result"] == expected
    assert page["result"]["items"] == expected
    assert error["error"]["details"]["payload"] == expected
    assert error["error"]["retryable"] is False
    waiting_ctx, waiting_out, _ = short_ctx(token, json=True)
    render_waiting(waiting_ctx, Waiting(ErrorCode.NOTHING_TO_CLAIM, "idle"), command="claim")
    assert json.loads(waiting_out.getvalue())["result"] is None  # required outcome framing


def test_diagnostic_severity_and_other_metadata_remain_untrusted() -> None:
    diagnostic = Diagnostic("NOTE_Q", "xQy", Severity.WARNING, target="zQ0")
    for json_mode in (False, True):
        ctx, out, err = short_ctx("warning", json=json_mode)
        ctx.redactor.register_secret("Q")
        render(ctx, {}, human=lambda _: "done", command="show", diagnostics=[diagnostic])
        if json_mode:
            assert json.loads(out.getvalue())["diagnostics"] == [
                {"code": f"NOTE_{MASK}", "severity": MASK, "message": f"x{MASK}y", "target": f"z{MASK}0"}
            ]
        else:
            assert err.getvalue() == f"{MASK}: NOTE_{MASK}: x{MASK}y\n"


@pytest.mark.parametrize("token", ["cli", "Q", "-Q"])
def test_request_id_prefix_is_trusted_but_command_and_id_suffix_are_data(token: str) -> None:
    ctx, out, _ = short_ctx(token, json=True)
    ctx.request_id = "cli-Qxcliy"
    render(ctx, {}, human=str, command=f"pre{token}post")
    render_error(ctx, NotFound(ErrorCode.NOT_FOUND, "absent"), command=f"pre{token}post")
    render_waiting(ctx, Waiting(ErrorCode.NOTHING_TO_CLAIM, "idle"), command=f"pre{token}post")
    render_page(ctx, Page(items=[], next=None), columns=[], command=f"pre{token}post")
    for line in out.getvalue().splitlines():
        document = json.loads(line)
        envelope_ok(document)
        assert document["command"] == f"pre{MASK}post"
        assert document["request_id"].startswith("cli-")
        assert token not in document["request_id"].removeprefix("cli-")
        assert document["request_id"] != ctx.request_id


def test_human_blocks_and_tables_hide_tokens_crossing_value_or_row_boundaries() -> None:
    ctx, out, err = short_ctx("Q\nR")
    render(ctx, None, human=lambda _: ["Q", "R"], command="show")
    assert "Q\nR" not in out.getvalue()
    assert "Q\nR" not in "\n".join(render_table(ctx, ["h"], [["Q"], ["R"]]))
    render_page(ctx, Page(items=["Q", "R"], next=None), columns=[Column[str]("h", str)], command="list")
    assert "Q\nR" not in out.getvalue()

    class Finding:
        code = "Q"
        severity = "R"
        entity = "-"
        message = "text"

    ctx.redactor.register_secret("Q  R")
    render_findings(ctx, [Finding()])
    assert "Q  R" not in err.getvalue()
    joined = "\n".join(render_table(ctx, ["a", "b"], [["Q", "R"]]))
    assert "Q  R" not in joined
    ctx.redactor.register_secret("Q\nK  R")
    assert "Q\nK  R" not in "\n".join(kv_lines(ctx, [("K", "Q"), ("K", "R")]))
    assert kv_lines(ctx, []) == []


def test_separate_error_blocks_cannot_reassemble_a_multiline_credential() -> None:
    token = "Zed\nerror: NOT_FOUND: Again"
    ctx, _, err = short_ctx(token)
    render_error(ctx, NotFound(ErrorCode.NOT_FOUND, "Zed"), command="show")
    render_error(ctx, NotFound(ErrorCode.NOT_FOUND, "Again"), command="show")
    assert token not in err.getvalue()


@pytest.mark.parametrize(
    ("token", "retryable"), [("true", True), ("false", False), ("tru", True), ("alse", False)]
)
def test_retryable_is_trusted_while_other_caller_metadata_is_redacted(token: str, retryable: bool) -> None:
    ctx, out, _ = short_ctx(token, json=True)
    ctx.request_id = f"cli-x{token}y"
    error = NotFound(
        ErrorCode.NOT_FOUND,
        f"x{token}y",
        retryable=retryable,
        details={"flag": retryable, f"x{token}y": token},
    )
    render_error(ctx, error, command=f"x{token}y")
    document = json.loads(out.getvalue())
    envelope_ok(document)
    emitted = document["error"]["retryable"]
    assert type(emitted) is bool
    assert emitted is retryable
    assert document["error"]["details"] == {"flag": MASK, f"x{MASK}y": MASK}
    assert document["error"]["message"] == f"x{MASK}y"
    assert document["command"] == f"x{MASK}y"
    assert document["request_id"] == f"cli-x{MASK}y"


# ---------------------------------------------------------------------------------------------------------
# a registered value never hides another detection (a review finding): the original text decides

REFERENCE = "secret://env/FIXTURE_SECRET"
DETECTIONS = [
    ("pass", "password=hunter2hunter2", "hunter2", f"{MASK}word={MASK}"),
    ("word", "password: hunter2hunter2", "hunter2", f"pass{MASK}: {MASK}"),
    ("api", "api_key=abcdefghij", "abcdefghij", f"{MASK}_key={MASK}"),
    ("-tok", "x-token=s3cr3t-value-1", "s3cr3t", f"x{MASK}en={MASK}"),
    ("sec", "secret=abcdefghij", "abcdefghij", f"{MASK}ret={MASK}"),
    ("Bear", "Bearer abcdefghijklmnopqrstuvwxyz", "abcdefghij", MASK),
    ("Bearer", "Authorization: Bearer abcdefghijklmnopqrstuvwxyz", "abcdefghij", f"Authorization: {MASK}"),
    ("cret", "secret://env/lower_invalid_value", "lower_invalid", f"se{MASK}:{MASK}"),
    ("cret", "secret://file/a\nb", "file/a", f"se{MASK}:{MASK}\nb"),
]


@pytest.mark.parametrize(("token", "value", "hidden", "expected"), DETECTIONS)
def test_a_registered_value_cannot_erase_a_pattern_detection(
    token: str, value: str, hidden: str, expected: str
) -> None:
    redactor = CliRedactor()
    redactor.register_secret(token)
    assert redactor.text(value) == expected
    assert hidden not in expected
    assert redactor.document({value: [value], "n": 1}) == {expected: [expected], "n": 1}


@pytest.mark.parametrize(("token", "value", "hidden", "expected"), DETECTIONS)
def test_a_registered_value_cannot_erase_a_detection_in_rendered_output(
    token: str, value: str, hidden: str, expected: str
) -> None:
    ctx, out, err = short_ctx(token)
    render(ctx, {"v": value}, human=lambda r: r["v"], command="x.show")
    render_error(ctx, NotFound(ErrorCode.NOT_FOUND, value), command="x.show")
    assert hidden not in out.getvalue() + err.getvalue()
    assert out.getvalue() == escape_terminal(expected) + "\n"
    assert err.getvalue() == f"error: NOT_FOUND: {escape_terminal(expected)}\n"
    assert safe_text(ctx, value) == escape_terminal(expected)
    ctx.stdin = Terminal(tty=True)
    ctx.stdin.write("n\n")
    ctx.stdin.seek(0)
    assert ctx.confirm(value) is False
    assert err.getvalue().endswith(f"{escape_terminal(expected)} [y/N] ")
    jctx, jout, _ = short_ctx(token, json=True)
    render(jctx, {value: value}, human=str, command="x.show")
    render_error(jctx, NotFound(ErrorCode.NOT_FOUND, value, details={"v": value}), command="x.show")
    assert hidden not in jout.getvalue()
    success, failure = (json.loads(line) for line in jout.getvalue().splitlines())
    assert success["result"] == {expected: expected}
    assert (failure["error"]["message"], failure["error"]["details"]) == (expected, {"v": expected})


@pytest.mark.parametrize(
    ("token", "value", "expected"),
    [
        ("zz", f"ref {REFERENCE} token=qwertyuiop", f"ref {REFERENCE} token={MASK}"),
        ("Q", f"ref {REFERENCE} Bearer abcdefghijklmnopqrstuvwxyz", f"ref {REFERENCE} {MASK}"),
        ("pass", f"ref {REFERENCE} password=hunter2hunter2", f"ref {REFERENCE} {MASK}word={MASK}"),
        ("cret", REFERENCE, f"se{MASK}://env/FIXTURE_SECRET"),
    ],
)
def test_valid_reference_metadata_stays_beside_masked_detections(
    token: str, value: str, expected: str
) -> None:
    ctx, out, _ = short_ctx(token, json=True)
    assert ctx.redactor.text(value) == expected
    render(ctx, {"v": value}, human=str, command="x.show")
    assert json.loads(out.getvalue())["result"] == {"v": expected}


# ---------------------------------------------------------------------------------------------------------
# a mask cannot complete another registered value (a review finding): already sealed, kept as a control

PRIMARY = "P" * 40


@pytest.mark.parametrize(
    ("secondary", "value"),
    [
        (MASK[3:] + "SECONDARY_0123456789", PRIMARY + "SECONDARY_0123456789"),
        ("SECONDARY_0123456789" + MASK[:4], "SECONDARY_0123456789" + PRIMARY),
        ("LEFT_FIXTURE" + MASK + "RIGHT_FIXTURE", "LEFT_FIXTURE" + PRIMARY + "RIGHT_FIXTURE"),
    ],
)
def test_a_mask_cannot_assemble_another_registered_value_in_cli_output(secondary: str, value: str) -> None:
    redactor = CliRedactor()
    for secret in (secondary, PRIMARY):
        redactor.register_secret(secret)
    assert redactor.text(value) == MASK
    assert redactor.document({value: [f"ref {REFERENCE} {value}"]}) == {MASK: [f"ref {REFERENCE} {MASK}"]}
