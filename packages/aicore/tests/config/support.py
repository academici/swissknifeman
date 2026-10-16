"""Shared helpers of the configuration tests: the fixture schema ``demo`` and a throwaway workspace."""
import tempfile
import unittest
from pathlib import Path

from aicore import config
from aicore.state import machine_config_file, project_config_file

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCHEMA_FILE = FIXTURES / "demo.config.schema.json"


def demo_schema() -> config.ModuleSchema:
    return config.load_module_schema(SCHEMA_FILE, "demo")


class Workspace(unittest.TestCase):
    """A temporary SKM_HOME, a project root and an explicit environment; nothing reads the real HOME."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.env = {"SKM_HOME": str(self.root / "skm")}
        self.project = self.root / "proj"
        self.project.mkdir()
        self.schema = demo_schema()
        self.warnings = []
        config.model._warned_env.clear()
        self.addCleanup(config.model._warned_env.clear)

    @property
    def machine_file(self) -> Path:
        return Path(machine_config_file(env=self.env))

    @property
    def project_file(self) -> Path:
        return Path(project_config_file(self.project))

    def write(self, path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def machine(self, body: str, version: bool = True) -> Path:
        return self.write(self.machine_file, ("schema_version = 1\n" if version else "") + body)

    def proj(self, body: str, version: bool = True) -> Path:
        return self.write(self.project_file, ("schema_version = 1\n" if version else "") + body)

    def resolve(self, **kwargs):
        kwargs.setdefault("schema", self.schema)
        kwargs.setdefault("env", dict(self.env))
        kwargs.setdefault("project", self.project)
        kwargs.setdefault("warn", self.warnings.append)
        return config.resolve("demo", **kwargs)
