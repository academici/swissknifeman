"""Check the affected-tests CLI without running the selected suites."""

import importlib
import shlex
import sys

import pytest

affected_tests = importlib.import_module("tools.affected_tests")


@pytest.mark.parametrize(
    ("paths", "args"),
    [
        (("src/skm/modules/exports/module.py",), []),
        (("src/skm/modules/exports/application/registry.py",), []),
        ((), ["--module", "exports"]),
    ],
)
def test_registration_selection(paths, args, monkeypatch, capsys):
    monkeypatch.setattr(affected_tests, "changed_paths", lambda root, base: paths)

    assert affected_tests.main(["--dry-run", "--uv", sys.executable, *args]) == 0
    commands = [shlex.split(line) for line in capsys.readouterr().out.splitlines() if " pytest " in line]
    unit, architecture = commands
    assert "tests/unit/bootstrap/test_modules.py" in unit
    assert architecture[-3:] == ["--dist", "loadfile", "tests/architecture"]
