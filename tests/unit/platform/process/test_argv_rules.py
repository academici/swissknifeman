from typing import cast

import pytest

from skm.platform.process.argv_rules import MAX_ARG_LEN, MAX_ARGV, check_argv


@pytest.mark.parametrize(
    "argv",
    [[], "echo hi", b"echo", [""], ["a\0b"], ["x", 1], ["x" * (MAX_ARG_LEN + 1)], ["x"] * (MAX_ARGV + 1)],
)
def test_invalid_vectors(argv: object) -> None:
    with pytest.raises(ValueError, match="argv"):
        check_argv(cast(list[str], argv))


def test_bounds_and_literal_arguments() -> None:
    assert check_argv(["x" * MAX_ARG_LEN]) == ("x" * MAX_ARG_LEN,)
    assert len(check_argv(["x"] * MAX_ARGV)) == MAX_ARGV
    args = [
        "codex",
        "-a",
        "never",
        "exec",
        "--json",
        "-c",
        'model_reasoning_effort="high"',
        "-",
        "",
        "$(touch /tmp/no)",
        "a b; c",
    ]
    result = check_argv(args)
    assert result == tuple(args)
    args.append("changed")
    assert result[-1] == "a b; c"
