"""Conventional release commits require a staged changelog (policy §5.9)."""

from .rule_ladder import GuardMode, LadderRule, LadderVerdict, verdict

RELEASE_TYPES = ("feat", "fix", "perf", "refactor")
RULES = tuple(
    LadderRule(
        "CHANGELOG_REQUIRED", rf"^{kind}(\([^)]*\))?!?:\s", "Stage a changelog entry before committing."
    )
    for kind in RELEASE_TYPES
)


def changelog_gate_verdict(message: str, *, mode: GuardMode) -> LadderVerdict:
    return verdict(message, rules=RULES, mode=mode)
