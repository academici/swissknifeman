"""Git remotes as match keys: normalization, redaction, provider and the concrete effect endpoint (workspace
§4.3, §5.1).

Ported from ``aicore/workspace/remotes.py`` (PORT-AS-IS). ``normalize_remote`` deliberately drops the
transport, the user info and the port of ssh-like schemes: its result is a key for matching a checkout, not
proof of the identity of an external server and not the address an approved effect may be sent to.
``remote_endpoint`` keeps what the normalized key loses."""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, override

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject

__all__ = [
    "NET_SCHEMES",
    "PORT_DROPPED",
    "NormalizedRemote",
    "RemoteEndpoint",
    "RepositoryProvider",
    "normalize_remote",
    "provider_of",
    "redact_remote",
    "remote_endpoint",
]

NET_SCHEMES: Final = ("https", "http", "ssh", "git", "git+ssh", "ssh+git")
PORT_DROPPED: Final = (
    "ssh",
    "git",
    "git+ssh",
    "ssh+git",
)  # the port of these schemes is not part of the match key

_URL: Final = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*)://(.*)$", re.DOTALL)
_SCP: Final = re.compile(r"^(?:[^@/\s]+@)?([^:/\s]+):(.*)$", re.DOTALL)
# The user part may itself hold "@": the host starts after the last "@" that precedes "host:".
_SCP_USER: Final = re.compile(r"^[^/\s]+@([^@:/\s]+:.*)$", re.DOTALL)
_DRIVE: Final = re.compile(r"^[A-Za-z]:[\\/]")
# Same language as the ``normalized_remote`` definition of ``urn:skm:workspace:defs:v1``.
_NORMALIZED: Final = re.compile(r"[^/\s]+/\S+")
_MAX_LENGTH: Final = 2048

_TRANSPORT: Final = {
    "https": "https",
    "http": "http",
    "ssh": "ssh",
    "git+ssh": "ssh",
    "ssh+git": "ssh",
    "git": "git",
}
_DEFAULT_PORT: Final = {"https": 443, "http": 80, "ssh": 22, "git": 9418}


class RepositoryProvider(StrEnum):
    """Hosting provider of a remote; ``repository`` re-exports it as the repository's provider."""

    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"
    GITEA = "gitea"
    OTHER = "other"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class NormalizedRemote:
    value: str  # "host[:port]/path"

    def __post_init__(self) -> None:
        if len(self.value) > _MAX_LENGTH or not _NORMALIZED.fullmatch(self.value):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "normalized remote must be 'host[:port]/path' without whitespace",
                details={"field": "normalized_remote"},
            )

    def host(self) -> str:
        """The part before the first ``/`` (host, with the port when the scheme keeps it)."""
        return self.value.partition("/")[0]

    @override
    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class RemoteEndpoint:
    """The concrete place an effect would go to, without credentials (workspace §4.3).

    Two remotes with one match key can still be two endpoints (``ssh`` on port 2222 against port 2200): an
    approval given for one endpoint is not valid for the other."""

    transport: str  # https | http | ssh | git
    hostname: str  # lower-case, no port
    effective_port: int
    repository_path: str

    def to_json(self) -> JsonObject:
        return {
            "transport": self.transport,
            "hostname": self.hostname,
            "effective_port": self.effective_port,
            "repository_path": self.repository_path,
        }


@dataclass(frozen=True, slots=True)
class _Parsed:
    scheme: str | None  # lower-case scheme; None for the scp form
    host: str  # lower-case, without the port
    port: str | None  # the text after the last ":" of a URL authority, as given
    path: str


def _parse(url: str) -> _Parsed | None:
    text = (url or "").strip()
    if not text or text.startswith(("/", ".", "~")) or _DRIVE.match(text):
        return None
    scheme: str | None = None
    port: str | None = None
    match = _URL.match(text)
    if match:
        scheme = match.group(1).lower()
        if scheme not in NET_SCHEMES:
            return None
        authority, slash, path = match.group(2).partition("/")
        host = authority.rpartition("@")[2]
        path = path.partition("?")[0].partition("#")[0] if slash else ""
        if ":" in host and not host.endswith("]"):
            host, _, port = host.rpartition(":")
    else:
        scp = _SCP.match(text)
        if not scp:
            return None
        host, path = scp.group(1), scp.group(2)
    host = host.lower()
    path = path.strip()
    while path.endswith(("/", ".git")):
        path = path[:-1] if path.endswith("/") else path[:-4]
    path = path.lstrip("/")
    if not host or not path or any(char.isspace() for char in host + path):
        return None
    return _Parsed(scheme, host, port, path)


def normalize_remote(url: str) -> NormalizedRemote | None:
    """``host[:port]/path`` for a network remote; ``None`` for a local path, ``file://`` or anything else.

    Scheme, user info, trailing ``/`` and ``.git`` are removed, the host is lower-cased, the path keeps its
    case. The port survives only for schemes outside ``PORT_DROPPED`` and only when it consists of digits."""
    parsed = _parse(url)
    if parsed is None:
        return None
    host = parsed.host
    if parsed.port and parsed.scheme not in PORT_DROPPED and parsed.port.isdigit():
        host = f"{host}:{parsed.port}"
    value = f"{host}/{parsed.path}"
    if len(value) > _MAX_LENGTH:
        return None
    return NormalizedRemote(value)


def remote_endpoint(url: str) -> RemoteEndpoint | None:
    """The endpoint (transport, hostname, effective port, repository path) of a network remote, or ``None``.

    The scp form is ssh on port 22. A port that is not a number in 1..65535 gives ``None``: an endpoint is
    never guessed. Credentials never reach the result."""
    parsed = _parse(url)
    if parsed is None:
        return None
    transport = _TRANSPORT["ssh" if parsed.scheme is None else parsed.scheme]
    if parsed.port is None or parsed.port == "":
        port = _DEFAULT_PORT[transport]
    elif parsed.port.isascii() and parsed.port.isdigit() and 1 <= int(parsed.port) <= 65535:
        port = int(parsed.port)
    else:
        return None
    return RemoteEndpoint(transport, parsed.host, port, parsed.path)


def redact_remote(url: str) -> str:
    """The remote without user info (``user:token@``), for output and logs.

    Everything between the scheme and the last ``@`` is dropped, even when a credential holds an unescaped
    ``/``, ``?`` or ``@``: a remote with ``@`` in its path loses part of the path, never part of a secret."""
    text = (url or "").strip()
    match = _URL.match(text)
    if match:
        public = match.group(2).rpartition("@")[2].partition("?")[0].partition("#")[0]
        return f"{match.group(1)}://{public}"
    scp = _SCP_USER.match(text)
    return scp.group(1) if scp else text


def provider_of(remote: NormalizedRemote | None) -> RepositoryProvider:
    if remote is None:
        return RepositoryProvider.NONE
    host = remote.host()
    if host == "github.com":
        return RepositoryProvider.GITHUB
    if host == "gitlab.com" or host.startswith("gitlab."):
        return RepositoryProvider.GITLAB
    if host == "bitbucket.org":
        return RepositoryProvider.BITBUCKET
    if host.startswith("gitea.") or host == "codeberg.org":
        return RepositoryProvider.GITEA
    return RepositoryProvider.OTHER
