"""Module manifest and host operation registration (kernel-platform §2.12, conventions §3).

Specs defined outside the kernel are typed ``object`` here so that the kernel never imports
``application_bus`` or ``bootstrap``: ``commands`` hold ``CommandSpec``, ``queries`` ``QuerySpec``,
``subscribers`` ``SubscriberSpec``, ``external_consumers`` ``ExternalConsumerSpec`` (all
``application_bus/registry.py``, checked by ``BusRegistry.build``) and ``doctor_checks`` ``DoctorCheckSpec``
(``bootstrap/doctor.py``, checked by ``DoctorCheckRegistry``).
"""

from collections.abc import Callable
from dataclasses import dataclass

from skm.kernel.events import DomainEvent
from skm.kernel.ports_uow import Surface

__all__ = ["HostOperationSpec", "ModuleManifest"]


@dataclass(frozen=True, slots=True)
class HostOperationSpec:
    name: str  # "<module>.host.<verb>_<noun>" (separate namespace from bus operations)
    run: Callable[..., object]  # def run(ctx: HostContext, request: X) -> Y
    request: type[object]  # generated class of urn:skm:<module>:host:<verb-noun>:v1
    result: type[object]  # generated class of urn:skm:<module>:host-result:<verb-noun>:v1
    surfaces: frozenset[Surface]  # where the operation may run: {CLI}, {WORKER}, {HOOK} or combinations


@dataclass(frozen=True, slots=True)
class ModuleManifest:
    id: str  # = package name modules/<id>
    depends_on: tuple[str, ...]  # every module whose public facade this module calls (ADR 0003)
    optional: bool
    db_schema: str | None  # "skm_<id>"; settings -> "skm_config", exports -> "skm_exports"
    settings_sections: tuple[str, ...]  # section ids; bootstrap resolves their schema URNs
    commands: tuple[object, ...] = ()
    queries: tuple[object, ...] = ()
    subscribers: tuple[object, ...] = ()
    external_consumers: tuple[object, ...] = ()  # outbox delivery by destination prefix
    events: tuple[type[DomainEvent], ...] = ()
    repository_ports: tuple[type[object], ...] = ()  # @repository_port Protocols of this module
    gateway_ports: tuple[type[object], ...] = ()  # gateway-marked Protocols of this module
    doctor_checks: tuple[object, ...] = ()
    permissions: frozenset[str] = frozenset()  # subset of the permission catalog declared by the module
    host_operations: tuple[HostOperationSpec, ...] = ()
