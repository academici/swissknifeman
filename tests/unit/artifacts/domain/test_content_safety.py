"""CS-* rules (artifacts §4.3); the applicable PS-* cases of legacy workspace test_safety.py, as CS-*."""

import json
from dataclasses import replace

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.json_types import JsonValue
from skm.modules.artifacts.domain.classification import Classification, allowed_for_runtime
from skm.modules.artifacts.domain.content_safety import (
    ABSOLUTE_PATH_PATTERN,
    BINARY_PROBE_BYTES,
    HOME_PATH_PATTERN,
    MASK,
    NOT_A_SECRET_PATTERNS,
    Admit,
    ContentKind,
    Reject,
    SafetyFinding,
    SafetyLevel,
    SafetyReport,
    SafetyRule,
    SafetyRules,
    decide_admission,
    is_safety_rule,
    scan_bytes,
    scan_document,
    symlink_finding,
)
from skm.modules.artifacts.domain.upload_rules import detect_media_type
from skm.platform.logging.redaction import DEFAULT_PATTERNS

TOKEN = "ghp_" + "a1B2" * 9  # 36 characters after the prefix
RULES = SafetyRules(
    secret_name_globs=(".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "credentials.*", "secrets.*"),
    token_patterns=(DEFAULT_PATTERNS[0],),
    named_secret_pattern=DEFAULT_PATTERNS[1],
    not_a_secret=NOT_A_SECRET_PATTERNS,
    home_path=HOME_PATH_PATTERN,
    absolute_path=ABSOLUTE_PATH_PATTERN,
    binary_probe_bytes=BINARY_PROBE_BYTES,
    max_text_scan_bytes=5 * 1024 * 1024,
)
SMALL = replace(RULES, max_text_scan_bytes=1000)


@pytest.mark.parametrize("value", [["CS-SYMLINK"], {"rule": "CS-SYMLINK"}])
def test_safety_rule_rejects_non_string_json_values(value: object) -> None:
    assert is_safety_rule(value) is False


def scan(
    content: str | bytes,
    name: str = "notes.md",
    kind: ContentKind = ContentKind.UPLOAD,
    declared: str | None = None,
    rules: SafetyRules = RULES,
) -> SafetyReport:
    data = content.encode() if isinstance(content, str) else content
    return scan_bytes(
        name, data[:rules.max_text_scan_bytes], lambda: data, len(data), rules, kind, declared,
        detect_media_type(data[:4096]),
    )  # fmt: skip


def rules_of(report: SafetyReport, level: SafetyLevel | None = None) -> list[str]:
    return [f.rule for f in report.findings if level is None or f.level == level]


def dumped(report: SafetyReport) -> str:
    return json.dumps([f.to_json() for f in report.findings], ensure_ascii=False)


def never_read() -> bytes:
    raise AssertionError("the body must not be read")


# --- CS-SECRET-CONTENT --------------------------------------------------------------------------


def test_a_token_in_a_text_file_blocks_and_is_never_printed() -> None:
    report = scan(f"line one\nthe key is {TOKEN} ok\nline three\n")
    assert rules_of(report) == ["CS-SECRET-CONTENT"]
    finding = report.findings[0]
    assert (finding.level, finding.line, finding.pointer) == (SafetyLevel.BLOCK, 2, None)
    assert MASK in finding.detail
    assert "1 match(es) of the token secret pattern, the first at line 2" in finding.detail
    text = dumped(report) + repr(report)
    assert TOKEN not in text
    assert TOKEN[4:] not in text
    assert report.verdict() == "block"


@pytest.mark.parametrize(
    "content",
    [
        '{"password": "hunter2hunter2"}',
        "API_KEY=abcdefgh12345678",
        "sk-" + "xY1" * 8,
        "AKIA" + "A" * 16,
        "xoxb-1234567890-abcdef",
        "Authorization: Bearer " + "z" * 24,
        "github_pat_" + "q" * 24,
    ],
)
def test_named_secrets_and_other_token_formats(content: str) -> None:
    report = scan(content)
    assert rules_of(report) == ["CS-SECRET-CONTENT"]
    assert content.split()[-1][-8:] not in dumped(report)


@pytest.mark.parametrize(
    "content",
    [
        "see task-development-workflow-and-more for details",
        "skill sk-plugin-development-guide",
        "findings-task-0204-lifecycle-compatibility-2026-09-22.json",
        'token = "<SET-ME-LATER>"',
        "SECRET=<SECRET_VALUE>",
        "api_key: ${API_KEY_VALUE}",
        'token = "env://MY_TOKEN_NAME"',
        "password: $PASSWORD_FROM_ENV",
        "the token budget is large\npassword: short\nsecret handling is discussed",
    ],
)
def test_slugs_placeholders_references_and_prose_are_not_secrets(content: str) -> None:
    report = scan(content + "\n")
    assert report.findings == ()
    assert report.verdict() == "ok"


@pytest.mark.parametrize(
    "content",
    [
        "sk-" + "Ab1" * 10,
        "sk-proj-" + "a1" * 12,
        'token = "plainvalue123"',
        "SECRET=abcd1234efgh",
        'token = "<abcdefgh1234567890"',
        "SECRET={Abcd1234efgh5678",
        'password: "$abcd1234efgh!x"',
        "api_key=env://a1b2c3d4e5f6?x=1",
        "token=<NAME>suffix1234",
        "password=${HOME}x1234567",
    ],
)
def test_a_value_that_only_looks_like_a_placeholder_is_still_a_secret(content: str) -> None:
    assert rules_of(scan(content + "\n")) == ["CS-SECRET-CONTENT"]


def test_matches_are_counted_and_the_first_line_and_pattern_are_named() -> None:
    report = scan(f"ok\npassword=abcdefgh1234 and {TOKEN}\n{TOKEN}\n")
    (finding,) = report.findings
    assert finding.line == 2
    assert finding.detail.startswith("3 match(es) of the token secret pattern, the first at line 2")


# --- CS-SECRET-NAME -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [".env", ".env.local", "id.pem", "tls.KEY", "store.p12", "store.pfx", "credentials.json", "secrets.yaml",
     "id.pem.", "ID.PEM ", "\uff0eenv"],
)  # fmt: skip
def test_secret_file_names_block_even_when_empty(name: str) -> None:
    report = scan("", name=name)
    assert rules_of(report) == ["CS-SECRET-NAME"]
    assert MASK in report.findings[0].detail
    assert report.verdict() == "block"


