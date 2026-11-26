"""The config surface imports the facade; reference generation does not import product code."""

import ast
import importlib
from pathlib import Path

import pytest

from ._tree import SourceFile
from .rules import RuleContext, rule_cli_thin

ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path("src/skm/entrypoints/cli/commands/config.py")
gen = importlib.import_module("tools.gen")
cli_reference = importlib.import_module("tools.codegen.cli_reference")


def test_config_uses_only_the_settings_facade() -> None:
    assert not rule_cli_thin([SourceFile.at(ROOT / CONFIG)], RuleContext(root=ROOT))
    tree = ast.parse((ROOT / CONFIG).read_text())
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module]
    assert all(
        name in {"skm.modules.settings", "skm.modules.settings.public"}
        for name in imports
        if name.startswith("skm.modules.")
    )


@pytest.mark.parametrize(
    "source",
    [
        "from skm.modules.settings.application.commands.set_value import handle",
        "from skm.modules.settings.domain.entry import ConfigEntry",
        "from skm.modules.settings.ports import ConfigEntryRepository",
    ],
)
def test_direct_handler_domain_and_repository_imports_are_rejected(source: str) -> None:
    assert rule_cli_thin([SourceFile.at(CONFIG, source)], RuleContext())


def test_cli_reference_is_static_and_tracks_command_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        assert not name.startswith("skm"), "reference generation must not import product code"
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    result = cli_reference.outputs(ROOT)
    text = result[Path("docs/reference/cli.md")]
    assert (ROOT / "docs/reference/cli.md").read_text() == text
    assert "settings.get_value" in text
    assert "--expect-digest" in text
    assert "--expected-version" in text
    # The owner column follows the facade a declaration imports the operation through.
    assert "| skm config doctor | platform.doctor |" in text
    assert "| skm config get | settings.get_value |" in text
    assert "unregistered" not in text


def test_reference_generator_closure_preserves_other_outputs(session_generated_outputs) -> None:
    rendered = session_generated_outputs
    assert len(rendered) >= 160  # accepted closure (>=159) plus the CLI reference
    assert Path("docs/reference/cli.md") in rendered
    assert all((ROOT / path).read_text() == content for path, content in rendered.items())
