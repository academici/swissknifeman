"""Second-layer masking, ported from aicore/util/redact.py without legacy imports.

Only JSON values reach this layer. It never reveals wrappers or stringifies arbitrary objects.
Metadata selection belongs to envelope.safe_fields; patterns cannot identify private prose.
"""

import json
import re
from collections.abc import Iterable, Iterator, Sequence
from threading import RLock
from typing import Final
from uuid import UUID

from skm.kernel.errors import ValidationFailed
from skm.kernel.generated._codec import SecretRef
from skm.kernel.json_types import JsonValue

__all__ = ["DEFAULT_PATTERNS", "ISSUED_TOKEN_VISIBLE_PATTERNS", "MASK", "Redactor", "mask_spans"]

MASK: Final = "\u2039redacted\u203a"
_ISSUER_TOKENS = (
    r"sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[abp]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|Bearer\s+\S{20,}"
)
# Bearer, session, CSRF, and pairing proofs can appear in transcripts, research text, and process output.
_TOKENS = re.compile(
    r"skm_live_[a-z2-7]{8}_[A-Za-z0-9_-]{43}_[0-9a-f]{8}"
    r"|skm_pair_[A-Za-z0-9_-]{43}"
    r"|skm_sess_[A-Za-z0-9_-]{43}"
    r"|skm_csrf_[A-Za-z0-9_-]{16,}\.[0-9a-f]{32,64}"
    r"|skm_[a-z2-7]{8}_[A-Za-z0-9_-]{43}|" + _ISSUER_TOKENS
)
_NAMED = re.compile(
    r"(?i)(?:((?:api[_-]?key|token|secret|password|passwd|passphrase|credential)[\"']?\s*[=:]\s*[\"']?)[^\s\"',;]{8,}"
    r"|((?:(?:set-)?cookie|x-skm-csrf)[\"']?\s*:\s*[\"']?)[^\r\n\"']+"
    r"|(skm_(?:session|csrf)[\"']?\s*[=:]\s*[\"']?)[^\s\"',;]+)"
)
DEFAULT_PATTERNS: Final = (_TOKENS, _NAMED)
# The CLI prints a token it has just issued (once, by design), so its own token format stays visible there.
ISSUED_TOKEN_VISIBLE_PATTERNS: Final = (re.compile(_ISSUER_TOKENS), _NAMED)
_SPACE = re.compile(r"\s")
_CLOSERS = {'"': '"', "'": "'", "(": ")", "[": "]", "{": "}"}


def _reference_syntax(value: str, match: re.Match[str]) -> bool:
    """Exempt only the literal ``secret:`` of a complete, delimited canonical reference.

    Use the pure value parser, never resolution or unescaping. Whole string values are checked
    whole; embedded text needs a delimiter, and a quote/bracket must have its matching closer.
    File references admit punctuation, so validating just the named pattern's prefix is unsafe.
    """
    if match.group(1) != "secret:":
        return False
    start = match.start()
    end = len(value)
    if start:
        before = value[start - 1]
        if before in _CLOSERS:
            if start > 1 and value[start - 2] == "\\":
                return False
            end = value.find(_CLOSERS[before], start)
            if end < 0 or value[end - 1] == "\\":
                return False
        else:
            if not before.isspace() and before not in "=:,;":
                return False
            boundary = _SPACE.search(value, start)
            if boundary is not None:
                end = boundary.start()
    try:
        SecretRef.parse(value[start:end])
    except ValidationFailed:
        return False
    return True


def _named_spans(value: str) -> Iterator[tuple[int, int]]:
    cursor = 0
    while (match := _NAMED.search(value, cursor)) is not None:
        if match.group(1) is not None and _reference_syntax(value, match):
            # Resume after ``secret:``, not after the reference: its file path can itself
            # contain a password/token/secret assignment that still needs masking.
            cursor = match.end(1)
        else:
            prefix_end = (
                match.end(1)
                if match.group(1) is not None
                else match.end(2)
                if match.group(2) is not None
                else match.end(3)
            )
            yield prefix_end, match.end()
            cursor = match.end()


