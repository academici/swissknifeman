"""Public facade of the settings module (settings §A.13): contracts for surfaces and tests only.

DTOs, results and views of the bus operations, the scope reference of the DTOs and ``entries_digest`` (the
CAS value of ``import_config``). There is no function to read configuration: modules read ``ctx.config``.

Surface code imports ``from skm.modules.settings import public as settings`` and asks the existing client,
for example ``client.ask(settings.GetGeneration())``. DTO construction does not open a transaction;
the bus owns that lifecycle. Import the facade instead of another module's generated or application code.

``entries_digest`` is the type-tagged digest of ``domain/digest.py``: §A.4 names plain canonical JSON of
``[key, op, value, locked]``, but that encoding (with floats as ``repr`` strings) gives ``1.5`` and
``"1.5"`` one digest; every consumer uses this one implementation.
"""

from skm.modules.settings.application.queries.explain_config import ExplainConfigResult
from skm.modules.settings.application.scopes import ScopeRefDto
from skm.modules.settings.domain.digest import entries_digest
from skm.modules.settings.domain.worker_config import PROJECT_WORKER_KEYS, worker_identifiers, worker_values
from skm.modules.settings.generated.commands import (
    ImportConfig,
    LockValue,
    RemoveValue,
    SetValue,
    UnlockValue,
    UnsetValue,
)
from skm.modules.settings.generated.queries import (
    ExplainConfig,
    ExportConfig,
    GetGeneration,
    GetHistory,
    GetHostConfig,
    GetSchema,
    GetValue,
    ListEntries,
)
from skm.modules.settings.generated.results import (
    GetGenerationResult,
    GetHostConfigResult,
    GetHostConfigResultPlugins,
    ImportConfigResult,
    LockValueResult,
    RemoveValueResult,
    SetValueResult,
    UnlockValueResult,
    UnsetValueResult,
)
from skm.modules.settings.generated.views import (
    EffectiveKeyView,
    EntryView,
    ExplainReport,
    ExportConfigView,
    GetHistoryView,
    GetSchemaView,
    GetValueView,
    HistoryView,
    ListEntriesView,
)

__all__ = [
    "PROJECT_WORKER_KEYS",
    "EffectiveKeyView",
    "EntryView",
    "ExplainConfig",
    "ExplainConfigResult",
    "ExplainReport",
    "ExportConfig",
    "ExportConfigView",
    "GetGeneration",
    "GetGenerationResult",
    "GetHistory",
    "GetHistoryView",
    "GetHostConfig",
    "GetHostConfigResult",
    "GetHostConfigResultPlugins",
    "GetSchema",
    "GetSchemaView",
    "GetValue",
    "GetValueView",
    "HistoryView",
    "ImportConfig",
    "ImportConfigResult",
    "ListEntries",
    "ListEntriesView",
    "LockValue",
    "LockValueResult",
    "RemoveValue",
    "RemoveValueResult",
    "ScopeRefDto",
    "SetValue",
    "SetValueResult",
    "UnlockValue",
    "UnlockValueResult",
    "UnsetValue",
    "UnsetValueResult",
    "entries_digest",
    "worker_identifiers",
    "worker_values",
]
