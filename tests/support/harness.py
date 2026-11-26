"""Subprocess diagnostics for the pytest policy, isolated from host controls."""

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def runner(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> Callable[..., pytest.RunResult]:
    original = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    # The nested runner only needs the actual policy, not its diagnostics plugin.
    original = original.replace('pytest_plugins = ["pytester", "support.harness"]', "")
    pytester.makeconftest(
        original
        + """
@pytest.fixture
def visible_env():
    return dict(os.environ)
"""
    )
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join((str(ROOT / "tests"), str(ROOT))))
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")

    def run(
        source: str, *, controls: dict[str, str] | None = None, args: tuple[str, ...] = ()
    ) -> pytest.RunResult:
        for name in tuple(os.environ):
            if name.startswith("SKM_") or name == "HYPOTHESIS_PROFILE":
                monkeypatch.delenv(name)
        for name, value in (controls or {}).items():
            monkeypatch.setenv(name, value)
        pytester.makepyfile(test_policy=source)
        pytester.makeini("""
[pytest]
addopts = --strict-markers --strict-config
filterwarnings = error
xfail_strict = true
markers =
    pg: PostgreSQL
    e2e: processes
    evals: paid runtime
    integration: isolated HOME
    slow: slow test
""")
        return pytester.runpytest_subprocess("-q", *args, timeout=30)

    return run


@pytest.fixture
def golden_cli(tmp_path: Path) -> Callable[[list[str]], subprocess.CompletedProcess[str]]:
    tool = tmp_path / "tools" / "golden.py"
    tool.parent.mkdir()
    shutil.copyfile(ROOT / "tools" / "golden.py", tool)
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join((str(ROOT / "tests"), str(ROOT))),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }

    def run(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(tool), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
            env=env,
        )

    return run


@pytest.fixture
def golden_check(
    golden_cli: Callable[[list[str]], subprocess.CompletedProcess[str]],
) -> Callable[[], subprocess.CompletedProcess[str]]:
    return lambda: golden_cli(["check"])


@pytest.fixture
def temporary_git(tmp_path: Path) -> None:
    git = shutil.which("git")
    assert git is not None, "golden update diagnostics require git"
    subprocess.run([git, "init", "--quiet", str(tmp_path)], capture_output=True, check=True, timeout=10)
