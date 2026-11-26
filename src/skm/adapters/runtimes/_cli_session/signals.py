"""Redacted process signals; provider classification belongs to the runtimes facade."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from skm.modules.runtimes import public as runtimes
from skm.modules.runtimes.domain.error_rules import ErrorRule
from skm.platform.logging.redaction import Redactor

__all__: list[str] = []


class SignalCollector:
    def __init__(self, redactor: Redactor) -> None:
        self.redactor = redactor
        self.stderr_tail = ""

    def stderr(self, redacted: str) -> None:
        self.stderr_tail = (self.stderr_tail + redacted)[-4000:]

    def collect(self, signals: runtimes.RuntimeSignals, exit_code: int | None) -> runtimes.RuntimeSignals:
        return replace(
            signals,
            exit_code=exit_code,
            fatal_text=None if signals.fatal_text is None else self.redactor.text(signals.fatal_text),
            stderr_tail=self.stderr_tail,
        )

    def classify(
        self, runtime_id: str, signals: runtimes.RuntimeSignals, rules: Sequence[ErrorRule], *, now_unix: int
    ) -> runtimes.ProviderFailure:
        return runtimes.classify(runtime_id, signals, rules, now_unix=now_unix)
