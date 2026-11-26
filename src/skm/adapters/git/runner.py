"""Safe Git subprocess runner and pre-execution repository trust boundary (adapters §3.2, workspace §6)."""

from __future__ import annotations

import errno
import os
import re
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, NoReturn

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, CapabilityUnavailable, InternalError, ValidationFailed
from skm.kernel.json_types import JsonValue

from .host_inputs import read_pointer as _read_bounded_nofollow
from .host_inputs import validate_config

if TYPE_CHECKING:
    from skm.platform.logging.redaction import Redactor
    from skm.platform.process import runner as process_runner

__all__ = [
    "GIT_ENV_ALLOWLIST",
    "GIT_ENV_OVERRIDES",
    "GLOBAL_GIT_ARGS",
    "MAX_GITFILE_BYTES",
    "MIN_GIT_VERSION",
    "GitCommandFailed",
    "GitResult",
    "GitRunner",
    "parse_git_version",
    "redact_git_text",
    "validate_repository_trust",
]

GLOBAL_GIT_ARGS: tuple[str, ...] = (
    "-c",
    "protocol.allow=never",
    "-c",
    "protocol.file.allow=never",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "credential.helper=",
    "-c",
    "advice.detachedHead=false",
    "-c",
    "gc.auto=0",
    "-c",
    "maintenance.auto=false",
    "-c",
    "core.quotepath=false",
    "-c",
    "commit.gpgsign=false",
    "-c",
    "tag.gpgsign=false",
    "-c",
    "core.autocrlf=false",
    "-c",
    "core.untrackedCache=false",
)

GIT_ENV_ALLOWLIST: tuple[str, ...] = ("PATH", "HOME", "USER", "LOGNAME", "TMPDIR", "SYSTEMROOT")

GIT_ENV_OVERRIDES: Mapping[str, str] = MappingProxyType(
    {
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/bin/false",
        "SSH_ASKPASS": "/bin/false",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_PAGER": "cat",
        "PAGER": "cat",
        "GIT_EDITOR": "true",
        "GIT_MERGE_AUTOEDIT": "no",
        "LC_ALL": "C",
        "LANG": "C",
    }
)

MIN_GIT_VERSION: tuple[int, int] = (2, 38)
MAX_GITFILE_BYTES: int = 4096
_STDERR_TAIL_CHARS: int = 2000
_DEFAULT_MAX_OUTPUT_BYTES: int = 1_048_576

_URL_USERINFO_RE = re.compile(
    r"((?:https?|ssh|git|git\+ssh|ssh\+git|ftps?)://)([^/\s@]+)(@)",
    re.IGNORECASE,
)
_SCP_USERINFO_RE = re.compile(r"(^|(?<=[\s\"'`]))([^\s@:/]+(?::[^\s@/]*)?)@([A-Za-z0-9._-]+:[^\s\"'`]+)")
_GIT_VERSION_RE = re.compile(r"git\s+version\s+((\d+)\.(\d+)(?:\.(\d+))?[^\r\n]*)", re.IGNORECASE)
_GIT_METADATA_ENTRIES: tuple[str, ...] = ("HEAD", "config", "hooks", "commondir", "gitdir", "objects", "refs")


@cache
def _redactor() -> Redactor:
    from skm.platform.logging.redaction import Redactor

    return Redactor()


def _default_exec_path() -> str:
    exec_dirs = [entry for entry in os.get_exec_path() if entry]
    return os.pathsep.join(exec_dirs) if exec_dirs else os.defpath


def _unsafe(message: str, **details: JsonValue) -> NoReturn:
    raise ValidationFailed(ErrorCode.REPOSITORY_UNSAFE, message, details=details or None)


