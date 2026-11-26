"""policy §5.8: off allows, the first match decides, an unknown mode is a schema error (not ``off``)."""

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.policy.domain.rule_ladder import GuardMode, LadderRule, parse_guard_mode, verdict

RULES = (
    LadderRule("first", r"\bdrop\b", "drops data", "high"),
    LadderRule("second", r"drop", "also matches", "low"),
)


def test_off_always_allows() -> None:
    result = verdict("drop table", rules=RULES, mode=GuardMode.OFF)
    assert result.decision == "allow"
    assert result.match is None


@pytest.mark.parametrize(("mode", "decision"), [(GuardMode.STRICT, "deny"), (GuardMode.WARN, "warn")])
def test_first_match_decides(mode: GuardMode, decision: str) -> None:
    result = verdict("please drop it", rules=RULES, mode=mode)
    assert result.decision == decision
    assert result.match == RULES[0]
    assert result.mode is mode


def test_no_match_allows() -> None:
    assert verdict("select 1", rules=RULES, mode=GuardMode.STRICT).decision == "allow"


@pytest.mark.parametrize("value", ["strict", "warn", "off"])
def test_known_modes_parse(value: str) -> None:
    assert parse_guard_mode(value) is GuardMode(value)


@pytest.mark.parametrize("value", ["bypass", "permissive", "", "STRICT", None, 1])
def test_unknown_mode_is_a_schema_error(value: object) -> None:
    with pytest.raises(ValidationFailed) as error:
        parse_guard_mode(value)
    assert error.value.code is ErrorCode.SCHEMA_INVALID
