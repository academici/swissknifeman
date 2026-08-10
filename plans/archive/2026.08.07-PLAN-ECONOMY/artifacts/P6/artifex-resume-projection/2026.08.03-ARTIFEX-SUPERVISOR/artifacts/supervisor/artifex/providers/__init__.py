"""Pure provider adapters; process ownership starts only in P3.4."""

from .codex import build_argv, fold_records, normalize_record, resolve_binary

__all__ = ("build_argv", "fold_records", "normalize_record", "resolve_binary")
