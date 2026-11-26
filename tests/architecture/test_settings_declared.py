"""Declared settings checks and metadata-driven CLI parsing use the canonical registry."""

from pathlib import Path

from ._tree import SourceFile
from .rules import RuleContext, rule_settings_declared

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path("src/skm/modules/planning/application/sample.py")


def test_known_key_is_accepted_and_typo_rejected() -> None:
    good = SourceFile.at(SOURCE, "def run(ctx): return ctx.config.get('execution.review.max_rounds')")
    bad = SourceFile.at(SOURCE, "def run(ctx): return ctx.config.get('execution.review.typo')")
    context = RuleContext(root=ROOT)
    assert rule_settings_declared([good], context) == []
    assert [v.detail for v in rule_settings_declared([bad], context)] == ["execution.review.typo"]


def test_config_command_has_no_undeclared_reads() -> None:
    assert (
        rule_settings_declared(
            [SourceFile.at(ROOT / "src/skm/entrypoints/cli/commands/config.py")], RuleContext(root=ROOT)
        )
        == []
    )


def test_unknown_typed_view_is_rejected() -> None:
    source = SourceFile.at(
        SOURCE,
        "from skm.modules.planning.generated.settings import WrongView\n"
        "def run(ctx): return ctx.config.section(WrongView)",
    )
    assert rule_settings_declared([source], RuleContext(root=ROOT))
