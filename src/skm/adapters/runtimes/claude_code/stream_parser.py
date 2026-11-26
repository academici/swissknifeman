"""Claude Code stream-json wire parser implementing ``_cli_session.session.StreamParser``."""

from __future__ import annotations

from collections.abc import Callable

from skm.adapters.runtimes._cli_session.stream_json import StreamJsonParser
from skm.adapters.runtimes._cli_session.wire_values import identity_redact

from .permissions import denial_hint
from .usage import UsageAccumulator

__all__: list[str] = []


class ClaudeStreamParser(StreamJsonParser):
    """Stateful line-by-line parser for Claude Code ``--output-format stream-json``."""

    def __init__(
        self,
        *,
        runtime_version: str | None = None,
        redact: Callable[[str], str] = identity_redact,
        subagent_disclosed: bool = False,
    ) -> None:
        super().__init__(
            usage=UsageAccumulator(subagent_disclosed=subagent_disclosed),
            denial_hint=denial_hint,
            version_fields=("claude_code_version",),
            runtime_version=runtime_version,
            redact=redact,
        )
