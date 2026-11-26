"""Architecture findings, exact exceptions and generated-schema provenance."""

from __future__ import annotations

import ast
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path

from ._allowlist import Allowance
from ._tree import (
    SourceFile,
    dotted,
)


@dataclass(frozen=True)
class Violation:
    rule: str
    path: str
    line: int
    message: str
    detail: str = ""

    def render(self) -> str:
        return f"{self.path}:{self.line}: [{self.rule}] {self.message}"


# Signatures owned by execution §6 and interfaces.md. Each pair is a source module
# and a full imported symbol. These permissions never cover executable references.
ANNOTATION_CONTRACTS = frozenset(
    {
        ("skm.modules.context.domain.research", "skm.modules.artifacts.public.StagedBlobRef"),
        ("skm.modules.context.domain.skill_selection", "skm.modules.extensions.public.SkillManifest"),
        ("skm.modules.context.domain.skill_selection", "skm.modules.extensions.public.VersionConstraint"),
        ("skm.modules.execution.domain.session", "skm.modules.runtimes.public.ResumeAllowance"),
        ("skm.modules.execution.domain.step", "skm.modules.runtimes.public.UsageReport"),
        ("skm.modules.integrations.domain.projection", "skm.modules.workspace.public.CheckoutBindingId"),
        *(
            (f"skm.modules.learning.domain.{source}", f"skm.modules.knowledge.public.{name}")
            for source, names in {
                "candidate": ("EvidenceRef", "LessonId", "LessonKind"),
                "detectors": ("EvidenceRef", "LessonKind"),
                "review": ("LessonKind",),
            }.items()
            for name in names
        ),
        *(
            ("skm.modules.execution.ports", f"skm.modules.{module}.{name}")
            for module, names in {
                "artifacts.public": ("BindingRole", "StagedBlobRef"),
                "runtimes.public": ("RuntimeRegistry", "UsageReport"),
                "execution.host.checks": ("CheckDeps", "CheckRequest", "CheckResult"),
                "execution.host.environment": (
                    "EnvironmentSpec",
                    "PreparedEnvironment",
                    "RemovedEnvironment",
                ),
                "execution.host.evidence": ("BlobUploader",),
                "execution.host.isolation": ("IsolationSpec", "WrappedCommand"),
                "execution.host.stages.base": ("StageOutcome", "StageRequest"),
            }.items()
            for name in names
        ),
        ("skm.modules.execution.ports", "skm.application_bus.context.CommandContext"),
        ("skm.modules.execution.ports", "skm.application_bus.host.HostContext"),
        ("skm.modules.execution.ports", "skm.platform.config.EffectiveConfig"),
        ("skm.modules.execution.ports", "skm.platform.logging.logger.StructLogger"),
        ("skm.modules.execution.host.context", "skm.modules.execution.ports.StageDeps"),
        ("skm.modules.execution.host.context", "skm.modules.runtimes.public.SessionHandle"),
        ("skm.modules.execution.host.worker_loop", "skm.modules.runtimes.public.SessionHandle"),
        ("skm.modules.execution.host.worker_loop", "skm.modules.execution.ports.StageDeps"),
        ("skm.modules.execution.host.stage_client", "skm.modules.execution.ports.StageClient"),
        *(
            (f"skm.modules.execution.host.stages.{stage}", "skm.modules.execution.ports.StageDeps")
            for stage in (
                "agent_step",
                "agent_review",
                "run_checks",
                "integrate",
                "prepare_environment",
                "advisor_consult",
            )
        ),
    }
)
# Owner contracts explicitly export these declarations at runtime (execution §13,
# access §13, runtimes §13, integrations §6 and adapters §8).
DECLARATION_CONTRACTS = frozenset(
    {
        ("skm.modules.execution.public", "skm.modules.execution.host.stages.base.StageOutcome"),
        ("skm.modules.execution.public", "skm.modules.execution.host.stages.base.StageRequest"),
        ("skm.modules.access.public", "skm.modules.access.permissions.PERMISSIONS"),
        ("skm.modules.execution.host.stage_client", "skm.modules.execution.ports.StageClient"),
        ("skm.adapters.http_client.client", "skm.application_bus.client.SkmClient"),
        ("skm.adapters.http_client.client", "skm.application_bus.client.QueryMeta"),
        ("skm.adapters.http_client.client", "skm.application_bus.client.StagedBlobRef"),
        ("skm.adapters.http_client.client", "skm.entrypoints.api.etag.encode_etag"),
        ("skm.adapters.http_client.client", "skm.entrypoints.api.routing.Route"),
        ("skm.adapters.http_client.client", "skm.entrypoints.api.routing.RouteTable"),
        ("skm.adapters.http_client.client", "skm.entrypoints.api.routing.encode_scope"),
        ("skm.adapters.http_client.retry", "skm.application_bus.registry.IdempotencyMode"),
        ("skm.bootstrap._http_mode", "skm.entrypoints.api.routes.MODULE_IDS"),
        ("skm.bootstrap._http_mode", "skm.entrypoints.api.routing.build_route_table"),
        ("skm.entrypoints.cli.commands.mcp", "skm.entrypoints.mcp.registry.published_tools"),
        ("skm.entrypoints.cli.commands.mcp", "skm.entrypoints.mcp.registry.tools_digest"),
        ("skm.entrypoints.cli.commands.mcp", "skm.entrypoints.mcp.server.serve"),
        ("skm.entrypoints.cli.commands.mcp", "skm.entrypoints.mcp.server.serve_stage"),
        ("skm.entrypoints.worker.main", "skm.entrypoints.mcp.server.serve_stage"),
        ("skm.entrypoints.cli.commands.mcp", "skm.entrypoints.mcp.session.McpSession"),
        ("skm.entrypoints.cli.commands.serve", "skm.entrypoints.api.app.serve_asgi"),
    }
)
VALUE_ANNOTATIONS = frozenset(
    {
        ("skm.modules.runtimes.public", "skm.modules.extensions.public.PackPins"),
        ("skm.modules.integrations.ports", "skm.modules.workspace.public.CheckoutBindingId"),
        *(
            (owner, target)
            for owner, target in ANNOTATION_CONTRACTS
            if owner.startswith(
                (
                    "skm.modules.learning.domain.",
                    "skm.modules.context.domain.skill_selection",
                    "skm.modules.integrations.domain.projection",
                )
            )
        ),
    }
)
PATH_CONTRACTS = frozenset(
    {
        "skm.modules.artifacts.ports",
        "skm.modules.integrations.ports",
        "skm.modules.exports.ports",
        "skm.modules.knowledge.ports",
        "skm.modules.execution.ports",
        "skm.modules.execution.host.environment",
        "skm.modules.execution.host.checks",
        "skm.modules.execution.host.isolation",
        "skm.modules.execution.host.evidence",
    }
)


