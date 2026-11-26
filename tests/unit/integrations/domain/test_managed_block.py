"""Unit and property tests for HTML-comment managed block codec (integrations §4.5)."""

from __future__ import annotations

import hashlib

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from skm.modules.integrations.domain.managed_block import (
    BlockMarker,
    extract_blocks,
    is_valid_block_id,
    parse_markers,
    render_block,
    replace_blocks,
)


def test_render_block_format_digest_and_trailing_newline_normalization() -> None:
    body = "Line one\nLine two\n\n\n"
    expected_body = "Line one\nLine two\n"
    expected_digest = hashlib.sha256(expected_body.encode("utf-8")).hexdigest()[:12]

    rendered = render_block("instructions.core", body)
    assert (
        rendered
        == (
            f"<!-- skm:begin id=instructions.core digest={expected_digest} -->\n"
            f"{expected_body}"
            f"<!-- skm:end id=instructions.core -->\n"
        ).encode()
    )


def test_render_block_empty_body_and_crlf_input_normalization() -> None:
    empty_digest = hashlib.sha256(b"").hexdigest()[:12]
    assert (
        render_block("instructions.project", "")
        == (
            f"<!-- skm:begin id=instructions.project digest={empty_digest} -->\n"
            f"<!-- skm:end id=instructions.project -->\n"
        ).encode()
    )

    crlf_rendered = render_block("instructions.core", "Alpha\r\nBeta\r\n\r\n")
    norm_digest = hashlib.sha256(b"Alpha\nBeta\n").hexdigest()[:12]
    assert (
        crlf_rendered
        == (
            f"<!-- skm:begin id=instructions.core digest={norm_digest} -->\n"
            f"Alpha\nBeta\n"
            f"<!-- skm:end id=instructions.core -->\n"
        ).encode()
    )


@pytest.mark.parametrize(
    ("block_id", "valid"),
    [
        ("instructions.core", True),
        ("instructions.project", True),
        ("a", True),
        ("skm-1.sub-2", True),
        ("", False),
        ("Instructions.Core", False),
        ("1leading-digit", False),
        ("trailing.", False),
        (".leading", False),
        ("bad space", False),
        ("under_score", False),
    ],
)
def test_block_id_validation(block_id: str, valid: bool) -> None:
    assert is_valid_block_id(block_id) is valid
    if not valid:
        with pytest.raises(ValueError, match="INTEGRATION_BOUNDARY_INVALID"):
            render_block(block_id, "body")


def test_extract_blocks_single_multiple_absent_and_stale_digest() -> None:
    ids = ("instructions.core", "instructions.project")
    assert extract_blocks(b"", ids) == b""
    assert extract_blocks(b"# User heading\nCustom text\n", ids) == b""

    b1 = render_block("instructions.core", "Core rules")
    b2 = render_block("instructions.project", "Project rules")
    doc = b"# Header\n\n" + b1 + b"\nMiddle paragraph\n\n" + b2 + b"\nFooter\n"
    assert extract_blocks(doc, ids) == b1 + b2

    # Marker digest is informational; user editing inside a block does NOT invalidate boundary extraction
    edited_b1 = (
        b"<!-- skm:begin id=instructions.core digest=000000000000 -->\n"
        b"User edited inside block\n"
        b"<!-- skm:end id=instructions.core -->\n"
    )
    edited_doc = b"Intro\n" + edited_b1 + b"Between\n" + b2
    assert extract_blocks(edited_doc, ids) == edited_b1 + b2


def test_parse_markers_captures_offsets() -> None:
    block = render_block("instructions.core", "Hello")
    raw = b"Prefix\n" + block + b"Suffix\n"
    markers = parse_markers(raw)
    assert markers is not None
    assert len(markers) == 2
    assert isinstance(markers[0], BlockMarker)
    assert markers[0].kind == "begin"
    assert markers[0].block_id == "instructions.core"
    assert markers[0].start == len(b"Prefix\n")
    assert markers[1].kind == "end"
    assert markers[1].end == len(b"Prefix\n") + len(block)


def test_replace_blocks_into_empty_and_non_empty_files() -> None:
    ids = ("instructions.core", "instructions.project")
    managed = render_block("instructions.core", "Core") + render_block("instructions.project", "Proj")

    # Empty file
    from_empty = replace_blocks(b"", managed, ids)
    assert from_empty == managed
    assert extract_blocks(from_empty, ids) == managed

    # Non-empty file ending with newline
    with_nl = b"# User Notes\nKeep me.\n"
    res_nl = replace_blocks(with_nl, managed, ids)
    assert res_nl == with_nl + managed
    assert replace_blocks(res_nl, b"", ids) == with_nl

    # Non-empty file WITHOUT trailing newline -> prepends '\n' before managed block
    without_nl = b"# User Notes without trailing newline"
    res_no_nl = replace_blocks(without_nl, managed, ids)
    assert res_no_nl == without_nl + b"\n" + managed
    assert extract_blocks(res_no_nl, ids) == managed


