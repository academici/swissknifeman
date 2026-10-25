"""Debug mode of a conductor run: ``[orch] debug`` (machine or project config, ``SKM_ORCH_DEBUG``) or ``--debug``.

Off by default. On, the run announces ``DEBUG_MODE`` right after ``run.start`` (and after a resume): the observer
protocol to follow (the ``orch-debug`` dev skill), the layer that switched the mode on, where the per-item metrics are
(the observer report of the run, written with or without debug) and the folder ``<run>/debug/`` for the notes of the
observer. The announcement writes no file: ``<run>/debug/journal.md`` is created by the agent of the protocol when it has
something to write. The mode is for the agent or person who watches the run; the roles, their prompts, the decisions of
the conductor and the facts of the lifecycle it records are the same with it and without it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from orch.conductor.infrastructure.files import REPORTS

ORCH_ROOT = Path(__file__).resolve().parents[3]
PROTOCOL = ORCH_ROOT / "dev-skills" / "orch-debug" / "SKILL.md"
FOLDER = "debug"
REASON = "DEBUG_MODE"


def source(settings) -> str:
    """The layer that set ``debug`` (``defaults``, ``machine``, ``project``, ``environment``, ``flags`` ...)."""
    if settings.resolved is None:
        return "settings"
    entries = settings.resolved.explain("debug")
    return entries[0].layer if entries else "defaults"


def announce(progress, directory: Path, run_id: str, settings) -> Optional[Path]:
    """Emit ``DEBUG_MODE`` when the mode is on and return the (not created) notes folder ``<run>/debug/``; ``None`` when
    it is off. Nothing is written but the beacon."""
    if not settings.debug:
        return None
    origin = source(settings)
    folder = Path(directory) / FOLDER
    progress.emit("info", reason_code=REASON,
                  message=f"debug mode on (from {origin}): follow {PROTOCOL}; per-item metrics in the observer report "
                          f"{REPORTS / run_id / 'observer.md'} (orch conduct observe --run {run_id}); notes of the "
                          f"observer, when there are any, in {folder / 'journal.md'}")
    return folder
