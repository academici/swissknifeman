"""Built-in components as ``ComponentSpec`` (mechanisms/02-plugins §3, mechanisms/01 §7).

Built-ins use the plugin component interface without a manifest and without the allowlist. Their keys are
reserved: a plugin component with the same ``(kind, key)`` is ``PLUGIN_CONFLICT`` unless
``plugins.override_builtin`` names ``<kind>:<key>`` and exactly one plugin replaces it. The adapters
themselves are wired by their owning packages; a built-in whose adapter is not wired reports
``CAPABILITY_UNAVAILABLE`` instead of constructing a stand-in.

``component_problem`` is the structural check every constructed component passes, built-in or plugin: the
owner Protocol of its kind (02-plugins §5). It proves the shape only; behaviour is the owner's contract suite.
"""

import os
from collections.abc import Callable, Mapping
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, cast, override

from skm.adapters.git.excludes import GitInfoExcludes
from skm.adapters.git.runner import validate_repository_trust
from skm.adapters.http_client.research import ResearchHttpTransport
from skm.adapters.research.codegraph import NativeCodeGraphAdapter
from skm.adapters.research.command import CommandResearchSource
from skm.adapters.research.filesystem import FilesystemResearchSource
from skm.adapters.research.mcp_stdio import McpStdioResearchSource
from skm.adapters.research.providers import (
    Context7ResearchSource,
    PerplexityApiResearchSource,
    PerplexityWebResearchSource,
    WebSearchResearchSource,
)
from skm.application_bus.subscribers import EventSink
from skm.bootstrap.plugin_distribution import RuntimeDataFiles
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.tokens import TokenEstimator
from skm.modules.artifacts.ports import BlobStore
from skm.modules.context.ports import ResearchSource
from skm.modules.execution.ports import CheckRunner, Isolation, StageHandler
from skm.modules.integrations.ports import IntegrationTarget
from skm.modules.runtimes.domain.capability import parse_capabilities
from skm.modules.runtimes.domain.error_rules import parse_error_rules
from skm.modules.runtimes.ports import AgentRuntime
from skm.platform.config.secrets import SecretResolver
from skm.platform.config.sources.document import decode_document
from skm.platform.tokens.heuristic import HeuristicTokenEstimator
from skm.plugin_api.manifest import ComponentKind, ComponentSpec, PluginContext, Side

if TYPE_CHECKING:
    from skm.modules.context.domain.research import ResearchSourceConfig, SourceQuery
    from skm.platform.config.effective import EffectiveConfig

__all__ = [
    "BUILTIN_COMPONENTS",
    "OWNER_PROTOCOLS",
    "build_native_codegraph",
    "builtin_keys",
    "builtin_runtime_data",
    "component_problem",
]

# Owner Protocols (02-plugins §5); a kind without one yet (exporter, knowledge_source) cannot be constructed.
OWNER_PROTOCOLS: Final[Mapping[ComponentKind, type]] = MappingProxyType(
    {
        ComponentKind.RUNTIME: AgentRuntime,
        ComponentKind.INTEGRATION_TARGET: IntegrationTarget,
        ComponentKind.CHECK_RUNNER: CheckRunner,
        ComponentKind.STAGE_HANDLER: StageHandler,
        ComponentKind.ISOLATION: Isolation,
        ComponentKind.SECRET_RESOLVER: SecretResolver,
        ComponentKind.BLOB_BACKEND: BlobStore,
        ComponentKind.TOKEN_ESTIMATOR: TokenEstimator,
        ComponentKind.EVENT_SINK: EventSink,
        ComponentKind.RESEARCH_SOURCE: ResearchSource,
    }
)


def _not_wired(kind: ComponentKind, key: str) -> Callable[[PluginContext], object]:
    def factory(_ctx: PluginContext) -> object:
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            f"built-in {kind.value} {key!r} is not wired into this build",
            details={"reason_code": "builtin_not_wired", "kind": kind.value, "key": key},
        )

    return factory


def _specs(kind: ComponentKind, side: Side, *keys: str) -> tuple[ComponentSpec, ...]:
    return tuple(ComponentSpec(kind=kind, key=key, side=side, factory=_not_wired(kind, key)) for key in keys)


class _ConfiguredFilesystemSource(FilesystemResearchSource):
    def __init__(self, config: Callable[[], object]) -> None:
        super().__init__()
        self._config = config

    @override
    def roots(
        self, config: "ResearchSourceConfig", query: "SourceQuery"
    ) -> tuple[tuple[str, Path, Path], ...]:
        # The host allowlist is live. Keep the registry's concurrency gates across configuration reads.
        host = cast("EffectiveConfig", self._config())
        allowed = cast("list[str] | None", host.get("context.research.fs_roots_allow"))
        return FilesystemResearchSource(fs_roots_allow=tuple(allowed or ())).roots(config, query)


def build_native_codegraph() -> NativeCodeGraphAdapter:
    return NativeCodeGraphAdapter(validate_repository_trust, GitInfoExcludes())


