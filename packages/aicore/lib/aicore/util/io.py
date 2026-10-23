"""Shared stdlib-only helpers for atomic file writes and resilient JSON reads."""
import copy
import errno
import json
import os
import shutil
from datetime import date
from pathlib import Path
from typing import Callable, Optional


def backup_file(path, *, suffix=".bak"):
    """Copy an existing file to ``<path><suffix>`` and return its path."""
    path = Path(path)
    if not path.exists():
        return None
    bak = path.with_name(path.name + suffix)
    shutil.copy2(path, bak)
    return bak


def safe_load_json(path, default=None, *, on_error: Optional[Callable] = None):
    """Read JSON, returning ``default`` for a missing or malformed file."""
    path = Path(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        if on_error is not None:
            on_error(e)
        return default


def read_ndjson_iter(path):
    """Yield dict records from NDJSON, skipping empty or malformed records."""
    path = Path(path)
    if not path.is_file():
        return
    with open(path, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except (ValueError, TypeError):
                continue
            if isinstance(rec, dict):
                yield rec


def read_ndjson(path):
    """Read an NDJSON file into a list of dictionaries."""
    return list(read_ndjson_iter(path))


def load_json_db(path, default, *, max_version=None):
    """Load a JSON database with backup-and-default recovery for corrupt files."""
    from .term import die, warn
    path = Path(path)
    if not path.exists():
        return copy.deepcopy(default)
    try:
        db = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        backup = path.with_name(f"{path.name}.corrupt.{date.today().isoformat()}")
        path.rename(backup)
        warn(f"{path} damaged → saved in {backup.name} (starting again)")
        return copy.deepcopy(default)
    if max_version is not None and isinstance(db, dict) and db.get("version", 1) > max_version:
        die(f"{path} is overwritten by a newer version - update the repository (git pull) and "
            f"restart installation")
    return db


def assert_safe_replace_target(path):
    """Reject unsafe existing targets for ``os.replace``.

    Symlinks, nonregular files, and hard links are unsafe; a missing target is valid.
    """
    path = Path(path)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    if os.path.islink(path):
        raise OSError(f"{path}: unsafe target for atomic replacement - symbolic link")
    if not os.path.isfile(path):
        raise OSError(f"{path}: unsafe target for atomic replacement - non-regular file")
    if st.st_nlink != 1:
        raise OSError(
            f"{path}: unsafe target for atomic replacement - st_nlink={st.st_nlink} "
            f"(hard link)"
        )


def atomic_write_text(path, text, *, encoding="utf-8", mode=None, check_target=True):
    """Atomically and durably write text (see :func:`_replace`); the new file gets ``mode``, else the umask's.

    ``check_target=False`` lets a symlink target be replaced by a regular file.
    """
    _replace(Path(path), text.encode(encoding), mode=mode, check_target=check_target, private=False)


def atomic_write_json(path, data, *, version=None, indent=2, mode=None, check_target=True):
    """Atomically write JSON with a final newline and optional leading version."""
    if version is not None and isinstance(data, dict):
        rest = {k: v for k, v in data.items() if k != "version"}
        data = {"version": version, **rest}
    atomic_write_text(path, json.dumps(data, indent=indent, ensure_ascii=False) + "\n",
                      mode=mode, check_target=check_target)


def durable_replace(path: "str | os.PathLike[str]", data: bytes, *, mode: Optional[int] = None) -> None:
    """Replace ``path`` with ``data`` (bytes) crash-safely, the new file private (``0600``) unless ``mode`` says
    otherwise; an unsafe target (symlink, hard link, not a regular file) is refused."""
    _replace(Path(path), data, mode=mode, check_target=True, private=True)


def _replace(path, data, *, mode, check_target, private):
    """A unique temporary file in the same folder (so the same filesystem), created exclusively and without
    following a link (a planted ``*.tmp`` symlink is never written through), flushed and ``fsync``-ed, then
    ``os.replace`` and an ``fsync`` of the folder. Two writers of one file never share a temporary file. A failure
    at any point leaves the old file untouched and removes the temporary one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if check_target:
        assert_safe_replace_target(path)
    name = path.with_name(f".{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    handle = os.open(str(name), flags, 0o600 if private else 0o666)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            os.chmod(name, mode)
        os.replace(name, path)
    except BaseException:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass
        raise
    _fsync_folder(path.parent)


# A filesystem that cannot open or fsync a folder says so with one of these; any other error (EIO, ENOSPC) means the
# rename may not be durable and is raised, so a caller never acknowledges a document that is not on disk.
_NO_FOLDER_SYNC = {errno.EINVAL, errno.EOPNOTSUPP, getattr(errno, "ENOTSUP", errno.EOPNOTSUPP), errno.EACCES,
                   errno.EPERM, errno.EISDIR, errno.EBADF}


def _fsync_folder(folder):
    """Make a rename in ``folder`` durable; a filesystem that cannot fsync a folder is left as it is."""
    try:
        handle = os.open(str(folder), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError as error:
        if error.errno in _NO_FOLDER_SYNC:
            return
        raise
    try:
        os.fsync(handle)
    except OSError as error:
        if error.errno not in _NO_FOLDER_SYNC:
            raise
    finally:
        os.close(handle)
