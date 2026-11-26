"""The one ``PathLike`` alias of the workspace package (a module that defined its own made pyright see distinct types)."""
from __future__ import annotations

import os
from typing import Union

PathLike = Union[str, "os.PathLike[str]"]
