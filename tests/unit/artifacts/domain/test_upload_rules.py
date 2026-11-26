import unicodedata

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.artifacts.domain.classification import Classification
from skm.modules.artifacts.domain.content_safety import (
    Admit,
    ContentKind,
    SafetyFinding,
    SafetyLevel,
    SafetyReport,
    SafetyRule,
    decide_admission,
)
from skm.modules.artifacts.domain.upload_rules import (
    EXECUTABLE_TYPES,
    MEDIA_SIGNATURES,
    OCTET_STREAM,
    detect_media_type,
    media_type_consistent,
    normalize_media_type,
    validate_filename,
)


def reason(name: object) -> str:
    with pytest.raises(ValidationFailed) as error:
        validate_filename(name)  # type: ignore[arg-type]
    assert error.value.code is ErrorCode.SCHEMA_INVALID
    assert error.value.details["field"] == "original_filename"
    return str(error.value.details["reason"])


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("a/b", "not_basename"),
        ("a\\b", "not_basename"),
        (".", "dot_name"),
        ("..", "dot_name"),
        ("bell\x07.txt", "control_char"),
        ("nul\x00.txt", "control_char"),
        ("del\x7f.txt", "control_char"),
        ("c1\x85.txt", "control_char"),
        ("invoice\N{RIGHT-TO-LEFT OVERRIDE}gpj.exe", "control_char"),
        ("lre\N{LEFT-TO-RIGHT EMBEDDING}.txt", "control_char"),
        ("isolate\N{LEFT-TO-RIGHT ISOLATE}.txt", "control_char"),
        ("pdi\N{POP DIRECTIONAL ISOLATE}.txt", "control_char"),
        ("surrogate\udcff.txt", "control_char"),
        ("", "too_long"),
        ("ж" * 128, "too_long"),  # 256 UTF-8 bytes
    ],
)
def test_validate_filename_rejects(name: str, expected: str) -> None:
    assert reason(name) == expected


def test_validate_filename_accepts_and_returns_nfc() -> None:
    nfd = unicodedata.normalize("NFD", "café.txt")
    assert nfd != "café.txt"
    assert validate_filename(nfd) == "café.txt"
    assert validate_filename("ж" * 127 + "a") == "ж" * 127 + "a"  # 255 bytes
    assert validate_filename("..hidden") == "..hidden"
    assert validate_filename("שלום.txt") == "שלום.txt"  # right-to-left letters are not direction controls


def test_validate_filename_rejects_non_string() -> None:
    assert reason(b"a.txt") == "not_basename"


HEADS = {
    "image/png": [b"\x89PNG\r\n\x1a\n" + b"\x00" * 8],
    "image/jpeg": [b"\xff\xd8\xff\xe0rest"],
    "image/gif": [b"GIF87a...", b"GIF89a..."],
    "image/webp": [b"RIFF\x10\x00\x00\x00WEBPVP8 "],
    "application/pdf": [b"%PDF-1.7\n"],
    "application/zip": [b"PK\x03\x04data", b"PK\x05\x06" + b"\x00" * 18],
    "application/gzip": [b"\x1f\x8b\x08\x00"],
    "application/x-7z-compressed": [b"7z\xbc\xaf\x27\x1c\x00\x04"],
    "application/x-tar": [b"name.txt".ljust(257, b"\x00") + b"ustar\x0000"],
    "application/vnd.sqlite3": [b"SQLite format 3\x00" + b"\x10\x00"],
    "application/wasm": [b"\x00asm\x01\x00\x00\x00"],
    "application/x-elf": [b"\x7fELF\x02\x01\x01"],
    "application/vnd.microsoft.portable-executable": [b"MZ\x90\x00"],
    "application/x-mach-binary": [
        b"\xfe\xed\xfa\xce\x00",
        b"\xfe\xed\xfa\xcf\x00",
        b"\xce\xfa\xed\xfe\x00",
        b"\xcf\xfa\xed\xfe\x00",
    ],
    "video/mp4": [b"\x00\x00\x00\x18ftypmp42"],
    "text/x-script": [b"#!/bin/sh\necho hi\n"],
}


def test_every_signature_row_is_covered() -> None:
    assert [row.media_type for row in MEDIA_SIGNATURES] == list(HEADS)


@pytest.mark.parametrize(("expected", "head"), [(k, h) for k, heads in HEADS.items() for h in heads])
def test_detect_each_signature(expected: str, head: bytes) -> None:
    assert detect_media_type(head) == expected


