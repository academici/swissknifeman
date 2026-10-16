"""Test doubles and gates for maind's link to harness.

Importing ``tests`` installs a fake harness for the whole process (``install_default``): an
executable in a temporary directory, named by ``SKM_HARNESS_BIN``, that answers harness's public
JSON commands from ``tests/fixtures/harness/*.json``, captured once from the real commands
(``capture_harness_fixtures.py``). No test depends on a harness that happens to be on PATH.

``FakeHarnessCase`` gives each test a fresh fake with a call log; ``NoHarnessCase`` removes the
partner altogether; ``RealHarnessCase`` runs only when the real harness was named by
``SKM_HARNESS_ROOT`` or ``SKM_HARNESS_BIN`` before the process started (``scripts/test-integration.sh``
sets it) and is skipped otherwise, like every test that needs a partner."""
import contextlib
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

from maind import harness_link

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "harness"
_ENV = ("MAIND_HARNESS_BIN", "SKM_HARNESS_BIN", "SKM_HARNESS_ROOT", "FAKE_HARNESS_FIXTURES",
        "FAKE_HARNESS_LOG", "FAKE_HARNESS_VALIDATE", "PATH")
ORIGINAL = {name: os.environ.get(name) for name in _ENV}   # what the process started with
_SCRIPT = '''#!{python}
import json, os, sys
from pathlib import Path

FIXTURES = Path(os.environ["FAKE_HARNESS_FIXTURES"])
TOKEN, PREFIX = "@HARNESS_PKG@", "packages/" + "harness"
args = sys.argv[1:]
log = os.environ.get("FAKE_HARNESS_LOG")
if log:
    with open(log, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(args) + "\\n")


def option(name, default=None):
    return args[args.index(name) + 1] if name in args else default


def emit(name, patch=None):
    document = json.loads((FIXTURES / name).read_text(encoding="utf-8").replace(TOKEN, PREFIX))
    if patch:
        patch(document)
    print(json.dumps(document))


if args[:2] == ["mcp", "catalog"]:
    emit("mcp-catalog.json")
elif args[:3] == ["hooks", "codex-lifecycle", "fragment"]:
    emit("codex-lifecycle-fragment.json")
elif args[:3] == ["hooks", "codex-lifecycle", "validate"]:
    emit("codex-lifecycle-" + os.environ.get("FAKE_HARNESS_VALIDATE", "valid") + ".json")
elif args[:2] == ["instructions", "scopes"]:
    emit("instruction-scopes.json")
elif args[:2] == ["profiles", "resolve"]:
    profile, trusted = option("--profile"), "--trusted" in args
    name = ("full-access" if profile == "trusted-full-access" else
            "green" if trusted else "untrusted")

    def patch(document):
        document["provider_id"] = option("--provider")
        for item in document["diagnostics"]:
            item["provider_id"] = option("--provider")
        if document["profile"]:
            document["profile"]["id"] = profile
    emit("profile-resolution-" + name + ".json", patch)
elif args[:2] == ["hooks", "show"]:
    root = Path(option("--target"))
    carrier = {{}}
    try:
        for line in (root / ".swissknifeman" / "hooks.env").read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                carrier[key] = value
    except OSError:
        pass
    modes = {{}}
    if "MEMORY_MODE" in carrier:
        modes["memory"] = {{"mode": carrier["MEMORY_MODE"]}}
    if "AGENT_ROUTER_POLICY" in carrier:
        modes["agent_router"] = {{"policy": carrier["AGENT_ROUTER_POLICY"]}}
    print(json.dumps({{"$schema": "urn:swissknifeman:harness:hooks-state:v1", "project": str(root),
                      "settings": {{"hooks": modes}} if modes else {{}}, "hooks_env": carrier,
                      "legacy": [], "stale": False}}))
elif args[0] == "hooks" and "--memory" in args:
    # Like the real command: the mode goes to the project carrier (the fake keeps no TOML).
    root = Path(option("--target")) / ".swissknifeman"
    root.mkdir(parents=True, exist_ok=True)
    (root / "hooks.env").write_text("# fake harness\\nMEMORY_MODE=" + option("--memory") + "\\n",
                                    encoding="utf-8")
    print("memory: mode " + option("--memory"))
else:
    print("fake harness: unsupported command: " + " ".join(args), file=sys.stderr)
    sys.exit(2)
'''


