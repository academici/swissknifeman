"""Content safety (CS-* rules, artifacts §4.3) and the admission decision; port of legacy workspace safety.py.

A finding never carries the matched text: details name the rule, a count, a line or a JSON pointer and
the mask. Filesystem observation (a symlink source) belongs to host operations: ``symlink_finding``.
"""

import fnmatch
import json
import re
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from enum import StrEnum
from re import Pattern
from typing import Final, Literal, TypeGuard, get_args

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonValue

from .classification import Classification, max_classification
from .upload_rules import EXECUTABLE_TYPES, media_type_consistent, normalize_media_type

__all__ = [
    "ABSOLUTE_PATH_PATTERN",
    "BINARY_PROBE_BYTES",
    "HOME_PATH_PATTERN",
    "MASK",
    "NOT_A_SECRET_PATTERNS",
    "Admission",
    "Admit",
    "ContentKind",
    "Reject",
    "SafetyFinding",
    "SafetyLevel",
    "SafetyReport",
    "SafetyRule",
    "SafetyRules",
    "SafetyVerdict",
    "decide_admission",
    "is_safety_rule",
    "scan_bytes",
    "scan_document",
    "symlink_finding",
]

MASK: Final = (
    "\N{SINGLE LEFT-POINTING ANGLE QUOTATION MARK}redacted\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK}"
)
BINARY_PROBE_BYTES: Final = 8000
HOME_PATH_PATTERN: Final = re.compile(r"/home/[^/\s\"']+/|/Users/[^/\s\"']+/|[A-Za-z]:\\\\?Users\\\\?")
ABSOLUTE_PATH_PATTERN: Final = re.compile(r"^(?:[/~]|[A-Za-z]:[\\/])")
# Redaction matches that are not secrets: a lower-case hyphenated ``sk-`` word (the tail of a slug such as
# ``task-development-workflow``; real keys carry digits or capitals) and a value that is wholly a placeholder
# (``<NAME>``, ``$NAME``, ``${NAME}``, ``{name}``) or a secret reference (``env://NAME``).
NOT_A_SECRET_PATTERNS: Final = (
    re.compile(r"sk-[a-z]+(?:-[a-z]+)*"),
    re.compile(
        r"<[A-Za-z][A-Za-z0-9_.-]*>|\$\{[A-Za-z_][A-Za-z0-9_]*\}|\$[A-Za-z_][A-Za-z0-9_]*"
        r"|\{[A-Za-z][A-Za-z0-9_.-]*\}|env://[A-Za-z0-9_][A-Za-z0-9_./-]*"
    ),
)
type SafetyRule = Literal[
    "CS-SECRET-NAME",
    "CS-SECRET-CONTENT",
    "CS-ABSOLUTE-PATH",
    "CS-HOME-PATH",
    "CS-BINARY",
    "CS-NOT-SCANNED",
    "CS-SYMLINK",
    "CS-MEDIA-MISMATCH",
    "CS-EXECUTABLE",
]
_SAFETY_RULES: Final = frozenset(get_args(SafetyRule.__value__))


def is_safety_rule(value: object) -> TypeGuard[SafetyRule]:
    """Whether ``value`` names one of the CS-* rules (a stored report or an acknowledgement request)."""
    return isinstance(value, str) and value in _SAFETY_RULES


_UNACKNOWLEDGEABLE: Final[frozenset[SafetyRule]] = frozenset(
    {"CS-SYMLINK"}
)  # the host op refuses a symlink source outright
_G21_RULES: Final[frozenset[SafetyRule]] = frozenset({"CS-MEDIA-MISMATCH", "CS-EXECUTABLE"})


class SafetyLevel(StrEnum):
    BLOCK = "block"
    WARN = "warn"
    INFO = "info"


class ContentKind(StrEnum):
    UPLOAD = "upload"
    PORTABLE_DOCUMENT = "portable_document"
    EVIDENCE = "evidence"


@dataclass(frozen=True, slots=True)
class SafetyRules:
    secret_name_globs: tuple[str, ...]
    token_patterns: tuple[Pattern[str], ...]
    named_secret_pattern: Pattern[str]
    not_a_secret: tuple[Pattern[str], ...]
    home_path: Pattern[str]
    absolute_path: Pattern[str]
    binary_probe_bytes: int
    max_text_scan_bytes: int