def _merge(spans: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    # Touching spans share one mask, so two masks never stand side by side as new text.
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = merged[-1][0], max(end, merged[-1][1])
        else:
            merged.append((start, end))
    return merged


def mask_spans(value: str, spans: list[tuple[int, int]], known: Sequence[str]) -> str:
    """Mask the spans, then the surviving characters of any known value the masks assembled.

    Spans come from the original input, yet an inserted mask can complete a registered value
    with the text beside it (the mask's tail plus a suffix). Each round masks at least one more
    original character, so the loop ends; a value wholly inside one mask is its fixed text.
    """
    merged = _merge(spans)
    while merged:
        parts: list[str] = []
        origins: list[int] = []  # original index of each shown character, -1 inside a mask
        cursor = 0
        for start, end in merged:
            parts.extend((value[cursor:start], MASK))
            origins.extend((*range(cursor, start), *(-1 for _ in MASK)))
            cursor = end
        parts.append(value[cursor:])
        origins.extend(range(cursor, len(value)))
        shown = "".join(parts)
        assembled: list[tuple[int, int]] = []
        for secret in known:
            at = shown.find(secret)
            while at >= 0:
                assembled.extend((index, index + 1) for index in origins[at : at + len(secret)] if index >= 0)
                at = shown.find(secret, at + 1)
        if not assembled:
            return shown
        merged = _merge((*merged, *assembled))
    return value


class Redactor:
    """Thread-safe registry; register_secret is the SecretResolvers on_reveal callback."""

    def __init__(self, patterns: Sequence[re.Pattern[str]] = DEFAULT_PATTERNS) -> None:
        self._patterns = tuple(patterns)
        self._values: set[str] = set()
        self._lock = RLock()

    def register_secret(self, value: str) -> None:
        if type(value) is not str:
            raise TypeError("a revealed secret must be a string")
        if len(value) >= 8:
            # ID projection canonicalizes UUID strings and UUID objects before this layer sees them.
            # Keep the revealed spelling too; ordinary secrets still use exact, case-sensitive matching.
            try:
                canonical = str(UUID(value))
            except ValueError:
                canonical = value
            with self._lock:
                self._values.update((value, canonical))

    def _known(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._values, key=lambda value: (-len(value), value)))

    def _spans(self, value: str, known: Sequence[str]) -> list[tuple[int, int]]:
        """Every literal occurrence and pattern match, all decided on the original input.

        Earlier masks must neither create a valid reference nor hide an overlapping registered
        credential, a named assignment or a bearer value. Subclasses mask from these spans too.
        """
        spans: list[tuple[int, int]] = []
        for secret in known:
            cursor = 0
            while (start := value.find(secret, cursor)) >= 0:
                spans.append((start, start + len(secret)))
                cursor = start + 1
        for pattern in self._patterns:
            if pattern is _NAMED:
                spans.extend(_named_spans(value))
            else:
                spans.extend(match.span() for match in pattern.finditer(value))
        return spans

    def _text(self, value: str, known: tuple[str, ...]) -> str:
        return mask_spans(value, self._spans(value, known), known)

    def text(self, value: str) -> str:
        if type(value) is not str:
            raise TypeError("redaction text must be a string")
        return self._text(value, self._known())

    def document(self, value: JsonValue) -> JsonValue:
        """Copy JSON, including keys and scalars, using one registry snapshot."""
        known = self._known()

        def walk(item: JsonValue) -> JsonValue:
            if type(item) is str:
                return self._text(item, known)
            if type(item) is list:
                return [walk(entry) for entry in item]
            if type(item) is dict:
                result: dict[str, JsonValue] = {}
                for key, entry in item.items():
                    if type(key) is not str:
                        raise TypeError("redaction document keys must be strings")
                    result[self._text(key, known)] = walk(entry)
                return result
            if item is None or type(item) in (bool, int, float):
                encoded = json.dumps(item, allow_nan=False)
                return MASK if any(secret in encoded for secret in known) else item
            raise TypeError("redaction accepts only JSON values")

        return walk(value)
