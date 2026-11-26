"""Git repository inspector and ``.skm/project.json`` marker management (adapters §3.3, workspace §6)."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast, overload, override

from skm.adapters.git.runner import GitCommandFailed, GitRunner, validate_repository_trust
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.modules.workspace.domain.checkout_marker import (
    CheckoutMarker,
    marker_from_document,
    marker_to_document,
)
from skm.modules.workspace.ports import MARKER_INVALID, RepositoryInspector

from ._checkout_marker import (
    MARKER_FILENAME,
    MAX_MARKER_BYTES,
    read_marker_at,
    split_marker_relpath,
    write_marker_bytes_nofollow,
)

if TYPE_CHECKING:
    from skm.kernel.clock import Clock
    from skm.modules.workspace.domain.checkout_binding import ObservedCheckout
    from skm.modules.workspace.domain.remote_url import NormalizedRemote

__all__ = ["MARKER_FILENAME", "MAX_MARKER_BYTES", "GitRepositoryInspector"]

_FETCH_SUFFIX: str = " (fetch)"


class GitRepositoryInspector(RepositoryInspector):
    """Git-backed implementation of ``RepositoryInspector`` (adapters §3.3, workspace §6)."""

    def __init__(self, runner: GitRunner | None = None, *, clock: Clock | None = None) -> None:
        if clock is None:
            from skm.platform.system_clock import SystemClock

            clock = SystemClock()
        self._runner = runner if runner is not None else GitRunner()
        self._clock: Clock = clock
        self._local = threading.local()

    @property
    def runner(self) -> GitRunner:
        return self._runner

    @property
    def last_diagnostics(self) -> tuple[str, ...]:
        """Thread-local diagnostics collected during the most recent ``observe`` call."""
        return cast(tuple[str, ...], getattr(self._local, "last_diagnostics", ()))

    def toplevel(self, path: str | Path, *, timeout_s: float | None = None) -> Path:
        """Resolve the Git working-tree root for ``path``, or raise ``REPOSITORY_UNSAFE`` on exit 128."""
        args = ("rev-parse", "--show-toplevel")
        result = self._runner.run(path, args, timeout_s=timeout_s, check=False)
        if result.exit_code == 0:
            raw_top = result.stdout.rstrip("\r\n")
            if raw_top:
                top_path = Path(raw_top)
                validate_repository_trust(top_path, allow_missing=False)
                return Path(os.path.normpath(str(top_path)))
        if result.exit_code == 128 and "not a git repository" in result.stderr.lower():
            raise ValidationFailed(
                ErrorCode.REPOSITORY_UNSAFE,
                "path is not a git repository",
                details={"path": str(path), "reason": "not_a_repository"},
            )
        raise GitCommandFailed(
            argv=self._runner.build_argv(path, args),
            exit_code=result.exit_code,
            stderr_tail=result.stderr,
        )

    def head(self, path: str | Path, *, timeout_s: float | None = None) -> str | None:
        """Resolve ``HEAD`` commit SHA, or ``None`` when ``HEAD`` is unborn."""
        args = ("rev-parse", "--verify", "--quiet", "HEAD")
        result = self._runner.run(path, args, timeout_s=timeout_s, check=False)
        if result.exit_code == 0:
            sha = result.stdout.strip().lower()
            return sha or None
        if result.exit_code in (1, 128):
            return None
        raise GitCommandFailed(
            argv=self._runner.build_argv(path, args),
            exit_code=result.exit_code,
            stderr_tail=result.stderr,
        )

    def remote_urls(self, path: str | Path, *, timeout_s: float | None = None) -> tuple[tuple[str, str], ...]:
        """Return ``(remote_name, redacted_fetch_url)`` pairs sorted deterministically."""
        from skm.modules.workspace.domain.remote_url import redact_remote

        result = self._runner.run(path, ("remote", "-v"), timeout_s=timeout_s, check=True)
        pairs: set[tuple[str, str]] = set()
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line or not line.endswith(_FETCH_SUFFIX):
                continue
            body = line[: -len(_FETCH_SUFFIX)]
            if "\t" not in body:
                continue
            remote_name, fetch_url = body.split("\t", 1)
            remote_name, fetch_url = remote_name.strip(), fetch_url.strip()
            if remote_name and fetch_url:
                pairs.add((remote_name, redact_remote(fetch_url)))
        return tuple(sorted(pairs))

    def remotes(self, path: str | Path, *, timeout_s: float | None = None) -> tuple[NormalizedRemote, ...]:
        """Return normalized fetch remotes sorted deterministically by remote name and URL."""
        from skm.modules.workspace.domain.remote_url import normalize_remote

        dedup_remotes: list[NormalizedRemote] = []
        seen_remotes: set[NormalizedRemote] = set()
        for _remote_name, fetch_url in self.remote_urls(path, timeout_s=timeout_s):
            norm_remote = normalize_remote(fetch_url)
            if norm_remote is not None and norm_remote not in seen_remotes:
                seen_remotes.add(norm_remote)
                dedup_remotes.append(norm_remote)
        return tuple(dedup_remotes)

    def is_dirty(self, path: str | Path, *, timeout_s: float | None = None) -> bool:
        """Return ``True`` if the working tree has staged or unstaged tracked changes."""
        result = self._runner.run(
            path,
            ("status", "--porcelain=v1", "-z", "--untracked-files=no"),
            timeout_s=timeout_s,
            check=True,
        )
        return len(result.stdout) > 0

    def branch_exists(self, path: str | Path, branch: str, *, timeout_s: float | None = None) -> bool:
        """Validate ``branch`` format and check whether ``refs/heads/<branch>`` exists."""
        if not branch or "\x00" in branch or branch.startswith("-"):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "branch name must not be empty or start with '-'",
                details={"branch": branch},
            )
        fmt = self._runner.run(
            path, ("check-ref-format", "--branch", branch), timeout_s=timeout_s, check=False
        )
        if fmt.exit_code != 0:
            return False
        ref_args = ("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")
        ref_check = self._runner.run(path, ref_args, timeout_s=timeout_s, check=False)
        if ref_check.exit_code == 0:
            return True
        if ref_check.exit_code in (1, 128):
            return False
        raise GitCommandFailed(
            argv=self._runner.build_argv(path, ref_args),
            exit_code=ref_check.exit_code,
            stderr_tail=ref_check.stderr,
        )

    @override
    def checkout_path(self, path: str) -> Path:
        return Path(path)

    @override
    def resolve_commit(self, path: str, ref: str) -> str:
        return self.resolve(path, ref)

    @override
    def merge_base(self, path: str, base: str, head: str) -> str:
        base, head = self.resolve(path, base), self.resolve(path, head)
        return self._runner.run(path, ("merge-base", base, head)).stdout.strip().lower()

    def resolve(self, path: str | Path, rev: str, *, timeout_s: float | None = None) -> str:
        """Resolve ``<rev>^{commit}`` to a lowercase commit SHA, or raise ``NOT_FOUND``."""
        if not rev or "\x00" in rev or rev.startswith("-"):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "revision must not be empty or start with '-'",
                details={"rev": rev},
            )
        rev_args = ("rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
        result = self._runner.run(path, rev_args, timeout_s=timeout_s, check=False)
        if result.exit_code == 0:
            sha = result.stdout.strip().lower()
            if sha:
                return sha
        if result.exit_code in (1, 128):
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "git revision does not resolve to a commit",
                details={"rev": rev},
            )
        raise GitCommandFailed(
            argv=self._runner.build_argv(path, rev_args),
            exit_code=result.exit_code,
            stderr_tail=result.stderr,
        )

    @staticmethod
    def read_marker_at(
        toplevel: str | Path, *, marker_relpath: str = MARKER_FILENAME
    ) -> CheckoutMarker | None:
        """Read and validate the checkout marker via descriptor-relative opens."""
        return read_marker_at(toplevel, marker_relpath=marker_relpath)

    def read_marker(
        self, toplevel: str | Path, *, marker_relpath: str = MARKER_FILENAME
    ) -> CheckoutMarker | None:
        """Read and validate ``<toplevel>/<marker_relpath>`` via descriptor-relative ``O_NOFOLLOW``."""
        return self.read_marker_at(toplevel, marker_relpath=marker_relpath)

    @overload
    def write_marker(
        self, path: str | Path, *, marker_relpath: str = MARKER_FILENAME, marker: CheckoutMarker
    ) -> None: ...

    @overload
    def write_marker(
        self,
        path: str | Path,
        marker: CheckoutMarker | Mapping[str, Any],
        *,
        marker_relpath: str = MARKER_FILENAME,
    ) -> None: ...

    @override
    def write_marker(
        self,
        path: str | Path,
        marker: CheckoutMarker | Mapping[str, Any] | None = None,
        *,
        marker_relpath: str = MARKER_FILENAME,
    ) -> None:
        """Atomically write ``<path>/<marker_relpath>`` via ``dir_fd`` and ``O_NOFOLLOW``."""
        split_marker_relpath(marker_relpath)
        validate_repository_trust(path, allow_missing=False)
        top_path = Path(os.path.normpath(str(path)))
        if marker is None:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "checkout marker is required")
        marker_obj = marker if isinstance(marker, CheckoutMarker) else marker_from_document(marker)
        doc = marker_to_document(marker_obj)
        payload = (json.dumps(dict(doc), indent=2, sort_keys=True) + "\n").encode("utf-8")
        write_marker_bytes_nofollow(top_path, marker_relpath, payload)

    @override
    def observe_with_diagnostics(
        self,
        path: str | Path,
        *,
        marker_relpath: str = MARKER_FILENAME,
        timeout_seconds: float | None = 60.0,
    ) -> tuple[ObservedCheckout, tuple[str, ...]]:
        """Observe ``path`` and return ``(ObservedCheckout, diagnostics)``."""
        from skm.modules.workspace.domain.checkout_binding import ObservedCheckout, normalize_locator

        split_marker_relpath(marker_relpath)
        now = self._clock.now()
        if not validate_repository_trust(path, allow_missing=True):
            self._local.last_diagnostics = ()
            return ObservedCheckout(False, None, (), None, None, now, None), ()

        try:
            top_path = self.toplevel(path, timeout_s=timeout_seconds)
        except ValidationFailed as exc:
            if exc.code is ErrorCode.REPOSITORY_UNSAFE and exc.details.get("reason") == "not_a_repository":
                self._local.last_diagnostics = ()
                return ObservedCheckout(True, None, (), None, None, now, None), ()
            raise

        normalized_top = normalize_locator(str(top_path))
        head_sha = self.head(top_path, timeout_s=timeout_seconds)
        remotes = self.remotes(top_path, timeout_s=timeout_seconds)
        dirty_flag = self.is_dirty(top_path, timeout_s=timeout_seconds)
        diagnostics: list[str] = []
        try:
            marker = self.read_marker(top_path, marker_relpath=marker_relpath)
        except ValidationFailed as exc:
            if exc.code is ErrorCode.SCHEMA_INVALID:
                marker = None
                diagnostics.append(MARKER_INVALID)
            else:
                raise

        diag_tuple = tuple(diagnostics)
        self._local.last_diagnostics = diag_tuple
        observed = ObservedCheckout(True, normalized_top, remotes, head_sha, marker, now, dirty_flag)
        return observed, diag_tuple

    @override
    def observe(
        self,
        path: str | Path,
        *,
        marker_relpath: str = MARKER_FILENAME,
        timeout_seconds: float = 60.0,
    ) -> ObservedCheckout:
        """Observe a local filesystem checkout path (workspace §6)."""
        observed, _diagnostics = self.observe_with_diagnostics(
            path,
            marker_relpath=marker_relpath,
            timeout_seconds=timeout_seconds,
        )
        return observed
