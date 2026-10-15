"""The closing role: a model registrar records the result with the one command the conductor built."""
from __future__ import annotations

import shlex
from typing import Optional

from orch.conductor import options as opts, prompts
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.settings import ORCH_ROOT


def close(self, item: Item, args: list) -> Optional[dict]:
    """The closing stage: a model registrar records the result with the one command built here. The conductor
    registers the result again right after: a repeat is a no-op when the closer did it, and it records the result
    when the closer could not (``close`` then says ``conductor`` and why), so the closing never loses a result."""
    route = item.routes["registrar"]
    # ``python3`` as a bare name: the launch catalog allows the registrar exactly ``python3 *orch.py source register *``.
    argv = ["python3", str(ORCH_ROOT / "scripts" / "orch.py"), *args]
    if self.config_file:  # an invocation config before the verb is outside that allowance: the closer is refused
        argv[2:2] = ["--config", str(self.config_file)]

    def run() -> dict:
        prompt = prompts.closer(item=item.ref, step="close", command=shlex.join(argv))
        try:
            text, meta = self._role(item, "close", "registrar", prompt, None)
        except Stop as stop:
            return {"by": "conductor", "reason_code": stop.code, "message": stop.message}
        return {"by": "closer", "answer": text[-1500:], **meta}

    found = self._step(item, "close", run, role="registrar", route=self.label(route),
                       verdict=lambda result: "closer ran" if result["by"] == "closer"
                       else f"closer failed ({result['reason_code']}); the conductor records")
    return found


def closer_named(item: Item) -> bool:
    """A model records the result (closing stage) only when a layer of the options names the registrar."""
    return bool(opts.stage_route(item.options, "registrar"))
