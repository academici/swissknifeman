"""Extraction of a role result from a session (execution §5.8, K15)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from skm.modules.execution.domain.repair import extract_result, extraction_errors

DOC: dict[str, Any] = {"status": "done", "summary": "ok"}
OTHER: dict[str, Any] = {"status": "blocked", "summary": "no"}


def fence(body: str, tag: str = "json") -> str:
    return f"```{tag}\n{body}\n```"


def text_of(*parts: str) -> str:
    return "\n\n".join(parts)


def test_structured_result_wins_over_the_text() -> None:
    found = extract_result(DOC, json.dumps(OTHER))
    assert found == {"kind": "extracted", "doc": DOC, "source": "structured"}
    assert (
        extract_result({}, "not json")["kind"] == "extracted"
    )  # an empty structured object is still structured


def test_whole_final_text_is_one_json_object() -> None:
    assert extract_result(None, json.dumps(DOC)) == {"kind": "extracted", "doc": DOC, "source": "final_text"}
    spaced = "\r\n  " + json.dumps(DOC, indent=2).replace("\n", "\r\n") + "  \r\n\r\n"
    assert extract_result(None, spaced) == {"kind": "extracted", "doc": DOC, "source": "final_text"}


def test_the_whole_text_is_taken_before_any_fence() -> None:
    inner = {
        "status": "done",
        "summary": "```json\n" + json.dumps(OTHER) + "\n```",
    }  # a fence inside a string
    assert extract_result(None, json.dumps(inner)) == {
        "kind": "extracted",
        "doc": inner,
        "source": "final_text",
    }


@pytest.mark.parametrize("tag", ["json", "JSON", "Json", ""])
def test_one_fenced_block_is_the_result(tag: str) -> None:
    text = text_of("I finished the task. Report:", fence(json.dumps(DOC), tag), "Thanks!")
    assert extract_result(None, text) == {"kind": "extracted", "doc": DOC, "source": "fenced"}


def test_crlf_text_and_indented_fences_are_read() -> None:
    text = "intro\r\n```json\r\n" + json.dumps(DOC, indent=1).replace("\n", "\r\n") + "\r\n```\r\ntail"
    assert extract_result(None, text)["doc"] == DOC
    assert extract_result(None, "intro\n   ```json\n" + json.dumps(DOC) + "\n   ```\n")["doc"] == DOC


def test_blocks_with_equal_content_are_one_candidate() -> None:
    reordered = json.dumps({"summary": "ok", "status": "done"}, indent=4)
    text = text_of(fence(json.dumps(DOC)), "and again:", fence(reordered, ""))
    assert extract_result(None, text) == {"kind": "extracted", "doc": DOC, "source": "fenced"}


def test_different_candidates_are_ambiguous_and_the_last_one_is_not_chosen() -> None:
    text = text_of(fence(json.dumps(DOC)), fence(json.dumps(OTHER)))
    found = extract_result(None, text)
    assert found == {"kind": "ambiguous", "candidates": [DOC, OTHER]}
    assert extraction_errors(found) == [
        {"path": "", "message": "several different result documents", "expected": ""}
    ]
    # order of appearance is kept, and a repeat of the first does not make it "the last"
    three = extract_result(
        None, text_of(fence(json.dumps(DOC)), fence(json.dumps(OTHER)), fence(json.dumps(DOC)))
    )
    assert three == {"kind": "ambiguous", "candidates": [DOC, OTHER]}


def test_missing_result() -> None:
    found = extract_result(None, "I could not finish.")
    assert found == {"kind": "missing"}
    assert extraction_errors(found) == [{"path": "", "message": "no result document", "expected": ""}]
    assert extract_result(None, "") == {"kind": "missing"}
    assert extraction_errors({"kind": "extracted", "doc": DOC, "source": "structured"}) == []


@pytest.mark.parametrize(
    "text",
    [
        fence(json.dumps(DOC), "python"),  # another language
        fence(json.dumps(DOC), "jsonc"),
        fence('{"status": "done"', "json"),  # broken JSON
        fence(json.dumps([DOC]), "json"),  # not an object
        fence('{"a": NaN}', "json"),  # not JSON
        fence('{"a": 1e999}', "json"),  # infinity
        "```json\n" + json.dumps(DOC),  # never closed
        json.dumps([DOC]),  # a top-level list
        "5",
        "null",
        '"just text"',
    ],
)
def test_text_that_holds_no_result_object_is_missing(text: str) -> None:
    assert extract_result(None, text) == {"kind": "missing"}


def test_other_blocks_do_not_disturb_the_one_result() -> None:
    text = text_of(
        fence("echo hi", "bash"), fence(json.dumps(DOC)), fence("x = 1", "python"), fence("{broken", "json")
    )
    assert extract_result(None, text)["doc"] == DOC


def test_a_longer_fence_can_contain_a_shorter_one() -> None:
    inner = "```json\n" + json.dumps(OTHER) + "\n```"
    text = "````json\n" + json.dumps({"status": "done", "summary": inner}) + "\n````"
    assert extract_result(None, text)["doc"] == {"status": "done", "summary": inner}


_FENCE_TAGS = (
    "",
    "json",
    "scout",
    "executor",
    "reviewer",
    "triager",
    "advisor",
    "researcher",
    "registrar",
    "context-map",
    "stage-report",
    "review-findings",
    "triage-result",
    "advice",
    "research-result",
    "registration-receipt",
)


def test_a_leading_bom_is_stripped_before_json_and_fences() -> None:
    payload = json.dumps(DOC)
    assert extract_result(None, "\ufeff" + payload) == {
        "kind": "extracted",
        "doc": DOC,
        "source": "final_text",
    }
    assert extract_result(None, "\r\n \ufeff" + payload)["doc"] == DOC
    quoted = {"status": "done", "summary": "\ufeffok"}
    assert extract_result(None, json.dumps(quoted))["doc"] == quoted  # a BOM inside a string stays
    for text in (
        "```json\n\ufeff" + payload + "\n```",
        "\ufeff```json\n" + payload + "\n```",
        "~~~\n\ufeff" + payload + "\n~~~",
        "\ufeff~~~\n" + payload + "\n~~~",
    ):
        assert extract_result(None, text) == {"kind": "extracted", "doc": DOC, "source": "fenced"}


def test_a_fence_closes_only_on_its_own_character_and_width() -> None:
    body = json.dumps(DOC)
    assert extract_result(None, f"~~~\n{body}\n~~~")["doc"] == DOC
    assert extract_result(None, f"~~~~json\n{body}\n~~~~~")["doc"] == DOC
    assert extract_result(None, "   ~~~\n" + body + "\n   ~~~\n")["doc"] == DOC
    # a shorter run, or the other character, does not end the fence, so the trailing words stay in the body
    for text in (
        f"~~~~\n{body}\n~~~\nnot json\n~~~~",
        f"~~~\n{body}\n```\nnot json\n~~~",
        f"```\n{body}\n~~~\nnot json\n```",
        f"````\n{body}\n```\nnot json\n````",
    ):
        assert extract_result(None, text) == {"kind": "missing"}
    both = text_of(f"~~~\n{body}\n~~~", fence(json.dumps(OTHER)))
    assert extract_result(None, both) == {"kind": "ambiguous", "candidates": [DOC, OTHER]}


@pytest.mark.parametrize("mark", ["```", "~~~"])
@pytest.mark.parametrize("tag", _FENCE_TAGS)
def test_role_and_kind_fences_are_results(mark: str, tag: str) -> None:
    text = f"{mark}{tag}\n{json.dumps(DOC)}\n{mark}"
    assert extract_result(None, text) == {"kind": "extracted", "doc": DOC, "source": "fenced"}


@pytest.mark.parametrize("tag", ["JSON", "Scout", "EXECUTOR", "Stage-Report", "Review-Findings"])
def test_fence_tags_are_casefolded(tag: str) -> None:
    assert extract_result(None, fence(json.dumps(DOC), tag))["doc"] == DOC
    assert extract_result(None, f"~~~{tag}\n{json.dumps(DOC)}\n~~~")["doc"] == DOC


@pytest.mark.parametrize("mark", ["```", "~~~"])
@pytest.mark.parametrize("tag", ["python", "jsonc", "javascript", "yaml"])
def test_other_fence_languages_are_not_results(mark: str, tag: str) -> None:
    assert extract_result(None, f"{mark}{tag}\n{json.dumps(DOC)}\n{mark}") == {"kind": "missing"}


def test_only_the_final_text_is_scanned() -> None:
    """The transcript is not an input: a result mentioned earlier is not part of final_text."""
    final_text = "Done, see the report file."
    assert extract_result(None, final_text) == {"kind": "missing"}


@given(st.text(max_size=300))
def test_extraction_is_total_and_deterministic(text: str) -> None:
    first = extract_result(None, text)
    assert first == extract_result(None, text)
    assert first["kind"] in ("extracted", "ambiguous", "missing")


@given(
    st.dictionaries(
        st.text(max_size=8), st.integers() | st.text(max_size=8) | st.booleans() | st.none(), max_size=6
    )
)
def test_a_json_object_round_trips_in_a_fence(document: dict[str, Any]) -> None:
    text = "result:\n" + fence(json.dumps(document, indent=2))
    found = extract_result(None, text)
    if not document:
        # `{}` is a valid object result
        assert found["doc"] == document
    assert found == {"kind": "extracted", "doc": document, "source": "fenced"}
