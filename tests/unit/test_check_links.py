"""Local Markdown links fail on missing files and heading anchors, without network IO."""

import importlib
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

import pytest

# Tools have a separate type-checking environment from tests.
_checker = importlib.import_module("tools.check_links")
check_file = cast(Callable[[Path], list[str]], _checker.check_file)
main = cast(Callable[[Sequence[str]], int], _checker.main)


def test_relative_files_and_unicode_heading_anchors(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    target = docs / "Target page.md"
    target.write_text("# Hello, `World`!\n## Привет мир\n## A_B - C\n", encoding="utf-8")
    source = tmp_path / "README.md"
    source.write_text(
        "[file](docs/Target%20page.md)\n"
        "[heading](docs/Target%20page.md#hello-world)\n"
        "[unicode](<docs/Target page.md#%D0%BF%D1%80%D0%B8%D0%B2%D0%B5%D1%82-%D0%BC%D0%B8%D1%80>)\n"
        "[punctuation](<docs/Target page.md#a_b---c>)\n",
        encoding="utf-8",
    )
    assert check_file(source) == []


@pytest.mark.parametrize("target", ["missing.md", "target.md#missing", "#missing"])
def test_broken_link_has_source_line_and_target(tmp_path: Path, target: str) -> None:
    (tmp_path / "target.md").write_text("# Existing\n", encoding="utf-8")
    source = tmp_path / "source.md"
    source.write_text(f"# Existing\n\n[broken]({target})\n", encoding="utf-8")
    assert check_file(source) == [f"{source}:3: broken link {target}"]


def test_same_file_duplicate_and_setext_headings(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text(
        "# Repeated\n# Repeated\nTitle\n=====\n[first](#repeated) [second](#repeated-1) [setext](#title)\n",
        encoding="utf-8",
    )
    assert check_file(source) == []


def test_external_schemes_and_code_examples_are_not_local_links(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text(
        "[web](https://example.invalid/missing#absent) [mail](mailto:missing@example.invalid)\n"
        "[ssh](ssh://example.invalid/path) [web](//example.invalid/path)\n"
        "`[inline](missing.md)`\n~~~markdown\n[example](missing.md)\n~~~\n"
        "````markdown\n```\n[example](missing.md)\n````\n",
        encoding="utf-8",
    )
    assert check_file(source) == []


def test_heading_inside_code_is_not_an_anchor(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text("```md\n# Fake\n```\n[broken](#fake)\n", encoding="utf-8")
    assert check_file(source) == [f"{source}:4: broken link #fake"]


def test_parentheses_and_optional_titles(tmp_path: Path) -> None:
    (tmp_path / "target(1).md").write_text("# Target\n", encoding="utf-8")
    source = tmp_path / "source.md"
    source.write_text('[valid](target(1).md#target "A title")\n', encoding="utf-8")
    assert check_file(source) == []


def test_cli_recurses_and_reports_all_failures(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    source = nested / "source.md"
    source.write_text("[bad](missing.md)\n[bad](#absent)\n", encoding="utf-8")
    (nested / "ignored.txt").write_text("[bad](missing.md)\n", encoding="utf-8")
    assert main([str(tmp_path)]) == 1
    assert capsys.readouterr().err.splitlines() == [
        f"{source}:1: broken link missing.md",
        f"{source}:2: broken link #absent",
    ]
    source.write_text("# Existing\n[valid](#existing)\n", encoding="utf-8")
    assert main([str(source), str(tmp_path)]) == 0
    assert capsys.readouterr().err == ""


def test_missing_input_is_not_silent_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = tmp_path / "missing"
    assert main([str(missing)]) == 1
    assert f"{missing}:1: broken link {missing}" in capsys.readouterr().err


@pytest.mark.parametrize(("target", "exit_code"), [("#existing", 0), ("missing.md", 1)])
def test_script_exit_status(tmp_path: Path, target: str, exit_code: int) -> None:
    source = tmp_path / "source.md"
    source.write_text(f"# Existing\n[link]({target})\n", encoding="utf-8")
    script = Path(__file__).resolve().parents[2] / "tools" / "check_links.py"
    result = subprocess.run(
        [sys.executable, str(script), str(source)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == exit_code
    assert result.stdout == ""
    assert result.stderr == (f"{source}:2: broken link {target}\n" if exit_code else "")


def test_nested_brackets_in_link_label_still_check_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text("[Use list[str]](missing.md)\n", encoding="utf-8")
    assert check_file(source) == [f"{source}:1: broken link missing.md"]
