"""Resource kinds and their layouts in a pack (extensions §4.2).

``locate`` maps a pack-relative path to its resource; ``validate_layout`` checks the files of one resource
against the layout and the limits of its kind. A file the digest skips is refused in every kind: stored, it
would be bytes no digest describes. Policy profiles are data of ``policy``, never a kind of resource
(D-REG-7).
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from skm.modules.extensions.domain.digest_rules import is_excluded

if TYPE_CHECKING:
    from typing import Literal

__all__ = [
    "KIND_SPECS",
    "MANIFEST_FILES",
    "RESOURCE_KINDS",
    "ROOT_FILES",
    "KindSpec",
    "LayoutViolation",
    "Located",
    "ResourceKind",
    "is_root_file",
    "locate",
    "validate_layout",
]


class ResourceKind(StrEnum):
    SKILL = "skill"
    STEERING = "steering"
    AGENT_PROFILE = "agent_profile"
    WORKFLOW = "workflow"
    PLAN_TEMPLATE = "plan_template"
    PROMPT_BLOCK = "prompt_block"
    INTEGRATION_BUNDLE = "integration_bundle"
    RUNTIME_CATALOG = "runtime_catalog"
    MODEL_GUIDELINE = "model_guideline"


@dataclass(frozen=True, slots=True)
class KindSpec:
    kind: ResourceKind
    layout: str
    manifest_urn: str
    key_from: Literal["dir", "file_stem", "role_and_stem", "fixed"]
    main_file: str | None
    max_files: int
    max_file_bytes: int
    max_total_bytes: int
    text_scan: bool


RESOURCE_KINDS = (
    KindSpec(
        ResourceKind.SKILL,
        "skills/<key>/",
        "urn:skm:extensions:skill-manifest:v1",
        "dir",
        "SKILL.md",
        200,
        1048576,
        8388608,
        True,
    ),
    KindSpec(
        ResourceKind.STEERING,
        "steering/<key>.md",
        "urn:skm:extensions:steering:v1",
        "file_stem",
        None,
        1,
        262144,
        262144,
        True,
    ),
    KindSpec(
        ResourceKind.AGENT_PROFILE,
        "agent-profiles/<key>.toml",
        "urn:skm:extensions:agent-profile:v1",
        "file_stem",
        None,
        1,
        65536,
        65536,
        True,
    ),
    KindSpec(
        ResourceKind.WORKFLOW,
        "workflows/<key>.toml",
        "urn:skm:execution:workflow:v1",
        "file_stem",
        None,
        1,
        65536,
        65536,
        False,
    ),
    KindSpec(
        ResourceKind.PLAN_TEMPLATE,
        "plan-templates/<key>/",
        "urn:skm:extensions:plan-template:v1",
        "dir",
        None,
        20,
        1048576,
        4194304,
        False,
    ),
    KindSpec(
        ResourceKind.PROMPT_BLOCK,
        "prompts/<role>/<name>.md",
        "urn:skm:extensions:prompt-block:v1",
        "role_and_stem",
        None,
        1,
        131072,
        131072,
        True,
    ),
    KindSpec(
        ResourceKind.INTEGRATION_BUNDLE,
        "integration-bundles/<key>/",
        "urn:skm:integrations:bundle:v1",
        "dir",
        None,
        500,
        1048576,
        16777216,
        False,
    ),
    KindSpec(
        ResourceKind.RUNTIME_CATALOG,
        "runtimes/<key>.toml",
        "urn:skm:runtimes:model-catalog:v1",
        "file_stem",
        None,
        1,
        524288,
        524288,
        False,
    ),
    KindSpec(
        ResourceKind.MODEL_GUIDELINE,
        "model-guidelines/<key>.toml",
        "urn:skm:runtimes:model-guideline:v1",
        "file_stem",
        None,
        1,
        65536,
        65536,
        False,
    ),
)

KIND_SPECS: Final[Mapping[ResourceKind, KindSpec]] = {spec.kind: spec for spec in RESOURCE_KINDS}
# Directory kinds keep their manifest in one file of the resource; the others are the manifest or front it.
MANIFEST_FILES: Final[Mapping[ResourceKind, str]] = {
    ResourceKind.SKILL: "manifest.toml",
    ResourceKind.PLAN_TEMPLATE: "manifest.toml",
    ResourceKind.INTEGRATION_BUNDLE: "bundle.toml",
}
ROOT_FILES: Final = ("pack.toml", "README.md", "LICENSE*", "CHANGELOG.md")
# What §4.2 lists inside a directory kind; an integration bundle holds any files besides ``bundle.toml``.
_LAYOUT_FILES: Final[Mapping[ResourceKind, frozenset[str]]] = {
    ResourceKind.SKILL: frozenset({"SKILL.md", "manifest.toml"}),
    ResourceKind.PLAN_TEMPLATE: frozenset({"manifest.toml", "template.json"}),
}
_LAYOUT_DIRECTORIES: Final[Mapping[ResourceKind, frozenset[str]]] = {
    ResourceKind.SKILL: frozenset({"references", "snippets", "examples"}),
}

_DIRECTORY: Final = re.compile(
    r"(?P<root>skills|plan-templates|integration-bundles)/(?P<key>[^/]+)/(?P<inner>.+)"
)
_SINGLE: Final = re.compile(
    r"(?P<root>steering|agent-profiles|workflows|runtimes|model-guidelines)/(?P<key>[^/]+)\.(?P<ext>md|toml)"
)
_PROMPT: Final = re.compile(r"prompts/(?P<role>[^/]+)/(?P<name>[^/]+)\.md")
_DIRECTORY_KINDS: Final = {
    "skills": ResourceKind.SKILL,
    "plan-templates": ResourceKind.PLAN_TEMPLATE,
    "integration-bundles": ResourceKind.INTEGRATION_BUNDLE,
}
_SINGLE_KINDS: Final = {
    ("steering", "md"): ResourceKind.STEERING,
    ("agent-profiles", "toml"): ResourceKind.AGENT_PROFILE,
    ("workflows", "toml"): ResourceKind.WORKFLOW,
    ("runtimes", "toml"): ResourceKind.RUNTIME_CATALOG,
    ("model-guidelines", "toml"): ResourceKind.MODEL_GUIDELINE,
}


@dataclass(frozen=True, slots=True)
class Located:
    kind: ResourceKind
    key: str
    inner: str  # POSIX path relative to the resource (the digest covers this path, not the pack path)


@dataclass(frozen=True, slots=True)
class LayoutViolation:
    reason: str
    path: str = ""


def is_root_file(path: str) -> bool:
    return "/" not in path and any(fnmatch.fnmatchcase(path, pattern) for pattern in ROOT_FILES)


def locate(path: str) -> Located | None:
    """The resource a pack-relative path belongs to; ``None``: it is outside every layout."""
    found = _PROMPT.fullmatch(path)
    if found is not None:
        return Located(ResourceKind.PROMPT_BLOCK, f"{found['role']}/{found['name']}", f"{found['name']}.md")
    found = _DIRECTORY.fullmatch(path)
    if found is not None:
        return Located(_DIRECTORY_KINDS[found["root"]], found["key"], found["inner"])
    found = _SINGLE.fullmatch(path)
    if found is not None:
        kind = _SINGLE_KINDS.get((found["root"], found["ext"]))
        if kind is not None:
            return Located(kind, found["key"], f"{found['key']}.{found['ext']}")
    return None


def _in_layout(kind: ResourceKind, path: str) -> bool:
    if is_excluded(path):
        return False
    listed = _LAYOUT_FILES.get(kind)
    if listed is None:
        return True
    head, separator, _ = path.partition("/")
    return head in _LAYOUT_DIRECTORIES.get(kind, ()) if separator else path in listed


def validate_layout(kind_spec: KindSpec, files: Mapping[str, bytes]) -> tuple[LayoutViolation, ...]:
    """Everything wrong with the files of one resource against the limits of its kind; ``()``: nothing."""
    found: list[LayoutViolation] = []
    if len(files) > kind_spec.max_files:
        found.append(LayoutViolation("too_many_files"))
    found.extend(
        LayoutViolation("file_too_large", path)
        for path, body in sorted(files.items())
        if len(body) > kind_spec.max_file_bytes
    )
    if sum(len(body) for body in files.values()) > kind_spec.max_total_bytes:
        found.append(LayoutViolation("resource_too_large"))
    required = MANIFEST_FILES.get(kind_spec.kind)
    if required is not None and required not in files:
        found.append(LayoutViolation("manifest_missing", required))
    if kind_spec.main_file is not None and kind_spec.main_file not in files:
        found.append(LayoutViolation("main_file_missing", kind_spec.main_file))
    found.extend(
        LayoutViolation("unexpected_file", path)
        for path in sorted(files)
        if not _in_layout(kind_spec.kind, path)
    )
    return tuple(found)