def write_executable(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def snapshot() -> dict:
    return {name: os.environ.get(name) for name in _ENV}


def restore(saved: dict) -> None:
    for name, value in saved.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    harness_link.clear_cache()


def install_fake(directory: Path, log: Path = None) -> Path:
    """Make ``harness`` resolve to a fake in ``directory`` and drop every other way to find one."""
    for name in _ENV:
        if name != "PATH":
            os.environ.pop(name, None)
    fake = write_executable(Path(directory) / "harness", _SCRIPT.format(python=sys.executable))
    os.environ["SKM_HARNESS_BIN"] = str(fake)
    os.environ["FAKE_HARNESS_FIXTURES"] = str(FIXTURES)
    if log is not None:
        os.environ["FAKE_HARNESS_LOG"] = str(log)
    harness_link.clear_cache()
    return fake


_default_dir = None


def install_default() -> None:
    """The process-wide fake; tests that want another partner state use the cases below."""
    global _default_dir
    if _default_dir is None:
        _default_dir = tempfile.TemporaryDirectory(prefix="fake-harness-default-")
        install_fake(Path(_default_dir.name))


class FakeHarnessCase(unittest.TestCase):
    """Each test gets its own fake with a call log (``fake_calls``)."""

    def setUp(self):
        super().setUp()
        self._saved = snapshot()
        self._scratch = tempfile.TemporaryDirectory(prefix="fake-harness-")
        self.fake_dir = Path(self._scratch.name)
        self.fake_log = self.fake_dir / "calls.jsonl"
        install_fake(self.fake_dir, self.fake_log)

    def tearDown(self):
        restore(self._saved)
        self._scratch.cleanup()
        super().tearDown()

    def fake_calls(self):
        if not self.fake_log.exists():
            return []
        return [json.loads(line) for line in self.fake_log.read_text(encoding="utf-8").splitlines()]


class NoHarnessCase(unittest.TestCase):
    """No harness anywhere: not named, not on PATH."""

    def setUp(self):
        super().setUp()
        self._saved = snapshot()
        self._empty = tempfile.TemporaryDirectory(prefix="no-harness-")
        for name in _ENV:
            os.environ.pop(name, None)
        os.environ["PATH"] = self._empty.name
        harness_link.clear_cache()

    def tearDown(self):
        restore(self._saved)
        self._empty.cleanup()
        super().tearDown()


def real_harness_named() -> bool:
    return bool(ORIGINAL.get("SKM_HARNESS_ROOT") or ORIGINAL.get("SKM_HARNESS_BIN"))


@contextlib.contextmanager
def real_harness(case: unittest.TestCase):
    """Within the block ``harness`` resolves as named when the process started; skip if none was."""
    if not real_harness_named():
        case.skipTest("harness not named by SKM_HARNESS_ROOT or SKM_HARNESS_BIN")
    saved = snapshot()
    for name in _ENV:
        if name != "PATH":
            os.environ.pop(name, None)
            if ORIGINAL.get(name) is not None:
                os.environ[name] = ORIGINAL[name]
    harness_link.clear_cache()
    try:
        if not harness_link.available():
            case.skipTest("the named harness is not executable")
        yield
    finally:
        restore(saved)


class RealHarnessCase(unittest.TestCase):
    """The harness named when the process started; skipped when none was named."""

    def setUp(self):
        super().setUp()
        manager = real_harness(self)
        manager.__enter__()
        self.addCleanup(manager.__exit__, None, None, None)
