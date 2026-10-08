"""Module configuration: TOML reading with line numbers and a comment-preserving editor.

``aicore.config`` may use :mod:`aicore.util` and :mod:`aicore.state`. The TOML parser is
reachable only through :mod:`aicore.config.toml`.
"""
from typing import Optional


class ConfigError(ValueError):
    """A configuration problem with a stable ``code`` and, when known, where it was found.

    ``str()`` is ``<file>:<line>: <layer>: <key>: <message> [<code>]`` without the empty parts.
    """

    def __init__(self, code: str, message: str, *, layer: Optional[str] = None,
                 file: Optional[str] = None, line: Optional[int] = None,
                 key: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.layer = layer
        self.file = file
        self.line = line
        self.key = key

    def __str__(self) -> str:
        where = ""
        if self.file:
            where = f"{self.file}:{self.line}" if self.line else str(self.file)
        elif self.line:
            where = f"line {self.line}"
        parts = [part for part in (where, self.layer, self.key, self.message) if part]
        return f"{': '.join(parts)} [{self.code}]"


from . import toml, toml_edit  # noqa: E402  (ConfigError is defined first: the submodules import it)

__all__ = ["ConfigError", "toml", "toml_edit"]
