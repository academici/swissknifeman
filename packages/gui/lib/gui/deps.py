"""Third-party Python packages of the gui HTTP backend without pip or a virtual environment (decision D11).

``requirements.lock`` pins every package as one ``py3-none-any`` wheel with its sha256. :func:`ensure` installs the
set into ``cache_dir("gui")/pydeps/py<major><minor>-<lock digest>``: with ``pip --require-hashes --target`` when pip
works, otherwise by itself from the PyPI JSON API (a wheel is accepted only when its sha256 is the one of the lock
line and its tags are pure Python; an archive member with an absolute path or ``..`` is refused). The install goes
to a sibling temporary folder and replaces the target in one ``os.replace``; a failure removes the partial folder.
:func:`activate` puts a complete folder first on ``sys.path``; only ``lib/gui/http`` imports what it provides.

stdlib only, and importable on Python 3.9 (the CLI imports it before its own version check matters).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import List, Mapping, NamedTuple, Optional

from aicore.state.locations import cache_dir

from .errors import GuiError

CODE = "GUI_DEPS_UNAVAILABLE"
LOCK = Path(__file__).resolve().parents[2] / "requirements.lock"
PYPI = "https://pypi.org"
ENV_DIR = "GUI_PYDEPS_DIR"
COMPLETE = ".complete"
TIMEOUT_S = 30
MAX_WHEEL_BYTES = 64 * 1024 * 1024
HINT = "run `gui deps ensure` (needs network once)"


class GuiDepsError(GuiError):
    """``GUI_DEPS_UNAVAILABLE``: the locked packages are not installed and could not be installed."""

    def __init__(self, message: str) -> None:
        super().__init__(CODE, message)


class Requirement(NamedTuple):
    name: str
    version: str
    sha256: str


def read_lock(lock_path: Path = LOCK) -> List[Requirement]:
    """The pinned wheels of the lock: ``name==version --hash=sha256:<hex>`` per line; ``#`` starts a comment."""
    found: List[Requirement] = []
    try:
        text = Path(lock_path).read_text(encoding="utf-8")
    except OSError as error:
        raise GuiDepsError(f"cannot read {lock_path}: {error.strerror}") from None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        pin, hashes = parts[0], [part for part in parts[1:] if part.startswith("--hash=sha256:")]
        name, sep, version = pin.partition("==")
        digest = hashes[0][len("--hash=sha256:"):] if len(hashes) == 1 else ""
        if not sep or not name or not version or len(parts) != 2 or len(digest) != 64 \
                or any(char not in "0123456789abcdef" for char in digest):
            raise GuiDepsError(f"{lock_path}:{number}: expected `name==version --hash=sha256:<hex>`")
        found.append(Requirement(name, version, digest))
    if not found:
        raise GuiDepsError(f"{lock_path}: no requirements")
    return found


def lock_digest(lock_path: Path = LOCK) -> str:
    """The first 16 hex characters of the sha256 of the lock file: the name of its install folder."""
    try:
        return hashlib.sha256(Path(lock_path).read_bytes()).hexdigest()[:16]
    except OSError as error:
        raise GuiDepsError(f"cannot read {lock_path}: {error.strerror}") from None


def site_dir(env: Optional[Mapping[str, str]] = None, *, lock_path: Path = LOCK) -> Path:
    """The install folder of the lock: ``$GUI_PYDEPS_DIR`` (absolute) or the per-lock folder in the gui cache."""
    environment = os.environ if env is None else env
    override = environment.get(ENV_DIR, "")
    if override:
        if not os.path.isabs(override):
            raise GuiDepsError(f"{ENV_DIR} must be an absolute path, got {override!r}")
        return Path(override)
    tag = f"py{sys.version_info[0]}{sys.version_info[1]}-{lock_digest(lock_path)}"
    return cache_dir("gui", env=environment) / "pydeps" / tag


def is_complete(folder: Path, lock_path: Path = LOCK) -> bool:
    """Whether ``folder`` holds a finished install of exactly this lock."""
    try:
        return (Path(folder) / COMPLETE).read_text(encoding="utf-8").strip() == lock_digest(lock_path)
    except OSError:
        return False


def ensure(env: Optional[Mapping[str, str]] = None, *, offline: bool = False, lock_path: Path = LOCK,
           index_url: str = PYPI, pip: Optional[bool] = None) -> Path:
    """Install the lock once and return its folder. ``pip=None`` uses pip when it works; ``offline`` never downloads."""
    target = site_dir(env, lock_path=lock_path)
    if is_complete(target, lock_path):
        return target
    if offline:
        raise GuiDepsError(f"{target} is not installed and offline mode forbids downloading; {HINT}")
    requirements = read_lock(lock_path)
    digest = lock_digest(lock_path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        work = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=str(target.parent)))
    except OSError as error:
        raise GuiDepsError(f"cannot create {target.parent}: {error.strerror}") from None
    try:
        if _pip_works() if pip is None else pip:
            _pip_install(lock_path, work)
        else:
            for requirement in requirements:
                _install_wheel(requirement, work, index_url)
        (work / COMPLETE).write_text(digest + "\n", encoding="utf-8")
        if target.exists() and not is_complete(target, lock_path):
            shutil.rmtree(target)  # a stale or interrupted install of another lock under the same name
        try:
            os.replace(work, target)
        except OSError:
            if not is_complete(target, lock_path):  # another process finished first: its folder is as good
                raise
    except GuiDepsError:
        raise
    except Exception as error:  # noqa: BLE001 - every failure of an install is the one code
        raise GuiDepsError(f"install into {target} failed: {error}; {HINT}") from None
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return target


