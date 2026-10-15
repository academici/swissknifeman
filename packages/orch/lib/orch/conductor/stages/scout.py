"""The scout stage: the context map of the piece (cached by its inputs) and the write-set hint it may carry."""
from __future__ import annotations

from typing import Optional

from aicore.util.digest import canonical_json_bytes, sha256_hex

from orch import render
from orch.conductor import contract, gates, process, prompts
from orch.conductor.domain.item import Item
from orch.conductor.domain.report import write_set_block
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock
from orch.conductor.infrastructure.files import runs_root, safe


def stage(self, item: Item) -> Optional[dict]:
    return next((stage for stage in item.policy.get("stages", [])
                 if stage.get("role") in ("scout", "context-scout")), None)


def scout(self, item: Item) -> str:
    item.state["expected"] = None  # the hint belongs to the scout answer read below; a skipped or retried scout leaves none
    stage = self._scout_stage(item)
    if stage is None:
        return ""
    route = item.routes["context-scout"]
    gate = gates.blocked(route["provider"], clock.wall())
    disabled = self.provider_disabled(route["provider"])
    if gate or disabled or not process.available(route["argv"]):
        code, why = ("PROVIDER_QUOTA", f"{route['provider']} is gated until {gate['until']}") if gate else \
            ("PROVIDER_DISABLED", disabled.split(": ", 1)[1]) if disabled else \
            ("PROVIDER_UNAVAILABLE", f"{route['argv'][0]} not found")
        if stage.get("on_unavailable") == "skip" and not stage.get("required"):
            self.progress.emit("stage.skip", item=item.ref, stage="scout", role="context-scout",
                               route=self.label(route), reason_code=code, message=f"{why}; optional stage skipped")
            return ""
        raise Stop(code, f"context-scout on {route['provider']}: {why}")
    key = sha256_hex(canonical_json_bytes({
        "input": item.input_doc.get("digest"),
        "plan": (item.input_doc.get("provenance") or {}).get("source_digest"),
        "route": [route["provider"], route["model"], route["effort"]],
        "role": render.load_role("context-scout", self.roles_dir)[0].get("instructions"),
        "skills": self._skills(item, "context-scout")}))
    cache = runs_root(self.project) / "cache" / "scout" / safe(item.ref) / f"{key[:32]}.txt"

    def run() -> dict:
        if cache.is_file():
            return {"text": cache.read_text(encoding="utf-8"), "cache": self._relative(cache), "hit": True}
        prompt = prompts.scout(item.input_doc, item=item.ref, step="scout", roles_dir=self.roles_dir, stub=self._stub("context-scout"),
                               skills=self._skills(item, "context-scout"),
                               skill_texts=self._skill_texts(item, "context-scout"))
        text, meta = self._role(item, "scout", "context-scout", prompt, None)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(text, encoding="utf-8")
        return {"text": text, "cache": self._relative(cache), "hit": False, **meta}

    found = self._step(item, "scout", run, role="context-scout", route=self.label(route),
                       verdict=lambda result: "cache" if result.get("hit") else "mapped")
    return self._hint(item, found["text"])


def hint(self, item: Item, text: str) -> str:
    """The scout's ``write-set`` block taken out of its answer into ``state.expected`` (a hint for the executor and
    for the deviation label); a missing or invalid block is ignored and said. Returns the answer without the block."""
    doc, error, shown = write_set_block(text)
    if doc is not None:
        problems = contract.problems(doc, "scout-write-set")
        if problems:
            doc, error = None, "; ".join(problems[:3])
    item.state["expected"] = doc
    if doc is None:
        self.progress.emit("info", item=item.ref, stage="scout", role="context-scout", reason_code="RESULT_HEALED",
                           message=f"context-scout write-set hint ignored: {error}"[:300])
    return shown
