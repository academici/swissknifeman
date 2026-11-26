from typing import Protocol
from skm.kernel.ports_uow import repository_port
from skm.kernel.gateways import host_gateway

@repository_port
class PlanRepository(Protocol): ...

@host_gateway
class Vcs(Protocol): ...
