"""``build_candidate``: domain values of a pack from its bytes, no IO (extensions §7.1 steps 2, 5, 6).

Everything is parsed as data: nothing in a payload is imported or executed. A file outside every layout, a
symlink the reader let through as a path, a manifest that its owner's schema refuses and a key that differs
from the layout all refuse the whole pack before persistence, independent of the order of the files.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING, Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.extensions.domain.compat import (
    DEFAULT_ALLOWED_LICENSES,
    KNOWN_TOOLS,
    PATTERNS,
    CompatCheck,
    CompatCheckId,
    CompatReport,
    CompatStatus,
    CompatVerdict,
    check_resource,
)
from skm.modules.extensions.domain.digest_rules import file_digest, pack_digest, resource_digest
from skm.modules.extensions.domain.keys import SemVer, parse_resource_key
from skm.modules.extensions.domain.kinds import (
    KIND_SPECS,
    MANIFEST_FILES,
    ResourceKind,
    is_root_file,
    locate,
    validate_layout,
)
from skm.modules.extensions.domain.pack import PackManifest, parse_pack_manifest
from skm.modules.extensions.domain.prompt_block import validate_prompt_block_variables
from skm.modules.extensions.domain.resource import ResourceFile
from skm.modules.extensions.domain.skill import parse_skill_frontmatter
from skm.platform.config.sources.document import decode_document
from skm.platform.schema.registry import SchemaRegistry

if TYPE_CHECKING:
    from skm.kernel.tokens import TokenEstimator
    from skm.modules.extensions.domain.payload import PackPayload

__all__ = [
    "DEFAULT_ALLOWED_LICENSES",
    "KNOWN_TOOLS",
    "PATTERNS",
    "PackCandidate",
    "ResourceCandidate",
    "build_candidate",
    "parse_text_resource",
    "schema_registry",
]

PACK_URN: Final = "urn:skm:extensions:pack:v1"
_UNSCANNED: Final = (
    CompatCheckId.LICENSE,
    CompatCheckId.PROVENANCE,
    CompatCheckId.INJECTION,
    CompatCheckId.BUDGET,
    CompatCheckId.TOOLS,
)
_NOT_SCANNED: Final = "not scanned"
_TOML_FENCE: Final = "+++"
_MEDIA_TYPES: Final = {
    "md": "text/markdown",
    "toml": "application/toml",
    "json": "application/json",
    "txt": "text/plain",
}


@dataclass(frozen=True, slots=True)
class ResourceCandidate:
    kind: ResourceKind
    key: str
    version: SemVer
    digest: str
    manifest: JsonObject
    files: tuple[ResourceFile, ...]
    bodies: Mapping[str, bytes]
    tokens_estimate: int
    compat: CompatReport

    @property
    def scanned(self) -> bool:
        """Every check of the report looked at the resource; its verdict means something only then."""
        return all(check.detail != _NOT_SCANNED for check in self.compat.checks)


@dataclass(frozen=True, slots=True)
class PackCandidate:
    manifest: PackManifest
    manifest_doc: JsonObject
    digest: str
    resources: tuple[ResourceCandidate, ...]


@cache
def schema_registry() -> SchemaRegistry:
    """The packaged schemas; loading them is slow and they never change in a process."""
    return SchemaRegistry.load_default()


def _invalid(reason: str, **details: JsonValue) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID, f"pack is invalid: {reason}", details={"reason": reason, **details}
    )


def _toml(text: str, path: str) -> JsonObject:
    """A manifest is JSON data: bad syntax or a value without a JSON form (a TOML date) refuses the pack."""
    try:
        return decode_document(text, "toml")
    except (TypeError, ValueError) as exc:
        raise _invalid("toml_invalid", path=path) from exc


def _text(body: bytes, path: str) -> str:
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _invalid("not_utf8", path=path) from exc


def parse_text_resource(text: str, path: str = "") -> tuple[JsonObject, str]:
    """``(meta, body)`` of a markdown resource: TOML between ``+++`` lines; without them ``({}, text)``."""
    lines = text.split("\n")
    if lines[0].strip() != _TOML_FENCE:
        return {}, text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == _TOML_FENCE:
            return _toml("\n".join(lines[1:index]), path), "\n".join(lines[index + 1 :])
    raise _invalid("front_matter_unterminated", path=path)


def _without_yaml_front_matter(text: str, *, key: str = "") -> str:
    """Validate and strip optional ``SKILL.md`` frontmatter (§4.2): only ``name`` and ``description``."""
    _, body = parse_skill_frontmatter(text, key=key)
    return body


def _manifest_and_body(
    kind: ResourceKind, files: Mapping[str, bytes], inner: str, *, key: str = ""
) -> tuple[JsonObject, str]:
    """The manifest document of a resource and the text its token estimate counts (``""``: none)."""
    if kind is ResourceKind.SKILL:
        manifest = _toml(_text(files[MANIFEST_FILES[kind]], MANIFEST_FILES[kind]), MANIFEST_FILES[kind])
        return manifest, _without_yaml_front_matter(_text(files["SKILL.md"], "SKILL.md"), key=key)
    if kind in MANIFEST_FILES:
        return _toml(_text(files[MANIFEST_FILES[kind]], MANIFEST_FILES[kind]), MANIFEST_FILES[kind]), ""
    text = _text(files[inner], inner)
    if kind in (ResourceKind.STEERING, ResourceKind.PROMPT_BLOCK):
        return parse_text_resource(text, inner)
    return _toml(text, inner), ""


def _require_schema(urn: str, document: JsonObject, *, kind: str, key: str) -> None:
    schemas = schema_registry()
    if urn not in schemas.urns():
        raise _invalid("unknown_schema", urn=urn, kind=kind, key=key)
    issues = schemas.validate(urn, document)
    if issues:
        raise _invalid(
            "manifest_invalid", urn=urn, kind=kind, key=key, issues=[str(issue) for issue in issues[:10]]
        )


def _media_type(path: str) -> str:
    return _MEDIA_TYPES.get(path.rpartition(".")[2], "application/octet-stream")


def _layout_report() -> CompatReport:
    """Only the layout is known when ``scan=False``: the report says what nobody looked at."""
    return CompatReport(
        (
            CompatCheck(CompatCheckId.LAYOUT, CompatStatus.OK, "layout and limits hold"),
            *(CompatCheck(check, CompatStatus.WARN, _NOT_SCANNED) for check in _UNSCANNED),
        ),
        CompatVerdict.CLEAN,
    )


@dataclass(frozen=True, slots=True)
class _CompatOptions:
    pack_license: str
    allowed_licenses: frozenset[str] = DEFAULT_ALLOWED_LICENSES
    max_skill_tokens: int = 8000
    max_steering_tokens: int = 2000
    extra_known_tools: frozenset[str] = frozenset()


def _compat_report(
    kind: ResourceKind,
    manifest: JsonObject,
    files: Mapping[str, bytes],
    tokens_estimate: int,
    options: _CompatOptions,
) -> CompatReport:
    """Deterministic compatibility checks (§4.10) for pack resources."""
    return check_resource(
        kind,
        manifest,
        files,
        tokens_estimate=tokens_estimate,
        pack_license=options.pack_license,
        allowed_licenses=options.allowed_licenses,
        max_skill_tokens=options.max_skill_tokens,
        max_steering_tokens=options.max_steering_tokens,
        extra_known_tools=options.extra_known_tools,
    )


def _resource(
    kind: ResourceKind,
    key: str,
    files: Mapping[str, bytes],
    *,
    pack_version: SemVer,
    estimator: TokenEstimator,
    scan: bool = True,
    options: _CompatOptions,
) -> ResourceCandidate:
    spec = KIND_SPECS[kind]
    parse_resource_key(key, prompt_block=kind is ResourceKind.PROMPT_BLOCK)
    violations = validate_layout(spec, files)
    if violations:
        raise _invalid(violations[0].reason, kind=kind.value, key=key, path=violations[0].path)
    inner = next(iter(sorted(files)))
    manifest, body = _manifest_and_body(kind, files, inner, key=key)
    if kind is not ResourceKind.PROMPT_BLOCK or manifest:  # the front matter of a prompt block is optional
        _require_schema(spec.manifest_urn, manifest, kind=kind.value, key=key)
    if kind is ResourceKind.PROMPT_BLOCK:
        validate_prompt_block_variables(manifest, body, key=key)
    declared = manifest.get("key")
    if declared is not None and declared != key:
        raise _invalid("key_mismatch", kind=kind.value, key=key, declared=cast("str", declared))
    version_text = manifest.get("version")
    tokens_estimate = estimator.estimate(body) if body else 0
    compat = _compat_report(kind, manifest, files, tokens_estimate, options) if scan else _layout_report()
    return ResourceCandidate(
        kind=kind,
        key=key,
        version=SemVer.parse(version_text) if isinstance(version_text, str) else pack_version,
        digest=resource_digest(files),
        manifest=manifest,
        files=tuple(
            ResourceFile(path, len(files[path]), file_digest(files[path]), _media_type(path))
            for path in sorted(files)
        ),
        bodies=dict(files),
        tokens_estimate=tokens_estimate,
        compat=compat,
    )


def _split_by_resource(payload: PackPayload) -> dict[tuple[ResourceKind, str], dict[str, bytes]]:
    grouped: dict[tuple[ResourceKind, str], dict[str, bytes]] = {}
    seen: set[str] = set()
    for item in payload.files:
        if item.path in seen:
            raise _invalid("duplicate_path", path=item.path)
        seen.add(item.path)
        if is_root_file(item.path):
            continue
        located = locate(item.path)
        if located is None:
            raise _invalid("unexpected_file", path=item.path)
        grouped.setdefault((located.kind, located.key), {})[located.inner] = item.content
    return grouped


def build_candidate(
    payload: PackPayload,
    *,
    estimator: TokenEstimator,
    scan: bool = True,
    allowed_licenses: frozenset[str] = DEFAULT_ALLOWED_LICENSES,
    max_skill_tokens: int = 8000,
    max_steering_tokens: int = 2000,
    extra_known_tools: frozenset[str] = frozenset(),
) -> PackCandidate:
    """§7.1 steps 2, 5 and 6: the pure part of an install, shared by ``install_pack`` and the builtin sync."""
    manifest_doc = _toml(payload.manifest_text, "pack.toml")
    _require_schema(PACK_URN, manifest_doc, kind="pack", key=str(manifest_doc.get("slug", "")))
    manifest = parse_pack_manifest(manifest_doc)
    options = _CompatOptions(
        pack_license=manifest.license,
        allowed_licenses=allowed_licenses,
        max_skill_tokens=max_skill_tokens,
        max_steering_tokens=max_steering_tokens,
        extra_known_tools=extra_known_tools,
    )
    resources = tuple(
        _resource(
            kind,
            key,
            files,
            pack_version=manifest.version,
            estimator=estimator,
            scan=scan,
            options=options,
        )
        for (kind, key), files in sorted(_split_by_resource(payload).items())
    )
    return PackCandidate(
        manifest=manifest,
        manifest_doc=manifest_doc,
        digest=pack_digest(
            manifest_doc,
            [(item.kind.value, item.key, str(item.version), item.digest) for item in resources],
        ),
        resources=resources,
    )