def test_replace_blocks_in_place_preserves_crlf_and_unicode_outside() -> None:
    ids = ("instructions.core", "instructions.project")
    old_b1 = (
        b"<!-- skm:begin id=instructions.core digest=aaaaaaaaaaaa -->\r\n"
        b"Old core\r\n"
        b"<!-- skm:end id=instructions.core -->\r\n"
    )
    old_b2 = (
        b"<!-- skm:begin id=instructions.project digest=bbbbbbbbbbbb -->\r\n"
        b"Old project\r\n"
        b"<!-- skm:end id=instructions.project -->\r\n"
    )
    prefix = "# User Heading 🚀\r\n日本語テキスト αβγ\r\n\r\n".encode()
    middle = "\r\n中間セクション CRLF ✨\r\n".encode()
    suffix = "\r\n末尾テキスト Ω".encode()

    raw = prefix + old_b1 + middle + old_b2 + suffix
    assert extract_blocks(raw, ids) == old_b1 + old_b2

    new_b1 = render_block("instructions.core", "New core αβγ")
    new_b2 = render_block("instructions.project", "New project δεζ")
    updated = replace_blocks(raw, new_b1 + new_b2, ids)

    assert updated == prefix + new_b1 + middle + new_b2 + suffix
    assert extract_blocks(updated, ids) == new_b1 + new_b2
    # Restoring old blocks recovers the exact original byte sequence including CRLF
    assert replace_blocks(updated, old_b1 + old_b2, ids) == raw


@pytest.mark.parametrize(
    "malformed",
    [
        # Missing end marker
        b"<!-- skm:begin id=instructions.core digest=0123456789ab -->\nBody\n",
        # Missing begin marker
        b"Body\n<!-- skm:end id=instructions.core -->\n",
        # End before begin
        (
            b"<!-- skm:end id=instructions.core -->\n"
            b"<!-- skm:begin id=instructions.core digest=0123456789ab -->\n"
            b"<!-- skm:end id=instructions.core -->\n"
        ),
        # Nested markers
        (
            b"<!-- skm:begin id=instructions.core digest=0123456789ab -->\n"
            b"<!-- skm:begin id=instructions.project digest=0123456789ab -->\n"
            b"<!-- skm:end id=instructions.project -->\n"
            b"<!-- skm:end id=instructions.core -->\n"
        ),
        # Duplicate block_id
        (
            b"<!-- skm:begin id=instructions.core digest=0123456789ab -->\n"
            b"<!-- skm:end id=instructions.core -->\n"
            b"<!-- skm:begin id=instructions.core digest=0123456789ab -->\n"
            b"<!-- skm:end id=instructions.core -->\n"
        ),
        # Reversed block order vs requested (instructions.core, instructions.project)
        (
            b"<!-- skm:begin id=instructions.project digest=0123456789ab -->\n"
            b"<!-- skm:end id=instructions.project -->\n"
            b"<!-- skm:begin id=instructions.core digest=0123456789ab -->\n"
            b"<!-- skm:end id=instructions.core -->\n"
        ),
        # Only one of two expected blocks present
        (
            b"<!-- skm:begin id=instructions.core digest=0123456789ab -->\n"
            b"Only one\n"
            b"<!-- skm:end id=instructions.core -->\n"
        ),
        # Truncated / malformed marker line
        b"<!-- skm:begin id=instructions.core digest=short -->\n<!-- skm:end id=instructions.core -->\n",
        b"<!-- skm:begin id=instructions.core\n",
        b"prefix <!-- skm:begin id=instructions.core digest=0123456789ab -->\n",
    ],
)
def test_malformed_markers_return_none_and_raise_boundary_invalid(malformed: bytes) -> None:
    ids = ("instructions.core", "instructions.project")
    assert extract_blocks(malformed, ids) is None
    managed = render_block("instructions.core", "A") + render_block("instructions.project", "B")
    with pytest.raises(ValueError, match="INTEGRATION_BOUNDARY_INVALID"):
        replace_blocks(malformed, managed, ids)


_SAFE_OUTSIDE_TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    max_size=120,
).filter(lambda s: "<!--" not in s)


@settings(max_examples=50, deadline=None)
@given(
    before=_SAFE_OUTSIDE_TEXT,
    between=_SAFE_OUTSIDE_TEXT,
    after=_SAFE_OUTSIDE_TEXT,
    body1=_SAFE_OUTSIDE_TEXT,
    body2=_SAFE_OUTSIDE_TEXT,
)
def test_property_outside_bytes_preserved_verbatim(
    before: str,
    between: str,
    after: str,
    body1: str,
    body2: str,
) -> None:
    # Ensure outside segments preceding a marker start at line boundaries so markers sit on own lines
    prefix = (before + "\n").encode() if before else b""
    middle = (between + "\n").encode() if between else b""
    suffix = after.encode()

    ids = ("instructions.core", "instructions.project")
    initial_b1 = render_block("instructions.core", "initial-1")
    initial_b2 = render_block("instructions.project", "initial-2")
    raw = prefix + initial_b1 + middle + initial_b2 + suffix

    rendered_b1 = render_block("instructions.core", body1)
    rendered_b2 = render_block("instructions.project", body2)
    new_managed = rendered_b1 + rendered_b2
    replaced = replace_blocks(raw, new_managed, ids)

    assert replaced == prefix + rendered_b1 + middle + rendered_b2 + suffix
    assert extract_blocks(replaced, ids) == new_managed
    assert replace_blocks(replaced, initial_b1 + initial_b2, ids) == raw
