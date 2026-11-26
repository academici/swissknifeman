"""Golden mismatches and legacy metadata are failures, updates are visible XFAILs."""

from pathlib import Path

import pytest

from support import golden


@pytest.fixture
def golden_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(golden, "GOLDEN_ROOT", tmp_path)
    monkeypatch.setattr(golden, "UPDATE", False)
    return tmp_path


def test_json_is_stable_and_mismatch_shows_diff(golden_root: Path) -> None:
    suite = golden_root / "example"
    suite.mkdir()
    expected = suite / "case.json"
    expected.write_text('{\n  "a": 1,\n  "b": 2\n}\n', encoding="utf-8")
    golden.assert_golden("example", "case", {"b": 2, "a": 1})
    with pytest.raises(AssertionError, match="golden mismatch") as error:
        golden.assert_golden("example", "case", {"a": 3, "b": 2})
    assert "--- " in str(error.value)
    assert "+++ actual" in str(error.value)
    assert '-  "a": 1' in str(error.value)
    assert '+  "a": 3' in str(error.value)
    assert expected.read_text(encoding="utf-8") == '{\n  "a": 1,\n  "b": 2\n}\n'


def test_text_is_compared_without_normalizing(golden_root: Path) -> None:
    (golden_root / "example").mkdir()
    (golden_root / "example" / "case.txt").write_text("one\n", encoding="utf-8")
    golden.assert_golden("example", "case", "one\n")
    with pytest.raises(AssertionError, match="golden mismatch"):
        golden.assert_golden("example", "case", "one")


def test_missing_golden_needs_explicit_update(golden_root: Path) -> None:
    with pytest.raises(AssertionError, match="explicitly run"):
        golden.assert_golden("missing", "case", {})
    assert not list(golden_root.iterdir())


def test_text_preserves_line_endings(golden_root: Path) -> None:
    (golden_root / "example").mkdir()
    (golden_root / "example" / "case.txt").write_bytes(b"one\r\n")
    golden.assert_golden("example", "case", "one\r\n")
    with pytest.raises(AssertionError, match="golden mismatch"):
        golden.assert_golden("example", "case", "one\n")


def test_update_writes_canonical_json_and_does_not_pass(
    golden_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(golden, "UPDATE", True)
    with pytest.raises(pytest.xfail.Exception, match="golden updated"):
        golden.assert_golden("example", "case", {"b": 2, "a": "текст"})
    assert (golden_root / "example" / "case.json").read_text(encoding="utf-8") == (
        '{\n  "a": "текст",\n  "b": 2\n}\n'
    )


@pytest.mark.parametrize(
    ("suite", "case"), [("../outside", "case"), ("example", "../case"), ("/outside", "case")]
)
def test_rejects_golden_path_escape(golden_root: Path, suite: str, case: str) -> None:
    with pytest.raises(ValueError, match="relative paths"):
        golden.assert_golden(suite, case, "data")


def test_rejects_symlink_escape(golden_root: Path, tmp_path: Path) -> None:
    (golden_root / "link").symlink_to(tmp_path.parent)
    with pytest.raises(ValueError, match="escapes"):
        golden.assert_golden("link", "case", "data")


def test_legacy_provenance_requires_source_and_revision(tmp_path: Path) -> None:
    fixture = tmp_path / "legacy.json"
    with pytest.raises(AssertionError, match="needs provenance"):
        golden.assert_legacy_source(fixture)
    source = tmp_path / "legacy.source.txt"
    source.write_text("source: packages/owner/fixture.json\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="source path and commit"):
        golden.assert_legacy_source(fixture)
    source.write_text("source: packages/owner/fixture.json\ncommit: 0d6a393\n", encoding="utf-8")
    assert "0d6a393" in golden.assert_legacy_source(fixture)


@pytest.mark.parametrize(
    "metadata",
    ["source: \ncommit: 0d6a393\n", "source: donor/case.json\ncommit: not-a-revision\n"],
)
def test_invalid_legacy_provenance_is_rejected(tmp_path: Path, metadata: str) -> None:
    (tmp_path / "legacy.source.txt").write_text(metadata, encoding="utf-8")
    with pytest.raises(AssertionError, match="source path and commit"):
        golden.assert_legacy_source(tmp_path / "legacy.json")