@dataclass(frozen=True, slots=True)
class SafetyFinding:
    rule: SafetyRule
    level: SafetyLevel
    detail: str
    line: int | None
    pointer: str | None

    def to_json(self) -> dict[str, JsonValue]:
        return {
            "rule": self.rule,
            "level": str(self.level),
            "detail": self.detail,
            "line": self.line,
            "pointer": self.pointer,
        }


type SafetyVerdict = Literal["ok", "warn", "block"]  # the admission verdict of a safety report


@dataclass(frozen=True, slots=True)
class SafetyReport:
    findings: tuple[SafetyFinding, ...]
    acknowledged: tuple[SafetyRule, ...]
    binary: bool

    def verdict(self) -> SafetyVerdict:
        """``block`` while a block finding is not acknowledged; an acknowledged one still warns."""
        acknowledged = set(self.acknowledged)
        levels = [(finding.level, finding.rule in acknowledged) for finding in self.findings]
        if any(level == SafetyLevel.BLOCK and not acked for level, acked in levels):
            return "block"
        if any(level in {SafetyLevel.BLOCK, SafetyLevel.WARN} for level, _ in levels):
            return "warn"
        return "ok"


def _finding(
    rule: SafetyRule, level: SafetyLevel, detail: str, line: int | None = None, pointer: str | None = None
) -> SafetyFinding:
    return SafetyFinding(rule, level, detail, line, pointer)


def symlink_finding() -> SafetyFinding:
    """``CS-SYMLINK``: a host op found a symbolic link where it reads a file; the link is never followed."""
    return _finding("CS-SYMLINK", SafetyLevel.BLOCK, "the source is a symbolic link and is not followed")


def _secret_name(name: str, rules: SafetyRules) -> SafetyFinding | None:
    folded = unicodedata.normalize("NFKC", name).casefold()
    # A trailing dot or space disappears on some file systems: "id.pem." lands as "id.pem".
    candidates = {folded, folded.rstrip(". ")}
    for glob in rules.secret_name_globs:
        if any(fnmatch.fnmatchcase(candidate, glob.casefold()) for candidate in candidates):
            return _finding(
                "CS-SECRET-NAME", SafetyLevel.BLOCK, f"the file name is a secret file name ({glob}): {MASK}"
            )
    return None


def _exempt(value: str, rules: SafetyRules) -> bool:
    return any(pattern.fullmatch(value) is not None for pattern in rules.not_a_secret)


def _token_exempt(match: re.Match[str], rules: SafetyRules) -> bool:
    text = match.group(0)
    start = match.start()
    if text.startswith("sk-") and start > 0 and match.string[start - 1].isalnum():
        return True  # the tail of a word such as ``task-0204-...``, not a key
    return _exempt(text, rules)


def _named_exempt(match: re.Match[str], rules: SafetyRules) -> bool:
    prefix_end = match.end(1) if match.re.groups and match.end(1) >= 0 else match.start()
    return _exempt(match.string[prefix_end : match.end()], rules)


def _secret_hits(line: str, rules: SafetyRules) -> tuple[int, str | None]:
    count = 0
    first: str | None = None
    groups: list[tuple[str, Pattern[str], Callable[[re.Match[str], SafetyRules], bool]]] = [
        ("token", pattern, _token_exempt) for pattern in rules.token_patterns
    ]
    groups.append(("named-secret", rules.named_secret_pattern, _named_exempt))
    for name, pattern, exempt in groups:
        hits = sum(1 for m in pattern.finditer(line) if m.end() > m.start() and not exempt(m, rules))
        if hits:
            count += hits
            first = first or name
    return count, first


def _secret_finding(
    count: int, name: str | None, where: str, *, line: int | None = None, pointer: str | None = None
) -> SafetyFinding:
    return _finding(
        "CS-SECRET-CONTENT",
        SafetyLevel.BLOCK,
        f"{count} match(es) of the {name} secret pattern, the first at {where}: {MASK}",
        line,
        pointer,
    )


def _text_secret(text: str, rules: SafetyRules) -> SafetyFinding | None:
    total = 0
    first: tuple[int, str | None] | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        count, name = _secret_hits(line, rules)
        if count:
            total += count
            first = first or (number, name)
    if first is None:
        return None
    return _secret_finding(total, first[1], f"line {first[0]}", line=first[0])


