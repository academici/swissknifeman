"""Build a bounded text pack from the local checkout gateway."""

from __future__ import annotations

import ast
import posixpath
from copy import copy
from dataclasses import dataclass
from glob import escape
from typing import TYPE_CHECKING

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.context.ports import CheckoutReader

if TYPE_CHECKING:
    from collections.abc import Iterator

    from skm.kernel.gateways import Gateways

PACK_MOUNT = "checkout"
DEFAULT_MAX_BYTES = 256 * 1024
_EXPANSION_LIMIT = 10_000


@dataclass(frozen=True, slots=True)
class PackContextRequest:
    paths: tuple[str, ...]
    max_bytes: int = DEFAULT_MAX_BYTES
    signatures_only: bool = False


@dataclass(frozen=True, slots=True)
class PackedFile:
    path: str
    content: str
    bytes: int


@dataclass(frozen=True, slots=True)
class SkippedFile:
    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class PackContextResult:
    files: tuple[PackedFile, ...]
    skipped: tuple[SkippedFile, ...]
    bytes: int
    exit_code: int


def _sensitive(path: str) -> bool:
    return any(
        name == ".git" or name.startswith((".env", "id_rsa")) or name.endswith((".pem", ".key"))
        for name in map(str.casefold, path.split("/"))
    )


def _relative(raw: str, root: str) -> str:
    if ".." in raw.split("/") or "\\" in raw or "\0" in raw:
        raise ValueError("path traversal")
    path = posixpath.normpath(raw)
    if not posixpath.isabs(path):
        return path
    if posixpath.commonpath((root, path)) != root:
        raise ValueError("path outside checkout")
    return posixpath.relpath(path, root)


def _signatures(body: list[ast.stmt]) -> Iterator[ast.stmt]:
    for node in body:
        if isinstance(node, ast.ClassDef):
            shell = copy(node)
            shell.body = list(_signatures(node.body)) or [ast.Pass()]
            yield shell
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            shell = copy(node)
            shell.body = [ast.Pass()]
            yield shell


def _python_signatures(text: str) -> str:
    return ast.unparse(ast.Module(body=list(_signatures(ast.parse(text).body)), type_ignores=[]))


def _expand(reader: CheckoutReader, pattern: str, skipped: list[SkippedFile]) -> tuple[str, ...]:
    matches, truncated = reader.expand(PACK_MOUNT, pattern, limit=_EXPANSION_LIMIT)
    if truncated:
        skipped.append(SkippedFile(pattern, "expansion_incomplete"))
    return matches


def pack_context(gateways: Gateways, request: PackContextRequest) -> PackContextResult:
    if request.max_bytes <= 0:
        raise ValidationFailed(ErrorCode.RUNTIME_INVALID_REQUEST, "--max-bytes must be positive")
    reader = gateways.get(CheckoutReader)
    root = reader.mount_root(PACK_MOUNT)
    files: list[PackedFile] = []
    skipped: list[SkippedFile] = []
    seen: set[str] = set()
    remaining = request.max_bytes

    def collect(relative: str, *, directory_allowed: bool = False) -> None:
        nonlocal remaining
        if relative in seen:
            return
        seen.add(relative)
        if _sensitive(relative):
            skipped.append(SkippedFile(relative, "sensitive"))
            return
        signatures = request.signatures_only
        is_python = relative.endswith(".py")
        if signatures and not is_python and not directory_allowed:
            skipped.append(SkippedFile(relative, "not_python"))
            return
        checked = reader.read(PACK_MOUNT, relative, max_bytes=remaining, follow_symlinks=False)
        if directory_allowed and checked.status == "path_invalid":
            matches = _expand(reader, f"{escape(relative)}/**", skipped)
            if matches:
                for match in matches:
                    collect(match)
                return
        raw = checked.data
        if raw is None or checked.status != "ok" or b"\0" in raw:
            reason = "binary" if checked.status == "ok" else checked.status
            skipped.append(SkippedFile(relative, reason))
            return
        if signatures and not is_python:
            skipped.append(SkippedFile(relative, "not_python"))
            return
        text = raw.decode("utf-8")
        if signatures:
            try:
                text = _python_signatures(text)
            except (SyntaxError, ValueError, RecursionError):
                skipped.append(SkippedFile(relative, "invalid_python"))
                return
        cost = max(len(raw), len(text.encode("utf-8")))
        if cost > remaining:
            skipped.append(SkippedFile(relative, "too_large"))
            return
        remaining -= cost
        files.append(PackedFile(relative, text, cost))

    for raw_path in request.paths or (".",):
        try:
            relative = _relative(raw_path, root)
        except ValueError:
            skipped.append(SkippedFile(raw_path, "path_outside_checkout"))
            continue
        if relative == ".":
            for match in _expand(reader, "**/*", skipped):
                collect(match)
        else:
            collect(relative, directory_allowed=True)

    rejected = {"path_outside_checkout", "path_invalid", "symlink_outside", "symlink_refused", "missing"}
    exit_code = int(
        any(entry.reason in rejected or entry.reason == "expansion_incomplete" for entry in skipped)
    )
    return PackContextResult(tuple(files), tuple(skipped), request.max_bytes - remaining, exit_code)
