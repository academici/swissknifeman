"""Network policy (policy §§4.2, 4.4, 5.3 N1).

Strictness ``none > allowlist > any``. ``hosts`` is a conjunction of host lists: under ``allowlist`` a host
passes only if it matches a pattern of every list, and a policy without any list passes nothing. A pattern
is ``host``, ``*.suffix`` (subdomains only) and optionally ``:port`` (without a port any port matches). The
pairwise intersection of two patterns is empty or one pattern, so a conjunction flattens exactly
(``flatten_hosts``). Matching classifies a request by name only; enforcement belongs to the sandbox/egress
backend (§5.3a).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

__all__ = [
    "FORGE_API_HOSTS",
    "NETWORK_MODE_ORDER",
    "REGISTRY_HOSTS",
    "NetworkLayer",
    "NetworkMode",
    "NetworkPolicy",
    "flatten_hosts",
    "host_matches",
    "intersect_patterns",
    "narrow_network",
    "pattern_subsumes",
    "stricter_network_mode",
]


class NetworkMode(StrEnum):
    NONE = "none"
    ALLOWLIST = "allowlist"
    ANY = "any"


NETWORK_MODE_ORDER: dict[NetworkMode, int] = {
    NetworkMode.ANY: 0,
    NetworkMode.ALLOWLIST: 1,
    NetworkMode.NONE: 2,
}

REGISTRY_HOSTS: dict[str, tuple[str, ...]] = {
    "python": ("pypi.org", "files.pythonhosted.org"),
    "node": ("registry.npmjs.org",),
    "php": ("packagist.org", "repo.packagist.org"),
    "cargo": ("crates.io", "index.crates.io", "static.crates.io"),
    "go": ("proxy.golang.org", "sum.golang.org"),
    "ruby": ("rubygems.org", "index.rubygems.org"),
    "brew": ("formulae.brew.sh", "ghcr.io"),
    "dart": ("pub.dev",),
    "jvm": ("repo.maven.apache.org", "plugins.gradle.org"),
}
FORGE_API_HOSTS: Final[Mapping[str, str]] = MappingProxyType({"gh": "api.github.com", "glab": "gitlab.com"})


@dataclass(frozen=True, slots=True)
class NetworkPolicy:
    mode: NetworkMode
    hosts: tuple[frozenset[str], ...]

    def allows(self, host: str, port: int | None) -> bool:
        if self.mode is NetworkMode.NONE:
            return False
        if self.mode is NetworkMode.ANY:
            return True
        return bool(self.hosts) and all(
            any(host_matches(pattern, host, port) for pattern in hosts) for hosts in self.hosts
        )


@dataclass(frozen=True, slots=True)
class NetworkLayer:
    mode: NetworkMode | None = None
    hosts: frozenset[str] | None = None  # explicit empty list: no host at all


def stricter_network_mode(a: NetworkMode, b: NetworkMode) -> NetworkMode:
    return a if NETWORK_MODE_ORDER[a] >= NETWORK_MODE_ORDER[b] else b


def narrow_network(a: NetworkPolicy, layer: NetworkLayer) -> NetworkPolicy:
    """A host list without a mode implies ``allowlist`` (like a program list for commands): an explicit
    list, even an empty one, always restricts."""
    layer_mode = layer.mode
    layer_hosts = layer.hosts
    if layer_mode is None and layer_hosts is not None:
        layer_mode = NetworkMode.ALLOWLIST
    elif layer_mode is NetworkMode.ALLOWLIST and layer_hosts is None:
        layer_hosts = frozenset[str]()
    mode = a.mode if layer_mode is None else stricter_network_mode(a.mode, layer_mode)
    hosts = a.hosts
    if layer_hosts is not None and layer_hosts not in hosts:
        hosts = (*hosts, layer_hosts)
    return NetworkPolicy(mode, hosts)


def _split(pattern: str) -> tuple[str, int | None]:
    name, sep, port = pattern.lower().rpartition(":")
    if sep and port.isdigit():
        return name, int(port)
    return pattern.lower(), None


def host_matches(pattern: str, host: str, port: int | None) -> bool:
    name, wanted = _split(pattern)
    host = host.lower().rstrip(".")
    if wanted is not None and wanted != port:
        return False
    if name.startswith("*."):
        return host.endswith(name[1:]) and len(host) > len(name) - 1
    return host == name


def _name_meet(a: str, b: str) -> str | None:
    if not a.startswith("*.") and not b.startswith("*."):
        return a if a == b else None
    if a.startswith("*.") and b.startswith("*."):
        if a.endswith(b[1:]) or a == b:
            return a
        return b if b.endswith(a[1:]) else None
    wild, exact = (a, b) if a.startswith("*.") else (b, a)
    return exact if host_matches(wild, exact, None) else None


def intersect_patterns(a: str, b: str) -> str | None:
    """The single pattern matching exactly what both match, or ``None`` when they share nothing."""
    name_a, port_a = _split(a)
    name_b, port_b = _split(b)
    if port_a is not None and port_b is not None and port_a != port_b:
        return None
    name = _name_meet(name_a, name_b)
    if name is None:
        return None
    port = port_a if port_a is not None else port_b
    return name if port is None else f"{name}:{port}"


def flatten_hosts(hosts: tuple[frozenset[str], ...]) -> frozenset[str]:
    """One host list equivalent to the conjunction (an empty conjunction is the empty list)."""
    if not hosts:
        return frozenset()
    result = set(hosts[0])
    for other in hosts[1:]:
        result = {meet for a in result for b in other if (meet := intersect_patterns(a, b)) is not None}
    return frozenset(result)


def pattern_subsumes(outer: str, inner: str) -> bool:
    """Every request matched by ``inner`` is matched by ``outer``."""
    return intersect_patterns(outer, inner) == _normal(inner)


def _normal(pattern: str) -> str:
    name, port = _split(pattern)
    return name if port is None else f"{name}:{port}"
