"""``$EDITOR`` round trip for local commands such as ``skm plan draft edit`` (cli §6.6).

The document is written to a private temporary file, the editor runs on it and the result is read back. A
document that is not valid JSON, or an editor that fails, keeps the file and reports its path so the work is
not lost; only a successful round trip removes it. Schema validation of the document stays with the command
that owns it (it calls the bus); this module has no business rules.
"""

import json
import os
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, ValidationFailed
from skm.kernel.json_types import JsonValue

__all__ = ["EditorRunner", "edit_document", "resolve_editor"]

type EditorRunner = Callable[[Sequence[str]], int]


def _run_editor(argv: Sequence[str]) -> int:
    return subprocess.run(list(argv), check=False).returncode


def resolve_editor(environ: Mapping[str, str]) -> list[str]:
    """``$VISUAL`` then ``$EDITOR``, split like a shell word list; none set is ``CAPABILITY_UNAVAILABLE``."""
    command = environ.get("VISUAL") or environ.get("EDITOR")
    argv = shlex.split(command) if command else []
    if not argv:
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "no editor configured: set $VISUAL or $EDITOR",
            details={"hint": "export EDITOR=vim"},
        )
    return argv


def _kept(path: Path, message: str, *, issues: list[JsonValue]) -> ValidationFailed:
    details: dict[str, JsonValue] = {"path": str(path), "hint": f"your edit is kept in {path}"}
    details["issues"] = issues
    return ValidationFailed(ErrorCode.SCHEMA_INVALID, message, details=details)


def edit_document(
    initial: Mapping[str, JsonValue],
    *,
    suffix: str = ".json",
    environ: Mapping[str, str],
    run: EditorRunner = _run_editor,
) -> dict[str, JsonValue]:
    """Let the user edit ``initial``; return the edited JSON object."""
    if suffix != ".json":
        raise ValueError("only .json documents can be edited until a TOML writer exists")
    argv = resolve_editor(environ)
    directory = Path(tempfile.mkdtemp(prefix="skm-edit-"))  # mode 0700
    path = directory / f"document{suffix}"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(initial, indent=2, ensure_ascii=False) + "\n")
    except BaseException:
        # nothing was edited yet: a failed copy (a full disk) must not leave the directory behind
        shutil.rmtree(directory, ignore_errors=True)
        raise
    status = run([*argv, str(path)])
    if status != 0:
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            f"the editor exited with status {status}",
            details={"path": str(path), "hint": f"your edit is kept in {path}"},
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise _kept(
            path,
            "the edited document is not valid JSON",
            issues=[{"pointer": "", "code": "json", "message": str(exc)}],
        ) from None
    if not isinstance(document, dict):
        raise _kept(
            path,
            "the edited document must be a JSON object",
            issues=[{"pointer": "", "code": "type", "message": "expected an object"}],
        )
    # The private directory is ours alone: editor backups and swap files go with the edit copy.
    shutil.rmtree(directory)
    return cast("dict[str, JsonValue]", document)