@dataclass
class RuleContext:
    depends_on: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    annotation_contracts: frozenset[tuple[str, str]] = ANNOTATION_CONTRACTS
    root: Path | None = None
    config_keys: frozenset[str] | None = None
    config_views: frozenset[str] | None = None
    implemented_ports: frozenset[str] = frozenset()
    schema_allowances: tuple[Allowance, ...] = ()
    generated_outputs: Mapping[Path, str] | None = field(default=None, init=False, repr=False)
    schema_sources: dict[str, tuple[str, dict]] | None = field(default=None, init=False, repr=False)
    schema_sites_cache: dict[str, tuple[set[tuple[str, int]], dict]] = field(
        default_factory=dict, init=False, repr=False
    )


def _schema_data_sites(file: SourceFile, ctx: RuleContext) -> tuple[set[tuple[str, int]], dict]:
    """Only inert slots of byte-for-byte fresh generator output qualify as schema data."""
    if ctx.root is None or "generated" not in file.path.parts:
        return set(), {}
    cached = ctx.schema_sites_cache.get(file.display_path)
    if cached is not None and file.source is None:
        return cached
    if not file.text.startswith("# generated by tools/gen.py from "):
        return set(), {}
    if ctx.generated_outputs is None:
        ctx.generated_outputs = dict(import_module("tools.gen").outputs(ctx.root, only="python"))
    if ctx.generated_outputs.get(Path(file.display_path)) != file.text:
        return set(), {}
    result = _extract_schema_data_sites(file)
    if file.source is None:
        ctx.schema_sites_cache[file.display_path] = result
    return result


