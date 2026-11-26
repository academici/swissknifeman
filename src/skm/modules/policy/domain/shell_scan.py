"""Shell text scanner (policy §5.6, port of auto-approve ``shellscan.py``).

``scan`` blanks the contents of quoted literals so that deny/ask patterns see only the text the shell
executes; bodies of ``$(…)`` and backticks stay visible, also inside double quotes. ``dynamic`` reports
constructs whose effect is computed at run time: ``$(``, a backtick, ``<(``, ``>(`` and ``$'``. The legacy
module kept the flag in a global; here every call owns its state.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ShellScan", "scan"]

_NORMAL = "n"
_SINGLE = "s"
_ANSI = "a"
_DOUBLE = "d"
_PAREN = "p"
_BACKTICK = "b"


@dataclass(frozen=True, slots=True)
class ShellScan:
    dynamic: bool
    visible_text: str


class _Scanner:
    def __init__(self, text: str) -> None:
        self.text = text
        self.out: list[str] = []
        self.stack: list[str] = [_NORMAL]
        self.dynamic = False
        self.i = 0

    def run(self) -> ShellScan:
        while self.i < len(self.text):
            mode = self.stack[-1]
            if mode == _SINGLE:
                self._single()
            elif mode == _ANSI:
                self._ansi()
            elif mode == _DOUBLE:
                self._double()
            else:
                self._code(mode)
        return ShellScan(self.dynamic, "".join(self.out))

    def _emit(self, text: str, *, hidden: bool = False) -> None:
        self.out.append(" " * len(text) if hidden else text)
        self.i += len(text)

    def _single(self) -> None:
        if self.text[self.i] == "'":
            self.stack.pop()
            self._emit("'")
        else:
            self._emit(self.text[self.i], hidden=True)

    def _ansi(self) -> None:
        char = self.text[self.i]
        if char == "\\":
            self._emit(self.text[self.i : self.i + 2], hidden=True)
        elif char == "'":
            self.stack.pop()
            self._emit("'")
        else:
            self._emit(char, hidden=True)

    def _double(self) -> None:
        text, i = self.text, self.i
        if text[i] == "\\":
            self._emit(text[i : i + 2], hidden=True)
        elif text[i] == '"':
            self.stack.pop()
            self._emit('"')
        elif text.startswith("$(", i):
            self.dynamic = True
            self.stack.append(_PAREN)
            self._emit("$(")
        elif text[i] == "`":
            self.dynamic = True
            self.stack.append(_BACKTICK)
            self._emit("`")
        else:
            self._emit(text[i], hidden=True)

    def _code(self, mode: str) -> None:
        text, i = self.text, self.i
        char = text[i]
        if char == "\\":
            self._emit(text[i : i + 2])
            return
        if char == "'":
            self.stack.append(_SINGLE)
            self._emit("'")
            return
        if text.startswith("$'", i):
            self.dynamic = True
            self.stack.append(_ANSI)
            self._emit("$'")
            return
        if char == '"':
            self.stack.append(_DOUBLE)
            self._emit('"')
            return
        if text.startswith(("$(", "<(", ">("), i):
            self.dynamic = True
            self.stack.append(_PAREN)
            self._emit(text[i : i + 2])
            return
        if char == "`":
            if mode == _BACKTICK:
                self.stack.pop()
            else:
                self.dynamic = True
                self.stack.append(_BACKTICK)
            self._emit("`")
            return
        if mode == _PAREN and char in "()":
            if char == "(":
                self.stack.append(_PAREN)
            else:
                self.stack.pop()
        self._emit(char)


def scan(command: str) -> ShellScan:
    """Visible text and the dynamic flag of one command line; never raises on unbalanced input."""
    return _Scanner(command).run()