def _home_paths(text: str, rules: SafetyRules) -> SafetyFinding | None:
    total = 0
    first: int | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        count = sum(1 for _ in rules.home_path.finditer(line))
        if count:
            total += count
            first = first or number
    if first is None:
        return None
    return _finding(
        "CS-HOME-PATH", SafetyLevel.WARN, f"{total} home-directory path(s), the first at line {first}", first
    )


def _pointer_part(part: str, rules: SafetyRules) -> str:
    # A pointer names where a value is; a key that itself looks like a secret or a path is masked.
    if _secret_hits(part, rules)[0] or rules.absolute_path.match(part) or rules.home_path.search(part):
        return MASK
    return part.replace("~", "~0").replace("/", "~1")


def _strings(document: JsonValue, rules: SafetyRules) -> Iterator[tuple[str, str | None, str]]:
    """``(pointer, string value or None, text for the secret rule)`` in document order, without recursion.

    A member is scanned as ``key: value`` so a named secret split into key and value is still found; a key
    that looks like a secret or a path is masked in every pointer under it.
    """
    stack: list[tuple[str, str | None, JsonValue]] = [("", None, document)]
    while stack:
        pointer, key, node = stack.pop()
        if isinstance(node, str):
            yield pointer, node, node if key is None else f"{key}: {node}"
            continue
        if key is not None:
            yield pointer, None, key
        if isinstance(node, dict):
            members = [(f"{pointer}/{_pointer_part(k, rules)}", k, v) for k, v in node.items()]
            stack.extend(reversed(members))
        elif isinstance(node, list):
            stack.extend(reversed([(f"{pointer}/{index}", None, v) for index, v in enumerate(node)]))


def _document_findings(document: JsonValue, rules: SafetyRules) -> list[SafetyFinding]:
    found: list[SafetyFinding] = []
    total = 0
    first: tuple[str, str | None] | None = None
    for pointer, text, scanned in _strings(document, rules):
        for line in scanned.splitlines() or [scanned]:
            count, name = _secret_hits(line, rules)
            if count:
                total += count
                first = first or (pointer or "/", name)
        if text is not None and (rules.absolute_path.match(text) or rules.home_path.search(text)):
            where = pointer or "/"
            found.append(
                _finding(
                    "CS-ABSOLUTE-PATH",
                    SafetyLevel.BLOCK,
                    f"an absolute path at {where} of a portable document",
                    pointer=where,
                )
            )
    if first is not None:
        found.insert(0, _secret_finding(total, first[1], f"pointer {first[0]}", pointer=first[0]))
    return found


def scan_document(doc: JsonValue, rules: SafetyRules) -> SafetyReport:
    """``CS-ABSOLUTE-PATH`` per string value with its pointer; ``CS-SECRET-CONTENT`` over all strings."""
    return SafetyReport(tuple(_document_findings(doc, rules)), (), False)


def _media_findings(declared: str | None, detected: str, rules: SafetyRules) -> list[SafetyFinding]:
    found: list[SafetyFinding] = []
    if not media_type_consistent(declared, detected):
        try:
            shown = normalize_media_type(declared)
        except ValidationFailed:
            shown = "an invalid media type"
        else:
            # Lower-casing can hide a case-sensitive token (``AKIA…``) that it still copies: judge both forms.
            if shown is None or _secret_hits(shown, rules)[0] or _secret_hits(str(declared), rules)[0]:
                shown = MASK
        found.append(_finding("CS-MEDIA-MISMATCH", SafetyLevel.WARN, f"{shown} → {detected}"))
    if detected in EXECUTABLE_TYPES:
        found.append(
            _finding("CS-EXECUTABLE", SafetyLevel.WARN, f"the signature is an executable format ({detected})")
        )
    return found


def _text_findings(text: str, rules: SafetyRules, kind: ContentKind) -> list[SafetyFinding]:
    found: list[SafetyFinding] = []
    secret = _text_secret(text, rules)
    if secret is not None:
        found.append(secret)
    if kind is ContentKind.PORTABLE_DOCUMENT:
        try:
            document = json.loads(text)
        except (ValueError, RecursionError):
            found.append(
                _finding(
                    "CS-NOT-SCANNED", SafetyLevel.INFO, "not a JSON document; path rules were not applied"
                )
            )  # the secret rule above still ran over the text
        else:
            decoded = _document_findings(document, rules)
            if secret is None:  # a secret hidden by JSON escapes (``ghp_…``) shows only once decoded
                found.extend(f for f in decoded if f.rule == "CS-SECRET-CONTENT")
            found.extend(f for f in decoded if f.rule == "CS-ABSOLUTE-PATH")
    else:
        home = _home_paths(text, rules)
        if home is not None:
            found.append(home)
    return found