@pytest.mark.parametrize("name", ["notes.env.md", "environment.txt", "key.txt", "pem", "my-credentials"])
def test_ordinary_names_are_not_secret_names(name: str) -> None:
    assert scan("hello", name=name).findings == ()


def test_a_large_file_is_not_scanned_but_its_name_still_counts() -> None:
    data = ("x" * 2000 + TOKEN).encode()
    report = scan_bytes(
        "big.pem", data[:100], never_read, len(data), SMALL, ContentKind.UPLOAD, None, "text/plain"
    )
    assert rules_of(report) == ["CS-SECRET-NAME", "CS-NOT-SCANNED"]


# --- CS-BINARY / CS-NOT-SCANNED -----------------------------------------------------------------


def test_binary_content_skips_the_text_rules_and_is_reported() -> None:
    data = b"\0\0" + TOKEN.encode() + b" /home/someone/x"
    report = scan_bytes(
        "b.bin", data, never_read, len(data), RULES, ContentKind.UPLOAD, None, "application/octet-stream"
    )
    assert rules_of(report) == ["CS-BINARY"]
    assert report.findings[0].level == SafetyLevel.INFO
    assert report.binary is True
    assert report.verdict() == "ok"


def test_a_nul_after_the_binary_probe_is_text() -> None:
    report = scan(b"a" * BINARY_PROBE_BYTES + b"\0" + TOKEN.encode())
    assert report.binary is False
    assert rules_of(report) == ["CS-SECRET-CONTENT"]


def test_an_archive_stays_bytes_and_is_not_inspected() -> None:
    member = f"../escape {TOKEN}".encode()
    data = b"../escape".ljust(257, b"\0") + b"ustar\x0000" + member
    report = scan(data, name="bundle.tar")
    assert rules_of(report) == ["CS-BINARY"]


def test_text_over_the_limit_is_not_scanned_and_says_so() -> None:
    data = (TOKEN + "\n" + "x" * 2000).encode()
    report = scan_bytes(
        "big.txt", data[:1000], never_read, len(data), SMALL, ContentKind.UPLOAD, None, "text/plain"
    )
    assert rules_of(report) == ["CS-NOT-SCANNED"]
    (finding,) = report.findings
    assert finding.level == SafetyLevel.INFO
    assert f"{len(data)} bytes exceed the text scan limit of 1000" in finding.detail
    assert report.verdict() == "ok"


