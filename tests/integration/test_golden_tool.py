"""Golden inventory detects orphans and untraceable legacy expectations."""

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration
type GoldenCheck = Callable[[], subprocess.CompletedProcess[str]]
type GoldenCli = Callable[[list[str]], subprocess.CompletedProcess[str]]


def test_orphan_golden_fails_with_its_path(tmp_path: Path, golden_check: GoldenCheck) -> None:
    suite = tmp_path / "tests" / "golden" / "example"
    suite.mkdir(parents=True)
    (suite / "case.json").write_text("{}\n", encoding="utf-8")
    result = golden_check()
    assert result.returncode == 1
    assert "orphan golden: tests/golden/example/case.json" in result.stderr


def test_literal_reference_handles_multiple_lines_and_nested_suites(
    tmp_path: Path, golden_check: GoldenCheck
) -> None:
    suite = tmp_path / "tests" / "golden" / "example" / "nested"
    suite.mkdir(parents=True)
    (suite / "case.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "tests" / "test_example.py").write_text(
        "def test_case():\n    assert_golden(\n        'example/nested',\n"
        "        'case',\n        {},\n    )\n",
        encoding="utf-8",
    )
    assert golden_check().returncode == 0


def test_legacy_fixture_requires_source_commit_pair(tmp_path: Path, golden_check: GoldenCheck) -> None:
    legacy = tmp_path / "tests" / "fixtures" / "legacy"
    legacy.mkdir(parents=True)
    (legacy / "case.json").write_text("{}\n", encoding="utf-8")
    result = golden_check()
    assert result.returncode == 1
    assert "legacy fixture needs provenance" in result.stderr
    provenance = legacy / "case.source.txt"
    provenance.write_text("source: donor/case.json\n", encoding="utf-8")
    result = golden_check()
    assert result.returncode == 1
    assert "needs source path and commit" in result.stderr
    provenance.write_text("source: donor/case.json\ncommit: 0d6a393\n", encoding="utf-8")
    assert golden_check().returncode == 0


def test_golden_sidecar_is_not_an_orphan(tmp_path: Path, golden_check: GoldenCheck) -> None:
    suite = tmp_path / "tests" / "golden" / "example"
    suite.mkdir(parents=True)
    (suite / "case.txt").write_text("legacy text", encoding="utf-8")
    (suite / "case.source.txt").write_text("source: donor/case.txt\ncommit: 0d6a393\n", encoding="utf-8")
    (tmp_path / "tests" / "test_example.py").write_text(
        'def test_example():\n    assert_golden("example", "case", "legacy text")\n', encoding="utf-8"
    )
    assert golden_check().returncode == 0


def test_update_command_reports_xfail_and_preserves_provenance(
    tmp_path: Path, golden_cli: GoldenCli, temporary_git: None
) -> None:
    tests = tmp_path / "tests"
    suite = tests / "golden" / "example"
    suite.mkdir(parents=True)
    fixture = suite / "case.txt"
    fixture.write_text("old\n", encoding="utf-8")
    provenance = suite / "case.source.txt"
    metadata = "source: donor/case.txt\ncommit: 0d6a393\n"
    provenance.write_text(metadata, encoding="utf-8")
    (tests / "test_update.py").write_text(
        "from pathlib import Path\nfrom support import golden\n"
        'golden.GOLDEN_ROOT = Path(__file__).parent / "golden"\n'
        'def test_changed():\n    golden.assert_golden("example", "case", "changed\\n")\n',
        encoding="utf-8",
    )
    result = golden_cli(["update", "test_changed"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "GOLDEN UPDATE" in result.stdout
    assert "1 xfailed" in result.stdout
    assert "1 passed" not in result.stdout
    assert fixture.read_text(encoding="utf-8") == "changed\n"
    assert provenance.read_text(encoding="utf-8") == metadata


def test_update_command_keeps_no_tests_exit_code(
    tmp_path: Path, golden_cli: GoldenCli, temporary_git: None
) -> None:
    (tmp_path / "tests").mkdir()
    result = golden_cli(["update", "no_such_test"])
    assert result.returncode == 5, result.stdout + result.stderr


def test_update_requires_an_explicit_pattern(golden_cli: GoldenCli) -> None:
    result = golden_cli(["update"])
    assert result.returncode == 2
    assert "pattern" in result.stderr
