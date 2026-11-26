"""Manage and query a checkout-local index with the native CodeGraph CLI."""

from __future__ import annotations

import json
import os
import shutil
import stat
from collections.abc import Collection
from hashlib import sha256
from pathlib import Path
from time import monotonic
from typing import Protocol, cast
from urllib.parse import quote

from skm.adapters.research.command import ProcessSession, array_value, object_value
from skm.adapters.research.filesystem import SECRET_FILE, SKIPPED_DIRS
from skm.adapters.research.retry import SourceBusy, SourceFailed
from skm.kernel.cancel import CancelToken
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, PreconditionFailed, ValidationFailed
from skm.kernel.json_types import JsonObject
from skm.modules.context.domain.research import (
    RawDocument,
    RawSourceReply,
    ResearchSourceConfig,
    ResearchTier,
    SourceQuery,
)
from skm.modules.context.ports import CodeGraphAction

__all__ = ["NativeCodeGraphAdapter"]

_INDEX_DIR = ".codegraph"
_DB = "codegraph.db"
_INDEX_FILES = (_DB, _DB + "-wal", _DB + "-shm", _DB + "-journal", ".gitignore")


class _RepositoryTrust(Protocol):
    def __call__(self, path: Path, *, checkout_root: Path, allow_missing: bool = False) -> bool: ...


class _GitExcludes(Protocol):
    def update(self, checkout: str, *, add: Collection[str]) -> bool: ...


def _document(mount: str, hit: object) -> RawDocument | None:
    node = object_value(object_value(hit)["node"])
    file, name, kind = node["filePath"], node["qualifiedName"], node["kind"]
    start, end = node["startLine"], node["endLine"]
    if (
        not isinstance(file, str)
        or not isinstance(name, str)
        or not isinstance(kind, str)
        or type(start) is not int
        or type(end) is not int
        or not 1 <= start <= end
    ):
        raise SourceFailed()
    path = Path(file)
    if (
        path.is_absolute()
        or not path.parts
        or any(ord(char) < 32 or ord(char) == 127 for char in file)
        or any(
            part in SKIPPED_DIRS or part in ("..", _INDEX_DIR) or SECRET_FILE.search(part)
            for part in path.parts
        )
    ):
        return None
    signature = node.get("signature")
    label = f"{kind} {name}" + (signature if isinstance(signature, str) else "")
    return RawDocument(
        f"mcp:codegraph/{quote(mount, safe='')}/{quote(path.as_posix())}#L{start}",
        name,
        f"{file}:{start}-{end}: {label}",
        {"line_from": start, "line_to": end},
    )


