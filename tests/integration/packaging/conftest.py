"""Build from this checkout and install only the release wheel and its locked dependencies."""

import fcntl
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _executable(name: str) -> str:
    path = shutil.which(name)
    assert path is not None, f"packaging tests require {name}"
    return path


UV = _executable("uv")


@pytest.fixture(scope="session")
def build_env(pytestconfig: pytest.Config) -> dict[str, str]:
    controls = pytestconfig.pluginmanager.get_plugin(str(ROOT / "tests/conftest.py"))
    assert controls is not None
    host = pytestconfig.stash[controls.CONTROLS].host_home
    env = os.environ.copy()
    # Without --color never, FORCE_COLOR (set in CI) wraps the path in ANSI codes and uv then builds offline
    # against a relative, empty cache.
    cache = subprocess.check_output(
        [UV, "--color", "never", "cache", "dir"], env={**env, "HOME": host}, text=True
    ).strip()
    # The build runs offline, so it can only use what this cache already holds.
    assert Path(cache).is_dir(), f"offline packaging builds need the uv cache, but {cache!r} does not exist"
    env.update(UV_CACHE_DIR=cache, UV_OFFLINE="1", UV_PYTHON_DOWNLOADS="never")
    env.pop("PYTHONPATH", None)
    env.pop("VIRTUAL_ENV", None)
    return env


@pytest.fixture(scope="session")
def distributions(tmp_path_factory: pytest.TempPathFactory, build_env: dict[str, str]) -> Path:
    # A fresh checkout has no dist. Serialize npm ci and Vite across xdist workers.
    with (tmp_path_factory.getbasetemp().parent / "skm-web-build.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not (ROOT / "web/dist/index.html").is_file():
            subprocess.run([_executable("make"), "web-build"], cwd=ROOT, check=True)
    output = tmp_path_factory.mktemp("release")
    subprocess.run([UV, "build", "--out-dir", output], cwd=ROOT, env=build_env, check=True)
    return output


@pytest.fixture(scope="session")
def installed_bin(
    distributions: Path, build_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory
) -> Path:
    cwd = tmp_path_factory.mktemp("install")
    venv = tmp_path_factory.mktemp("release-venv")
    python = venv / "bin/python"
    env = {**build_env, "UV_PROJECT_ENVIRONMENT": str(venv)}
    (wheel,) = distributions.glob("*.whl")
    # Resolve dependencies from the frozen lock's cached URLs, including platform-specific wheels.
    for args in (
        ["venv", "--python", sys.executable, venv],
        [
            "sync",
            "--project",
            ROOT,
            "--python",
            sys.executable,
            "--frozen",
            "--offline",
            "--no-dev",
            "--no-install-project",
        ],
        ["pip", "install", "--offline", "--python", python, wheel],
    ):
        subprocess.run([UV, *args], cwd=cwd, env=env, check=True)
    return python.parent
