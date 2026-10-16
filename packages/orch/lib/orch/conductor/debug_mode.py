"""Debug mode of a conductor run: ``[orch] debug`` (machine or project config, ``SKM_ORCH_DEBUG``) or ``--debug``.

Off by default. On, the run announces ``DEBUG_MODE`` right after ``run.start`` (and after a resume): the observer
protocol to follow (the ``orch-debug`` dev skill), the layer that switched the mode on, and the journal folder
``<run>/debug/`` with a journal, a metrics table and findings, created once and kept by a resume. The mode is
for the agent or person who watches the run; the roles, their prompts and the decisions of the conductor are the
same with it and without it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from orch.conductor.infrastructure.clock import utc_now

ORCH_ROOT = Path(__file__).resolve().parents[3]
PROTOCOL = ORCH_ROOT / "dev-skills" / "orch-debug" / "SKILL.md"
FOLDER = "debug"
REASON = "DEBUG_MODE"

_SKELETONS = {
    "journal.md": "# Observer journal — run {run}\n\nChronological: every action and decision of the observer, written "
                  "when it is made.\n\n| time (UTC) | item | action or decision | why |\n|---|---|---|---|\n"
                  "| {now} | - | debug mode on ({source}) | - |\n",
    "metrics.md": "# Metrics per item — run {run}\n\nAn empty cell is «not measured» with the reason.\n\n"
                  "| item | wall / estimate | executor / review / checks / correction min | checks share | check rounds | "
                  "review rounds | repeats | heals / repairs | beacons | tokens in / out | deviations | findings |\n"
                  "|---|---|---|---|---|---|---|---|---|---|---|---|\n",
    "findings.md": "# Findings — run {run}\n\nNumbered: symptom, cause, fix (commit), what to rethink.\n",
}


def source(settings) -> str:
    """The layer that set ``debug`` (``defaults``, ``machine``, ``project``, ``environment``, ``flags`` ...)."""
    if settings.resolved is None:
        return "settings"
    entries = settings.resolved.explain("debug")
    return entries[0].layer if entries else "defaults"


def open_journal(directory: Path, run_id: str, origin: str) -> Path:
    """``<run>/debug/`` with its three files; a file that exists is left as it is (a resume keeps the record)."""
    folder = Path(directory) / FOLDER
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name, text in _SKELETONS.items():
        path = folder / name
        if not path.exists():
            path.write_text(text.format(run=run_id, now=utc_now(), source=origin), encoding="utf-8")
    return folder


def announce(progress, directory: Path, run_id: str, settings) -> Optional[Path]:
    """Emit ``DEBUG_MODE`` and open the journal when the mode is on; ``None`` (and nothing written) when it is off."""
    if not settings.debug:
        return None
    origin = source(settings)
    folder = open_journal(directory, run_id, origin)
    progress.emit("info", reason_code=REASON,
                  message=f"debug mode on (from {origin}): follow {PROTOCOL}; journal, metrics and findings in {folder}")
    return folder