def redact_git_text(text: str) -> str:
    """Redact credentials and URL userinfo from Git argv, stdout, or stderr strings."""

    def _replace_userinfo(match: re.Match[str]) -> str:
        scheme, userinfo, at_sign = match.group(1), match.group(2), match.group(3)
        if scheme.lower() in ("ssh://", "git+ssh://", "ssh+git://") and userinfo == "git":
            return match.group(0)
        return f"{scheme}[REDACTED]{at_sign}"

    def _replace_scp_userinfo(match: re.Match[str]) -> str:
        prefix, userinfo, target = match.group(1), match.group(2), match.group(3)
        if userinfo == "git":
            return match.group(0)
        return f"{prefix}[REDACTED]@{target}"

    redacted = _SCP_USERINFO_RE.sub(_replace_scp_userinfo, _URL_USERINFO_RE.sub(_replace_userinfo, text))
    return _redactor().text(redacted)


@dataclass(frozen=True, slots=True)
class GitResult:
    """Completed Git subprocess result."""

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class GitBytesResult:
    exit_code: int
    stdout: bytes
    stderr: bytes
    duration_ms: int


class GitCommandFailed(InternalError):
    """Raised when a Git command exits non-zero with ``check=True``."""

    def __init__(
        self,
        argv: Sequence[str],
        exit_code: int,
        stderr_tail: str,
        message: str | None = None,
    ) -> None:
        redacted_argv = [redact_git_text(str(item)) for item in argv]
        argv_json: list[JsonValue] = list(redacted_argv)
        redacted_tail = redact_git_text(stderr_tail)[-_STDERR_TAIL_CHARS:]
        super().__init__(
            ErrorCode.INTERNAL_ERROR,
            message or f"git command failed with exit code {exit_code}",
            details={"argv": argv_json, "exit_code": exit_code, "stderr_tail": redacted_tail},
        )
        self.argv: tuple[str, ...] = tuple(redacted_argv)
        self.exit_code: int = exit_code
        self.stderr_tail: str = redacted_tail


def parse_git_version(raw: str) -> tuple[tuple[int, int, int], str]:
    """Parse ``git --version`` output into ``((major, minor, patch), version_string)``."""
    match = _GIT_VERSION_RE.search(raw)
    if match is None:
        found = raw.strip() or "<empty>"
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "git >= 2.38 required",
            details={"found": found},
        )
    major = int(match.group(2))
    minor = int(match.group(3))
    patch = int(match.group(4)) if match.group(4) is not None else 0
    return (major, minor, patch), f"{major}.{minor}.{patch}"


def _require_owned_by_current_uid(st: os.stat_result, path: Path) -> None:
    euid = os.geteuid() if hasattr(os, "geteuid") else None
    if euid is not None and st.st_uid != euid:
        _unsafe(
            "repository path is not owned by the current effective UID",
            path=str(path),
            owner_uid=st.st_uid,
            expected_uid=euid,
        )


def _ensure_no_symlink_ancestors(path: Path, *, allow_missing_leaf: bool = False) -> os.stat_result | None:
    raw = str(path)
    if not raw or "\x00" in raw or "\n" in raw or "\r" in raw:
        _unsafe("checkout path contains invalid control characters")
    if not path.is_absolute():
        _unsafe("checkout path must be absolute", path=raw)
    current = Path(path.anchor)
    parts = path.parts[1:]
    if not parts:
        try:
            st = os.lstat(current)
        except OSError:
            _unsafe("checkout root cannot be inspected", path=str(current))
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            _unsafe("checkout root is not a real directory", path=str(current))
        return st

    last_st: os.stat_result | None = None
    for index, part in enumerate(parts):
        if part in ("", "."):
            continue
        current = current.parent if part == ".." else current / part
        is_last = index == len(parts) - 1
        try:
            st = os.lstat(current)
        except FileNotFoundError:
            if allow_missing_leaf:
                return None
            _unsafe("repository path does not exist", path=str(current))
        except OSError as exc:
            _unsafe("repository path cannot be inspected", path=str(current), errno=exc.errno)
        if stat.S_ISLNK(st.st_mode):
            _unsafe("repository path must not traverse symlinks", path=str(current))
        if not stat.S_ISDIR(st.st_mode):
            _unsafe("repository path component is not a directory", path=str(current))
        if is_last:
            last_st = st
    return last_st


