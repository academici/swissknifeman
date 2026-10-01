"""Pure provider adapters; process ownership lives in the worker, not here."""

from .codex import build_argv, fold_records, normalize_record, resolve_binary

__all__ = ("build_argv", "fold_records", "normalize_record", "resolve_binary")