def _not_scanned(detail: str) -> SafetyFinding:
    return _finding("CS-NOT-SCANNED", SafetyLevel.INFO, f"{detail}; text rules were not applied")


def _read_text_findings(data: bytes, rules: SafetyRules, kind: ContentKind) -> list[SafetyFinding]:
    if len(data) > rules.max_text_scan_bytes:  # the reader returned more than the declared size
        return [_not_scanned(f"more than the text scan limit of {rules.max_text_scan_bytes} bytes")]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [_not_scanned("not UTF-8 text")]
    return _text_findings(text, rules, kind)


def scan_bytes(
    name: str,
    head: bytes,
    read_all: Callable[[], bytes],
    size: int,
    rules: SafetyRules,
    kind: ContentKind,
    declared_media_type: str | None,
    detected_media_type: str,
) -> SafetyReport:
    """The CS-* rules over one byte object (§4.3); ``read_all`` is called only for text within the limit."""
    found: list[SafetyFinding] = []
    secret_name = _secret_name(name, rules)
    if secret_name is not None:
        found.append(secret_name)
    binary = b"\x00" in head[: rules.binary_probe_bytes]
    if binary:
        found.append(_finding("CS-BINARY", SafetyLevel.INFO, "binary content; text rules were not applied"))
    elif size > rules.max_text_scan_bytes:
        found.append(_not_scanned(f"{size} bytes exceed the text scan limit of {rules.max_text_scan_bytes}"))
    else:
        found.extend(_read_text_findings(read_all(), rules, kind))
    found.extend(_media_findings(declared_media_type, detected_media_type, rules))
    return SafetyReport(tuple(found), (), binary)


@dataclass(frozen=True, slots=True)
class Admit:
    """Admitted content: the final classification and the report with the acknowledged rules recorded.

    ``escalated_by`` names the rules that imposed a classification floor (evidence with block findings →
    ``restricted``; G21 warnings → at least ``internal``); the caller logs them.
    """

    classification: Classification
    report: SafetyReport
    escalated_by: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Reject:
    findings: tuple[SafetyFinding, ...]
    reason: str

    def error(self) -> ValidationFailed:
        return ValidationFailed(
            ErrorCode.CONTENT_UNSAFE,
            "the content failed the content-safety rules",
            details={"reason": self.reason, "findings": [finding.to_json() for finding in self.findings]},
        )


type Admission = Admit | Reject


def _rank_at_least(value: Classification, minimum: Classification) -> bool:
    return max_classification(value, minimum) == value


def decide_admission(
    report: SafetyReport,
    kind: ContentKind,
    classification: Classification,
    acknowledge: tuple[str, ...] | list[str],
    *,
    acknowledge_min_classification: Classification = Classification.CONFIDENTIAL,
) -> Admission:
    """The admission table of §4.3; an acknowledgement never lowers a classification nor covers evidence."""
    blocks = sorted({f.rule for f in report.findings if f.level == SafetyLevel.BLOCK})
    escalated: list[str] = []
    recorded = replace(report, acknowledged=())
    if blocks and kind is ContentKind.PORTABLE_DOCUMENT:
        return Reject(report.findings, "portable_document_blocked")
    if blocks and kind is ContentKind.EVIDENCE:
        classification = Classification.RESTRICTED
        escalated.extend(blocks)
    elif blocks:
        acked = set(acknowledge)
        if any(rule in _UNACKNOWLEDGEABLE or rule not in acked for rule in blocks):
            return Reject(report.findings, "not_acknowledged")
        if not _rank_at_least(classification, acknowledge_min_classification):
            return Reject(report.findings, "classification_below_acknowledge_minimum")
        recorded = replace(report, acknowledged=tuple(blocks))
    g21 = sorted({f.rule for f in report.findings if f.rule in _G21_RULES})
    if g21:
        classification = max_classification(classification, Classification.INTERNAL)
        escalated.extend(g21)
    return Admit(classification, recorded, tuple(escalated))
