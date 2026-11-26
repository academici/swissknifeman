"""The installed distribution and CLI share one package version."""

import subprocess
import sysconfig
import tomllib
from importlib.metadata import version
from io import StringIO
from pathlib import Path

import pytest

import skm
from skm.entrypoints.cli.main import main


def cli_path() -> str:
    executable = Path(sysconfig.get_path("scripts")) / "skm"
    assert executable.is_file(), "the installed skm console script must be available"
    return str(executable)


def test_cli_path_ignores_other_installations(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    other_cli = tmp_path / "skm"
    other_cli.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    other_cli.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))

    assert Path(cli_path()) == Path(sysconfig.get_path("scripts")) / "skm"
    assert Path(cli_path()) != other_cli


def test_package_version() -> None:
    root = Path(__file__).resolve().parents[2]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    expected = project["project"]["version"]
    result = subprocess.run([cli_path(), "--version"], capture_output=True, text=True, check=True)

    assert skm.__version__ == version("skm") == expected
    assert result.stdout == f"{expected}\n"
    assert result.stderr == ""


def run_main(*argv: str) -> tuple[int, str, str]:
    # Usage errors come from the parser alone; the console script itself is covered above.
    out, err = StringIO(), StringIO()
    code = main(list(argv), environ={}, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


@pytest.mark.parametrize("argument", ["unknown-command", "--unknown", "--ver"])
def test_cli_rejects_unsupported_arguments(argument: str) -> None:
    code, out, err = run_main(argument)

    assert code == 2
    assert out == ""
    assert "unrecognized arguments" in err


def test_cli_plan_group_requires_a_verb() -> None:
    code, out, err = run_main("plan")

    assert code == 2
    assert out == ""
    assert "the following arguments are required: plan_verb" in err