BUILTIN_COMPONENTS: Final[tuple[ComponentSpec, ...]] = (
    *_specs(
        ComponentKind.RUNTIME,
        Side.HOST,
        "antigravity",
        "claude_code",
        "codex",
        "cursor",
        "fake",
        "gemini_cli",
        "grok",
    ),
    *_specs(
        ComponentKind.INTEGRATION_TARGET,
        Side.HOST,
        "antigravity",
        "claude_code",
        "codex",
        "cursor",
        "gemini_cli",
        "grok",
    ),
    *_specs(ComponentKind.CHECK_RUNNER, Side.HOST, "command", "manual", "shell"),
    *_specs(ComponentKind.ISOLATION, Side.HOST, "container", "landlock", "none", "worktree"),
    *_specs(ComponentKind.SECRET_RESOLVER, Side.BOTH, "env", "file", "keyring"),
    ComponentSpec(ComponentKind.RESEARCH_SOURCE, "command", Side.HOST, lambda _ctx: CommandResearchSource()),
    ComponentSpec(
        ComponentKind.RESEARCH_SOURCE, "codegraph", Side.HOST, lambda _ctx: build_native_codegraph()
    ),
    ComponentSpec(
        ComponentKind.RESEARCH_SOURCE,
        "filesystem",
        Side.HOST,
        lambda ctx: _ConfiguredFilesystemSource(ctx.config),
    ),
    ComponentSpec(
        ComponentKind.RESEARCH_SOURCE, "mcp_stdio", Side.HOST, lambda _ctx: McpStdioResearchSource()
    ),
    ComponentSpec(
        ComponentKind.RESEARCH_SOURCE,
        "context7",
        Side.HOST,
        lambda _ctx: Context7ResearchSource(ResearchHttpTransport(), credential=os.environ.get),
    ),
    ComponentSpec(
        ComponentKind.RESEARCH_SOURCE,
        "perplexity_api",
        Side.HOST,
        lambda _ctx: PerplexityApiResearchSource(ResearchHttpTransport(), credential=os.environ.get),
    ),
    ComponentSpec(
        ComponentKind.RESEARCH_SOURCE,
        "perplexity_web",
        Side.HOST,
        lambda _ctx: PerplexityWebResearchSource(ResearchHttpTransport()),
    ),
    ComponentSpec(
        ComponentKind.RESEARCH_SOURCE,
        "web_search",
        Side.HOST,
        lambda _ctx: WebSearchResearchSource(ResearchHttpTransport(), credential=os.environ.get),
    ),
    ComponentSpec(
        kind=ComponentKind.TOKEN_ESTIMATOR,
        key="heuristic-v1",
        side=Side.CONTROL_PLANE,
        factory=lambda _ctx: HeuristicTokenEstimator(),
    ),
)


@cache
def builtin_runtime_data() -> tuple[RuntimeDataFiles, ...]:
    """Read the built-in CLI runtime declarations for the control-plane catalog."""
    root = Path(__file__).resolve().parents[1]
    data: list[RuntimeDataFiles] = []
    for runtime_id in ("antigravity", "claude_code", "codex", "cursor", "gemini_cli", "grok"):
        directory = Path("adapters/runtimes") / runtime_id
        capabilities = directory / "capabilities.toml"
        error_rules = directory / "error_rules.toml"
        data.append(
            RuntimeDataFiles(
                runtime_id,
                parse_capabilities(
                    decode_document((root / capabilities).read_text(encoding="utf-8"), "toml")
                ),
                parse_error_rules(decode_document((root / error_rules).read_text(encoding="utf-8"), "toml")),
                capabilities.as_posix(),
                error_rules.as_posix(),
            )
        )
    return tuple(data)


def builtin_keys(
    components: tuple[ComponentSpec, ...] = BUILTIN_COMPONENTS,
) -> frozenset[tuple[ComponentKind, str]]:
    return frozenset((spec.kind, spec.key) for spec in components)


def _member_names(protocol: type) -> frozenset[str]:
    """Public attributes and methods a Protocol declares (owner Protocols are not runtime_checkable)."""
    names: set[str] = set()
    for klass in protocol.__mro__:
        if not getattr(klass, "_is_protocol", False) or klass.__name__ in {"Protocol", "Generic"}:
            continue
        names.update(name for name in getattr(klass, "__annotations__", {}) if not name.startswith("_"))
        members = vars(klass).items()
        names.update(
            n for n, v in members if not n.startswith("_") and (callable(v) or isinstance(v, property))
        )
    return frozenset(names)


def component_problem(spec: ComponentSpec, built: object) -> tuple[str, str] | None:
    """``(reason, message)`` when ``built`` does not fit the owner Protocol of ``spec.kind``, else None."""
    protocol = OWNER_PROTOCOLS.get(spec.kind)
    if protocol is None:
        return "kind_unsupported", f"kind {spec.kind} has no owner Protocol yet"
    members = _member_names(protocol)
    if spec.kind is ComponentKind.STAGE_HANDLER:  # a host handler runs, a control-plane handler decides
        members = (members - {"run", "decide"}) | {
            "run" if getattr(built, "side", None) == "host" else "decide"
        }
    missing = sorted(name for name in members if not hasattr(built, name))
    if missing:
        return "protocol", f"{spec.kind}:{spec.key} lacks {', '.join(missing)} of {protocol.__name__}"
    if spec.kind is ComponentKind.RUNTIME and getattr(built, "runtime_id", None) != spec.key:
        return "runtime_id", f"runtime_id differs from the component key {spec.key!r}"
    return None
