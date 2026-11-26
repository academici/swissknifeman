"""policy §5.6: quoted literals are blanked, substitution bodies stay visible, ``dynamic`` is per call."""

import pytest

from skm.modules.policy.domain.shell_scan import scan


def test_command_substitution_inside_double_quotes_is_visible() -> None:
    result = scan('echo "msg $(git push) end"')
    assert "git push" in result.visible_text
    assert "msg" not in result.visible_text
    assert result.dynamic


def test_single_quoted_text_is_hidden_and_static() -> None:
    result = scan("echo 'git push $(rm -rf /)'")
    assert "git" not in result.visible_text
    assert "rm" not in result.visible_text
    assert not result.dynamic


def test_backtick_body_is_visible_also_in_double_quotes() -> None:
    result = scan('echo "`id -u`"')
    assert "id -u" in result.visible_text
    assert result.dynamic


@pytest.mark.parametrize(
    "command", ["diff <(ls a) b", "tee >(cat)", "echo $'\\x41'", "echo $(date)", "echo `date`"]
)
def test_dynamic_constructs(command: str) -> None:
    assert scan(command).dynamic


@pytest.mark.parametrize("command", ["ls -la", 'echo "$HOME"', "cat a > b", "echo '$(x)'"])
def test_static_lines(command: str) -> None:
    assert not scan(command).dynamic


def test_two_calls_do_not_share_state() -> None:
    assert scan("echo $(x)").dynamic
    assert not scan("echo x").dynamic


def test_positions_are_preserved_and_unbalanced_input_does_not_raise() -> None:
    text = 'echo "abc'
    assert len(scan(text).visible_text) == len(text)
    assert scan("echo $(unclosed").dynamic