def test_detect_text_and_octet_stream() -> None:
    assert detect_media_type("plain ü text\n".encode()) == "text/plain"
    assert detect_media_type(b"") == "text/plain"
    cut = ("a" * 4095 + "ж").encode()  # the head ends inside a two-byte character
    assert detect_media_type(cut[:4096]) == "text/plain"
    assert detect_media_type(b"abc\xff\xfe") == OCTET_STREAM  # not UTF-8
    assert detect_media_type(b"abc\x00def") == OCTET_STREAM
    assert detect_media_type(b"#!\x00\x01binary") == OCTET_STREAM  # a script must be text
    assert detect_media_type(b"RIFF\x10\x00\x00\x00WAVE") == OCTET_STREAM  # RIFF without WEBP


def test_detect_reads_only_the_first_4096_bytes() -> None:
    assert detect_media_type(b"a" * 4096 + b"\x00") == "text/plain"
    assert detect_media_type(b"a" * 300 + b"\x00") == OCTET_STREAM
    assert detect_media_type(b"x" * 256) == "text/plain"  # a short head never reaches the tar offset


def test_signature_order_first_match_wins() -> None:
    # A JPEG that also carries "ftyp" at offset 4 is still a JPEG: rows are checked from the top.
    assert detect_media_type(b"\xff\xd8\xff\x00ftypmp42") == "image/jpeg"


@pytest.mark.parametrize(
    ("declared", "detected", "expected"),
    [
        (None, "image/png", True),
        ("image/png", OCTET_STREAM, True),
        ("text/html", OCTET_STREAM, True),
        ("image/png", "image/png", True),
        ("IMAGE/PNG; charset=binary", "image/png", True),
        ("image/jpg", "image/jpeg", True),
        ("application/x-gzip", "application/gzip", True),
        ("application/x-zip-compressed", "application/zip", True),
        ("application/x-pdf", "application/pdf", True),
        ("text/markdown", "text/plain", True),
        ("text/x-python", "text/x-script", True),
        ("application/json", "text/plain", True),
        ("application/x-ndjson", "text/plain", True),
        ("application/yaml", "text/plain", True),
        ("image/svg+xml", "text/plain", True),
        ("application/x-sh", "text/x-script", True),
        ("image/png", "text/plain", False),
        ("application/zip", "application/zip", True),
        ("application/java-archive", "application/zip", True),
        ("application/epub+zip", "application/zip", True),
        ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/zip", True),
        ("application/vnd.oasis.opendocument.text", "application/zip", True),
        ("application/pdf", "application/zip", False),
        ("image/png", "application/x-elf", False),
        ("application/pdf", "image/png", False),
        ("text/plain", "application/pdf", False),
        ("not a media type", "image/png", False),
    ],
)
def test_media_type_consistent(declared: str | None, detected: str, expected: bool) -> None:
    assert media_type_consistent(declared, detected) is expected


def test_normalize_media_type() -> None:
    assert normalize_media_type(None) is None
    assert normalize_media_type(" Text/Plain ; charset=utf-8") == "text/plain"
    for bad in ["text", "text/", "/plain", "a b/c", "text/plain/x", "t" * 201]:
        with pytest.raises(ValidationFailed) as error:
            normalize_media_type(bad)
        assert error.value.details["reason"] == "invalid_media_type"


def test_executable_types() -> None:
    assert (
        frozenset(
            {
                "application/x-elf",
                "application/vnd.microsoft.portable-executable",
                "application/x-mach-binary",
                "application/wasm",
                "text/x-script",
            }
        )
        == EXECUTABLE_TYPES
    )


@pytest.mark.parametrize("rule", ["CS-MEDIA-MISMATCH", "CS-EXECUTABLE"])
@pytest.mark.parametrize("kind", list(ContentKind))
def test_g21_warnings_raise_public_to_internal(rule: SafetyRule, kind: ContentKind) -> None:
    report = SafetyReport((SafetyFinding(rule, SafetyLevel.WARN, "d", None, None),), (), False)
    admission = decide_admission(report, kind, Classification.PUBLIC, ())
    assert isinstance(admission, Admit)
    assert admission.classification is Classification.INTERNAL
    assert admission.escalated_by == (rule,)
    assert report.verdict() == "warn"


def test_g21_warnings_never_lower_a_classification() -> None:
    report = SafetyReport((SafetyFinding("CS-EXECUTABLE", SafetyLevel.WARN, "d", None, None),), (), False)
    admission = decide_admission(report, ContentKind.UPLOAD, Classification.CONFIDENTIAL, ())
    assert isinstance(admission, Admit)
    assert admission.classification is Classification.CONFIDENTIAL


def test_without_g21_warnings_public_stays_public() -> None:
    admission = decide_admission(SafetyReport((), (), False), ContentKind.UPLOAD, Classification.PUBLIC, ())
    assert isinstance(admission, Admit)
    assert (admission.classification, admission.escalated_by) == (Classification.PUBLIC, ())
