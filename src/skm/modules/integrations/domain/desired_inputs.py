"""Pure domain assembly helpers for ``ProjectionInputs`` (integrations §4.11, §5.1)."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.outcomes import Diagnostic as KernelDiagnostic
from skm.kernel.outcomes import Severity
from skm.modules.integrations.domain.bundle import (
    IntegrationBundleManifest,
    normalize_desired_json,
    normalize_desired_map,
    resolve_bundle_asset_path,
)
from skm.modules.integrations.domain.hook_events import HookClass, HookEventKind
from skm.modules.integrations.domain.hook_subscriptions import (
    ExecutionLocation,
    parse_subscriptions,
    validate_subscription,
)
from skm.modules.integrations.domain.ownership import Ownership, sha256_tagged
from skm.modules.integrations.domain.target import TargetId

__all__ = [
    "BundleTargetAccumulator",
    "build_agent_doc",
    "build_core_instruction_block",
    "build_project_instruction_block",
    "collect_host_subscription_events",
    "empty_instruction_block",
    "encode_inputs_digest_bytes",
    "extract_bundle_source_bytes",
    "format_diagnostic",
    "skill_matches_target",
    "skill_requires",
    "steering_matches_project",
    "steering_priority",
    "tool_admits",
]

_HOOK_CLASS_ORDER: Final[tuple[HookClass, ...]] = (
    HookClass.ENFORCEMENT,
    HookClass.WORKFLOW,
    HookClass.OBSERVATION,
)
_AGENT_FILE_FMT: Final[Mapping[TargetId, str]] = {
    TargetId.CLAUDE_CODE: ".claude/agents/{name}.md",
    TargetId.CODEX: ".codex/agents/{name}.toml",
    TargetId.CURSOR: ".cursor/agents/{name}.md",
}


def build_agent_doc(
    prof: Any,
    *,
    name: str,
    digest: str,
    bundle_meta: tuple[str, str, str] | None = None,
) -> JsonObject:
    doc: dict[str, object] = {
        "key": prof.key,
        "name": name,
        "version": str(prof.version),
        "role": prof.role,
        "title": prof.title,
        "description": prof.description,
        "model_class": prof.model_class,
        "effort": prof.effort,
        "digest": digest,
    }
    if bundle_meta is not None:
        doc["bundle_key"], doc["bundle_version"], doc["bundle_digest"] = bundle_meta
    return normalize_desired_map(doc)


def format_diagnostic(diag: KernelDiagnostic) -> JsonObject:
    return {
        "code": str(diag.code),
        "severity": str(diag.severity.value),
        "message": str(diag.message),
        "target": None if diag.target is None else str(diag.target),
        "details": normalize_desired_json(dict(diag.details) if diag.details else {}),
    }


def tool_admits(pat: str, tool: str) -> bool:
    if pat.startswith("mcp:") and pat.endswith("*"):
        return tool.startswith("mcp:") if pat == "mcp:*" else tool.startswith(pat[:-1])
    return pat == tool


def empty_instruction_block(*, enabled: bool) -> JsonObject:
    return {"enabled": enabled, "content": "", "sections": [], "digest": sha256_tagged(b"")}


def build_core_instruction_block(*, key: str, version: str, digest: str, body: str) -> JsonObject:
    ctext = body.strip()
    return {
        "enabled": True,
        "key": key,
        "version": version,
        "resource_digest": digest,
        "content": ctext,
        "sections": [{"key": key, "version": version, "digest": digest, "body": body}],
        "digest": sha256_tagged(ctext.encode("utf-8")),
    }


def build_project_instruction_block(
    sections_in: Sequence[tuple[str, str, int, str, str]],
    *,
    project_text: str,
) -> JsonObject:
    sections: list[JsonValue] = []
    parts: list[str] = []
    for key, version, priority, digest, body in sections_in:
        sections.append(
            {"key": key, "version": version, "priority": priority, "digest": digest, "body": body}
        )
        if body.strip():
            parts.append(body.strip())
    if project_text.strip():
        parts.append(project_text.strip())
    pcontent = "\n\n".join(parts)
    return {
        "enabled": True,
        "content": pcontent,
        "project_text": project_text,
        "sections": sections,
        "digest": sha256_tagged(pcontent.encode("utf-8")),
    }


def steering_priority(manifest: Mapping[str, Any]) -> int:
    raw = manifest.get("priority", 0)
    return raw if isinstance(raw, int) and not isinstance(raw, bool) else 0


def steering_matches_project(manifest: Mapping[str, Any], project_slug: str) -> bool:
    raw_scope = manifest.get("scope")
    if not isinstance(raw_scope, Mapping):
        return True
    scope_map = cast("Mapping[str, object]", raw_scope)
    if scope_map.get("global") is True:
        return True
    raw_projects = scope_map.get("projects")
    if (
        isinstance(raw_projects, Sequence)
        and not isinstance(raw_projects, (str, bytes))
        and raw_projects
        and project_slug not in {str(item) for item in cast("Sequence[object]", raw_projects)}
    ):
        return False
    return not any(
        isinstance(scope_map.get(dim), Sequence)
        and not isinstance(scope_map.get(dim), (str, bytes))
        and bool(scope_map.get(dim))
        for dim in ("directories", "languages", "task_types", "risk")
    )


def skill_matches_target(manifest: Mapping[str, Any], target: TargetId) -> bool:
    adapters = manifest.get("adapters")
    if isinstance(adapters, Sequence) and not isinstance(adapters, (str, bytes)) and adapters:
        return target.value in {str(a) for a in cast("Sequence[object]", adapters)}
    return True


def skill_requires(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    raw_req = manifest.get("requires")
    if isinstance(raw_req, Sequence) and not isinstance(raw_req, (str, bytes)):
        return tuple(str(req) for req in cast("Sequence[object]", raw_req))
    return ()


def extract_bundle_source_bytes(
    bodies: Mapping[str, str] | None,
    file_metas: Sequence[tuple[str, int, str]],
    *,
    source: str,
    bundle_key: str,
) -> bytes:
    body_map = bodies or {}
    if source not in body_map:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"bundle {bundle_key!r} is missing referenced asset source {source!r}",
            details={"bundle": bundle_key, "source": source},
        )
    text_or_b64 = body_map[source]
    utf8_bytes = text_or_b64.encode("utf-8")
    for path, size_bytes, fdigest in file_metas:
        if path == source:
            if len(utf8_bytes) == size_bytes and sha256_tagged(utf8_bytes) == fdigest:
                return utf8_bytes
            return base64.b64decode(text_or_b64)
    return utf8_bytes


@dataclass
class BundleTargetAccumulator:
    """Tracks bundle target support, agent name collisions, and asset path collisions."""

    target: TargetId
    pack_prefix: str
    seen_agents: set[str] = field(default_factory=set[str])
    occupied_files: set[str] = field(default_factory=set[str])
    occupied_blocks: set[tuple[str, str]] = field(default_factory=set[tuple[str, str]])
    agents: list[JsonObject] = field(default_factory=list[JsonObject])
    assets: list[tuple[str, str, str, JsonObject]] = field(
        default_factory=list[tuple[str, str, str, JsonObject]]
    )

    def check_target_supported(
        self,
        manifest: IntegrationBundleManifest,
        diagnostics: list[KernelDiagnostic],
    ) -> bool:
        if self.target not in manifest.targets:
            diagnostics.append(
                KernelDiagnostic(
                    code=ErrorCode.CAPABILITY_UNAVAILABLE.value,
                    message=f"bundle {manifest.key!r} does not support target {self.target.value!r}",
                    severity=Severity.WARNING,
                    target=f"integration_bundle:{manifest.key}",
                    details={"bundle": manifest.key, "target": self.target.value},
                )
            )
            return False
        if manifest.agents and self.target not in _AGENT_FILE_FMT:
            diagnostics.append(
                KernelDiagnostic(
                    code=ErrorCode.CAPABILITY_UNAVAILABLE.value,
                    message=f"target {self.target.value!r} lacks agents surface for {manifest.key!r}",
                    severity=Severity.WARNING,
                    target=f"integration_bundle:{manifest.key}",
                    details={"bundle": manifest.key, "target": self.target.value, "surface": "agents"},
                )
            )
        return True

    def reserve_agent_name(self, agent_key: str) -> str:
        ename = f"{self.pack_prefix}-{agent_key}" if self.pack_prefix else agent_key
        if ename in self.seen_agents:
            raise ValidationFailed(ErrorCode.INTEGRATION_PATH_COLLISION, f"duplicate bundle agent {ename!r}")
        self.seen_agents.add(ename)
        return ename

    def record_agent(self, ename: str, doc: Mapping[str, object]) -> None:
        if self.target in _AGENT_FILE_FMT:
            self.occupied_files.add(_AGENT_FILE_FMT[self.target].format(name=ename))
        self.agents.append(normalize_desired_map(doc))

    def collect_assets(
        self,
        manifest: IntegrationBundleManifest,
        *,
        bundle_digest: str,
        bodies: Mapping[str, str] | None,
        file_metas: Sequence[tuple[str, int, str]],
    ) -> None:
        for asset in manifest.assets:
            if asset.target is not self.target:
                continue
            raw_bytes = extract_bundle_source_bytes(
                bodies, file_metas, source=asset.source, bundle_key=manifest.key
            )
            expanded = resolve_bundle_asset_path(
                raw_path=asset.path,
                target=self.target,
                surface=asset.surface,
                pack_prefix=self.pack_prefix,
                ownership=asset.ownership,
            )
            if asset.ownership is Ownership.MANAGED_FILE:
                if expanded in self.occupied_files or any(p == expanded for p, _ in self.occupied_blocks):
                    raise ValidationFailed(
                        ErrorCode.INTEGRATION_PATH_COLLISION, f"duplicate bundle path {expanded!r}"
                    )
                self.occupied_files.add(expanded)
            else:
                bpair = (expanded, asset.block_id or "")
                if expanded in self.occupied_files or bpair in self.occupied_blocks:
                    raise ValidationFailed(
                        ErrorCode.INTEGRATION_PATH_COLLISION, f"colliding block at {expanded!r}"
                    )
                self.occupied_blocks.add(bpair)
            self.assets.append(
                (
                    expanded,
                    manifest.key,
                    asset.block_id or "",
                    normalize_desired_map(
                        {
                            "bundle_key": manifest.key,
                            "bundle_version": manifest.version,
                            "bundle_digest": bundle_digest,
                            "target": self.target.value,
                            "surface": asset.surface.value,
                            "source": asset.source,
                            "raw_path": asset.path,
                            "path": expanded,
                            "pack_prefix": self.pack_prefix,
                            "ownership": asset.ownership.value,
                            "block_id": asset.block_id,
                            "content_b64": base64.b64encode(raw_bytes).decode("ascii"),
                            "digest": sha256_tagged(raw_bytes),
                        }
                    ),
                )
            )


def collect_host_subscription_events(
    raw_subs: object,
) -> tuple[tuple[str, tuple[Literal["enforcement", "workflow", "observation"], ...]], ...]:
    if not isinstance(raw_subs, Mapping) or not raw_subs:
        return ()
    parsed, _violations = parse_subscriptions(cast("Mapping[str, JsonValue]", raw_subs), {})
    classes_by_kind: dict[HookEventKind, set[HookClass]] = {kind: set() for kind in HookEventKind}
    for sub in parsed:
        if not sub.enabled or sub.execution_location is not ExecutionLocation.HOST:
            continue
        if validate_subscription(sub, hookable_types=frozenset(), sink_ids=frozenset()):
            continue
        for pattern in sub.event_types:
            if pattern == "client:*":
                for kind in HookEventKind:
                    classes_by_kind[kind].add(sub.hook_class)
            elif pattern.startswith("client:"):
                classes_by_kind[HookEventKind(pattern.removeprefix("client:"))].add(sub.hook_class)
    out: list[tuple[str, tuple[Literal["enforcement", "workflow", "observation"], ...]]] = []
    for kind in HookEventKind:
        present = classes_by_kind[kind]
        if present:
            ordered: tuple[Literal["enforcement", "workflow", "observation"], ...] = tuple(
                cls.value for cls in _HOOK_CLASS_ORDER if cls in present
            )
            out.append((kind.value, ordered))
    return tuple(out)


def encode_inputs_digest_bytes(payload: Mapping[str, object]) -> bytes:
    normalized = normalize_desired_json(payload)
    return json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