def test_the_text_limit_is_inclusive() -> None:
    at = ("x" * (1000 - len(TOKEN)) + TOKEN).encode()
    assert len(at) == 1000
    assert rules_of(scan(at, rules=SMALL)) == ["CS-SECRET-CONTENT"]
    assert rules_of(scan(at + b"x", rules=SMALL)) == ["CS-NOT-SCANNED"]


def test_a_reader_returning_more_than_the_limit_is_not_scanned() -> None:
    data = ("x" * 2000 + TOKEN).encode()
    report = scan_bytes("a.txt", data[:10], lambda: data, 10, SMALL, ContentKind.UPLOAD, None, "text/plain")
    assert rules_of(report) == ["CS-NOT-SCANNED"]


def test_non_utf8_text_is_reported_as_not_scanned() -> None:
    report = scan(b"\xff\xfe " + TOKEN.encode())
    assert rules_of(report) == ["CS-NOT-SCANNED"]
    assert "not UTF-8" in report.findings[0].detail
    assert TOKEN not in dumped(report)


# --- CS-HOME-PATH / CS-ABSOLUTE-PATH ------------------------------------------------------------


@pytest.mark.parametrize("kind", [ContentKind.UPLOAD, ContentKind.EVIDENCE])
def test_home_paths_only_warn(kind: ContentKind) -> None:
    text = json.dumps(
        {"a": "/home/someone/x", "b": "see /Users/me/y and /home/someone/z", "c": "C:\\Users\\me\\w"}
    )
    report = scan("first line\n" + text, kind=kind)
    assert rules_of(report) == ["CS-HOME-PATH"]
    (finding,) = report.findings
    assert (finding.level, finding.line) == (SafetyLevel.WARN, 2)
    assert "4 home-directory path(s)" in finding.detail
    assert "someone" not in dumped(report)
    assert report.verdict() == "warn"


def test_paths_outside_home_do_not_warn() -> None:
    assert scan('{"root": "/srv/app", "rel": "relative/path"}').findings == ()


def test_an_absolute_path_in_a_portable_document_blocks() -> None:
    document: JsonValue = {
        "name": "/home/someone/x",
        "ok": "relative/path",
        "files": [{"path": "C:\\data\\x"}],
        "source": {"checkout_name": "~/x"},
        "note": "at /Users/me/z now",
        "created_by": "/srv/x",
        "a/b~c": "/etc/passwd",
    }
    report = scan_document(document, RULES)
    assert rules_of(report) == ["CS-ABSOLUTE-PATH"] * 6
    pointers = [f.pointer for f in report.findings]
    assert pointers == ["/name", "/files/0/path", "/source/checkout_name", "/note", "/created_by", "/a~1b~0c"]
    assert all(f.level == SafetyLevel.BLOCK and f"at {f.pointer} of" in f.detail for f in report.findings)
    assert "someone" not in dumped(report)
    assert report.verdict() == "block"


def test_a_relative_portable_document_passes() -> None:
    report = scan_document({"name": "demo", "items": ["a/b", "c"], "n": 1, "x": None}, RULES)
    assert report.findings == ()
    assert report.verdict() == "ok"


def test_portable_document_bytes_are_parsed_for_absolute_paths() -> None:
    report = scan(
        json.dumps({"root": "/srv/app", "home": "/home/someone/x"}), kind=ContentKind.PORTABLE_DOCUMENT
    )
    assert [(f.rule, f.pointer) for f in report.findings] == [
        ("CS-ABSOLUTE-PATH", "/root"),
        ("CS-ABSOLUTE-PATH", "/home"),
    ]  # judged by the block rule alone: no CS-HOME-PATH warning


def test_invalid_json_portable_document_is_not_a_path_finding() -> None:
    report = scan("{broken /home/someone/x", kind=ContentKind.PORTABLE_DOCUMENT)
    assert rules_of(report) == ["CS-NOT-SCANNED"]
    assert rules_of(scan("{broken " + TOKEN, kind=ContentKind.PORTABLE_DOCUMENT)) == [
        "CS-SECRET-CONTENT",
        "CS-NOT-SCANNED",
    ]


