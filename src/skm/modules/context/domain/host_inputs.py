"""Pure host-input planning and immutable host read evidence (context §§4.2, 5.1)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, cast

from skm.kernel.json_types import JsonObject
from skm.modules.context.domain.blocks import BlockType, TrustLevel
from skm.modules.context.domain.carriers import instruction_carrier_dirs
from skm.modules.context.domain.research import ResearchQuerySpec

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from typing import Literal

    from skm.modules.context.domain.contracts import Digest
    from skm.modules.context.domain.policy import ContextPolicy


class HostInputKind(StrEnum):
    REPO_INSTRUCTIONS = "repo_instructions"
    REPOSITORY_PATH = "repository_path"
    DEPENDENCY_MANIFEST = "dependency_manifest"
    RESEARCH_QUERY = "research_query"


class HostReadStatus(StrEnum):
    OK = "ok"
    MISSING = "missing"
    TOO_LARGE = "too_large"
    BINARY = "binary"
    PATH_INVALID = "path_invalid"
    SYMLINK_OUTSIDE = "symlink_outside"
    SYMLINK_REFUSED = "symlink_refused"
    NO_MATCHING_SECTIONS = "no_matching_sections"
    BUDGET_EXCEEDED = "budget_exceeded"
    OVER_MAX_FILES = "over_max_files"
    SELF_LOADED = "self_loaded"


@dataclass(frozen=True, slots=True)
class HostSelector:
    kind: Literal["whole", "markdown_sections", "markdown_heading", "line_range"]
    sections: tuple[str, ...] = ()
    heading: str | None = None
    line_from: int | None = None
    line_to: int | None = None


@dataclass(frozen=True, slots=True)
class HostInputRequest:
    request_id: str
    kind: HostInputKind
    mount: str
    path: str
    alternatives: tuple[str, ...]
    selector: HostSelector
    max_bytes: int
    required: bool
    block_type: BlockType | None
    trust: TrustLevel
    source_ref: str
    follow_symlinks: bool
    skip_if_resolved_in: tuple[str, ...]
    research: ResearchQuerySpec | None


@dataclass(frozen=True, slots=True)
class HostBlock:
    request_id: str
    status: HostReadStatus
    resolved_path: str | None
    text: str | None
    text_digest: Digest | None
    size_bytes: int | None
    tokens_estimate: int | None
    research_query_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HostBlockMeta:
    request_id: str
    status: HostReadStatus
    resolved_path: str | None
    text_digest: Digest | None
    size_bytes: int | None
    tokens_estimate: int | None
    research_query_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HostFacts:
    deps: frozenset[str]
    work_paths: tuple[tuple[str, str], ...]
    work_paths_truncated: bool
    baseline: Mapping[str, str]


def plan_host_inputs(
    entity_paths: Sequence[tuple[str, str]],
    materials: Sequence[JsonObject],
    policy: ContextPolicy,
    settings: JsonObject,
) -> tuple[HostInputRequest, ...]:
    """Settings may carry already-routed runtime metadata; never discover user-global inputs."""
    out: list[HostInputRequest] = []
    seen: set[tuple[str, str, HostSelector]] = set()
    host = _object(settings.get("host_inputs"))
    file_max = int(cast("int", host.get("file_max_bytes", 262144)))
    runtime = _object(settings.get("runtime"))
    primary = str(runtime.get("primary_mount", entity_paths[0][0] if entity_paths else "repo"))
    self_loaded = tuple(str(name) for name in _array(runtime.get("self_loaded_instruction_files")))

    def add(
        kind: HostInputKind,
        mount: str,
        path: str,
        selector: HostSelector,
        *,
        max_bytes: int = file_max,
        required: bool = False,
        alternatives: tuple[str, ...] = (),
        research: ResearchQuerySpec | None = None,
    ) -> None:
        key = (mount, path, selector)
        if key in seen:
            return
        seen.add(key)
        source = "research:" + path if research else f"repo:{mount}/{path}#{selector_ref(selector)}"
        out.append(
            HostInputRequest(
                f"hi:{len(out)}",
                kind,
                mount,
                path,
                alternatives,
                selector,
                max_bytes,
                required,
                {
                    HostInputKind.REPO_INSTRUCTIONS: BlockType.REPO_INSTRUCTIONS,
                    HostInputKind.REPOSITORY_PATH: BlockType.MATERIALS,
                    HostInputKind.RESEARCH_QUERY: BlockType.RESEARCH,
                }.get(kind),
                TrustLevel.EXTERNAL if research else TrustLevel.REPOSITORY,
                source,
                kind is HostInputKind.REPOSITORY_PATH,
                self_loaded
                if kind is HostInputKind.REPO_INSTRUCTIONS and mount == primary and not path
                else (),
                research,
            )
        )

    if policy.repo_mode != "none" and BlockType.REPO_INSTRUCTIONS in policy.include:
        selector = (
            HostSelector("markdown_sections", policy.repo_sections)
            if policy.repo_mode == "constraints"
            else HostSelector("whole")
        )
        for mount, directory in instruction_carrier_dirs(entity_paths):
            add(
                HostInputKind.REPO_INSTRUCTIONS,
                mount,
                directory + "/" if directory else "",
                selector,
                max_bytes=policy.repo_max_bytes,
                alternatives=policy.repo_files,
            )
    for material in materials:
        if material.get("kind") != "repository_path" or BlockType.MATERIALS not in policy.include:
            continue
        required = bool(material.get("required", False))
        if not required and not policy.include_optional_materials:
            continue
        selector = selector_from_json(_object(material.get("selector")))
        mount, path = str(material.get("mount", primary)), str(material.get("path", ""))
        for index, old in enumerate(out):
            if (
                (old.mount, old.path, old.selector) == (mount, path, selector)
                and required
                and not old.required
            ):
                out[index] = replace(old, required=True)
        add(HostInputKind.REPOSITORY_PATH, mount, path, selector, required=required)
    if policy.skills_mode == "auto":
        for mount in sorted({mount for mount, _ in entity_paths}):
            for name in ("pyproject.toml", "package.json", "composer.json"):
                add(HostInputKind.DEPENDENCY_MANIFEST, mount, name, HostSelector("whole"))
    if BlockType.RESEARCH in policy.include:
        for value in _array(settings.get("research_queries")):
            raw = _object(value)
            text = str(raw.get("text", "")).strip()
            if not text:
                continue
            query = ResearchQuerySpec(
                text,
                tuple(str(v) for v in _array(raw.get("sources"))),
                "deep" if raw.get("depth") == "deep" else "standard",
                int(cast("int", raw.get("max_documents", 10))),
                bool(raw.get("use_cache", True)),
                bool(raw.get("save_as_material", False)),
            )
            digest = "sha256:" + sha256(text.encode("utf-8")).hexdigest()
            add(
                HostInputKind.RESEARCH_QUERY,
                "",
                digest,
                HostSelector("whole"),
                max_bytes=int(cast("int", host.get("max_bytes", 2097152))),
                research=query,
            )
    return tuple(out)


def _object(value: object) -> JsonObject:
    return cast("JsonObject", value) if isinstance(value, dict) else {}


def _array(value: object) -> list[object]:
    return cast("list[object]", value) if isinstance(value, list) else []


def selector_from_json(raw: JsonObject) -> HostSelector:
    kind = str(raw.get("kind", "whole"))
    if kind not in {"whole", "markdown_sections", "markdown_heading", "line_range"}:
        raise ValueError("unsupported host selector")
    return HostSelector(
        cast('Literal["whole", "markdown_sections", "markdown_heading", "line_range"]', kind),
        tuple(str(s) for s in _array(raw.get("sections"))),
        str(raw["heading"]) if raw.get("heading") is not None else None,
        int(cast("int", raw["line_from"])) if raw.get("line_from") is not None else None,
        int(cast("int", raw["line_to"])) if raw.get("line_to") is not None else None,
    )


def selector_ref(selector: HostSelector) -> str:
    if selector.kind == "markdown_sections":
        return "markdown-sections=" + "|".join(selector.sections)
    if selector.kind == "markdown_heading":
        return "markdown-heading=" + (selector.heading or "")
    if selector.kind == "line_range":
        return f"line-range={selector.line_from}-{selector.line_to}"
    return "whole"
