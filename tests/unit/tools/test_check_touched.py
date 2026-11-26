"""Diff preflight must retain all change sources and propagate unavailable/failed checks."""

import importlib
import shutil
import subprocess
from pathlib import Path

import pytest

check_touched = importlib.import_module("tools.check_touched")


def _git(root: Path, *args: str) -> None:
    executable = shutil.which("git")
    assert executable is not None
    subprocess.run([executable, *args], cwd=root, check=True, capture_output=True, timeout=10)


def test_git_diff_retains_commits_index_worktree_deletions_and_untracked_names(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")
    for name in ("staged.py", "unstaged.py", "removed.py", "renamed.py"):
        (tmp_path / name).write_text("before\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "base")
    _git(tmp_path, "tag", "base")
    (tmp_path / "committed.py").write_text("branch\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "branch")
    (tmp_path / "staged.py").write_text("index\n")
    _git(tmp_path, "add", "staged.py")
    (tmp_path / "staged.py").write_text("before\n")
    (tmp_path / "unstaged.py").write_text("worktree\n")
    (tmp_path / "removed.py").unlink()
    _git(tmp_path, "mv", "renamed.py", "renamed after.py")
    (tmp_path / "untracked with spaces\nand\rcarriage return.py").write_text("untracked\n")
    assert set(check_touched.changed_paths(tmp_path, "base")) == {
        "committed.py",
        "staged.py",
        "unstaged.py",
        "removed.py",
        "renamed.py",
        "renamed after.py",
        "untracked with spaces\nand\rcarriage return.py",
    }
    with pytest.raises(subprocess.CalledProcessError):
        check_touched.changed_paths(tmp_path, "missing-branch")


def _file(root: Path, relative: str) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# test input\n")
    return relative


def test_changed_tests_and_tools_get_their_own_typechecking_configuration(tmp_path: Path) -> None:
    tests = _file(tmp_path, "tests/unit/test_example.py")
    tool = _file(tmp_path, "tools/example.py")
    checks = check_touched.check_commands(tmp_path, (tests, tool))
    typed = [command[3:] for command in checks if command[3] == "pyright"]
    assert typed == [("pyright", tests), ("pyright", "--project", "tools/pyrightconfig.json", tool)]
    assert not any("pytest" in command for command in checks)


def test_deleted_product_file_still_checks_inventory_and_incoming_doc_links(tmp_path: Path) -> None:
    checks = check_touched.check_commands(tmp_path, ("src/skm/kernel/removed.py",))
    assert any("tests/architecture" in command for command in checks)
    assert any("tools/check_links.py" in command and "docs" in command for command in checks)
    assert not any("pyright" in command for command in checks)


@pytest.mark.parametrize(
    "path",
    ["src/skm/modules/demo/generated/views.py", "tests/architecture/fixtures/bad_tree/bad.py"],
)
def test_generated_and_intentionally_invalid_fixtures_use_owning_checks(tmp_path: Path, path: str) -> None:
    _file(tmp_path, path)
    checks = check_touched.check_commands(tmp_path, (path,))
    assert not any("ruff" in command or "pyright" in command for command in checks)
    assert any("tests/architecture" in command for command in checks)
    if "generated" in path:
        assert any("tools/schema_check.py" in command for command in checks)


def test_checker_configuration_changes_widen_to_full_static_checks(tmp_path: Path) -> None:
    checks = check_touched.check_commands(tmp_path, ("pyrightconfig.json",))
    assert any(command[3:] == ("pyright",) for command in checks)
    assert any(command[3:] == ("pyright", "--project", "tools/pyrightconfig.json") for command in checks)
    assert any(command[3:] == ("ruff", "check", "src", "tests", "tools") for command in checks)
    assert any("tests/architecture" in command for command in checks)


def test_markdown_only_changes_do_not_start_python_or_architecture_checks(tmp_path: Path) -> None:
    doc = _file(tmp_path, "tests/support/README.md")
    checks = check_touched.check_commands(tmp_path, (doc,))
    assert len(checks) == 1
    assert "tools/check_links.py" in checks[0]
    assert doc in checks[0]


def test_dry_run_reports_no_checks_and_never_spawns_a_checker(monkeypatch, capsys) -> None:
    monkeypatch.setattr(check_touched, "changed_paths", lambda root, base: ("README.md",))

    def forbidden(*args, **kwargs):
        pytest.fail("dry-run started a check")

    monkeypatch.setattr(check_touched.subprocess, "run", forbidden)
    assert check_touched.main(["--dry-run"]) == 0
    assert "Dry run only; no checks ran." in capsys.readouterr().out


@pytest.mark.parametrize("code", [1, 3, 5])
def test_failed_unavailable_or_empty_checks_never_report_success(monkeypatch, capsys, code) -> None:
    monkeypatch.setattr(check_touched, "changed_paths", lambda root, base: ("README.md",))
    monkeypatch.setattr(
        check_touched.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], code)
    )
    assert check_touched.main([]) == 1
    assert "Selected preflight checks passed" not in capsys.readouterr().out


def test_python_changes_keep_the_generated_source_index_in_sync(tmp_path: Path) -> None:
    product = _file(tmp_path, "src/skm/kernel/example.py")
    checks = check_touched.check_commands(tmp_path, (product,))
    assert any(command[3:] == ("python", "tools/source_index.py", "--check") for command in checks)
    doc = _file(tmp_path, "tests/support/README.md")
    assert not any(
        "tools/source_index.py" in command for command in check_touched.check_commands(tmp_path, (doc,))
    )


def test_affected_tests_hint_lists_only_existing_product_files(tmp_path: Path) -> None:
    product = _file(tmp_path, "src/skm/kernel/example.py")
    paths = (product, "src/skm/kernel/removed.py", "tests/unit/test_example.py")
    hint = check_touched.affected_tests_command(tmp_path, paths)
    assert hint is not None
    assert hint[3:] == ("python", "tools/source_index.py", "--tests", product)
    assert check_touched.affected_tests_command(tmp_path, ("README.md",)) is None
