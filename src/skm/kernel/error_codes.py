"""Error code catalog (kernel-platform §2.5); definitions live in ``generated/error_codes.py``."""

from .generated.error_codes import CATALOG, ErrorCategory, ErrorCode, ErrorCodeInfo

__all__ = ["CATALOG", "ErrorCategory", "ErrorCode", "ErrorCodeInfo"]
