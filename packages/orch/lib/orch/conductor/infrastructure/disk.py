"""Free disk space: a run that fills the disk dies in the middle of a heavy check with a truncated trace, so the
conductor looks at the space before it starts and before the checks of a round (``limits.disk_min_gb``)."""
from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
from typing import Optional

GIB = 1024 ** 3


def free_gb(path) -> float:
    """Free space of the file system that holds ``path`` (a seam for the tests)."""
    return shutil.disk_usage(path).free / GIB


def shortage(project: Path, min_gb: float) -> Optional[str]:
    """The sentence that names the file system below ``min_gb`` free (the project, then the temporary directory, which
    the checks fill with their own copies), or None. ``min_gb`` 0 looks at nothing."""
    if not min_gb or min_gb <= 0:
        return None
    seen = set()
    for label, path in (("the project", Path(project)), ("the temporary directory", Path(tempfile.gettempdir()))):
        try:
            device = path.stat().st_dev
            if device in seen:
                continue
            seen.add(device)
            free = free_gb(path)
        except OSError:
            continue
        if free < min_gb:
            return f"{free:.1f} GB free under {label} ({path}), below limits.disk_min_gb {min_gb:g}"
    return None
