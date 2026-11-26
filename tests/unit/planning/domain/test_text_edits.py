"""``replace_text``: exact narrative edits guarded by a UTF-8 digest of the whole field (planning §5.3.7)."""

import copy
import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, SkmError, ValidationFailed
from skm.modules.planning.domain.changes import ItemDefaults, PatchChange, ReplaceTextChange, apply_changes
from skm.modules.planning.domain.item import Effort, ModelClass
from skm.modules.planning.domain.review_requirement import ReviewMode
from skm.modules.planning.domain.text_edits import TEXT_EDIT_FIELDS, is_text_field, text_digest
from skm.platform.schema.registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[4]
EXAMPLE = ROOT / "tests/fixtures/corpus/examples/plans/auth-refresh.specification.json"
SPECIFICATION = "urn:skm:planning:specification:v1"
DEFAULTS = ItemDefaults(ModelClass.IMPLEMENTATION, Effort.MEDIUM, ReviewMode.REQUIRED)


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def _doc() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text())


def _edit(doc, target, pointer, old, new, *, current=None, index=0) -> dict[str, Any]:
    value = current if current is not None else _read(doc, target, pointer)
    change = ReplaceTextChange(target, pointer, text_digest(value), old, new)
    changes = [PatchChange("plan", {})] * index + [change]
    return apply_changes(doc, changes, defaults=DEFAULTS).document


def _read(doc, target, pointer):
    node = doc if target == "plan" else doc[target] if target == "brief" else None
    if node is None:
        node = next(
            e
            for a in (
                "items",
                "units",
                "phases",
                "checks",
                "decisions",
                "materials",
                "requirements",
                "criteria",
            )
            for e in doc[a]
            if e["key"] == target or f"{e.get('owner')}:{e['key']}" == target
        )
    for part in pointer[1:].split("/"):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def _failure(doc, target, pointer, old, new, *, digest=None, index=0) -> SkmError:
    value = _read(doc, target, pointer) if digest is None else ""
    change = ReplaceTextChange(target, pointer, digest or text_digest(value), old, new)
    with pytest.raises(SkmError) as raised:
        apply_changes(doc, [PatchChange("plan", {})] * index + [change], defaults=DEFAULTS)
    return raised.value


def test_digest_is_sha256_of_the_utf8_bytes_of_the_whole_value():
    assert text_digest("é👍") == "sha256:" + hashlib.sha256("é👍".encode()).hexdigest()
    assert text_digest("") == "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_exact_edit_of_an_item_field_by_key_and_by_entity_id():
    doc = _doc()
    summary = doc["items"][0]["summary"]
    out = _edit(doc, "P1.1", "/summary", "repository over it", "storage layer")
    assert out["items"][0]["summary"] == summary.replace("repository over it", "storage layer")
    by_id = _edit(
        doc,
        f"entity:{doc['items'][0]['id']}",
        "/summary",
        "repository over it",
        "storage layer",
        current=summary,
    )
    assert by_id == out
    assert doc["items"][0]["summary"] == summary  # the input is never mutated


def test_replace_inside_nested_arrays_and_brief_forms():
    doc = _doc()
    out = _edit(doc, "plan", "/rules/1", "reversible", "tested")
    assert out["rules"][1] == "Every database change ships with a tested migration."
    out = _edit(doc, "plan", "/brief/messages/0/text", "must not", "may not")
    assert "may not be reusable" in out["brief"]["messages"][0]["text"]
    assert _edit(doc, "brief", "/messages/0/text", "must not", "may not") == out
    out = _edit(doc, "P1.1", "/reads/0/why", "Agreed", "Signed-off")
    assert out["items"][0]["reads"][0]["why"] == "Signed-off table layout."
    out = _edit(doc, "P1.1:V1", "/definition/expect", "exit 0", "exit 1")
    assert out["checks"][0]["definition"]["expect"] == "exit 1"