def _extract_schema_data_sites(file: SourceFile) -> tuple[set[tuple[str, int]], dict]:  # noqa: PLR0912
    sites: set[tuple[str, int]] = set()
    lines = file.text.splitlines()
    defaults = {}
    field_origins = {}
    class_defaults = {}

    def literals(node):
        sites.update(
            (v.value, v.lineno)
            for v in ast.walk(node)
            if isinstance(v, ast.Constant) and isinstance(v.value, str)
        )

    for node in file.tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            fields = isinstance(target, ast.Attribute) and target.attr == "_FIELDS"
            descriptor = isinstance(target, ast.Name) and target.id.startswith("_SPEC_")
            if fields or descriptor:
                try:
                    ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    continue
                literals(node.value)
                if fields and isinstance(node.value, ast.Tuple):
                    for row in node.value.elts:
                        if isinstance(row, ast.Tuple) and len(row.elts) == 7:
                            value = row.elts[4]
                            comment = lines[row.lineno - 2].strip()
                            if (
                                isinstance(value, ast.Constant)
                                and isinstance(value.value, str)
                                and comment.startswith("# schema field: ")
                            ):
                                try:
                                    location = json.loads(comment.removeprefix("# schema field: "))
                                except ValueError:
                                    continue
                                if not isinstance(location, str):
                                    continue
                                defaults[(value.value, value.lineno)] = location
                                if (
                                    isinstance(target, ast.Attribute)
                                    and isinstance(target.value, ast.Name)
                                    and isinstance(row.elts[1], ast.Constant)
                                ):
                                    field_origins[(target.value.id, row.elts[1].value)] = location
            elif isinstance(node.value, ast.Call) and dotted(node.value.func) == "TypedDict":
                literals(node.value)
        elif isinstance(node, ast.TypeAlias):
            for child in ast.walk(node.value):
                if isinstance(child, ast.Subscript) and dotted(child.value) == "Literal":
                    literals(child.slice)
        elif isinstance(node, ast.ClassDef):
            enum = any(dotted(base) == "StrEnum" for base in node.bases)
            dataclass = any(
                isinstance(d, ast.Call) and dotted(d.func) == "dataclass" for d in node.decorator_list
            )
            for child in node.body:
                if dataclass and isinstance(child, ast.AnnAssign):
                    for annotation in ast.walk(child.annotation):
                        if isinstance(annotation, ast.Subscript) and dotted(annotation.value) == "Literal":
                            literals(annotation.slice)
                if (
                    (enum and isinstance(child, ast.Assign))
                    or (dataclass and isinstance(child, ast.AnnAssign))
                ) and child.value is not None:
                    try:
                        ast.literal_eval(child.value)
                    except (ValueError, TypeError):
                        continue
                    literals(child.value)
                    if (
                        (
                            dataclass
                            and isinstance(child, ast.AnnAssign)
                            and isinstance(child.target, ast.Name)
                        )
                        and isinstance(child.value, ast.Constant)
                        and isinstance(child.value.value, str)
                    ):
                        class_defaults[(child.value.value, child.value.lineno)] = (
                            node.name,
                            child.target.id,
                        )
    for site, key in class_defaults.items():
        if key in field_origins:
            defaults[site] = field_origins[key]
    return sites, defaults


def _schema_default_allowed(file: SourceFile, value: str, line: int, ctx: RuleContext) -> bool:
    if not ctx.schema_allowances or ctx.root is None:
        return False
    _, defaults = _schema_data_sites(file, ctx)
    location = defaults.get((value, line))
    if not location:
        return False
    if ctx.schema_sources is None:
        ctx.schema_sources = {}
        for path in (ctx.root / "src/skm/schemas").rglob("*.v*.json"):
            if "data" not in path.relative_to(ctx.root / "src/skm/schemas").parts:
                doc = json.loads(path.read_text())
                ctx.schema_sources[doc["$id"]] = (path.relative_to(ctx.root).as_posix(), doc)
    urn, _, pointer = location.partition("#")
    if urn not in ctx.schema_sources:
        return False
    source, node = ctx.schema_sources[urn]
    try:
        for part in pointer.strip("/").split("/"):
            node = node[part.replace("~1", "/").replace("~0", "~")]
    except (KeyError, TypeError):
        return False
    if node.get("default") != value:
        return False
    finding = Violation("neutral-literals", source, 0, "", value)
    return any(allowance.matches(finding) for allowance in ctx.schema_allowances)


def _violation(rule: str, file: SourceFile, line: int, message: str, detail: str = "") -> Violation:
    return Violation(rule, file.display_path, line, message, detail)
