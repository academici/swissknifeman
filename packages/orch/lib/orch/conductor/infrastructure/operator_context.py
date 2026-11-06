"""Snapshot and read caller context for one blocked retry, separate from the execution input and authority."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock
from orch.conductor.infrastructure.files import safe


MAX_BYTES = 65536


def requested(path: Path | None, refs, *, fresh_context: bool, raises) -> dict | None:
    if path is None:
        return None
    if fresh_context or raises or len(refs) != 1:
        raise Stop("OPTIONS_INVALID", "--note-file requires exactly one --retry item; no --fresh-context or --raise-limit")
    return read_note(path)


def read_note(path: Path) -> dict:
    try:
        source = path.resolve()
        with source.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise Stop("OPERATOR_CONTEXT_INVALID", f"cannot read UTF-8 note: {error}") from None
    if not text.strip() or b"\0" in raw or len(raw) > MAX_BYTES:
        raise Stop("OPERATOR_CONTEXT_INVALID", "note must contain 1..65536 UTF-8 bytes, without NUL")
    return {"source": str(source), "raw": raw, "sha256": sha256(raw).hexdigest()}


def record(owner, ref: str, item: dict, step: str | None, note: dict) -> None:
    if step is None:
        raise Stop("RETRY_NOT_BLOCKED", "operator context requires an executor round to retry; answer held questions explicitly")
    history = item.get("operator_context") or []
    if history and all(history[-1][key] == value for key, value in
                       (("step", step), ("source", note["source"]), ("sha256", note["sha256"]))):
        return
    number = len(history) + 1
    path = owner.directory / safe(ref) / "operator-context" / f"{number}.md"
    try:
        path.parent.resolve().relative_to((owner.directory / safe(ref)).resolve())
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.is_symlink() or path.read_bytes() != note["raw"]:
                raise Stop("OPERATOR_CONTEXT_CHANGED", f"retry note snapshot differs: {path}")
        else:
            with path.open("xb") as stream:
                stream.write(note["raw"])
    except (OSError, ValueError) as error:
        raise Stop("OPERATOR_CONTEXT_INVALID", f"cannot snapshot retry note: {error}") from None
    item.setdefault("operator_context", []).append({"n": number, "step": step, "source": note["source"],
        "file": path.relative_to(owner.directory).as_posix(), "sha256": note["sha256"], "at": clock.utc_now()})
    owner.progress.emit("info", item=ref, stage=step, reason_code="OPERATOR_CONTEXT_RECORDED",
                        message=f"caller note {number}: sha256:{note['sha256']}; input, authority and budgets unchanged")


def current(owner, item, step: str) -> dict | None:
    note = next((row for row in reversed(item.state.get("operator_context") or []) if row["step"] == step), None)
    if note is None:
        return None
    expected = owner.directory / safe(item.ref) / "operator-context" / f"{note['n']}.md"
    if note["file"] != expected.relative_to(owner.directory).as_posix() or expected.is_symlink():
        raise Stop("OPERATOR_CONTEXT_CHANGED", "retry note snapshot identity changed")
    try:
        expected.resolve().relative_to(item.directory.resolve())
        raw = expected.read_bytes()
    except (OSError, ValueError) as error:
        raise Stop("OPERATOR_CONTEXT_CHANGED", f"cannot read retry note snapshot: {error}") from None
    if sha256(raw).hexdigest() != note["sha256"]:
        raise Stop("OPERATOR_CONTEXT_CHANGED", "retry note snapshot digest changed")
    return {**note, "text": raw.decode("utf-8")}