def _resolve_real_git_dir(base_dir: Path, raw_target: str) -> Path:
    if not raw_target or "\x00" in raw_target or "\n" in raw_target or "\r" in raw_target:
        _unsafe("gitdir pointer target is invalid")
    candidate = Path(raw_target)
    if candidate.is_absolute():
        st = _ensure_no_symlink_ancestors(candidate, allow_missing_leaf=False)
        if st is None:
            _unsafe("gitdir target does not exist", path=str(candidate))
        resolved = Path(os.path.normpath(str(candidate)))
        _require_owned_by_current_uid(st, resolved)
        return resolved

    _ensure_no_symlink_ancestors(base_dir, allow_missing_leaf=False)
    current = base_dir
    for part in candidate.parts:
        if part in ("", "."):
            continue
        current = current.parent if part == ".." else current / part
        try:
            st = os.lstat(current)
        except OSError:
            _unsafe("gitdir target does not exist", path=str(current))
        if stat.S_ISLNK(st.st_mode):
            _unsafe("gitdir target must not traverse symlinks", path=str(current))
        if not stat.S_ISDIR(st.st_mode):
            _unsafe("gitdir target is not a directory", path=str(current))
    final_st = os.lstat(current)
    _require_owned_by_current_uid(final_st, current)
    return current


def _validate_objects_info(git_dir: Path) -> None:
    objects_info = git_dir / "objects" / "info"
    try:
        info_st = os.lstat(objects_info)
    except FileNotFoundError:
        return
    except OSError:
        _unsafe("git objects/info cannot be inspected", path=str(objects_info))
    if stat.S_ISLNK(info_st.st_mode) or not stat.S_ISDIR(info_st.st_mode):
        _unsafe("git objects/info must be a real directory", path=str(objects_info))
    _require_owned_by_current_uid(info_st, objects_info)
    for alt_name in ("alternates", "http-alternates"):
        alt_path = objects_info / alt_name
        try:
            os.lstat(alt_path)
        except FileNotFoundError:
            continue
        except OSError:
            _unsafe("git alternates file cannot be inspected", path=str(alt_path))
        _unsafe(f"git objects/info/{alt_name} is not permitted", path=str(alt_path))


def _validate_git_dir_contents(git_dir: Path) -> None:
    try:
        dir_st = os.lstat(git_dir)
    except OSError:
        _unsafe("git metadata directory cannot be inspected", path=str(git_dir))
    if stat.S_ISLNK(dir_st.st_mode) or not stat.S_ISDIR(dir_st.st_mode):
        _unsafe("git metadata directory is not a real directory", path=str(git_dir))
    _require_owned_by_current_uid(dir_st, git_dir)

    for name in _GIT_METADATA_ENTRIES:
        entry = git_dir / name
        try:
            entry_st = os.lstat(entry)
        except FileNotFoundError:
            continue
        except OSError:
            _unsafe("git metadata entry cannot be inspected", path=str(entry))
        if stat.S_ISLNK(entry_st.st_mode):
            _unsafe(f"git metadata entry '{name}' must not be a symlink", path=str(entry))
        _require_owned_by_current_uid(entry_st, entry)
        if name == "hooks" and stat.S_ISDIR(entry_st.st_mode):
            try:
                with os.scandir(entry) as it:
                    for hook in it:
                        hook_st = hook.stat(follow_symlinks=False)
                        if stat.S_ISLNK(hook_st.st_mode):
                            _unsafe("git hook entry must not be a symlink", path=hook.path)
                        _require_owned_by_current_uid(hook_st, Path(hook.path))
            except ValidationFailed:
                raise
            except OSError:
                _unsafe("git hooks directory cannot be inspected", path=str(entry))
    validate_config(git_dir / "config")
    validate_config(git_dir / "config.worktree")
    _validate_objects_info(git_dir)


