"""K12 secret globs against shell globs: a word bash expands onto a secret overlaps it."""

import pytest

from skm.modules.policy.domain.glob_overlap import glob_overlap

HOME = "/home/dev/"


@pytest.mark.parametrize(
    ("word", "glob"),
    [
        ("/home/dev/.netr?", ".netrc"),
        ("/home/dev/.pgpas*", ".pgpass"),
        ("/home/dev/.*", ".netrc"),
        ("/home/dev/.ss?/config", ".ssh/**"),
        ("/home/dev/.[s]sh/config", ".ssh/**"),
        ("/home/dev/.[a-z]sh/config", ".ssh/**"),
        ("/home/dev/.ssh/*", ".ssh/**"),
        ("/home/de?/.ssh/config", ".ssh/**"),
        ("/home/dev/.config/gh/host?.yml", ".config/gh/hosts.yml"),
    ],
)
def test_a_glob_bash_expands_onto_a_home_secret_overlaps(word: str, glob: str) -> None:
    assert glob_overlap(word, glob, prefix=HOME)


@pytest.mark.parametrize(
    ("word", "glob"),
    [
        ("/home/dev/*", ".netrc"),  # a wildcard never expands onto a leading dot
        ("/home/dev/*/config", ".ssh/**"),
        ("/home/dev/[.]ssh/config", ".ssh/**"),
        ("/home/dev/.[!s]sh/config", ".ssh/**"),
        ("/home/dev/.[a-r]sh/config", ".ssh/**"),
        ("/home/dev/proj/*", ".ssh/**"),
    ],
)
def test_a_glob_that_cannot_reach_a_home_secret_does_not_overlap(word: str, glob: str) -> None:
    assert not glob_overlap(word, glob, prefix=HOME)


@pytest.mark.parametrize(
    ("word", "glob", "overlap"),
    [(".en?", ".env", True), (".env*", ".env.*", True), ("*", ".env", False), ("*.py", "*.pem", False)],
)
def test_basenames(word: str, glob: str, *, overlap: bool) -> None:
    assert glob_overlap(word, glob) is overlap


def test_highest_unicode_codepoint_can_occur_in_a_glob() -> None:
    assert glob_overlap("notes-\U0010ffff.*", "notes-?.txt")