@pytest.mark.parametrize(
    ("text", "old", "occurrences"), [("abc", "x", 0), ("a b a", "a", 2), ("aaa", "aa", 2), ("aaaa", "aa", 3)]
)
def test_zero_multiple_and_overlapping_matches_are_a_match_count_conflict(text, old, occurrences):
    doc = _doc()
    doc["items"][0]["summary"] = text
    error = _failure(doc, "P1.1", "/summary", old, "z")
    assert isinstance(error, Conflict)
    assert error.code is ErrorCode.VERSION_CONFLICT
    assert dict(error.details) == {
        "target": "P1.1",
        "pointer": "/summary",
        "change_index": 0,
        "applied": False,
        "reason": "text_match_count",
        "occurrences": occurrences,
    }


def test_stale_digest_is_a_text_changed_conflict_before_matching():
    doc = _doc()
    error = _failure(doc, "P1.1", "/summary", "repository", "x", digest=text_digest("another text"), index=2)
    assert error.code is ErrorCode.VERSION_CONFLICT
    assert (error.details["reason"], error.details["change_index"], error.details["applied"]) == (
        "text_changed",
        2,
        False,
    )


def test_the_digest_covers_the_whole_field_not_only_the_replaced_part():
    doc = _doc()
    value = doc["items"][0]["summary"]
    error = _failure(doc, "P1.1", "/summary", "repository", "x", digest=text_digest("repository"))
    assert error.details["reason"] == "text_changed"
    assert value != "repository"


def test_unicode_is_neither_normalised_nor_matched_fuzzily():
    decomposed = "café \U0001f44d"
    precomposed = unicodedata.normalize("NFC", decomposed)
    assert decomposed != precomposed
    doc = _doc()
    doc["items"][0]["summary"] = decomposed
    assert _failure(doc, "P1.1", "/summary", precomposed.split(" ")[0], "x").details["occurrences"] == 0
    out = _edit(doc, "P1.1", "/summary", "é", "E")
    assert out["items"][0]["summary"] == "cafE \U0001f44d"
    out = _edit(doc, "P1.1", "/summary", "\U0001f44d", "\U0001f44e\U0001f3fd")
    assert out["items"][0]["summary"] == "café \U0001f44e\U0001f3fd"
    assert text_digest(decomposed) != text_digest(
        precomposed
    )  # normalised text has another digest: a stale read


def test_line_endings_are_kept_byte_for_byte():
    doc = _doc()
    doc["items"][0]["summary"] = "first\r\nsecond\nthird"
    assert _failure(doc, "P1.1", "/summary", "first\nsecond", "x").details["occurrences"] == 0
    out = _edit(doc, "P1.1", "/summary", "first\r\nsecond", "1\r\n2")
    assert out["items"][0]["summary"] == "1\r\n2\nthird"
    out = _edit(doc, "P1.1", "/summary", "\r\n", "\n")
    assert out["items"][0]["summary"] == "first\nsecond\nthird"


def test_empty_new_text_is_valid_and_keeps_the_member_empty_not_unset(registry):
    doc = _doc()
    doc["items"][0]["sections"] = [{"id": "notes", "title": "Notes", "text": "scratch"}]
    out = _edit(doc, "P1.1", "/sections/0/text", "scratch", "")
    assert out["items"][0]["sections"][0]["text"] == ""  # explicit empty, not a deleted member
    registry.require_valid(SPECIFICATION, out)


def test_emptying_a_required_text_is_reported_by_the_final_schema_without_an_invented_index(registry):
    doc = _doc()
    doc["items"][0]["summary"] = "x"
    with pytest.raises(ValidationFailed) as raised:
        apply_changes(
            doc,
            [ReplaceTextChange("P1.1", "/summary", text_digest("x"), "x", "")],
            defaults=DEFAULTS,
            validate=lambda d: registry.require_valid(SPECIFICATION, d),
        )
    assert raised.value.code is ErrorCode.SCHEMA_INVALID
    assert "change_index" not in raised.value.details
    assert raised.value.details["applied"] is False


