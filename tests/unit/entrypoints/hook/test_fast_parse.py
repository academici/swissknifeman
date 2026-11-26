"""The hook entrypoint parses the common flags without falling back to argparse."""

import argparse
from types import SimpleNamespace

import pytest

from skm.entrypoints.hook.main import _fast_parse, main, register_arguments

REQUIRED = ("PreToolUse", "--target", "tree", "--surface", "claude", "--project", "proj")


def test_fast_parse_accepts_required_flags_and_optional_class() -> None:
    args = _fast_parse([*REQUIRED, "--class", "enforcement"])
    assert args is not None
    assert args.event_name == "PreToolUse"
    assert args.target == "tree"
    assert args.surface == "claude"
    assert args.project == "proj"
    assert args.hook_class == "enforcement"
    assert args.bootstrap is None


def test_fast_parse_accepts_equals_forms_and_bootstrap() -> None:
    args = _fast_parse(
        [
            "PreToolUse",
            "--target=tree",
            "--surface=claude",
            "--project=proj",
            "--bootstrap=instance/bootstrap",
        ]
    )
    assert args is not None
    assert args.target == "tree"
    assert args.bootstrap == "instance/bootstrap"
    assert args.hook_class is None


@pytest.mark.parametrize(
    "tokens",
    [
        ("--target", "tree", "--surface", "claude", "--project", "proj"),  # missing event
        ("PreToolUse", "--target", "tree", "--surface", "claude"),  # missing project
        ("PreToolUse", "extra", "--target", "tree", "--surface", "claude", "--project", "proj"),
        ("PreToolUse", "--target", "tree", "--surface", "claude", "--project", "proj", "--unknown", "x"),
        ("PreToolUse", "--target", "tree", "--target", "other", "--surface", "claude", "--project", "proj"),
        ("PreToolUse", "--target", "tree", "--surface", "claude", "--project", "proj", "--class", "other"),
        ("PreToolUse", "--target", "--surface", "claude", "--project", "proj"),  # value looks like a flag
    ],
)
def test_fast_parse_rejects_incomplete_or_unknown_tokens(tokens: tuple[str, ...]) -> None:
    assert _fast_parse(tokens) is None


def test_main_uses_the_fast_path_and_forwards_the_namespace(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[object] = []

    def invoke(args: object, *rest: object) -> int:
        seen.append(args)
        return 17

    monkeypatch.setattr("skm.bootstrap.hook.invoke", invoke)
    assert main([*REQUIRED, "--class=workflow"]) == 17
    args = seen[0]
    assert isinstance(args, SimpleNamespace)
    assert args.event_name == "PreToolUse"
    assert args.hook_class == "workflow"


def test_register_arguments_requires_target_surface_and_project() -> None:
    parser = argparse.ArgumentParser(prog="skm-hook", allow_abbrev=False)
    register_arguments(parser)
    parser.add_argument("--bootstrap")
    with pytest.raises(SystemExit):
        parser.parse_args(["PreToolUse"])
