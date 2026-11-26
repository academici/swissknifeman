"""Bus operations of the settings module (settings §A.3, §A.7, §A.8)."""

from skm.modules.settings.application.commands import (
    import_config,
    lock_value,
    remove_value,
    set_value,
    unlock_value,
    unset_value,
)
from skm.modules.settings.application.queries import (
    explain_config,
    export_config,
    get_generation,
    get_history,
    get_host_config,
    get_schema,
    get_value,
    list_entries,
)

__all__ = ["COMMANDS", "QUERIES"]

COMMANDS = (
    set_value.SPEC,
    unset_value.SPEC,
    remove_value.SPEC,
    lock_value.SPEC,
    unlock_value.SPEC,
    import_config.SPEC,
)
QUERIES = (
    get_value.SPEC,
    explain_config.SPEC,
    export_config.SPEC,
    get_schema.SPEC,
    list_entries.SPEC,
    get_history.SPEC,
    get_generation.SPEC,
    get_host_config.SPEC,
)
