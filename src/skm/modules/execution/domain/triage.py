"""Pure, conservative triage rejection verification (execution §5.8 TR)."""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING

from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.finding import Severity

if TYPE_CHECKING:
    from collections.abc import Sequence

    from skm.modules.execution.domain.finding import Finding

__all__ = ["reverify_decision", "trivial_command"]


def reverify_decision(finding: Finding, decision: JsonObject) -> JsonObject:
    """Use independent host verification facts to accept a serious finding's rejection."""
    result: JsonObject = {**decision, "finding_key": finding.finding_key, "severity": finding.severity.value}
    if decision.get("decision") != "rejected" or finding.severity not in {Severity.BLOCKER, Severity.MAJOR}:
        return result
    repro, facts = decision.get("reproduction"), decision.get("verification")
    code = "TRIAGE_REPRO_UNVERIFIED"
    if isinstance(repro, dict):
        argv = repro.get("argv")
        if isinstance(argv, list) and argv and all(isinstance(arg, str) for arg in argv):
            if trivial_command([str(arg) for arg in argv]):
                code = "TRIAGE_REPRO_TRIVIAL"
            elif (
                isinstance(facts, dict)
                and facts.get("verified") is True
                and not facts.get("timed_out")
                and not facts.get("interrupted")
                and not facts.get("spawn_error")
                and type(facts.get("exit_code")) is int
                and type(repro.get("exit")) is int
            ):
                if facts["exit_code"] == repro["exit"]:
                    return result
                code = "TRIAGE_REPRO_MISMATCH"
    return {**result, "decision": "confirmed", "code": code}


def trivial_command(argv: Sequence[str]) -> bool:
    """Recognise commands with no evidence, including shell wrappers, without executing them."""
    tokens = list(argv)
    for _ in range(8):
        if not tokens:
            return True
        name = tokens[0].rsplit("/", 1)[-1]
        if name in {"sh", "bash", "dash", "zsh", "ksh"}:
            command = next(
                (
                    i
                    for i, arg in enumerate(tokens[1:], 1)
                    if arg.startswith("-") and not arg.startswith("--") and "c" in arg
                ),
                None,
            )
            if command is None or command + 1 >= len(tokens):
                return False
            try:
                lexer = shlex.shlex(tokens[command + 1], posix=True, punctuation_chars=True)
                lexer.whitespace_split = True
                tokens = list(lexer)
            except ValueError:
                return False
            continue
        if name == "env":
            unwrapped = _env_command(tokens[1:])
            if unwrapped is None:
                return False
            tokens = unwrapped
            continue
        return name in {"true", ":", "echo", "printf"} or (
            name == "exit" and (len(tokens) == 1 or tokens[1] == "0")
        )
    return True


def _env_command(tokens: list[str]) -> list[str] | None:
    """Remove env options and assignments without reading or expanding the host environment."""
    while tokens:
        arg, *rest = tokens
        if arg in {"-i", "--ignore-environment", "-"}:
            tokens = rest
        elif arg in {"-u", "--unset", "-C", "--chdir"}:
            if not rest:
                return None
            tokens = rest[1:]
        elif arg.startswith(("--unset=", "--chdir=")) or (arg[:2] in {"-u", "-C"} and len(arg) > 2):
            tokens = rest
        elif arg in {"-S", "--split-string"} or arg.startswith(("-S", "--split-string=")):
            if arg in {"-S", "--split-string"}:
                if not rest:
                    return None
                value, *rest = rest
            else:
                value = arg[2:] if arg.startswith("-S") else arg.partition("=")[2]
            try:
                tokens = shlex.split(value) + rest
            except ValueError:
                return None
        elif arg == "--":
            tokens = rest
            break
        elif "=" in arg and not arg.startswith("-"):
            tokens = rest
        else:
            break
    while tokens and "=" in tokens[0] and not tokens[0].startswith("-"):
        tokens = tokens[1:]
    return tokens
