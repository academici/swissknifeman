"""Bearer credentials and the shared client request headers."""

import re
from uuid import uuid4

from skm import __version__
from skm.platform.config.secrets import SecretValue
from skm.platform.logging.redaction import DEFAULT_PATTERNS, Redactor

__all__ = ["CLIENT_VERSION", "BearerHeaders"]

CLIENT_VERSION = re.sub(r"\.dev([0-9]+)(\+|$)", lambda m: f"+dev.{m[1]}" + ("." if m[2] else ""), __version__)


class BearerHeaders:
    def __init__(self, token: SecretValue) -> None:
        if not isinstance(token, SecretValue):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("Bearer credentials require SecretValue")
        value = token.reveal()
        if not value or any(not ("!" <= char <= "~") for char in value):
            raise ValueError("Invalid bearer credential")
        self._token = token
        patterns = DEFAULT_PATTERNS if len(value) >= 8 else (*DEFAULT_PATTERNS, re.compile(re.escape(value)))
        self.redactor = Redactor(patterns)
        self.redactor.register_secret(value)

    def new(self, accept: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token.reveal()}",
            "Accept": accept,
            "X-Request-Id": str(uuid4()),
            "SKM-Client-Version": CLIENT_VERSION,
        }