@pytest.mark.parametrize(
    ("text", "pointer"),
    [
        ('{"note": "\\u0067hp_' + TOKEN[4:] + '"}', "/note"),
        ('{"list": ["ok", "\\u0041KIA' + "B" * 16 + '"]}', "/list/1"),
        ('{"pass\\u0077ord": "hunter2hunter2"}', "/password"),
    ],
)
def test_a_secret_hidden_by_json_escapes_in_portable_document_bytes_blocks(text: str, pointer: str) -> None:
    assert rules_of(scan(text)) == []  # the raw text alone shows no secret
    report = scan(text, kind=ContentKind.PORTABLE_DOCUMENT)
    assert [(f.rule, f.pointer) for f in report.findings] == [("CS-SECRET-CONTENT", pointer)]
    assert all(value not in dumped(report) for value in (TOKEN[4:], "B" * 16, "hunter2"))
    reject = rejected(decide_admission(report, ContentKind.PORTABLE_DOCUMENT, Classification.RESTRICTED, ()))
    assert reject.reason == "portable_document_blocked"


def test_a_raw_text_secret_in_a_portable_document_is_reported_once() -> None:
    report = scan(json.dumps({"note": TOKEN, "p": "/etc/x"}), kind=ContentKind.PORTABLE_DOCUMENT)
    assert [(f.rule, f.line, f.pointer) for f in report.findings] == [
        ("CS-SECRET-CONTENT", 1, None),
        ("CS-ABSOLUTE-PATH", None, "/p"),
    ]


def test_a_named_secret_split_into_key_and_value_is_found() -> None:
    report = scan_document({"nested": [{"password": "hunter2hunter2"}], "token": "short"}, RULES)
    assert [(f.rule, f.pointer) for f in report.findings] == [("CS-SECRET-CONTENT", "/nested/0/password")]
    assert "hunter2" not in dumped(report)


def test_document_secrets_are_counted_with_a_pointer_and_never_copied() -> None:
    document: JsonValue = {"ok": "x", "deep": {"list": ["fine", f"key {TOKEN}"]}, "password": "abcd1234efgh"}
    report = scan_document(document, RULES)
    (finding,) = report.findings
    assert (finding.rule, finding.pointer, finding.line) == ("CS-SECRET-CONTENT", "/deep/list/1", None)
    assert finding.detail.startswith(
        "2 match(es) of the token secret pattern, the first at pointer /deep/list/1"
    )
    assert TOKEN not in dumped(report)


def test_secret_or_path_keys_never_enter_a_pointer() -> None:
    report = scan_document({TOKEN: {"p": "/etc/x"}, "/home/someone/k": "v"}, RULES)
    assert [(f.rule, f.pointer) for f in report.findings] == [
        ("CS-SECRET-CONTENT", f"/{MASK}"),
        ("CS-ABSOLUTE-PATH", f"/{MASK}/p"),
    ]
    assert TOKEN not in dumped(report)
    assert "someone" not in dumped(report)


def test_a_deep_document_is_scanned_without_recursion() -> None:
    document: JsonValue = "/etc/x"
    for _ in range(5000):
        document = [document]
    report = scan_document(document, RULES)
    assert rules_of(report) == ["CS-ABSOLUTE-PATH"]


# --- CS-SYMLINK / CS-MEDIA-MISMATCH / CS-EXECUTABLE ---------------------------------------------


def test_symlink_finding_blocks_and_scan_bytes_never_reports_it() -> None:
    finding = symlink_finding()
    assert (finding.rule, finding.level) == ("CS-SYMLINK", SafetyLevel.BLOCK)
    assert SafetyReport((finding,), (), False).verdict() == "block"
    assert "CS-SYMLINK" not in rules_of(scan("x", name="link.md"))


def test_media_mismatch_warns_with_declared_and_detected() -> None:
    report = scan(b"%PDF-1.7\n", name="a.png", declared="image/png; q=1")
    assert rules_of(report) == ["CS-MEDIA-MISMATCH"]
    assert report.findings[0].detail == "image/png \u2192 application/pdf"
    assert report.verdict() == "warn"
    assert scan(b"%PDF-1.7\n", declared="application/pdf").findings == ()
    assert scan(b"%PDF-1.7\n").findings == ()


def test_media_mismatch_detail_never_copies_an_invalid_or_secret_declared_type() -> None:
    bad = scan(b"%PDF-1.7\n", declared=f"bad {TOKEN}")
    secret = scan(b"%PDF-1.7\n", declared="text/sk-" + "a1b2" * 6)
    assert [f.detail for f in bad.findings] == ["an invalid media type \u2192 application/pdf"]
    assert [f.detail for f in secret.findings] == [f"{MASK} \u2192 application/pdf"]


