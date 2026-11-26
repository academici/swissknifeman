"""policy §§5.4, 5.10: the judge table, unwrapping, aliases, all violations and the regex safety net."""

import pytest

from skm.modules.policy.domain.git_guard import REGEX_FALLBACK, check, fallback_hits, violations


@pytest.mark.parametrize(
    ("command", "rule"),
    [
        ("git push -f origin main", "push-force"),
        ("git push --force-with-lease", "push-force"),
        ("git push --force-with-lease=main:abc", "push-force"),
        ("git push --force-if-includes", "push-force"),
        ("git push --mirror", "push-force"),
        ("git push --delete origin x", "push-force"),
        ("git push -d origin x", "push-force"),
        ("git push --prune origin", "push-force"),
        ("git push origin +main", "push-force"),
        ("git push origin :old", "push-force"),
        ("git push -uf origin main", "push-force"),
        ("git push origin main", "git-push"),
        ("git reset --hard HEAD~1", "reset-hard"),
        ("git reset --keep", "reset-hard"),
        ("git reset --merge", "reset-hard"),
        ("git clean -fdx", "git-clean-f"),
        ("git clean --force", "git-clean-f"),
        ("git branch -D topic", "git-branch-delete"),
        ("git branch -d -f topic", "git-branch-delete"),
        ("git branch --delete --force topic", "git-branch-delete"),
        ("git checkout .", "git-checkout-dot"),
        ("git checkout -- .", "git-checkout-dot"),
        ("git restore :/", "git-checkout-dot"),
        ("git restore --staged --worktree .", "git-checkout-dot"),
        ("git checkout -f main", "git-checkout-force"),
        ("git switch --discard-changes main", "git-checkout-force"),
        ("git switch -f main", "git-checkout-force"),
        ("git stash drop", "git-stash-drop"),
        ("git stash clear", "git-stash-drop"),
        ("git reflog expire --all", "git-reflog-expire"),
        ("git reflog delete HEAD@{1}", "git-reflog-expire"),
        ("git update-ref -d refs/heads/x", "git-update-ref-delete"),
        ("git rebase --onto main a b", "rebase-onto"),
        ("git filter-branch --tree-filter x", "git-filter-branch"),
    ],
)
def test_judge_table(command: str, rule: str) -> None:
    found = check(command)
    assert found is not None
    assert found.id == rule


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git clean -n -f",
        "git clean --dry-run --force",
        "git branch -d topic",
        "git restore --staged .",
        "git log --grep push",
        "git stash list",
        'echo "git push"',
        "git commit -m 'push --force'",
    ],
)
def test_safe_commands(command: str) -> None:
    assert check(command) is None


@pytest.mark.parametrize(
    "command",
    [
        "env -i GIT_DIR=x git push",
        "sudo -u root git push",
        "timeout 5 git push",
        "xargs git push",
        "bash -c 'git push'",
        'sh -lc "cd x && git push"',
        "eval git push",
        "find . -maxdepth 0 -exec git push \\;",
        "git -C /repo push",
        "git -c user.name=x push",
        "/usr/bin/git push",
        "A=1 git push",
    ],
)
def test_wrappers_and_bodies_are_unwrapped(command: str) -> None:
    found = check(command)
    assert found is not None
    assert found.id == "git-push"


@pytest.mark.parametrize(
    ("command", "rule"),
    [
        # R4: git reads every unambiguous abbreviation of a long option
        ("git reset --har HEAD~1", "reset-hard"),
        ("git reset --h", "reset-hard"),
        ("git reset --ke", "reset-hard"),
        ("git reset --mer", "reset-hard"),
        ("git reset --m", "reset-hard"),  # ambiguous mixed/merge: never assumed harmless
        ("git reset --hard=x", "reset-hard"),
        ("git reset --bogus", "reset-hard"),  # a spelling the guard does not know is refused
        ("git clean --for -d", "git-clean-f"),
        ("git clean --f", "git-clean-f"),
        ("git clean --forc --no-dry-run -n", "git-clean-f"),
        ("git clean -f --dry --no-dry", "git-clean-f"),
        ("git clean --bogus -f", "git-clean-f"),
        ("git clean --n -f", "git-clean-f"),  # ambiguous among the negations
        ("git -c alias.r='reset --har' r", "reset-hard"),
    ],
)
def test_abbreviated_destructive_flags_are_judged(command: str, rule: str) -> None:
    found = check(command)
    assert found is not None, command
    assert found.id == rule


@pytest.mark.parametrize(
    "command",
    [
        "git reset --soft HEAD~1",
        "git reset --mi",
        "git reset --quiet --no-refresh",
        "git reset -- --hard",
        "git reset HEAD~1",
        "git clean --dry --for",
        "git clean --no-f -d",
        "git clean -n",
    ],
)
def test_understood_harmless_spellings_pass(command: str) -> None:
    assert check(command) is None


def test_regex_fallback_reads_abbreviations() -> None:
    assert {rule.id for rule in fallback_hits("git reset --har")} == {"reset-hard"}
    assert {rule.id for rule in fallback_hits("git reset --k; ls")} == {"reset-hard"}
    assert {rule.id for rule in fallback_hits("git clean --for -d")} == {"git-clean-f"}
    assert fallback_hits("git reset --mixed") == ()
    assert fallback_hits("git clean --format") == ()


def test_alias_expansion() -> None:
    found = check("git -c alias.ship=push ship origin main")
    assert found is not None
    assert found.id == "git-push"
    forced = check("git -c alias.ship='push --force' ship")
    assert forced is not None
    assert forced.id == "push-force"


def test_shell_alias_body_is_judged() -> None:
    found = check("git -c 'alias.x=!git reset --hard' x")
    assert found is not None
    assert found.id == "reset-hard"


def test_violations_returns_every_hit() -> None:
    found = violations("git reset --hard && git push -f && git clean -fd")
    assert [item.id for item in found] == ["reset-hard", "push-force", "git-clean-f"]
    assert found[0].severity == "critical"


def test_unbalanced_quotes_fall_back_to_regex() -> None:
    found = violations("git push origin 'main")
    assert found
    assert found[0].id == "git-push"


def test_regex_fallback_has_eleven_rules_and_ignores_quoted_text() -> None:
    assert len(REGEX_FALLBACK) == 11
    assert fallback_hits('echo "git push --force"') == ()
    assert {rule.id for rule in fallback_hits("git  push   --force")} >= {"push-force", "git-push"}
    assert {rule.id for rule in fallback_hits("git reset --hard")} == {"reset-hard"}
