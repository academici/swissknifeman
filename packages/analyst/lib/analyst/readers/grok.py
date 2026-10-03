"""Grok capture reuses the Codex hook envelope; provider_id is grok."""
from .codex import CodexCaptureReader


class GrokCaptureReader(CodexCaptureReader):
    reader_id = "grok-hook-context"
    provider_id = "grok"