def test_unset_is_not_expressible_and_a_missing_field_is_not_a_string():
    doc = _doc()
    for target, pointer in (
        ("P1.1", "/guidance_md"),
        ("P1.1", "/research/question"),
        ("P1.1", "/deliverables/9"),
    ):
        change = ReplaceTextChange(target, pointer, text_digest(""), "x", "y")
        with pytest.raises(ValidationFailed) as raised:
            apply_changes(doc, [change], defaults=DEFAULTS)
        assert raised.value.code is ErrorCode.INVALID_REFERENCE
        assert raised.value.details["reason"] == "not_a_string"


def test_non_string_values_at_allowed_pointers_are_rejected():
    doc = _doc()
    doc["items"][0]["deliverables"] = [5]
    change = ReplaceTextChange("P1.1", "/deliverables/0", text_digest("5"), "5", "6")
    with pytest.raises(ValidationFailed) as raised:
        apply_changes(doc, [change], defaults=DEFAULTS)
    assert raised.value.details["reason"] == "not_a_string"


@pytest.mark.parametrize(
    ("target", "pointer", "field"),
    [
        ("P1.1", "/id", "id"),
        ("P1.1", "/key", "key"),
        ("P1.1", "/phase", "phase"),
        ("P1.1:V1", "/owner", "owner"),
        ("P1.1:V1", "/key", "key"),
        ("P1.1/U1", "/id", "id"),
        ("plan", "/schema", "schema"),
        ("plan", "/items/0/title", "items"),
        ("plan", "/phases/0/goal", "phases"),
        ("R1", "/key", "key"),
    ],
)
def test_owned_fields_stay_owned(target, pointer, field):
    doc = _doc()
    change = ReplaceTextChange(target, pointer, text_digest("irrelevant"), "x", "y")
    with pytest.raises(ValidationFailed) as raised:
        apply_changes(doc, [change], defaults=DEFAULTS)
    assert raised.value.code is ErrorCode.FIELD_OWNED
    assert raised.value.details["field"] == field
    assert raised.value.details["applied"] is False


@pytest.mark.parametrize(
    ("target", "pointer"),
    [
        ("P1.1", "/work_kind"),
        ("P1.1", "/route/class"),
        ("P1.1", "/reads/0/ref"),
        ("P1.1", "/reads/0/path"),
        ("P1.1", "/change_hints/0/pattern"),
        ("P1.1", "/depends_on/0"),
        ("P1.2", "/depends_on/0"),
        ("P1.1/U1", "/write_scope/0/pattern"),
        ("P1.1:V2", "/definition/script"),
        ("P1.1:V2", "/definition/risk_ack"),
        ("P1.1:V1", "/definition/argv/0"),
        ("D1", "/state"),
        ("D1", "/applies_to/0"),
        ("material/storage-design", "/kind"),
        ("plan", "/plan_relations/0/target"),
        ("plan", "/extensions"),
        ("execution_constraints", "/required_isolation"),
    ],
)
def test_references_enums_paths_scripts_and_security_fields_are_structural_edits(target, pointer):
    doc = _doc()
    change = ReplaceTextChange(target, pointer, text_digest("x"), "x", "y")
    with pytest.raises(ValidationFailed) as raised:
        apply_changes(doc, [change], defaults=DEFAULTS)
    assert raised.value.code is ErrorCode.INVALID_REFERENCE
    assert raised.value.details["reason"] == "not_text_field"


def test_bad_pointer_syntax_and_unknown_target():
    doc = _doc()
    for pointer in ("summary", "/"):
        with pytest.raises(ValidationFailed) as raised:
            apply_changes(
                doc, [ReplaceTextChange("P1.1", pointer, text_digest("x"), "x", "y")], defaults=DEFAULTS
            )
        assert raised.value.details["reason"] == "bad_pointer"
    with pytest.raises(NotFound) as missing:
        apply_changes(
            doc, [ReplaceTextChange("P9.9", "/title", text_digest("x"), "x", "y")], defaults=DEFAULTS
        )
    assert missing.value.details["change_index"] == 0
    assert missing.value.details["applied"] is False