def activate(env: Optional[Mapping[str, str]] = None, *, lock_path: Path = LOCK) -> Path:
    """Put the installed lock first on ``sys.path``; ``GUI_DEPS_UNAVAILABLE`` when it is not installed."""
    folder = site_dir(env, lock_path=lock_path)
    if not is_complete(folder, lock_path):
        raise GuiDepsError(f"third-party packages are not installed in {folder}; {HINT}")
    entry = str(folder)
    if entry not in sys.path:
        sys.path.insert(0, entry)
    return folder


def _pip_works() -> bool:
    try:
        result = subprocess.run([sys.executable, "-m", "pip", "--version"], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _pip_install(lock_path: Path, work: Path) -> None:
    command = [sys.executable, "-m", "pip", "install", "--require-hashes", "--no-deps", "--only-binary=:all:",
               "--disable-pip-version-check", "--no-input", "--quiet", "--target", str(work), "-r", str(lock_path)]
    result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=600, check=False)
    if result.returncode != 0:
        tail = result.stdout.decode("utf-8", "replace").strip().splitlines()[-5:]
        raise GuiDepsError("pip install failed: " + " | ".join(tail))


def _pure_python(filename: str) -> bool:
    """Whether a wheel file name carries the tags ``py3`` (possibly among others), ``none`` and ``any``."""
    if not filename.endswith(".whl"):
        return False
    parts = filename[:-4].split("-")
    if len(parts) not in (5, 6):
        return False
    python, abi, platform = parts[-3:]
    return "py3" in python.split(".") and abi == "none" and platform == "any"


def _fetch(url: str, limit: int) -> bytes:
    scheme = urllib.parse.urlsplit(url).scheme
    if scheme not in ("https", "http"):
        raise GuiDepsError(f"refusing to download {url!r}: only http(s) URLs")
    with urllib.request.urlopen(url, timeout=TIMEOUT_S) as response:  # noqa: S310 - scheme checked above
        data = response.read(limit + 1)
    if len(data) > limit:
        raise GuiDepsError(f"{url} is larger than {limit} bytes")
    return data


def _install_wheel(requirement: Requirement, work: Path, index_url: str) -> None:
    name, version, digest = requirement
    meta_url = f"{index_url.rstrip('/')}/pypi/{urllib.parse.quote(name)}/{urllib.parse.quote(version)}/json"
    try:
        meta = json.loads(_fetch(meta_url, 8 * 1024 * 1024).decode("utf-8"))
    except GuiDepsError:
        raise
    except Exception as error:  # noqa: BLE001 - network and JSON failures alike
        raise GuiDepsError(f"cannot read the PyPI metadata of {name}=={version}: {error}") from None
    files = meta.get("urls") if isinstance(meta, dict) else None
    chosen = [entry for entry in files or () if isinstance(entry, dict)
              and entry.get("packagetype") == "bdist_wheel"
              and isinstance(entry.get("digests"), dict) and entry["digests"].get("sha256") == digest]
    if not chosen:
        raise GuiDepsError(f"{name}=={version}: no wheel with the locked sha256 {digest[:12]}…")
    entry = chosen[0]
    if not _pure_python(str(entry.get("filename", ""))):
        raise GuiDepsError(f"{name}=={version}: {entry.get('filename')!r} is not a py3-none-any wheel")
    try:
        data = _fetch(str(entry.get("url", "")), MAX_WHEEL_BYTES)
    except GuiDepsError:
        raise
    except Exception as error:  # noqa: BLE001
        raise GuiDepsError(f"cannot download {entry.get('filename')}: {error}") from None
    if hashlib.sha256(data).hexdigest() != digest:
        raise GuiDepsError(f"{entry.get('filename')}: sha256 mismatch with the lock")
    archive = work / ".download.whl"
    archive.write_bytes(data)
    try:
        _unpack(archive, work)
    finally:
        archive.unlink()


def _unpack(archive: Path, work: Path) -> None:
    """Extract a wheel into ``work``: ``<dist>.data/purelib|platlib`` go to the root, other ``.data`` parts are
    skipped (scripts and headers are not needed for imports); a member that could leave ``work`` is refused."""
    root = os.path.realpath(work)
    try:
        bundle = zipfile.ZipFile(archive)
    except zipfile.BadZipFile:
        raise GuiDepsError(f"{archive.name} is not a zip archive") from None
    with bundle:
        for member in bundle.infolist():
            name = member.filename
            path = PurePosixPath(name)
            if name.startswith(("/", "\\")) or "\\" in name or ".." in path.parts or (path.parts and ":" in path.parts[0]):
                raise GuiDepsError(f"archive member {name!r} escapes the install folder")
            parts = path.parts
            if parts and parts[0].endswith(".data"):
                if len(parts) < 3 or parts[1] not in ("purelib", "platlib"):
                    continue
                parts = parts[2:]
            if member.is_dir() or not parts:
                continue
            destination = os.path.join(root, *parts)
            if os.path.commonpath([root, os.path.realpath(destination)]) != root:
                raise GuiDepsError(f"archive member {name!r} escapes the install folder")
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            with bundle.open(member) as source, open(destination, "wb") as sink:
                shutil.copyfileobj(source, sink)
