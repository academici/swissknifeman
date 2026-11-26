"""Bind the episodic memory port for trusted host-only entry points."""

from skm.adapters.knowledge.local_sqlite_memory import LocalSqliteMemoryStore
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.modules.knowledge.ports import EpisodeScope as EpisodeScope
from skm.modules.knowledge.ports import LocalEpisodicMemory as LocalEpisodicMemory
from skm.platform.config.bootstrap import BootstrapConfig
from skm.platform.system_clock import SystemClock

__all__ = ["EpisodeScope", "LocalEpisodicMemory", "local_episodic_memory"]


def local_episodic_memory(bootstrap: BootstrapConfig) -> LocalEpisodicMemory:
    """Bind the host-only port outside the application bus and worker compositions."""
    if bootstrap.access_mode != "embedded":
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE, "Local episodic memory requires embedded host mode"
        )
    profile = bootstrap.instance_profile or "default"
    return LocalSqliteMemoryStore(
        bootstrap.state_dir / "episodic-memory" / f"{profile}.sqlite3", SystemClock()
    )
