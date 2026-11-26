"""``skm version`` (cli §6.1): package, known schema and Python versions; no bus, no DB, no bootstrap."""

import json
import platform
import re
import subprocess
import sysconfig
from collections.abc import Generator
from io import StringIO
from pathlib import Path

import pytest

import skm
from skm.bootstrap.composition import KNOWN_SCHEMA_VERSION
from skm.entrypoints.cli.commands import GROUPS
from skm.entrypoints.cli.commands.version import GROUP
from skm.entrypoints.cli.main import Backend, main
from skm.entrypoints.cli.output import ENVELOPE_SCHEMA
from skm.platform.logging import setup

SUMMARY = re.compile(r"skm (?P<package>\S+) \(schema (?P<schema>\d{4}), python (?P<python>\d+\.\d+\.\d+)\)\n")


@pytest.fixture(autouse=True)
def isolated_logging() -> Generator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(setup._state, "settings", setup._state.settings)  # main() reconfigures logging
        yield


def never_a_backend(options: object, environ: object) -> Backend:
    raise AssertionError("skm version must not build a backend")


def run(*argv: str, environ: dict[str, str] | None = None) -> tuple[int, str, str]:
    out, err = StringIO(), StringIO()
    code = main(
        list(argv),
        environ=environ if environ is not None else {},
        stdout=out,
        stderr=err,
        backend=never_a_backend,
    )
    return code, out.getvalue(), err.getvalue()


def test_the_group_needs_no_backend_and_is_discovered() -> None:
    assert GROUP.name == "version"
    assert GROUP.requires_backend is False
    assert GROUP.module is None
    assert GROUP in GROUPS


def test_human_summary_follows_the_catalog_format() -> None:
    code, out, err = run("version")
    assert (code, err) == (0, "")
    match = SUMMARY.fullmatch(out)
    assert match is not None, out
    assert match["package"] == skm.__version__
    assert int(match["schema"]) == KNOWN_SCHEMA_VERSION
    assert match["python"] == platform.python_version()


@pytest.mark.parametrize("argv", [("--json", "version"), ("version", "--json")])
def test_json_output_is_the_envelope_with_the_three_versions(argv: tuple[str, ...]) -> None:
    code, out, err = run(*argv)
    assert (code, err) == (0, "")
    document = json.loads(out)
    assert document["schema"] == ENVELOPE_SCHEMA
    assert (document["ok"], document["command"], document["diagnostics"]) == (True, "version", [])
    assert document["request_id"].startswith("cli-")
    assert document["result"] == {
        "package_version": skm.__version__,
        "schema_version": KNOWN_SCHEMA_VERSION,
        "python_version": platform.python_version(),
    }


def test_version_works_before_init_without_a_dsn_or_bootstrap(tmp_path: Path) -> None:
    # an empty environment: no SKM_DATABASE_URL, no bootstrap file anywhere under HOME
    code, out, _ = run("version", environ={"HOME": str(tmp_path)})
    assert code == 0
    assert SUMMARY.fullmatch(out)


def test_quiet_prints_nothing_but_still_succeeds() -> None:
    assert run("--quiet", "version") == (0, "", "")


def test_the_global_version_flag_keeps_the_p00_01_contract(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"], environ={}, backend=never_a_backend) == 0
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == (f"{skm.__version__}\n", "")


def test_the_installed_console_script_runs_version_with_a_clean_environment(tmp_path: Path) -> None:
    executable = Path(sysconfig.get_path("scripts")) / "skm"
    result = subprocess.run(
        [str(executable), "version"],
        capture_output=True,
        text=True,
        check=False,
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stderr
    assert SUMMARY.fullmatch(result.stdout)
