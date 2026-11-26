"""Shared contract of the isolation backends and their fail-closed coverage check (adapters §7, §7.3).

A profile name selects a mechanism, not a set of guarantees. Before a unit is spawned each backend states
which ``IsolationProperty`` values it can *prove* on this host (``proven``). Companion components (a cgroup
launcher, an egress boundary, a native client sandbox) add proofs only per request: each is asked to verify
the exact paths, network hosts and command line (``ProofRequest``), its ``CompanionProof`` must carry the
digest of that request and an absolute launcher that the wrapped argv starts with, so the proof is enforced
before the spawn. Labels, names and free-text evidence prove nothing. ``assess`` compares the proofs with the
properties the request requires and raises ``SANDBOX_UNAVAILABLE`` for any gap, an unbound or failing proof
included. A weaker profile is never substituted, ``runtimes.degraded.allow`` has no say here, and ``none`` is
reachable only with the host flag.

``WrappedProcess`` is the structural twin of ``execution.host.isolation.WrappedCommand``: that class lives in
the execution host layer, which adapters may not import, so the host operation takes the four fields.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Literal, Protocol

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.policy.domain.render import IsolationProperty
from skm.modules.runtimes.domain.request import ProcessOwner, ProcessOwnership

if TYPE_CHECKING:
    pass

__all__ = [
    "SpecView",
    "accept_proof",
    "assess",
    "request_binding",
    "spec_requirements",
    "unavailable",
    "verify_companions",
]


class SpecView(Protocol):
    """The fields of ``IsolationSpec`` the adapters read (the class itself is host-layer, see module doc)."""

    @property
    def workdir(self) -> Path: ...
    @property
    def readable(self) -> tuple[Path, ...]: ...
    @property
    def writable(self) -> tuple[Path, ...]: ...
    @property
    def protected(self) -> tuple[Path, ...]: ...
    @property
    def read_only_root(self) -> bool: ...
    @property
    def network(self) -> Literal["none", "allowlist", "full"]: ...
    @property
    def network_hosts(self) -> tuple[str, ...]: ...
    @property
    def env(self) -> Mapping[str, str]: ...
    @property
    def materials_dir(self) -> Path | None: ...
    @property
    def credential_mounts(self) -> tuple[JsonObject, ...]: ...
    @property
    def owner(self) -> ProcessOwner: ...


@dataclass(frozen=True, slots=True)
class WrappedProcess:
    argv: tuple[str, ...]
    env: Mapping[str, str]
    cwd: Path
    ownership: ProcessOwnership


@dataclass(frozen=True, slots=True)
class ProofRequest:
    """The exact request a companion is asked to prove: paths, hosts, launch and backend context.

    ``binding`` is the digest of all of it (``request_binding``); a proof is accepted only for this digest.
    ``required`` is what the request needs overall, ``needed`` what the backend alone does not prove.
    """

    profile: str
    spec: SpecView
    argv: tuple[str, ...]
    context: Mapping[str, str]
    required: frozenset[IsolationProperty]
    needed: frozenset[IsolationProperty]
    binding: str


@dataclass(frozen=True, slots=True)
class CompanionProof:
    """A companion's result for one ``ProofRequest``: what it verified and how it enforces it before spawn.

    ``launch`` is an absolute launcher argv prefix that execs the rest of the command line inside the
    verified boundary; the wrapped argv starts with it, so the proof is also the enforcement. ``evidence``
    only describes (probe, version, digest) and proves nothing by itself. A proof of ``LIFECYCLE`` carries the
    prepared ownership of the very owner of the request.
    """

    properties: frozenset[IsolationProperty]
    binding: str
    launch: tuple[str, ...]
    evidence: str
    ownership: ProcessOwnership | None = None


@dataclass(frozen=True, slots=True)
class Companion:
    """A component that can prove properties the profile does not (cgroup launcher, egress boundary...).

    Nothing a companion declares is believed: ``properties`` only says what it may be asked, and ``verify`` is
    called per request (never cached) and must return a ``CompanionProof`` bound to that request and to a
    launcher that enforces it. A missing, stale, over-claiming or failing proof is ``SANDBOX_UNAVAILABLE``.
    """

    component: str
    properties: frozenset[IsolationProperty]
    verify: Callable[[ProofRequest], CompanionProof]

    def __post_init__(self) -> None:
        if not self.component:
            raise ValueError("a companion needs a component name")
        if not self.properties:
            raise ValueError("a companion must prove at least one property")
        if not callable(self.verify):
            raise ValueError("a companion needs a verify function that proves the exact request")


@dataclass(frozen=True, slots=True)
class AcceptedProof:
    component: str
    proof: CompanionProof


@dataclass(frozen=True, slots=True)
class Coverage:
    profile: str
    required: frozenset[IsolationProperty]
    proven: Mapping[IsolationProperty, str]  # property -> "component: evidence"
    launch: tuple[
        str, ...
    ] = ()  # companion launcher prefixes, outermost first; apply before the backend argv
    ownership: ProcessOwnership | None = None  # prepared by the companion that proved LIFECYCLE
    enforced_by: tuple[str, ...] = ()

    def to_json(self) -> JsonObject:
        return {
            "profile": self.profile,
            "required": list[JsonValue](sorted(item.value for item in self.required)),
            "proven": {item.value: text for item, text in sorted(self.proven.items())},
            "enforced_by": list[JsonValue](self.enforced_by),
            "launch": list[JsonValue](self.launch),
        }


def unavailable(profile: str, reason: str, message: str, **details: JsonValue) -> CapabilityUnavailable:
    return CapabilityUnavailable(
        ErrorCode.SANDBOX_UNAVAILABLE,
        f"isolation profile {profile} is unavailable: {message}",
        details={"profile": profile, "reason": reason, **details},
    )


def spec_requirements(spec: SpecView, *, confined: bool = True) -> frozenset[IsolationProperty]:
    """Properties the spec itself demands; ``confined=False`` is the unconfined profile (host flag)."""
    if not confined:
        return frozenset()
    required = {IsolationProperty.FS_WRITE, IsolationProperty.FS_READ, IsolationProperty.LIFECYCLE}
    if spec.network == "none":
        required.add(IsolationProperty.NETWORK_NONE)
    elif spec.network == "allowlist":
        required.add(IsolationProperty.NETWORK_ALLOWLIST)
    if spec.credential_mounts:
        required.add(IsolationProperty.CREDENTIALS)
    return frozenset(required)


def request_binding(
    profile: str, spec: SpecView, argv: Sequence[str], context: Mapping[str, str] | None = None
) -> str:
    """Digest of everything a proof must cover: the paths, network mode and hosts, credential mounts, the
    owner, the command line, the names (not values) of the environment and the backend context."""
    document: JsonObject = {
        "profile": profile,
        "workdir": str(spec.workdir),
        "readable": list[JsonValue](str(path) for path in spec.readable),
        "writable": list[JsonValue](str(path) for path in spec.writable),
        "protected": list[JsonValue](str(path) for path in spec.protected),
        "read_only_root": spec.read_only_root,
        "network": spec.network,
        "network_hosts": list[JsonValue](spec.network_hosts),
        "materials_dir": None if spec.materials_dir is None else str(spec.materials_dir),
        "credential_mounts": list[JsonValue](spec.credential_mounts),
        "env_names": list[JsonValue](sorted(spec.env)),
        "owner": list[JsonValue](
            (
                str(spec.owner.host_id),
                str(spec.owner.worker_id),
                str(spec.owner.attempt_id),
                str(spec.owner.stage_record_id),
                spec.owner.unit_kind,
                str(spec.owner.unit_id),
                spec.owner.owner_nonce,
            )
        ),
        "argv": list[JsonValue](argv),
        "context": dict[str, JsonValue](context or {}),
    }
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _refuse_proof(profile: str, component: str, reason: str, message: str) -> CapabilityUnavailable:
    return unavailable(
        profile, reason, f"companion {component}: {message}", component=component, proof_failure=reason
    )


def _launcher_problem(launch: Sequence[str], spec: SpecView) -> str | None:
    """Why ``launch`` cannot be trusted as the enforcement started before the unit; ``None`` if it can."""
    if not launch or any(
        not isinstance(item, str) or not item or "\0" in item  # pyright: ignore[reportUnnecessaryIsInstance]
        for item in launch
    ):
        return "the proof names no launcher that enforces it before the spawn"
    launcher = launch[0]
    if not os.path.isabs(launcher) or not os.path.isfile(launcher) or not os.access(launcher, os.X_OK):
        return f"launcher {launcher} is not an absolute path to an executable file"
    real = os.path.realpath(launcher)
    for root in (spec.workdir, *spec.writable):
        base = os.path.realpath(root)
        if os.path.commonpath((real, base)) == base:
            return f"launcher {launcher} lies where the unit can write ({root})"
    return None


def accept_proof(profile: str, companion: Companion, request: ProofRequest) -> AcceptedProof:
    """Ask ``companion`` for the proof of exactly ``request`` and refuse anything that is not one.

    Refused (``SANDBOX_UNAVAILABLE``, nothing weaker substituted): a verifier that raises or answers with
    anything but a ``CompanionProof``; a proof bound to another request (stale, reused, forged), claiming
    properties the companion does not declare or none; a launcher that is not an absolute executable outside
    the unit's writable area; a lifecycle proof without ownership of this very owner.
    """
    name = companion.component
    try:
        proof = companion.verify(request)
    except CapabilityUnavailable:
        raise
    except Exception as error:  # an unknown verification result is an unproven property
        raise _refuse_proof(
            profile, name, "companion_proof_failed", f"verification failed ({type(error).__name__})"
        ) from error
    if not isinstance(proof, CompanionProof):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise _refuse_proof(profile, name, "companion_proof_invalid", "the answer is not a proof")
    if not proof.properties or not proof.properties <= companion.properties:
        raise _refuse_proof(
            profile, name, "companion_proof_overclaim", "it proves no or undeclared properties"
        )
    if proof.binding != request.binding:
        raise _refuse_proof(
            profile, name, "companion_proof_unbound", "the proof does not cover this exact request"
        )
    if not proof.evidence.strip():
        raise _refuse_proof(profile, name, "companion_proof_invalid", "the proof carries no evidence")
    problem = _launcher_problem(proof.launch, request.spec)
    if problem is not None:
        raise _refuse_proof(profile, name, "companion_launch_untrusted", problem)
    if IsolationProperty.LIFECYCLE in proof.properties:
        owned = proof.ownership
        if (
            not isinstance(owned, ProcessOwnership)
            or owned.owner != request.spec.owner
            or owned.kind == "pgroup_best_effort"
        ):
            raise _refuse_proof(
                profile, name, "companion_ownership_invalid", "no prepared containment of this owner"
            )
    return AcceptedProof(name, proof)


def verify_companions(
    profile: str, companions: Iterable[Companion], request: ProofRequest
) -> tuple[AcceptedProof, ...]:
    """Proofs of the companions that may close a gap of ``request`` (the others are not consulted)."""
    return tuple(
        accept_proof(profile, companion, request)
        for companion in companions
        if companion.properties & request.needed
    )


def assess(
    profile: str,
    required: frozenset[IsolationProperty],
    own: Mapping[IsolationProperty, str],
    accepted: Iterable[AcceptedProof] = (),
) -> Coverage:
    """Every required property needs a proof from the backend or an accepted companion proof, else
    ``SANDBOX_UNAVAILABLE``. The launchers of the accepted proofs become the prefix of the wrapped argv."""
    proven = dict(own)
    launch: list[str] = []
    ownership: ProcessOwnership | None = None
    names: list[str] = []
    for item in accepted:
        names.append(item.component)
        launch.extend(item.proof.launch)
        for prop in item.proof.properties:
            proven.setdefault(prop, f"{item.component}: {item.proof.evidence}")
        if (
            IsolationProperty.LIFECYCLE in item.proof.properties
            and IsolationProperty.LIFECYCLE not in own
            and ownership is None
        ):
            ownership = item.proof.ownership
    missing = sorted(item.value for item in required if item not in proven)
    coverage = Coverage(
        profile,
        required,
        {item: proven[item] for item in required if item in proven},
        tuple(launch),
        ownership,
        tuple(names),
    )
    if missing:
        raise unavailable(
            profile,
            "property_unproven",
            f"no enforcing backend proves {', '.join(missing)}",
            missing=list[JsonValue](missing),
            coverage=coverage.to_json(),
        )
    return coverage


class BackendIsolation:
    """Common part of the built-in profiles: coverage check before any argv is built.

    ``require`` adds properties the spec cannot state (resource limits, disk quota, client config isolation);
    ``companions`` are the extra components of this host's combination, consulted per request.
    """

    profile: ClassVar[str]
    confined: ClassVar[bool] = True

    def __init__(
        self, *, companions: Sequence[Companion] = (), require: Iterable[IsolationProperty] = ()
    ) -> None:
        self._companions = tuple(companions)
        self._require = frozenset(require)

    def proven(self, spec: SpecView) -> Mapping[IsolationProperty, str]:
        """Properties this backend alone enforces for ``spec`` on this host (overridden by each profile)."""
        raise NotImplementedError

    def coverage(
        self, spec: SpecView, argv: Sequence[str], context: Mapping[str, str] | None = None
    ) -> Coverage:
        """Proofs for exactly ``argv`` and ``spec`` (``context``: backend facts such as image or network)."""
        required = spec_requirements(spec, confined=self.confined) | self._require
        own = self.proven(spec)
        needed = frozenset(item for item in required if item not in own)
        request = ProofRequest(
            self.profile,
            spec,
            tuple(argv),
            dict(context or {}),
            required,
            needed,
            request_binding(self.profile, spec, argv, context),
        )
        return assess(self.profile, required, own, verify_companions(self.profile, self._companions, request))

    def ownership(self, spec: SpecView, coverage: Coverage) -> ProcessOwnership:
        """Prepared containment of the owner: a companion's proven one, else a best-effort process group."""
        if coverage.ownership is not None:
            return coverage.ownership
        return ProcessOwnership(
            owner=spec.owner, kind="pgroup_best_effort", ref=f"pgroup:{spec.owner.unit_id}"
        )
