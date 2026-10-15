"""Shared stdlib-only helpers for atomic file writes and resilient JSON reads."""
import copy
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
    """Atomically write text through a sibling temporary file.

    Optionally set final permissions and reject unsafe replacement targets.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding=encoding)
        if mode is not None:
            os.chmod(tmp, mode)
        if check_target:
            assert_safe_replace_target(path)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def atomic_write_json(path, data, *, version=None, indent=2, mode=None, check_target=True):
    """Atomically write JSON with a final newline and optional leading version."""
    if version is not None and isinstance(data, dict):
        rest = {k: v for k, v in data.items() if k != "version"}
        data = {"version": version, **rest}
    atomic_write_text(path, json.dumps(data, indent=indent, ensure_ascii=False) + "\n",
                      mode=mode, check_target=check_target)


def durable_replace(path, data, *, mode=None):
    """Replace ``path`` with ``data`` (bytes) crash-safely: a unique temporary file in the same folder (so the same
    filesystem), flushed and ``fsync``-ed, then ``os.replace`` and an ``fsync`` of the folder. A failure at any point
    leaves the old file untouched and removes the temporary one; an unsafe target (symlink, hard link, not a regular
    file) is refused like :func:`atomic_write_text` does."""
    import tempfile

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    assert_safe_replace_target(path)
    handle, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
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
    try:
        folder = os.open(str(path.parent), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(folder)
    except OSError:
        pass
    finally:
        os.close(folder)
