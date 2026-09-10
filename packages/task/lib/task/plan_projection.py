"""Shared deterministic writer and freshness check for plan projections."""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


class ProjectionError(ValueError):
    """A projection cannot be built or is not fresh."""


METADATA_FIELDS = (
    "projection",
    "projection_version",
    "source_scope",
    "through",
    "inputs_sha256",
    "generated_by",
)


def inputs_sha256(paths, *, root) -> str:
    """Hash named inputs, including relative paths, in deterministic order."""
    root = Path(root)
    digest = hashlib.sha256()
    for path in sorted((Path(path) for path in paths), key=lambda value: str(value)):
        try:
            relative = path.relative_to(root).as_posix()
            payload = path.read_bytes()
        except (OSError, ValueError) as exc:
            raise ProjectionError(f"вход проекции недоступен: {path}") from exc
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def metadata_block(*, projection, projection_version, source_scope, through,
                   inputs_sha256_value, generated_by) -> str:
    """Render the canonical metadata block shared by every projection."""
    values = {
        "projection": projection,
        "projection_version": projection_version,
        "source_scope": source_scope,
        "through": through,
        "inputs_sha256": inputs_sha256_value,
        "generated_by": generated_by,
    }
    if set(values) != set(METADATA_FIELDS) or any(not str(value) for value in values.values()):
        raise ProjectionError("метаданные проекции неполны")
    lines = ["<!-- plan-projection"]
    lines.extend(f"{field}: {values[field]}" for field in METADATA_FIELDS)
    lines.append("-->")
    return "\n".join(lines)


def rendered_file(*, metadata: str, title: str, body: str) -> str:
    """Build one complete generated Markdown file without wall-clock state."""
    if not metadata.startswith("<!-- plan-projection\n"):
        raise ProjectionError("метаданные проекции неканоничны")
    return f"{metadata}\n\n# {title}\n\n> Не править руками: это генерируемый вид.\n\n{body.rstrip()}\n"


def write_or_check(target, expected: str, *, check: bool) -> bool:
    """Atomically write a projection, or compare its bytes in ``--check`` mode."""
    target = Path(target)
    encoded = expected.encode("utf-8")
    if check:
        try:
            actual = target.read_bytes()
        except OSError as exc:
            raise ProjectionError(f"вид отсутствует или не читается: {target}") from exc
        if actual != encoded:
            raise ProjectionError(f"вид устарел: {target}")
        return False
    if target.is_file() and target.read_bytes() == encoded:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f".{target.name}.", delete=False) as tmp:
        tmp.write(encoded)
        temporary = Path(tmp.name)
    try:
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return True
