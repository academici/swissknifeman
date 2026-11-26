"""Byte-preserving edits to an existing SKM exclude block."""

from skm.adapters.git.excludes import _merge


def test_update_preserves_crlf_and_user_entries_on_both_sides() -> None:
    prefix = b"# user before\r\n/keep\r\n"
    suffix = b"/.skm\r\n# user after"
    original = prefix + b"# BEGIN SKM MANAGED EXCLUDES\r\n/.skm\r\n# END SKM MANAGED EXCLUDES\r\n" + suffix
    new = _merge(original, {b"/.skm-dev"}, {b"/.skm"})
    assert new == (
        prefix + b"# BEGIN SKM MANAGED EXCLUDES\r\n/.skm-dev\r\n# END SKM MANAGED EXCLUDES\r\n" + suffix
    )
    assert _merge(new, set(), {b"/.skm-dev"}) == prefix + suffix
