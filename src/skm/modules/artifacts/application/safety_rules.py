"""``build_safety_rules``: the CS-* rule inputs from the effective configuration (artifacts §4.3, §13).

Token and named-secret patterns are the platform redaction patterns (never copied here); the operator's
``logging.redact_patterns`` only add token patterns. The globs are matched in lower case.
"""

import re

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, ValidationFailed
from skm.modules.artifacts.domain.content_safety import (
    ABSOLUTE_PATH_PATTERN,
    BINARY_PROBE_BYTES,
    HOME_PATH_PATTERN,
    NOT_A_SECRET_PATTERNS,
    SafetyRules,
)
from skm.modules.artifacts.generated.settings import ArtifactsSettings
from skm.platform.config.effective import EffectiveConfig
from skm.platform.logging.redaction import DEFAULT_PATTERNS

__all__ = ["build_safety_rules"]

_REDACT_KEY = "logging.redact_patterns"
_NOT_VISIBLE = frozenset({ErrorCode.CONFIG_SCOPE_NOT_ALLOWED, ErrorCode.CONFIG_UNKNOWN_KEY})


def _operator_patterns(config: EffectiveConfig) -> tuple[re.Pattern[str], ...]:
    try:
        configured = config.get(_REDACT_KEY)
    except ValidationFailed as error:
        if error.code in _NOT_VISIBLE:  # a chain that cannot see the key adds nothing
            return ()
        raise
    if not isinstance(configured, list):
        return ()
    compiled: list[re.Pattern[str]] = []
    for text in configured:
        try:
            compiled.append(re.compile(str(text)))
        except re.error:
            raise InternalError(
                ErrorCode.INTERNAL_ERROR,
                "a configured redaction pattern does not compile",
                details={"key": _REDACT_KEY},
            ) from None
    return tuple(compiled)


def build_safety_rules(config: EffectiveConfig) -> SafetyRules:
    safety = config.section(ArtifactsSettings).safety
    tokens, named = DEFAULT_PATTERNS
    return SafetyRules(
        secret_name_globs=tuple(glob.lower() for glob in safety.secret_name_globs),
        token_patterns=(tokens, *_operator_patterns(config)),
        named_secret_pattern=named,
        not_a_secret=NOT_A_SECRET_PATTERNS,
        home_path=HOME_PATH_PATTERN,
        absolute_path=ABSOLUTE_PATH_PATTERN,
        binary_probe_bytes=BINARY_PROBE_BYTES,
        max_text_scan_bytes=safety.max_text_scan_bytes,
    )
