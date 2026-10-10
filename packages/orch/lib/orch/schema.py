"""Closed-profile JSON Schema validator of the exec/v1 contracts: the aicore validator, re-exported.

orch keeps no validator of its own. The profile (supported keywords, issue codes and texts) is the one of
``aicore.util.schema``; this module only keeps the names orch and its tests use.
"""
from __future__ import annotations

from aicore.util.schema import (
    DIALECT,
    ERROR_CODES,
    SUPPORTED_KEYWORDS,
    RefError,
    Registry,
    SchemaProfileError,
    ValidationIssue,
    clear_registry_cache,
    load_registry,
    validate,
    validate_node,
)

__all__ = (
    "DIALECT", "ERROR_CODES", "SUPPORTED_KEYWORDS", "RefError", "Registry", "SchemaProfileError",
    "ValidationIssue", "clear_registry_cache", "load_registry", "validate", "validate_node",
)