@pytest.mark.parametrize("declared", ["text/AKIAIOSFODNN7EXAMPLE", "Text/AKIAIOSFODNN7EXAMPLE; charset=x"])
def test_media_mismatch_detail_never_copies_a_secret_that_lower_casing_hides(declared: str) -> None:
    report = scan(b"%PDF-1.7\n", declared=declared)
    assert [f.detail for f in report.findings] == [f"{MASK} \u2192 application/pdf"]
    assert "iosfodnn7example" not in dumped(report).casefold()


@pytest.mark.parametrize(
    ("head", "detected"),
    [(b"\x7fELF\x02", "application/x-elf"), (b"MZ\x90\x00", "application/vnd.microsoft.portable-executable"),
     (b"\x00asm\x01", "application/wasm"), (b"\xcf\xfa\xed\xfe", "application/x-mach-binary"),
     (b"#!/bin/sh\necho hi\n", "text/x-script")],
)  # fmt: skip
def test_executable_signatures_warn(head: bytes, detected: str) -> None:
    report = scan(head)
    assert "CS-EXECUTABLE" in rules_of(report, SafetyLevel.WARN)
    assert detected in report.findings[-1].detail
    assert report.verdict() == "warn"


def test_non_executable_signature_does_not_warn() -> None:
    assert scan(b"\x89PNG\r\n\x1a\n\x00\x00", declared="image/png").findings[-1].rule == "CS-BINARY"


# --- verdict ------------------------------------------------------------------------------------


def finding(rule: SafetyRule, level: SafetyLevel) -> SafetyFinding:
    return SafetyFinding(rule, level, "d", None, None)


def test_verdicts() -> None:
    block = finding("CS-SECRET-NAME", SafetyLevel.BLOCK)
    warn = finding("CS-HOME-PATH", SafetyLevel.WARN)
    info = finding("CS-BINARY", SafetyLevel.INFO)
    assert SafetyReport((), (), False).verdict() == "ok"
    assert SafetyReport((info,), (), True).verdict() == "ok"
    assert SafetyReport((warn, info), (), False).verdict() == "warn"
    assert SafetyReport((block, warn), (), False).verdict() == "block"
    assert SafetyReport((block,), ("CS-SECRET-NAME",), False).verdict() == "warn"
    assert SafetyReport((block,), ("CS-HOME-PATH",), False).verdict() == "block"  # another rule's ack


# --- admission (§4.3 table) ---------------------------------------------------------------------

SECRET = finding("CS-SECRET-CONTENT", SafetyLevel.BLOCK)
NAME = finding("CS-SECRET-NAME", SafetyLevel.BLOCK)
CLEAN = SafetyReport((finding("CS-HOME-PATH", SafetyLevel.WARN),), (), False)
BLOCKED = SafetyReport((SECRET, NAME), (), False)


def admitted(admission: Admit | Reject) -> Admit:
    assert isinstance(admission, Admit), admission
    return admission


def rejected(admission: Admit | Reject) -> Reject:
    assert isinstance(admission, Reject), admission
    return admission


@pytest.mark.parametrize("kind", list(ContentKind))
def test_without_block_findings_every_kind_is_admitted_as_requested(kind: ContentKind) -> None:
    admit = admitted(decide_admission(CLEAN, kind, Classification.PUBLIC, ()))
    assert (admit.classification, admit.report, admit.escalated_by) == (Classification.PUBLIC, CLEAN, ())


def test_upload_with_every_block_acknowledged_and_confidential_is_admitted() -> None:
    acknowledge = ["CS-SECRET-NAME", "CS-SECRET-CONTENT", "CS-HOME-PATH"]
    admit = admitted(decide_admission(BLOCKED, ContentKind.UPLOAD, Classification.CONFIDENTIAL, acknowledge))
    assert admit.classification is Classification.CONFIDENTIAL
    assert admit.report.acknowledged == ("CS-SECRET-CONTENT", "CS-SECRET-NAME")
    assert admit.report.verdict() == "warn"
    assert admit.escalated_by == ()