class NativeCodeGraphAdapter:
    """Use fixed native commands and the trusted Git exclude writer for each checkout."""

    kind = "codegraph"

    def __init__(self, trust: _RepositoryTrust, excludes: _GitExcludes) -> None:
        self._trust = trust
        self._excludes = excludes

    def _checkout(self, checkout: str) -> Path:
        root = Path(checkout)
        if ".." in root.parts:
            raise ValidationFailed(
                ErrorCode.REPOSITORY_UNSAFE, "CodeGraph requires a canonical checkout path"
            )
        self._trust(root, checkout_root=root)
        directory = root / _INDEX_DIR
        if self._trust(directory, checkout_root=root, allow_missing=True):
            for name in _INDEX_FILES:
                try:
                    info = (directory / name).lstat()
                except FileNotFoundError:
                    continue
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1:
                    raise ValidationFailed(ErrorCode.REPOSITORY_UNSAFE, "Unsafe CodeGraph index file")
        return root

    @staticmethod
    def _environment() -> dict[str, str]:
        return {
            "PATH": os.pathsep.join(path for path in os.get_exec_path() if Path(path).is_absolute()),
            "LANG": "C.UTF-8",
            "CODEGRAPH_TELEMETRY": "0",
            "DO_NOT_TRACK": "1",
        }

    @staticmethod
    def _run(
        executable: str, args: tuple[str, ...], env: dict[str, str], cancel: CancelToken, timeout: float
    ) -> bytes:
        if timeout <= 0:
            raise SourceBusy("CodeGraph timed out")
        session = ProcessSession((executable, "--no-color", *args), env, cancel, timeout)
        try:
            return session.exchange(b"")
        finally:
            session.close()

    def _status(self, executable: str, root: Path, env: dict[str, str], cancel: CancelToken) -> JsonObject:
        raw = self._run(executable, ("status", "--json", str(root)), env, cancel, 30)
        state = object_value(json.loads(raw))
        if type(state.get("initialized")) is not bool or state.get("projectPath") != str(root):
            raise SourceFailed()
        return cast("JsonObject", state)

    def manage(self, action: CodeGraphAction, checkout: str, *, cancel: CancelToken) -> JsonObject:
        cancel.raise_if_cancelled()
        root = self._checkout(checkout)
        env = self._environment()
        executable = shutil.which("codegraph", path=env["PATH"])
        if executable is None:
            if action == "doctor":
                return {"healthy": False, "installed": False, "message": "Install CodeGraph on this host"}
            raise CapabilityUnavailable(ErrorCode.CAPABILITY_UNAVAILABLE, "CodeGraph is unavailable on PATH")
        if action == "index" and not (root / _INDEX_DIR / _DB).is_file():
            raise PreconditionFailed(
                ErrorCode.INVALID_TRANSITION, "Run skm graph init for this checkout first"
            )
        if action in ("init", "index"):
            self._excludes.update(str(root), add=(_INDEX_DIR + "/",))
        try:
            if action in ("init", "index"):
                flag = "--yes" if action == "init" else "--quiet"
                self._run(executable, (action, flag, str(root)), env, cancel, 600)
            state = self._status(executable, root, env, cancel)
            if action in ("init", "index") and state["initialized"] is not True:
                raise SourceFailed()
        except (OSError, ValueError, RecursionError) as exc:
            message = "CodeGraph timed out" if isinstance(exc, SourceBusy) else "CodeGraph command failed"
            if action == "doctor":
                return {"healthy": False, "installed": True, "message": message}
            raise CapabilityUnavailable(ErrorCode.CAPABILITY_UNAVAILABLE, message) from exc
        if action != "doctor":
            return state
        index = state.get("index")
        message = None
        if state["initialized"] is False:
            message = "Run skm graph init for this checkout"
        elif state.get("worktreeMismatch") or (
            isinstance(index, dict)
            and (index.get("reindexRecommended") or index.get("state") not in (None, "complete"))
        ):
            message = "Run skm graph index to rebuild this checkout's index"
        return {
            "healthy": message is None,
            "installed": True,
            "message": message,
            "status": state,
            "mcp": {"type": "stdio", "command": executable, "args": ["serve", "--mcp", "--path", str(root)]},
        }

    def validate_config(self, config: ResearchSourceConfig) -> tuple[str, ...]:
        problems: list[str] = []
        if config.tier is not ResearchTier.CODEGRAPH:
            problems.append("tier")
        if config.argv or config.env_allow or config.roots:
            problems.append("argv_env_or_roots")
        if not 0 < config.timeout_seconds <= 3600:
            problems.append("timeout_seconds")
        return tuple(problems)

    def search(
        self, config: ResearchSourceConfig, query: SourceQuery, *, cancel: CancelToken
    ) -> RawSourceReply:
        cancel.raise_if_cancelled()
        if self.validate_config(config):
            raise SourceFailed("RESEARCH_SOURCE_INVALID")
        env = self._environment()
        executable = shutil.which("codegraph", path=env["PATH"])
        if executable is None or "\0" in query.text:
            raise SourceFailed()
        deadline = monotonic() + config.timeout_seconds
        limit = min(query.max_documents, 50)
        documents: dict[str, RawDocument] = {}
        digest = sha256()
        indexed = False
        try:
            for mount, checkout in sorted(query.mounts.items()):
                cancel.raise_if_cancelled()
                root = self._checkout(checkout)
                if not (root / _INDEX_DIR / _DB).is_file():
                    continue
                indexed = True
                raw = self._run(
                    executable,
                    ("query", "--path", str(root), "--json", "--limit", str(limit), "--", query.text),
                    env,
                    cancel,
                    deadline - monotonic(),
                )
                digest.update(raw)
                for hit in array_value(json.loads(raw)):
                    if (doc := _document(mount, hit)) is not None:
                        documents.setdefault(doc.origin, doc)
                    if len(documents) >= limit:
                        break
                if len(documents) >= limit:
                    break
        except SourceBusy:
            raise
        except (OSError, ValueError, KeyError, RecursionError, ValidationFailed) as exc:
            raise SourceFailed() from exc
        if not indexed:
            raise SourceFailed()
        return RawSourceReply(tuple(documents.values()), None, (), None, "sha256:" + digest.hexdigest())
