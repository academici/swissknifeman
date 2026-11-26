"""Recognize test and lint runners in shell command position."""

import re
import shlex

from skm.kernel.languages import RUNNER_DIAGNOSTICS, RUNNER_NAMES, RUNNER_WITH_ARGS, RUNNER_WRAPPER

# Consume quotes, escapes and descriptor redirection before looking for shell separators.
_BOUNDARY = re.compile(
    r"""'[^']*'|"(?:\\.|[^"\\])*"|\\[\s\S]|[<>]&|"""
    r"(?P<comment>(?<![^\s|;&])\#[^\n]*)|(?P<separator>[|;&\n]+)"
)
_DIAGNOSTIC = RUNNER_DIAGNOSTICS
_RUNNER = re.compile(r"(?:" + "|".join(re.escape(name) for name in RUNNER_NAMES) + r")")
_RUNNER_WITH_ARGS = re.compile(
    r"(?:" + "|".join(re.escape(phrase) for phrase in RUNNER_WITH_ARGS) + r")(?: |$)"
)
# ``python3`` and ``python3.12`` keep the historical optional version suffix.
_WRAPPER = re.compile(
    r"(?:"
    + "|".join(
        r"python(?:3(?:\.\d+)?)? -m" if phrase == "python -m" else re.escape(phrase)
        for phrase in RUNNER_WRAPPER
        if phrase != "python3 -m"
    )
    + r")(?: --[\w-]+)* "
)
_ASSIGNMENT = re.compile(r"[a-zA-Z_][a-zA-Z_0-9]*=.*", re.DOTALL)


def _without_assignments(words: list[str]) -> list[str]:
    index = next((i for i, word in enumerate(words) if not _ASSIGNMENT.fullmatch(word)), len(words))
    return words[index:]


def _command(words: list[str]) -> str:
    command = shlex.join(_without_assignments(words))
    while wrapper := _WRAPPER.match(command):
        if command.startswith("command -v "):
            break
        unwraps_env = command.startswith("env ")
        command = command[wrapper.end() :]
        if unwraps_env:
            command = shlex.join(_without_assignments(shlex.split(command)))
    return command


def _segments(command: str) -> list[str]:
    start = 0
    segments: list[str] = []
    for match in _BOUNDARY.finditer(command):
        if match.lastgroup is not None:
            segments.append(command[start : match.start()])
            start = match.end()
    segments.append(command[start:])
    return [segment for part in segments if (segment := _command(shlex.split(part)))]


def _executable(command: str) -> str:
    return shlex.split(command)[0].rsplit("/", 1)[-1]


def _is_diagnostic(command: str) -> bool:
    return _executable(command) in _DIAGNOSTIC or command.split(maxsplit=2)[:2] == ["command", "-v"]


def is_real_check(cmd: str | None, extra: tuple[str, ...] = ()) -> bool:
    if not cmd:
        return False
    try:
        segments = _segments(cmd)
    except ValueError:
        return False
    if not segments:
        return False

    def runner(command: str) -> bool:
        return (
            _RUNNER.fullmatch(_executable(command)) is not None
            or _RUNNER_WITH_ARGS.match(command) is not None
            or any(re.match(pattern, command) is not None for pattern in extra)
        )

    # A diagnostic command anywhere in the pipeline requires a runner in its first segment.
    if any(_is_diagnostic(segment) for segment in segments):
        return not _is_diagnostic(segments[0]) and runner(segments[0])
    return any(runner(segment) for segment in segments)
