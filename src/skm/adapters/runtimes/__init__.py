"""Agent runtime adapters (Claude Code, Codex, Cursor, Grok and a deterministic fake) behind ``AgentRuntime``.

``_cli_session`` is the shared CLI process lifecycle (bounded capture, cancellation, transcripts) that every
CLI-based adapter builds on; each runtime subpackage adds detection, launch, permissions and stream parsing.
"""

__all__: list[str] = []
