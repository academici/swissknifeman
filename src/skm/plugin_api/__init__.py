"""The stable import surface of plugins (mechanisms/02-plugins §2, ADR 0022).

A plugin imports only this package. It re-exports, unchanged, the manifest (§3), the component Protocols and
DTOs of their owners (§5), ``SkmError``/``ErrorCode`` and ``Diagnostic``. ``API_VERSION`` grows only with an
incompatible change of a component protocol (mechanisms/10).

Under the layer rules (00-conventions §2) this package reaches the kernel and module ``public`` facades only;
owner Protocols that their facade does not export yet are re-exported here once it does.
"""

from typing import Final

from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.outcomes import Diagnostic, Severity
from skm.kernel.tokens import TokenEstimator
from skm.modules.context.public import (
    RawDocument,
    RawSourceReply,
    ResearchSource,
    ResearchSourceConfig,
    SourceQuery,
)
from skm.modules.runtimes.public import (
    AgentRequest,
    AgentRuntime,
    Capability,
    CapabilityRecord,
    CapabilityStatus,
    RuntimeCapabilities,
    RuntimeId,
    RuntimeResult,
    SelfLoadedSource,
    SessionEvent,
    SessionHandle,
    UsageReport,
)

from .manifest import PLUGIN_ID_PATTERN, ComponentKind, ComponentSpec, PluginContext, PluginManifest, Side

__all__ = [
    "API_VERSION",
    "PLUGIN_ID_PATTERN",
    "AgentRequest",
    "AgentRuntime",
    "Capability",
    "CapabilityRecord",
    "CapabilityStatus",
    "Clock",
    "ComponentKind",
    "ComponentSpec",
    "Diagnostic",
    "ErrorCode",
    "PluginContext",
    "PluginManifest",
    "RawDocument",
    "RawSourceReply",
    "ResearchSource",
    "ResearchSourceConfig",
    "RuntimeCapabilities",
    "RuntimeId",
    "RuntimeResult",
    "SelfLoadedSource",
    "SessionEvent",
    "SessionHandle",
    "Severity",
    "Side",
    "SkmError",
    "SourceQuery",
    "TokenEstimator",
    "UsageReport",
]

API_VERSION: Final = 1