def _validate_dot_git(repo_root: Path, dot_git: Path, *, required: bool = False) -> None:
    try:
        git_st = os.lstat(dot_git)
    except FileNotFoundError:
        if required:
            _unsafe("bound checkout has no .git entry", path=str(dot_git))
        return
    except OSError:
        _unsafe("cannot inspect .git entry", path=str(dot_git))

    if stat.S_ISLNK(git_st.st_mode):
        _unsafe(".git must not be a symlink", path=str(dot_git))
    _require_owned_by_current_uid(git_st, dot_git)

    if stat.S_ISDIR(git_st.st_mode):
        resolved_gitdir = dot_git
    elif stat.S_ISREG(git_st.st_mode):
        content = _read_bounded_nofollow(dot_git, max_bytes=MAX_GITFILE_BYTES)
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if len(lines) != 1 or not lines[0].startswith("gitdir:"):
            _unsafe("invalid .git gitdir pointer file", path=str(dot_git))
        gitdir_target = lines[0][len("gitdir:") :].strip()
        resolved_gitdir = _resolve_real_git_dir(repo_root, gitdir_target)
    else:
        _unsafe(".git must be a directory or regular gitdir file", path=str(dot_git))

    _validate_git_dir_contents(resolved_gitdir)

    commondir_file = resolved_gitdir / "commondir"
    try:
        commondir_st = os.lstat(commondir_file)
    except FileNotFoundError:
        commondir_st = None
    except OSError:
        _unsafe("cannot inspect commondir file", path=str(commondir_file))

    if commondir_st is not None:
        if stat.S_ISLNK(commondir_st.st_mode) or not stat.S_ISREG(commondir_st.st_mode):
            _unsafe("commondir must be a regular file", path=str(commondir_file))
        commondir_text = _read_bounded_nofollow(commondir_file, max_bytes=MAX_GITFILE_BYTES)
        commondir_lines = [line.strip() for line in commondir_text.splitlines() if line.strip()]
        if len(commondir_lines) != 1:
            _unsafe("invalid commondir pointer file", path=str(commondir_file))
        resolved_commondir = _resolve_real_git_dir(resolved_gitdir, commondir_lines[0])
        _validate_git_dir_contents(resolved_commondir)