def test_upload_acknowledged_below_the_minimum_classification_is_rejected() -> None:
    acknowledge = ("CS-SECRET-CONTENT", "CS-SECRET-NAME")
    reject = rejected(decide_admission(BLOCKED, ContentKind.UPLOAD, Classification.INTERNAL, acknowledge))
    assert reject.reason == "classification_below_acknowledge_minimum"
    admitted(
        decide_admission(
            BLOCKED,
            ContentKind.UPLOAD,
            Classification.INTERNAL,
            acknowledge,
            acknowledge_min_classification=Classification.INTERNAL,
        )
    )
    rejected(
        decide_admission(
            BLOCKED,
            ContentKind.UPLOAD,
            Classification.CONFIDENTIAL,
            acknowledge,
            acknowledge_min_classification=Classification.RESTRICTED,
        )
    )


@pytest.mark.parametrize("acknowledge", [(), ("CS-SECRET-NAME",), ("CS-HOME-PATH",)])
def test_upload_with_an_unacknowledged_block_is_rejected(acknowledge: tuple[str, ...]) -> None:
    reject = rejected(decide_admission(BLOCKED, ContentKind.UPLOAD, Classification.RESTRICTED, acknowledge))
    assert reject.reason == "not_acknowledged"
    error = reject.error()
    assert error.code is ErrorCode.CONTENT_UNSAFE
    assert [item["rule"] for item in error.details["findings"]] == ["CS-SECRET-CONTENT", "CS-SECRET-NAME"]  # type: ignore[index, union-attr]


def test_a_symlink_source_cannot_be_acknowledged() -> None:
    report = SafetyReport((symlink_finding(),), (), False)
    reject = rejected(decide_admission(report, ContentKind.UPLOAD, Classification.RESTRICTED, ["CS-SYMLINK"]))
    assert reject.reason == "not_acknowledged"


@pytest.mark.parametrize("acknowledge", [(), ("CS-SECRET-CONTENT", "CS-SECRET-NAME")])
def test_evidence_with_block_findings_is_kept_as_restricted_and_never_reaches_a_runtime(
    acknowledge: tuple[str, ...],
) -> None:
    admit = admitted(decide_admission(BLOCKED, ContentKind.EVIDENCE, Classification.PUBLIC, acknowledge))
    assert admit.classification is Classification.RESTRICTED
    assert admit.report.acknowledged == ()  # acknowledging never applies to evidence
    assert admit.report.verdict() == "block"
    assert admit.escalated_by == ("CS-SECRET-CONTENT", "CS-SECRET-NAME")
    assert not allowed_for_runtime(admit.classification, Classification.CONFIDENTIAL)


def test_an_acknowledged_upload_is_not_lowered_for_a_runtime() -> None:
    acknowledge = ("CS-SECRET-CONTENT", "CS-SECRET-NAME")
    admit = admitted(decide_admission(BLOCKED, ContentKind.UPLOAD, Classification.RESTRICTED, acknowledge))
    assert admit.classification is Classification.RESTRICTED
    assert not allowed_for_runtime(admit.classification, Classification.CONFIDENTIAL)


@pytest.mark.parametrize("acknowledge", [(), ("CS-ABSOLUTE-PATH",)])
def test_portable_document_with_any_block_is_rejected(acknowledge: tuple[str, ...]) -> None:
    report = scan_document({"p": "/etc/x"}, RULES)
    reject = rejected(
        decide_admission(report, ContentKind.PORTABLE_DOCUMENT, Classification.RESTRICTED, acknowledge)
    )
    assert reject.reason == "portable_document_blocked"
    assert reject.error().code is ErrorCode.CONTENT_UNSAFE


def test_g21_warnings_combine_with_an_evidence_block() -> None:
    report = SafetyReport((SECRET, finding("CS-EXECUTABLE", SafetyLevel.WARN)), (), False)
    admit = admitted(decide_admission(report, ContentKind.EVIDENCE, Classification.PUBLIC, ()))
    assert admit.classification is Classification.RESTRICTED
    assert admit.escalated_by == ("CS-SECRET-CONTENT", "CS-EXECUTABLE")


def test_rejection_details_never_hold_the_secret() -> None:
    report = scan(f"api_key={TOKEN}\n", name=".env")
    error = rejected(decide_admission(report, ContentKind.UPLOAD, Classification.PUBLIC, ())).error()
    problem = json.dumps(error.to_problem(), ensure_ascii=False)
    assert TOKEN not in problem
    assert TOKEN[4:] not in problem
    assert "CS-SECRET-NAME" in problem
    assert "CS-SECRET-CONTENT" in problem
