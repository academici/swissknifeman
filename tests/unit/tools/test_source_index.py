"""The generated source index stays in sync with the tree and its helpers report real files and tests."""

import importlib
from pathlib import Path

import pytest

source_index = importlib.import_module("tools.source_index")


def test_committed_source_index_matches_the_tree() -> None:
    committed = (source_index.ROOT / source_index.OUTPUT).read_text(encoding="utf-8")
    assert committed == source_index.render(), "run: make source-index"


def test_units_split_containers_and_keep_every_python_file_once() -> None:
    units = source_index.units()
    paths = {unit.path.as_posix() for unit in units}
    expected = {"src/skm/kernel", "src/skm/modules/planning", "src/skm/adapters/postgres", "src/skm/platform"}
    assert expected <= paths
    assert "src/skm/modules" not in paths
    listed = [path for unit in units for path in unit.files]
    assert len(listed) == len(set(listed))
    assert all("generated" not in path.parts for path in listed)


@pytest.mark.parametrize(
    ("docstring", "expected"),
    [
        ("Short.", "Short."),
        ("First sentence. Second one.", "First sentence."),
        ("Wrapped\nfirst line.\n\nSecond paragraph.", "Wrapped first line."),
        ("Pipes | in tables.", "Pipes \\| in tables."),
        ("", ""),
    ],
)
def test_first_sentence_is_one_table_safe_line(docstring: str, expected: str) -> None:
    assert source_index.first_sentence(docstring) == expected


def test_long_summaries_are_truncated() -> None:
    summary = source_index.first_sentence("x" * 500)
    assert len(summary) == 200
    assert summary.endswith("…")


def test_importing_tests_are_collected_test_modules_only() -> None:
    kernel_tests = source_index.importing_tests("skm.kernel")
    assert kernel_tests
    assert all(path.name.startswith("test_") for path in kernel_tests)
    assert Path("tests/fakes/clock.py") not in kernel_tests


def test_cli_lists_file_summaries_and_rejects_paths_outside_the_package(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert source_index.main(["--files", str(source_index.ROOT / "src/skm/kernel/clock.py")]) == 0
    assert capsys.readouterr().out.startswith("src/skm/kernel/clock.py  [")
    with pytest.raises(SystemExit, match="not an existing path"):
        source_index.main(["--files", str(source_index.ROOT / "tests")])


def test_outline_lists_public_signatures_and_reexports_without_private_names() -> None:
    text = source_index.outline(Path("src/skm/modules/planning/public.py"))
    lines = text.splitlines()
    assert lines[0].startswith("src/skm/modules/planning/public.py: ")
    assert any(line.startswith("  def get_revision_specification(uow: UnitOfWork") for line in lines)
    assert not any(line.lstrip().startswith(("def _", "class _")) for line in lines)
    reexports = next(line for line in lines if line.startswith("  re-exported: "))
    assert "Specification" in reexports.split(": ", 1)[1].split(", ")
    assert len(lines) < 60


def test_outline_rejects_directories() -> None:
    with pytest.raises(SystemExit, match="one Python file"):
        source_index.main(["--outline", str(source_index.ROOT / "src/skm/kernel")])