def _present(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _validate_bound_checkout(target: Path, root: Path) -> None:
    if not target.is_relative_to(root):
        _unsafe("path is outside the bound checkout", path=str(target), checkout=str(root))
    _require_owned_by_current_uid(root.lstat(), root)
    current = target
    while current != root:
        bare = _present(current / "HEAD") and (
            _present(current / "commondir")
            or ((current / "objects").is_dir() and (current / "refs").is_dir())
        )
        if _present(current / ".git") or bare:
            _unsafe("nested repository in the bound checkout", path=str(current))
        current = current.parent
    _validate_dot_git(root, root / ".git", required=True)


def validate_repository_trust(
    path: str | Path, *, allow_missing: bool = False, checkout_root: Path | None = None
) -> bool:
    """Validate the path and Git metadata, using an explicit checkout boundary when supplied.

    Returns ``True`` if ``path`` exists and is a safe directory, or ``False`` when
    ``allow_missing=True`` and ``path`` does not exist (with no symlink ancestors).
    Raises ``ValidationFailed(ErrorCode.REPOSITORY_UNSAFE, ...)`` on any violation.
    """
    raw = str(path)
    if not raw or "\x00" in raw or "\n" in raw or "\r" in raw:
        _unsafe("checkout path contains invalid characters")
    target = Path(raw)
    if target.parts[:2] == ("/", ".skm-checkout"):
        _unsafe("opaque checkout references require a verified machine binding")
    if not target.is_absolute():
        _unsafe("checkout path must be absolute", path=raw)
    leaf_st = _ensure_no_symlink_ancestors(target, allow_missing_leaf=allow_missing)
    if leaf_st is None:
        return False

    norm_target = Path(os.path.normpath(str(target)))
    _require_owned_by_current_uid(leaf_st, norm_target)
    if checkout_root is not None:
        _validate_bound_checkout(norm_target, checkout_root)
        return True

    for candidate in (norm_target, *norm_target.parents):
        dot_git = candidate / ".git"
        try:
            os.lstat(dot_git)
        except FileNotFoundError:
            continue
        cand_st = os.lstat(candidate)
        _require_owned_by_current_uid(cand_st, candidate)
        _validate_dot_git(candidate, dot_git)
    return True


class GitRunner:
    """Hardened wrapper over ``skm.platform.process.runner`` for Git commands (adapters §3.2)."""

    def __init__(
        self,
        git_binary: str = "git",
        *,
        base_env: Mapping[str, str] | None = None,
        env: Mapping[str, str] | None = None,
        default_timeout_s: float = 60.0,
        max_output_bytes: int = _DEFAULT_MAX_OUTPUT_BYTES,
        checkout_root: Path | None = None,
    ) -> None:
        if not git_binary or "\x00" in git_binary:
            raise ValueError("git_binary must be a non-empty string without NUL")
        self._git_binary = git_binary
        source_env = base_env if base_env is not None else env
        self._base_env: Mapping[str, str] = (
            dict(source_env) if source_env is not None else {"PATH": _default_exec_path()}
        )
        self._default_timeout_s = float(default_timeout_s)
        self._max_output_bytes = int(max_output_bytes)
        self._checkout_root = checkout_root

    @property
    def git_binary(self) -> str:
        return self._git_binary

    def build_environment(
        self,
        base_env: Mapping[str, str] | None = None,
        *,
        allow_ssh_agent: bool = False,
    ) -> dict[str, str]:
        """Construct the sanitized Git subprocess environment."""
        from skm.platform.process.environment import build_env

        source = base_env if base_env is not None else self._base_env
        allow = (
            (*GIT_ENV_ALLOWLIST, "SSH_AUTH_SOCK", "SSH_AGENT_PID") if allow_ssh_agent else GIT_ENV_ALLOWLIST
        )
        env = build_env(source, allow=allow, extra=GIT_ENV_OVERRIDES)
        if not env.get("PATH"):
            env["PATH"] = _default_exec_path()
        return env

    def build_argv(self, cwd: str | Path, args: Sequence[str]) -> list[str]:
        """Construct the hardened Git argv list for ``cwd`` and ``args``."""
        argv = [self._git_binary, *GLOBAL_GIT_ARGS, "-C", str(cwd)]
        if self._checkout_root is not None:
            if not args or args[0].startswith("-"):
                raise ValueError("bound Git invocations require a subcommand")
            # Pin Git to the metadata validated for this checkout before any subprocess starts.
            argv.extend((f"--git-dir={self._checkout_root / '.git'}", f"--work-tree={self._checkout_root}"))
        return [*argv, *map(str, args)]

    def _validate_cwd(self, cwd: str | Path) -> None:
        if self._checkout_root is None:
            validate_repository_trust(cwd, allow_missing=False)
        else:
            validate_repository_trust(cwd, checkout_root=self._checkout_root)

    def run(
        self,
        cwd: str | Path,
        args: Sequence[str],
        *,
        timeout_s: float | None = None,
        check: bool = True,
        allow_ssh_agent: bool = False,
    ) -> GitResult:
        """Validate ``cwd`` trust boundary and execute a Git command without shell interpolation."""
        raw = self.run_bytes(cwd, args, timeout_s=timeout_s, check=check, allow_ssh_agent=allow_ssh_agent)
        return GitResult(
            raw.exit_code,
            raw.stdout.decode("utf-8", "replace"),
            raw.stderr.decode("utf-8", "replace"),
            raw.duration_ms,
        )

    def run_bytes(
        self,
        cwd: str | Path,
        args: Sequence[str],
        *,
        stdin: bytes | None = None,
        env: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
        check: bool = True,
        allow_ssh_agent: bool = False,
    ) -> GitBytesResult:
        self._validate_cwd(cwd)
        target = Path(os.path.normpath(str(cwd)))
        full_argv = self.build_argv(target, args)
        child_env = self.build_environment(allow_ssh_agent=allow_ssh_agent)
        if env:
            if not set(env) <= {
                "GIT_INDEX_FILE",
                "GIT_AUTHOR_NAME",
                "GIT_AUTHOR_EMAIL",
                "GIT_COMMITTER_NAME",
                "GIT_COMMITTER_EMAIL",
                "GIT_AUTHOR_DATE",
                "GIT_COMMITTER_DATE",
            }:
                raise ValueError("unsafe Git environment override")
            child_env.update(env)
        effective_timeout = self._default_timeout_s if timeout_s is None else float(timeout_s)
        proc = self._execute(full_argv, cwd=target, env=child_env, timeout_s=effective_timeout, stdin=stdin)
        if proc.stdout_truncated or proc.stderr_truncated:
            raise GitCommandFailed(full_argv, proc.exit_code, "Git output exceeded capture limit")
        if check and proc.exit_code != 0:
            raise GitCommandFailed(full_argv, proc.exit_code, proc.stderr.decode("utf-8", "replace"))
        return GitBytesResult(
            proc.exit_code, proc.stdout, proc.stderr, max(0, round(proc.duration_seconds * 1000))
        )

    def check_version(
        self,
        cwd: str | Path | None = None,
        *,
        timeout_s: float = 10.0,
    ) -> tuple[int, int, int]:
        """Run ``git --version`` and verify Git >= 2.38."""
        workdir = Path(os.path.normpath(str(cwd))) if cwd is not None else Path("/")
        if cwd is not None:
            self._validate_cwd(workdir)
        argv = [self._git_binary, "--version"]
        proc = self._execute(argv, cwd=workdir, env=self.build_environment(), timeout_s=timeout_s)
        stdout_text = proc.stdout.decode("utf-8", errors="replace")
        stderr_text = proc.stderr.decode("utf-8", errors="replace")
        if proc.exit_code != 0:
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "git --version probe failed",
                details={
                    "tool": "git",
                    "exit_code": proc.exit_code,
                    "stderr_tail": redact_git_text(stderr_text)[-_STDERR_TAIL_CHARS:],
                },
            )
        version, version_str = parse_git_version(stdout_text)
        if (version[0], version[1]) < MIN_GIT_VERSION:
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "git >= 2.38 required",
                details={"found": version_str},
            )
        return version

    def _execute(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        timeout_s: float,
        stdin: bytes | None = None,
    ) -> process_runner.ProcessResult:
        from skm.platform.process import runner as process_runner

        redacted_argv: list[JsonValue] = [redact_git_text(str(item)) for item in argv]
        try:
            proc = process_runner.run(
                argv,
                cwd=cwd,
                env=env,
                timeout_seconds=timeout_s,
                stdin=stdin,
                max_stdout_bytes=self._max_output_bytes,
                max_stderr_bytes=self._max_output_bytes,
            )
        except TimeoutError as exc:
            raise BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE,
                "git command timed out",
                details={"tool": "git", "argv": redacted_argv},
            ) from exc
        except (FileNotFoundError, PermissionError) as exc:
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "git executable is not available",
                details={"tool": "git"},
            ) from exc
        except OSError as exc:
            if exc.errno in {errno.ENOENT, errno.EACCES, errno.ENOEXEC, errno.ENOTDIR}:
                raise CapabilityUnavailable(
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                    "git executable is not available",
                    details={"tool": "git"},
                ) from exc
            raise

        if proc.timed_out:
            raise BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE,
                "git command timed out",
                details={"tool": "git", "argv": redacted_argv},
            )
        return proc
