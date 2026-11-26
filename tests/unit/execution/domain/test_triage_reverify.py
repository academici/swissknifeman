"""TR decisions use independent facts and preserve finding identity and severity."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

import pytest

from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.finding import Severity
from skm.modules.execution.domain.triage import reverify_decision, trivial_command
from unit.execution.domain.test_finding_key import make


@pytest.mark.parametrize(
    "argv",
    [
        ["true"],
        ["/usr/bin/true"],
        [":"],
        ["exit", "0"],
        ["echo", "ok"],
        ["printf", "%s", "ok"],
        ["sh", "-c", "true"],
        ["bash", "-lc", "exit 0"],
        ["bash", "-xec", "true;"],
        ["sh", "-c", "exit 0;"],
        ["env", "LANG=C", "/bin/echo", "ok"],
        [],
    ],
)
def test_trivial_commands_are_not_reproduction(argv: list[str]) -> None:
    assert trivial_command(argv)


@pytest.mark.parametrize(
    "wrapper",
    [
        ["-i"],
        ["--ignore-environment"],
        ["-u", "TOKEN"],
        ["--unset=TOKEN"],
        ["-C", "/work"],
        ["--chdir=/work"],
        ["LANG=C"],
        ["--"],
        ["-uTOKEN"],
        ["-C/work"],
        ["--unset", "TOKEN"],
        ["--chdir", "/work"],
        ["-i", "-u", "TOKEN", "-C", "/work", "LANG=C"],
        ["-S", "/usr/bin/true"],
        ["--split-string", "/usr/bin/true"],
        ["--split-string=/usr/bin/true"],
        ["-S/usr/bin/true"],
        ["-S", "-i -u TOKEN LANG=C /usr/bin/true"],
    ],
)
def test_env_wrapped_trivial_rejection_is_reconfirmed(wrapper: list[str]) -> None:
    argv = ["/usr/bin/env", *wrapper, "/usr/bin/true"]
    assert trivial_command(argv)
    decision: JsonObject = {
        "decision": "rejected",
        "reproduction": {"argv": [*argv], "exit": 0},
        "verification": {"verified": True, "exit_code": 0},
    }
    receipt = reverify_decision(make(1, Severity.MAJOR, "high"), decision)
    assert receipt["decision"] == "confirmed"
    assert receipt["code"] == "TRIAGE_REPRO_TRIVIAL"


@pytest.mark.parametrize(
    "argv",
    [
        ["env", "-i", "python", "-m", "pytest"],
        ["env", "-u", "true", "python", "-m", "pytest"],
        ["env", "-C", "true", "python", "-m", "pytest"],
        ["env", "-S", "python -m pytest"],
        ["env", "-u"],
        ["env", "-C"],
        ["env", "-S"],
        ["env", "-S", "'"],
        ["env", "--unknown=value", "true"],
    ],
)
def test_env_keeps_meaningful_commands_and_rejects_malformed_options(argv: list[str]) -> None:
    assert not trivial_command(argv)


@pytest.mark.parametrize(
    "argv",
    [
        ["python", "-m", "pytest"],
        ["false"],
        ["exit", "1"],
        ["sh", "-c", "python -m pytest"],
        ["sh", "-c", "'"],
        ["sh"],
    ],
)
def test_meaningful_or_unparseable_commands_require_a_runner(argv: list[str]) -> None:
    assert not trivial_command(argv)


@pytest.mark.parametrize("severity", [Severity.MAJOR, Severity.BLOCKER])
@pytest.mark.parametrize(
    ("facts", "code"),
    [
        ({"verified": True, "exit_code": 0}, "TRIAGE_REPRO_MISMATCH"),
        ({"verified": False}, "TRIAGE_REPRO_UNVERIFIED"),
        ({"verified": True, "exit_code": 1, "timed_out": True}, "TRIAGE_REPRO_UNVERIFIED"),
        ({"verified": True, "exit_code": 1, "spawn_error": "SANDBOX_UNAVAILABLE"}, "TRIAGE_REPRO_UNVERIFIED"),
        ({"verified": True, "exit_code": 1, "interrupted": True}, "TRIAGE_REPRO_UNVERIFIED"),
        ({"verified": True, "exit_code": True}, "TRIAGE_REPRO_UNVERIFIED"),
    ],
)
def test_serious_rejection_requires_exact_verified_exit(severity: Severity, facts: Any, code: str) -> None:
    finding = make(1, severity, "high")
    decision = {
        "finding_id": "F1",
        "decision": "rejected",
        "reason": "Claim",
        "reproduction": {"argv": ["python", "-m", "pytest"], "exit": 1},
        "verification": facts,
    }
    before = deepcopy(decision)
    result = reverify_decision(finding, decision)
    assert result["decision"] == "confirmed"
    assert result["code"] == code
    assert result["finding_key"] == finding.finding_key
    assert result["severity"] == severity.value
    assert decision == before


def test_matching_reproduction_keeps_rejection() -> None:
    result = reverify_decision(
        make(1, Severity.MAJOR, "high"),
        {
            "decision": "rejected",
            "reproduction": {"argv": ["pytest"], "exit": 1},
            "verification": {"verified": True, "exit_code": 1},
        },
    )
    assert result["decision"] == "rejected"
    assert "code" not in result


def test_trivial_match_is_still_confirmed() -> None:
    result = reverify_decision(
        make(1, Severity.BLOCKER, "high"),
        {
            "decision": "rejected",
            "reproduction": {"argv": ["sh", "-c", "true"], "exit": 0},
            "verification": {"verified": True, "exit_code": 0},
        },
    )
    assert result["code"] == "TRIAGE_REPRO_TRIVIAL"
    assert result["decision"] == "confirmed"


@pytest.mark.parametrize("reproduction", [None, {}, {"argv": ["pytest"]}, {"argv": [12], "exit": 0}])
def test_missing_reproduction_does_not_clear_serious_finding(reproduction: Any) -> None:
    result = reverify_decision(
        make(1, Severity.MAJOR, "high"), {"decision": "rejected", "reproduction": reproduction}
    )
    assert result["decision"] == "confirmed"


def test_minor_rejection_needs_no_process_and_existing_confirmation_stays() -> None:
    finding = make(1, Severity.MINOR, "high")
    assert reverify_decision(finding, {"decision": "rejected"})["decision"] == "rejected"
    assert (
        reverify_decision(replace(finding, severity=Severity.BLOCKER), {"decision": "confirmed"})["decision"]
        == "confirmed"
    )
