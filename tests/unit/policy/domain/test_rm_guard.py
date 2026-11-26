"""policy §5.5: deletions stay strictly inside the write roots; anything unclear is unsafe."""

import posixpath

import pytest

from skm.modules.policy.domain.rm_guard import rm_is_safe, rm_targets

ROOT = "/w/repo"
HOME = "/home/dev"


def resolve(path: str, cwd: str) -> str:
    return posixpath.normpath(posixpath.join(cwd, path))


def safe(command: str, cwd: str = ROOT, roots: tuple[str, ...] = (ROOT, "/w/tmp")) -> bool:
    return rm_is_safe(command, cwd, roots, ("/var/lib/skm",), HOME, resolve=resolve)


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf build",
        "rm -f a.txt b.txt",
        "rm -- -weird-name",
        "rmdir --ignore-fail-on-non-empty empty",
        "rm -rf build/*.o",
        "rm -rf *",
        "cd build && rm -f out.o",
        "cd sub; rm x",
        "rm -rf /w/tmp/cache",
        "git rm -r --cached vendor",
        "git rm src/old.py",
        "ls && echo done",
        "rm",
    ],
)
def test_safe_deletions(command: str) -> None:
    assert safe(command)


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "rm -rf /etc/passwd",
        "rm -rf .",
        "rm -rf /w/repo",
        "rm -rf ../other",
        "rm -rf $DIR",
        "rm -rf `pwd`",
        "rm -rf {a,b}",
        "rm -rf .git",
        "rm -rf .git/hooks",
        "rm -rf .*",
        "rm -rf ~/x",
        "rm --no-preserve-root -rf x",
        "rm -P x",
        "echo rm x",
        "xargs rm",
        "sudo rm x",
        "rm x\nrm y",
        "cd /etc && rm passwd",
        "cd x || rm y",
        "cd x | rm y",
        "popd && rm y",
        "rm -rf /var/lib/skm/state",
        "rm 'unbalanced",
    ],
)
def test_unsafe_deletions(command: str) -> None:
    assert not safe(command)


@pytest.mark.parametrize(
    "command", ["cat <<EOF\nnot a deletion\nEOF", "printf 'a\\nb'\nls", "echo 'unbalanced", "lsrm x; rm.txt"]
)
def test_a_line_without_a_deletion_program_is_left_to_the_syntax_gate(command: str) -> None:
    # legacy safedirs_applicable: the newline and parse refusals apply to lines that name rm/rmdir only
    assert safe(command)


@pytest.mark.parametrize("command", ["/bin/rm -rf /etc/x", "/usr/bin/rmdir /etc", "cat <<EOF\nrm -rf /\nEOF"])
def test_a_path_head_or_a_multiline_body_still_deletes(command: str) -> None:
    assert not safe(command)


@pytest.mark.parametrize(
    "command",
    [
        # R2: a pipeline member runs in a subshell (or under lastpipe in the shell): the directory is unknown
        "ls | cd /w/repo/build; rm -rf x",
        "ls |& cd /w/repo/build; rm -rf x",
        "ls | pushd /w/repo/build; rm -rf x",
        "cd /w/repo/build & rm -rf x",
        "true && cd /w/repo/build; rm -rf x",
        "true || cd /w/repo/build; rm -rf x",
        "true || cd /w/repo/build && rm -rf x",
        "(cd /w/repo/build); rm -rf x",
        "env cd /w/repo/build; rm -rf x",
        "command cd /w/repo/build; rm -rf x",
        "echo > cd /w/repo/build; rm -rf x",
    ],
)
def test_a_cd_that_may_not_move_the_shell_leaves_the_directory_unknown(command: str) -> None:
    # run from "/": only a cd that surely moved the shell would put x inside the write roots
    assert not safe(command, cwd="/")


@pytest.mark.parametrize(
    "command",
    ["cd /w/repo/build; rm -rf x", "cd /w/repo/build && rm -rf x", "cd /w/repo/build > /dev/null; rm -rf x"],
)
def test_a_cd_of_the_shell_itself_still_moves(command: str) -> None:
    assert safe(command, cwd="/")


@pytest.mark.parametrize(
    "command",
    [
        # R3: the wrapper runs the deletion in its own directory, also through a path head
        "env -C /etc /bin/rm passwd",
        "env --chdir=/etc /bin/rm passwd",
        "env -C /etc rm passwd",
        "sudo -D /etc /usr/bin/rm passwd",
        "timeout 5 /bin/rmdir x",
        # a redirect does not end the command: /etc/passwd is still an operand
        "rm -f build/x > /dev/null /etc/passwd",
    ],
)
def test_a_wrapped_or_redirected_deletion_is_unsafe(command: str) -> None:
    assert not safe(command)


def test_home_is_expanded_and_judged_like_any_path() -> None:
    assert rm_is_safe("rm ~/scratch/x", ROOT, (f"{HOME}/scratch",), (), HOME, resolve=resolve)
    assert not rm_is_safe("rm ~/x", ROOT, (ROOT,), (), None, resolve=resolve)


def test_globs_can_be_disabled() -> None:
    assert not rm_is_safe("rm *.o", ROOT, (ROOT,), (), HOME, resolve=resolve, allow_globs=False)


def test_git_protection_can_be_disabled() -> None:
    assert rm_is_safe("rm -rf .git/hooks", ROOT, (ROOT,), (), HOME, resolve=resolve, protect_git=False)


def test_targets_follow_cd_and_keep_globs() -> None:
    assert rm_targets("cd build && rm -f a.o *.tmp; git rm --cached x; git rm y", ROOT, resolve) == (
        "/w/repo/build/a.o",
        "/w/repo/build/*.tmp",
        "/w/repo/build/y",
    )
    assert rm_targets("rm 'broken", ROOT, resolve) == ()
