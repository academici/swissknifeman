"""Explicit test composition using the final AgentRuntime/RuntimeRegistry ports."""

from dataclasses import dataclass

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.modules.runtimes.ports import AgentRuntime


@dataclass(frozen=True)
class TestRuntimeRegistry:
    __test__ = False
    fake: AgentRuntime | None = None

    def ids(self) -> frozenset[str]:
        return frozenset() if self.fake is None else frozenset({self.fake.runtime_id})

    def get(self, runtime_id: str) -> AgentRuntime:
        if self.fake is None or self.fake.runtime_id != runtime_id:
            raise NotFound(ErrorCode.NOT_FOUND, "test runtime is not registered", details={"kind": "runtime"})
        return self.fake
