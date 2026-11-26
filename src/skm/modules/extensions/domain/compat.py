"""Deterministic compatibility checks for pack resources (extensions §4.10)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final, cast

from skm.modules.extensions.domain.kinds import KIND_SPECS, ResourceKind, validate_layout

if TYPE_CHECKING:
    from skm.kernel.tokens import TokenEstimator

__all__ = [
    "DEFAULT_ALLOWED_LICENSES",
    "KNOWN_TOOLS",
    "PATTERNS",
    "CompatCheck",
    "CompatCheckId",
    "CompatReport",
    "CompatStatus",
    "CompatVerdict",
    "check_resource",
]

DEFAULT_ALLOWED_LICENSES: Final = frozenset(
    {
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "CC-BY-4.0",
        "CC0-1.0",
        "ISC",
        "MIT",
        "MPL-2.0",
        "Unlicense",
    }
)
KNOWN_TOOLS: Final = frozenset(
    {
        "Bash",
        "Edit",
        "Glob",
        "Grep",
        "MultiEdit",
        "NotebookEdit",
        "Read",
        "Skill",
        "Task",
        "Agent",
        "TodoWrite",
        "WebFetch",
        "WebSearch",
        "Write",
    }
)
_MAX_FILE_BYTES: Final = 1_000_000
_HEX64: Final = re.compile(r"^[0-9a-f]{64}$")
_SECRET: Final = (
    r"(?:(?:~|\$HOME|/home/[\w.-]+|/root)/\.(?:ssh|aws|gnupg|kube)\b|\bid_(?:rsa|ed25519)\b"
    r"|(?<![\w/.])\.env(?:\.\w+)?\b)"
)
_VERBS: Final = (
    r"(?:read|cat|print|show|dump|send|upload|post|copy|include|прочита\w*|выведи|отправ\w*|покажи)"
)
PATTERNS: Final[dict[str, tuple[re.Pattern[str], bool]]] = {
    "secret-read": (re.compile(rf"\b{_VERBS}\b.{{0,80}}?{_SECRET}", re.I | re.S), True),
    "disable-checks": (
        re.compile(
            r"--no-verify|--no-gpg-sign|--insecure\b|NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*0|"
            r"verify\s*=\s*False|(?:disable|turn off|отключи)\s+(?:the\s+)?(?:safety|security|sandbox|"
            r"ssl|tls|certificate|hooks?|проверк\w+)",
            re.I,
        ),
        True,
    ),
    "pipe-to-shell": (
        re.compile(r"\b(?:curl|wget)\b[^|\n]*\|\s*(?:sudo\s+)?(?:ba|z)?sh\b", re.I),
        False,
    ),
    "hide-actions": (
        re.compile(
            r"(?:do not|don't|never)\s+(?:tell|mention|inform|show|reveal)"
            r"[^.\n]{0,40}\b(?:user|human|owner)\b"
            r"|hide\s+(?:this|these|the)\b[^.\n]{0,30}\bfrom\b[^.\n]{0,20}\b(?:user|human)\b"
            r"|без ведома пользователя|не сообщай пользователю|скрой от пользователя",
            re.I,
        ),
        False,
    ),
    "prompt-injection": (
        re.compile(
            r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|rules)"
            r"|disregard\s+(?:the\s+)?(?:system|previous)\s+(?:prompt|instructions)"
            r"|игнорируй\s+(?:все\s+)?(?:предыдущие|прошлые)\s+(?:инструкции|правила)",
            re.I,
        ),
        False,
    ),
}
_NEGATION_BEFORE: Final = re.compile(
    r"(?:\bnever|\bdo not|\bdon't|\bmust not|\bavoid|\bне|\bнельзя)\s+(?:\w+\s+){0,2}$",  # noqa: RUF001
    re.I,
)


class CompatCheckId(StrEnum):
    LICENSE = "license"
    PROVENANCE = "provenance"
    INJECTION = "injection"
    BUDGET = "budget"
    TOOLS = "tools"
    LAYOUT = "layout"


class CompatStatus(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


class CompatVerdict(StrEnum):
    CLEAN = "clean"
    QUARANTINE = "quarantine"


@dataclass(frozen=True, slots=True)
class CompatCheck:
    id: CompatCheckId
    status: CompatStatus
    detail: str


@dataclass(frozen=True, slots=True)
class CompatReport:
    checks: tuple[CompatCheck, ...]
    verdict: CompatVerdict


def _check_license(
    kind: ResourceKind,
    manifest: Mapping[str, object],
    *,
    pack_license: str,
    allowed_licenses: frozenset[str],
) -> CompatCheck:
    lic = str(manifest.get("license") or pack_license).strip()
    if lic in allowed_licenses:
        return CompatCheck(CompatCheckId.LICENSE, CompatStatus.OK, lic)
    if lic.startswith("N/A") and kind is ResourceKind.SKILL and manifest.get("kind") == "reference":
        return CompatCheck(CompatCheckId.LICENSE, CompatStatus.WARN, f"no vendored code: {lic}")
    return CompatCheck(CompatCheckId.LICENSE, CompatStatus.FAIL, f"{lic} is not in allowed_licenses")


def _as_dict(val: object) -> Mapping[str, object] | None:
    return cast("Mapping[str, object]", val) if isinstance(val, Mapping) else None


def _as_list(val: object) -> Sequence[object] | None:
    return cast("Sequence[object]", val) if isinstance(val, list) else None


def _check_provenance(manifest: Mapping[str, object]) -> CompatCheck:
    prov = _as_dict(manifest.get("provenance"))
    if prov is None or prov.get("source", "local") != "upstream":
        return CompatCheck(CompatCheckId.PROVENANCE, CompatStatus.OK, "local provenance")
    anchor = prov.get("upstream_sha")
    if not isinstance(anchor, str) or not _HEX64.match(anchor):
        return CompatCheck(
            CompatCheckId.PROVENANCE, CompatStatus.FAIL, "upstream_sha is missing or not a sha256 hex"
        )
    files = _as_list(prov.get("files"))
    if files is None or not files:
        return CompatCheck(CompatCheckId.PROVENANCE, CompatStatus.FAIL, "files[] is empty")
    shas: set[str] = set()
    for raw_row in files:
        row = _as_dict(raw_row)
        if row is None:
            return CompatCheck(CompatCheckId.PROVENANCE, CompatStatus.FAIL, "files[] entry is not a table")
        url, sha = row.get("url"), row.get("sha256")
        if not isinstance(url, str) or not url or not isinstance(sha, str) or not _HEX64.match(sha):
            return CompatCheck(
                CompatCheckId.PROVENANCE, CompatStatus.FAIL, "files[] entry without url or sha256"
            )
        shas.add(sha)
    return CompatCheck(CompatCheckId.PROVENANCE, CompatStatus.OK, "verified" if anchor in shas else "anchor")


def _scan_text(text: str, name: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for pid, (pattern, negatable) in PATTERNS.items():
        for match in pattern.finditer(text):
            line_start = text.rfind("\n", 0, match.start()) + 1
            if negatable and _NEGATION_BEFORE.search(text[line_start : match.start()]):
                continue
            line_no = text.count("\n", 0, match.start()) + 1
            snippet = " ".join(match.group(0).split())[:80]
            found[pid] = f"{name} line {line_no}: {snippet}"
            break
    return found


def _accepted_waivers(manifest: Mapping[str, object]) -> dict[tuple[str, str], str]:
    prov = _as_dict(manifest.get("provenance"))
    if prov is None or prov.get("source") != "upstream":
        return {}
    raw_accepted = _as_list(manifest.get("compat_accepted"))
    if raw_accepted is None:
        return {}
    accepted: dict[tuple[str, str], str] = {}
    for raw_row in raw_accepted:
        row = _as_dict(raw_row)
        if row is None:
            continue
        file_name, reason, checks = row.get("file"), row.get("reason"), _as_list(row.get("checks"))
        if isinstance(file_name, str) and isinstance(reason, str) and reason and checks is not None:
            for pid in checks:
                if isinstance(pid, str):
                    accepted[(file_name, pid)] = reason
    return accepted


def _check_injection(
    kind: ResourceKind, manifest: Mapping[str, object], files: Mapping[str, bytes]
) -> CompatCheck:
    if not KIND_SPECS[kind].text_scan:
        return CompatCheck(CompatCheckId.INJECTION, CompatStatus.OK, "text scan not applicable")
    accepted = _accepted_waivers(manifest)
    hits: dict[str, str] = {}
    waived: list[str] = []
    for path in sorted(files):
        body = files[path]
        if path.rpartition(".")[2] not in ("md", "txt", "toml") or len(body) > _MAX_FILE_BYTES:
            continue
        try:
            content = body.decode("utf-8-sig")
        except UnicodeDecodeError:
            continue
        for pid, where in _scan_text(content, path).items():
            if (path, pid) in accepted:
                waived.append(f"{pid} in {path}: {accepted[(path, pid)]}")
            else:
                hits.setdefault(pid, where)
    if hits:
        detail = "; ".join(f"{pid} ({where})" for pid, where in sorted(hits.items()))
        return CompatCheck(CompatCheckId.INJECTION, CompatStatus.FAIL, detail)
    if waived:
        return CompatCheck(
            CompatCheckId.INJECTION, CompatStatus.WARN, "accepted by compat_accepted: " + "; ".join(waived)
        )
    return CompatCheck(CompatCheckId.INJECTION, CompatStatus.OK, "no dangerous-instruction pattern")


def _check_budget(
    kind: ResourceKind,
    manifest: Mapping[str, object],
    tokens_estimate: int,
    *,
    max_skill_tokens: int,
    max_steering_tokens: int,
) -> CompatCheck:
    if kind is ResourceKind.SKILL:
        raw = manifest.get("max_tokens")
        limit = raw if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0 else max_skill_tokens
        status = CompatStatus.FAIL if tokens_estimate > limit else CompatStatus.OK
        return CompatCheck(CompatCheckId.BUDGET, status, f"{tokens_estimate} tokens of {limit}")
    if kind is ResourceKind.STEERING:
        limit = max_steering_tokens
        status = CompatStatus.FAIL if tokens_estimate > limit else CompatStatus.OK
        return CompatCheck(CompatCheckId.BUDGET, status, f"{tokens_estimate} tokens of {limit}")
    return CompatCheck(CompatCheckId.BUDGET, CompatStatus.OK, "no token budget limit")


def _check_tools(kind: ResourceKind, manifest: Mapping[str, object], *, known: frozenset[str]) -> CompatCheck:
    tools: list[str] = []
    if kind is ResourceKind.SKILL:
        raw = _as_list(manifest.get("requires_tools"))
        if raw is not None:
            tools = [str(item) for item in raw]
    elif kind is ResourceKind.AGENT_PROFILE:
        perms = _as_dict(manifest.get("permissions"))
        layer = _as_dict(perms.get("layer")) if perms is not None else None
        raw = _as_list(layer.get("tools")) if layer is not None else None
        if raw is not None:
            tools = [str(item) for item in raw]
    unknown = sorted({t for t in tools if t.split("(")[0] not in known and not t.startswith("mcp__")})
    if unknown:
        return CompatCheck(CompatCheckId.TOOLS, CompatStatus.WARN, "unknown tools: " + ", ".join(unknown))
    return CompatCheck(CompatCheckId.TOOLS, CompatStatus.OK, f"{len(tools)} tools, all known")


def _estimate_from_files(
    kind: ResourceKind, files: Mapping[str, bytes], estimator: TokenEstimator | None
) -> int:
    if estimator is None:
        return 0
    if kind is ResourceKind.SKILL and "SKILL.md" in files:
        text = files["SKILL.md"].decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
        lines = text.split("\n")
        if lines[0].strip() == "---":
            for idx, line in enumerate(lines[1:], start=1):
                if line.strip() == "---":
                    text = "\n".join(lines[idx + 1 :])
                    break
        return estimator.estimate(text)
    if kind in (ResourceKind.STEERING, ResourceKind.PROMPT_BLOCK) and files:
        inner = next(iter(sorted(files)))
        text = files[inner].decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
        lines = text.split("\n")
        if lines[0].strip() == "+++":
            for idx, line in enumerate(lines[1:], start=1):
                if line.strip() == "+++":
                    text = "\n".join(lines[idx + 1 :])
                    break
        return estimator.estimate(text)
    return 0


def check_resource(  # noqa: PLR0913
    kind: ResourceKind,
    manifest: Mapping[str, object],
    files: Mapping[str, bytes],
    *,
    pack_license: str = "Apache-2.0",
    allowed_licenses: frozenset[str] = DEFAULT_ALLOWED_LICENSES,
    estimator: TokenEstimator | None = None,
    tokens_estimate: int | None = None,
    max_tokens: int | None = None,
    max_skill_tokens: int | None = None,
    max_steering_tokens: int | None = None,
    known_tools: frozenset[str] = KNOWN_TOOLS,
    extra_known_tools: frozenset[str] = frozenset(),
    layout_ok: bool = True,
) -> CompatReport:
    """Run deterministic compatibility checks (§4.10) on a single pack resource."""
    effective_tokens = (
        tokens_estimate if tokens_estimate is not None else _estimate_from_files(kind, files, estimator)
    )
    effective_skill_limit = (
        max_skill_tokens if max_skill_tokens is not None else (max_tokens if max_tokens is not None else 8000)
    )
    effective_steering_limit = (
        max_steering_tokens
        if max_steering_tokens is not None
        else (max_tokens if max_tokens is not None else 2000)
    )
    effective_known_tools = known_tools | extra_known_tools
    violations = validate_layout(KIND_SPECS[kind], files)
    if violations:
        layout_check = CompatCheck(
            CompatCheckId.LAYOUT,
            CompatStatus.FAIL,
            f"layout invalid: {violations[0].reason} ({violations[0].path})",
        )
    elif not layout_ok:
        layout_check = CompatCheck(
            CompatCheckId.LAYOUT,
            CompatStatus.FAIL,
            "layout or limit check failed",
        )
    else:
        layout_check = CompatCheck(
            CompatCheckId.LAYOUT,
            CompatStatus.OK,
            "layout and limits hold",
        )
    checks = (
        _check_license(
            kind,
            manifest,
            pack_license=pack_license,
            allowed_licenses=allowed_licenses,
        ),
        _check_provenance(manifest),
        _check_injection(kind, manifest, files),
        _check_budget(
            kind,
            manifest,
            effective_tokens,
            max_skill_tokens=effective_skill_limit,
            max_steering_tokens=effective_steering_limit,
        ),
        _check_tools(kind, manifest, known=effective_known_tools),
        layout_check,
    )
    verdict = (
        CompatVerdict.QUARANTINE
        if any(check.status is CompatStatus.FAIL for check in checks)
        else CompatVerdict.CLEAN
    )
    return CompatReport(checks, verdict)
