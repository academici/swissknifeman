"""Shared git-guardrails policy core for Codex, Cursor and Grok.

The argv-level check lives in the Claude hook directory (`git_guard.py`) so that one implementation
serves every provider; the regexes below stay as a safety net behind it.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from .lifecycle_policy_core import PolicyMatch, PolicyRule, PolicyVerdict, normalize_mode, verdict

_GUARD_PATH = (Path(__file__).resolve().parents[2] / "configs" / "claude-code" / "hooks"
               / "git-guardrails" / "git_guard.py")
_guard = None


def _load_guard():
    """Import git_guard.py by path; raises when it is missing so the handler refuses the command."""
    global _guard
    if _guard is None:
        spec = importlib.util.spec_from_file_location("harness_git_guard", _GUARD_PATH)
        if spec is None or spec.loader is None:
            raise ImportError("git_guard.py not found: %s" % _GUARD_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _guard = module
    return _guard

RULES = (
    PolicyRule(
        id="git-push",
        pattern=r"git push",
        reason="matches dangerous git push pattern",
        tier="high",
    ),
    PolicyRule(
        id="git-reset-hard",
        pattern=r"git reset --hard",
        reason="matches dangerous git reset --hard pattern",
        tier="critical",
    ),
    PolicyRule(
        id="git-clean-fd",
        pattern=r"git clean -fd",
        reason="matches dangerous git clean -fd pattern",
        tier="critical",
    ),
    PolicyRule(
        id="git-clean-f",
        pattern=r"git clean -f",
        reason="matches dangerous git clean -f pattern",
        tier="critical",
    ),
    PolicyRule(
        id="git-branch-delete",
        pattern=r"git branch -D",
        reason="matches dangerous git branch deletion pattern",
        tier="high",
    ),
    PolicyRule(
        id="git-checkout-dot",
        pattern=r"git checkout \.",
        reason="matches dangerous checkout dot pattern",
        tier="high",
    ),
    PolicyRule(
        id="git-restore-dot",
        pattern=r"git restore \.",
        reason="matches dangerous restore dot pattern",
        tier="high",
    ),
    PolicyRule(
        id="push-force",
        pattern=r"push --force",
        reason="matches dangerous force push pattern",
        tier="critical",
    ),
    PolicyRule(
        id="push-force-with-lease",
        pattern=r"push --force-with-lease",
        reason="matches dangerous force-with-lease pattern",
        tier="critical",
    ),
    PolicyRule(
        id="reset-hard",
        pattern=r"reset --hard",
        reason="matches dangerous reset --hard pattern",
        tier="critical",
    ),
    PolicyRule(
        id="rebase-onto",
        pattern=r"rebase --onto",
        reason="matches dangerous rebase --onto pattern",
        tier="critical",
    ),
)


def git_guardrails_verdict(command: str, *, mode: str):
    """Evaluate a git command against the declared off/warn/strict ladder.

    The argv check runs first (global options, wrappers, shell bodies, aliases, flag variants); the
    regexes then judge the whitespace-normalized text.
    """
    normalized = normalize_mode(mode)
    if normalized == "off" or not isinstance(command, str):
        return PolicyVerdict(normalized, "allow", None)
    found = _load_guard().check(command)
    if found is not None:
        match = PolicyMatch(found.id, "argv:" + found.id, found.reason, found.tier)
        return PolicyVerdict(normalized, "deny" if normalized == "strict" else "warn", match)
    return verdict(re.sub(r"\s+", " ", command), rules=RULES, mode=mode)
