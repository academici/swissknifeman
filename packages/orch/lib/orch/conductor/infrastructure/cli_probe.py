"""Which flags a provider CLI lists: one ``<cli> --help`` per command and flags, cached for the process."""
from __future__ import annotations

import os
import subprocess
from typing import Callable, Optional

_KNOWN: dict = {}  # (command, flags) -> whether the provider CLI lists the flags in its --help


def knows(argv: list, flags: list, note: Optional[Callable[[str], None]] = None) -> bool:
    """Whether the provider CLI of ``argv`` lists ``flags`` in its ``--help`` (an older CLI without ``--safe-mode``
    still runs, isolated by the environment only, and ``note``, when given, gets the text that says so once)."""
    command = next((arg for arg in argv if os.path.basename(arg) in ("claude", "codex", "grok")), None)
    if command is None:  # a test stand-in or a wrapper the conductor does not know: pass the flags as asked
        return True
    key = (command, tuple(flags))
    if key not in _KNOWN:
        try:
            text = subprocess.run([command, "--help"], capture_output=True, text=True, timeout=20).stdout
        except (OSError, subprocess.SubprocessError):
            text = ""
        _KNOWN[key] = all(flag in text for flag in flags)
        if not _KNOWN[key] and note is not None:
            note(f"{command} does not list {' '.join(flags)}; roles are isolated by the environment only")
    return _KNOWN[key]


def run_knows(self, argv: list, flags: list) -> bool:
    """:func:`knows` for the run: its progress says an unlisted flag once (ISOLATION_PARTIAL)."""
    def note(message: str) -> None:
        if self.progress is not None:
            self.progress.emit("info", reason_code="ISOLATION_PARTIAL", message=message)
    return knows(argv, flags, note)