def test_empty_old_text_is_refused():
    doc = _doc()
    error = _failure(doc, "P1.1", "/summary", "", "x")
    assert error.code is ErrorCode.SCHEMA_INVALID
    assert error.details["reason"] == "old_text_empty"


def test_failing_edit_discards_the_successful_prefix():
    doc = _doc()
    before = copy.deepcopy(doc)
    good = ReplaceTextChange(
        "P1.1", "/summary", text_digest(doc["items"][0]["summary"]), "repository", "store"
    )
    bad = ReplaceTextChange("P1.2", "/summary", text_digest("stale"), "x", "y")
    with pytest.raises(Conflict) as raised:
        apply_changes(doc, [good, bad], defaults=DEFAULTS)
    assert raised.value.details["change_index"] == 1
    assert doc == before


def test_edit_after_a_rekey_in_the_same_batch_addresses_the_same_entity_by_id():
    from skm.modules.planning.domain.changes import RekeyChange

    doc = _doc()
    uid = f"entity:{doc['items'][0]['id']}"
    digest = text_digest(doc["items"][0]["summary"])
    out: dict[str, Any] = apply_changes(
        doc,
        [RekeyChange("P1.1", "P1.9"), ReplaceTextChange(uid, "/summary", digest, "repository", "store")],
        defaults=DEFAULTS,
    ).document
    assert next(i for i in out["items"] if i["key"] == "P1.9")["summary"].count("store") == 1


def test_allowlist_is_the_planning_table_per_owner():
    sections = {"sections[].title", "sections[].text"}
    brief = {"messages[].text", "{constraints,environment,out_of_scope}[]"}
    assert set(TEXT_EDIT_FIELDS["plan"]) == {
        "title",
        "goal",
        "context_md",
        "non_goals[]",
        "rules[]",
        "brief.messages[].text",
        "brief.{constraints,environment,out_of_scope}[]",
        "plan_relations[].note",
        *sections,
    }
    assert set(TEXT_EDIT_FIELDS["brief"]) == brief
    assert set(TEXT_EDIT_FIELDS["phase"]) == {
        "title",
        "goal",
        "context_md",
        "contract.{consumes,produces,boundaries}[]",
        "pitfalls[]",
        "deliverables[]",
        "assurance.{impact,note}",
        "assurance.seams[]",
        "batches[].note",
        "supporting[].why",
        *sections,
    }
    assert set(TEXT_EDIT_FIELDS["item"]) == {
        "title",
        "summary",
        "why",
        "rules[]",
        "guidance_md",
        "deliverables[]",
        "relations[].note",
        "reads[].why",
        "examples[].why",
        "change_hints[].note",
        "artifacts[].note",
        "research.{question,notes}",
        "review.reason",
        "review.reviewer.note",
        *sections,
    }
    assert set(TEXT_EDIT_FIELDS["unit"]) == {
        "title",
        "goal",
        "instructions_md",
        "reads[].why",
        "outputs[].note",
        "command.definition.expect",
        *sections,
    }
    assert set(TEXT_EDIT_FIELDS["requirement"]) == set(TEXT_EDIT_FIELDS["criterion"]) == {"statement"}
    assert set(TEXT_EDIT_FIELDS["check"]) == {"definition.instructions_md", "definition.expect"}
    assert set(TEXT_EDIT_FIELDS["decision"]) == {
        "title",
        "question",
        "context_md",
        "decision",
        "rationale",
        "options[].text",
        "consequences[]",
        "evidence[].note",
        *sections,
    }
    assert set(TEXT_EDIT_FIELDS["material"]) == {"title", "why"}
    assert is_text_field("phase", "/contract/produces/3")
    assert not is_text_field("phase", "/contract/other/3")
    assert is_text_field("item", "/review/reviewer/note")
    assert not is_text_field("item", "/review/reviewer/model")
    assert is_text_field("decision", "/options/1/text")
    assert not is_text_field("decision", "/options/1/key")
    assert not is_text_field("item", "/summary/0")
    assert not is_text_field("item", "/summary ")
