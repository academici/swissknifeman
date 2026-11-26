"""policy §§5.2, 5.2a: simple commands of the supported subset; everything else is unsupported, not empty."""

import pytest

from skm.modules.policy.domain.shell_words import MAX_DEPTH, SimpleCommand, parse, simple_commands


def supported(command: str) -> tuple[SimpleCommand, ...]:
    commands = simple_commands(command)
    assert commands is not None, parse(command).error
    return commands


def argvs(command: str) -> list[tuple[str, ...]]:
    return [item.argv for item in supported(command)]


def test_separators_split_simple_commands() -> None:
    assert argvs("a 1; b && c || d | e |& f & g") == [
        ("a", "1"),
        ("b",),
        ("c",),
        ("d",),
        ("e",),
        ("f",),
        ("g",),
    ]


def test_wrappers_and_their_options_are_skipped() -> None:
    [command] = supported("sudo -u root env -i A=1 timeout -s KILL 5 nice -n 3 git push")
    assert command.argv == ("git", "push")
    assert command.wrappers == ("sudo", "env", "timeout", "nice")
    assert command.assignments == ("A=1",)


@pytest.mark.parametrize(
    ("command", "chdirs"),
    [
        ("env -C /etc /bin/rm passwd", ("/etc",)),
        ("env --chdir=/etc /bin/rm passwd", ("/etc",)),
        ("env --chdir /etc /bin/rm passwd", ("/etc",)),
        ("env --ch /etc /bin/rm passwd", ("/etc",)),  # getopt_long abbreviation
        ("env -C/etc /bin/rm passwd", ("/etc",)),
        ("env -iC /etc /bin/rm passwd", ("/etc",)),
        ("env -i -u HOME -C /etc A=1 /bin/rm passwd", ("/etc",)),
        ("sudo -D /etc env -C sub /bin/rm passwd", ("/etc", "sub")),
        ("sudo --chdir=/etc /bin/rm passwd", ("/etc",)),
        # one invocation keeps only its last directory; nested wrappers stay sequential
        ("env -C build -C . /bin/rm passwd", (".",)),
        ("env --chdir=build --chdir=. /bin/rm passwd", (".",)),
        ("env -C build --ch=/etc /bin/rm passwd", ("/etc",)),
        ("sudo -D build -D /etc /bin/rm passwd", ("/etc",)),
        ("env -C build env -C . /bin/rm passwd", ("build", ".")),
    ],
)
def test_wrapper_directories_are_kept(command: str, chdirs: tuple[str, ...]) -> None:
    [found] = supported(command)
    assert found.argv == ("/bin/rm", "passwd")
    assert tuple(word.value for word in found.chdirs) == chdirs


def test_an_unresolved_wrapper_directory_stays_opaque() -> None:
    [found] = supported('env -C "$D" /bin/rm passwd')
    assert found.chdirs[0].opaque


@pytest.mark.parametrize(
    "command",
    ["env -C $D -C build touch x", "env --chdir=$D --chdir=build touch x", "env -C build -C $D touch x"],
)
def test_a_later_directory_does_not_drop_an_opaque_one(command: str) -> None:
    # unquoted ``$D`` may split into a directory and a program: env would run that program instead
    [found] = supported(command)
    assert any(word.opaque for word in found.chdirs)
    assert supported("timeout 5 rm x")[0].chdirs == ()


def test_xargs_is_a_wrapper() -> None:
    assert argvs("xargs -0 -n 1 rm -f") == [("rm", "-f")]


def test_prefix_assignments_and_quotes() -> None:
    [command] = supported("LANG=C grep 'a b' \"c d\" e\\ f")
    assert command.assignments == ("LANG=C",)
    assert command.argv == ("grep", "a b", "c d", "e f")


def test_shell_bodies_eval_find_exec_and_substitutions_are_parsed_one_level_deeper() -> None:
    commands = simple_commands(
        "bash -lc 'git push' && eval \"git reset --hard\" ; find . -exec rm {} \\; ; echo $(id)"
    )
    assert commands is not None
    nested = {(item.argv, item.depth) for item in commands}
    assert (("git", "push"), 1) in nested
    assert (("git", "reset", "--hard"), 1) in nested
    assert (("rm", "{}"), 1) in nested
    assert (("id",), 1) in nested


def test_redirect_targets_are_listed() -> None:
    [command] = supported("cmd > out.txt 2>&1 >> log &> all < input <<< text")
    assert command.redirect_targets == ("out.txt", "log", "all")
    assert command.read_targets == ("input",)


def test_unresolved_words_are_opaque() -> None:
    [command] = supported("rm $TARGET")
    assert command.words[1].opaque


@pytest.mark.parametrize("word", ["~root/x", "~root", "~-", "~+/x", "~nobody/.ssh"])
def test_tildes_naming_another_directory_are_opaque(word: str) -> None:
    # bash expands ~user from the password database and ~+/~- from PWD/OLDPWD
    [command] = supported(f"touch {word}")
    assert command.words[1].opaque
    assert simple_commands(f"echo x > {word}") is None  # an unresolved redirect target is unsupported


@pytest.mark.parametrize(
    ("word", "value"), [("~/x", "~/x"), ("~", "~"), ("'~root'/x", "~root/x"), ("\\~root", "~root")]
)
def test_the_own_home_and_quoted_tildes_stay_literal(word: str, value: str) -> None:
    [command] = supported(f"touch {word}")
    assert (command.words[1].value, command.words[1].opaque) == (value, False)


@pytest.mark.parametrize(
    "command",
    [
        "cat <<EOF\nx\nEOF",
        "f() { rm -rf /; }",
        "function f { x; }",
        "for i in a; do rm $i; done",
        "while true; do x; done",
        "if true; then x; fi",
        "case x in a) y;; esac",
        "(cd /tmp && rm x)",
        "{ rm x; }",
        "echo 'unbalanced",
        "echo $'ansi'",
        "ls {a,b}",
        "$CMD arg",
        "echo > $OUT",
        'bash -c "$BODY"',
        "a &&",
        "| b",
        "env -S 'rm -rf /'",
        "env --split-string='rm -rf /'",
        "env -C /etc sh -c 'rm passwd'",
        "env -C /etc eval rm passwd",
        "env -C /etc find . -exec rm {} \\;",
    ],
)
def test_unsupported_syntax_is_reported_not_ignored(command: str) -> None:
    result = parse(command)
    assert not result.supported
    assert simple_commands(command) is None


def _wrapped(levels: int) -> str:
    nested = "true"
    for _ in range(levels):
        nested = "sh -c '" + nested.replace("'", "'\\''") + "'"
    return nested


def test_depth_limit() -> None:
    deepest = simple_commands(_wrapped(MAX_DEPTH))
    assert deepest is not None
    assert max(item.depth for item in deepest) == MAX_DEPTH
    assert simple_commands(_wrapped(MAX_DEPTH + 1)) is None
    assert parse(_wrapped(MAX_DEPTH + 1)).error == "nesting deeper than MAX_DEPTH"


def test_head_is_basename_but_program_keeps_the_path() -> None:
    [command] = supported("./bin/git status")
    assert command.head == "git"
    assert command.program == "./bin/git"


def test_cd_connector_is_recorded() -> None:
    first, second = supported("cd x || rm y")
    assert first.connector == "||"
    assert second.argv == ("rm", "y")
