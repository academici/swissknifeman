"""policy §5.7: every allowlist rule against the built-in read-only command data."""

from collections.abc import Mapping

import pytest

from skm.modules.policy.domain.allowlist import segment_allowlisted
from skm.modules.policy.domain.profiles import PolicyProfile
from skm.modules.policy.domain.shell_words import simple_commands


@pytest.fixture
def listed(profiles: Mapping[str, PolicyProfile]):
    commands = profiles["read-only"].permissions.commands

    def run(command: str) -> bool:
        segments = simple_commands(command)
        assert segments is not None
        return all(segment_allowlisted(segment, commands) for segment in segments)

    return run


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "LANG=C LC_ALL=C sort file",
        "TERM=xterm cat x",
        "X=1",
        "export FOO=bar",
        "declare -a FILES[0]=x",
        "read line",
        "read -r -p 'name? ' -t 5 answer rest",
        "read -d PATH",
        "read -a parts",
        "printf -v out %s x",
        "printf '%s' -v",
        "printf -- -v",
        "true",
        ":",
        "find . -name '*.py'",
        "sort -n file",
        "uniq file",
        "git status",
        "git -C sub log --oneline",
        "git branch",
        "git branch --list -a",
        "git reflog",
        "gh pr view 12",
        "gh issue list",
        "gh search code foo",
        "gh api repos/x/y",
        "gh api -X GET repos/x/y",
        "env",
        "env -0",
        "hostname",
        "xxd in",
        "hostname -f",
        "hostname --fqdn",
        "xxd -l 16 -c 8 in",
        "xxd -s -16 in -",
        "xxd -groupsize 2 in",
        "xxd -g4 -cols 8 in",
        "xxd -c8 -R never in -",
        "xxd -capitalize in",
        "tree -L 2",
        "sort --numeric-sort file",
        "sort -- file",
        "git branch --list --all",
        "yq '.a' f.yaml",
        "env LANG=C ls",
    ],
)
def test_allowlisted(listed, command: str) -> None:
    assert listed(command)


@pytest.mark.parametrize(
    "command",
    [
        "PATH=/tmp ls",
        "LD_PRELOAD=x.so ls",
        "GIT_DIR=x git status",
        "export PATH=/tmp",
        "declare -x LD_LIBRARY_PATH=x",
        "declare HOME[0]=/tmp/x",
        "typeset -x PATH[0]+=:/tmp",
        "read PATH",
        "read -r line HOME",
        "read -ra PATH",
        "read -raPATH",
        "read -a 'LD_PRELOAD[0]'",
        "read -- HOME",
        "printf -v HOME %s /tmp/x",
        "printf -vPATH %s /tmp",
        "printf -v 'PATH[0]' %s /tmp",
        "PYTHONPATH=x",
        "find . -delete",
        "find . -exec rm {} ;",
        "sort -o out file",
        "sort -no out file",
        "sort --out=x file",
        "sort --outp x file",
        "sort --compress-prog=sh -S1 file",
        "date --se=now",
        "file --comp x.magic",
        "tree -o out",
        "yq -i '.a=1' f.yaml",
        "xxd -r dump",
        "xxd in out",
        "xxd -l 16 in out",
        "xxd -c8 -- in out",
        "xxd --revert dump",
        "xxd -rubbish dump",
        "xxd -seek 16 in out",
        "xxd -groupsize 2 in out",
        "xxd in -r",
        "tree -R -L 1 -H .",
        "date -s now",
        "hostname evil",
        "hostname --file=name.txt",
        "hostname -Fname.txt",
        "hostname --fi=name.txt",
        "rg --pre ./x foo",
        "uniq a b",
        "env FOO=1",
        "git branch -D x",
        "git branch new-branch",
        "git branch --set-upstream-to=o/x",
        "git branch --unset-up",
        "git branch --set-up=o/x",
        "git branch --edit-desc",
        "git reflog expire --all",
        "git diff --output=x",
        "git log --ext-diff",
        "git -c core.pager=sh log",
        "git push",
        "gh api -X POST repos/x/y",
        "gh api repos/x/y -f a=b",
        "gh api --method=DELETE x",
        "gh pr merge 1",
        "gh pr",
        "./ls",
        "bin/ls",
        "/bin/ls",
        "timeout 5 ls",
        "rm x",
        "python3 -c 'print(1)'",
    ],
)
def test_not_allowlisted(listed, command: str) -> None:
    assert not listed(command)
