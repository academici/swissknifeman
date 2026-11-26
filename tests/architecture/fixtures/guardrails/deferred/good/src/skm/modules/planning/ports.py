from typing import Protocol
from skm.kernel.ports_uow import repository_port, host_gateway

@repository_port
class PlanRepository(Protocol):
    def get(self, identity: str) -> object: ...

@repository_port
class FutureRepository(Protocol):
    def get(self, identity: str) -> object: ...

@host_gateway
class Vcs(Protocol):
    def run(self) -> None: ...
