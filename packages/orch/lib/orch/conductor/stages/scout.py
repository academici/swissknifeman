"""The scout stage: the context map of the piece (cached by its inputs) and the write-set hint it may carry."""
from __future__ import annotations

from typing import Optional

from aicore.util.digest import canonical_json_bytes, sha256_hex
from aicore.util.io import durable_replace

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
    route = item.routes.get("context-scout")
    if route is None:  # routing already reported the optional role's LAUNCH_UNKNOWN or LAUNCH_REFUSED
        return ""
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
    key = cache_key(self, item, route)
    cache = runs_root(self.project) / "cache" / "scout" / safe(item.ref) / f"{key[:32]}.txt"

    def run() -> dict:
        hit = cached(cache)
        if hit is not None:
            return {"text": hit, "cache": self._relative(cache), "hit": True}
        prompt = prompts.scout(item.input_doc, item=item.ref, step="scout", roles_dir=self.roles_dir, stub=self._stub("context-scout", route),
                               skills=self._skills(item, "context-scout"),
                               skill_texts=self._skill_texts(item, "context-scout"))
        text, meta = self._role(item, "scout", "context-scout", prompt, None)
        try:
            durable_replace(cache, text.encode("utf-8"))  # whole or not there: a run that dies mid-write leaves no half map
        except OSError:  # a cache that cannot be written costs the next run a scout, not this one
            pass
        return {"text": text, "cache": self._relative(cache), "hit": False, **meta}

    found = self._step(item, "scout", run, role="context-scout", route=self.label(route),
                       verdict=lambda result: "cache" if result.get("hit") else "mapped")
    return self._hint(item, found["text"])


def scout_input(doc: dict) -> dict:
    """The part of an execution-input the scout map depends on.

    ``provenance`` and ``digest`` change with every journal write. The ``input_id`` suffix is that digest.
    ``lessons[].ts`` is the time a lesson was recorded, not scope, an instruction or a dependency; the lesson
    text stays in the key, so a different lesson still misses."""
    kept = {name: value for name, value in doc.items() if name not in ("provenance", "digest")}
    if isinstance(kept.get("input_id"), str):
        kept["input_id"] = kept["input_id"].rsplit("@", 1)[0]
    lessons = kept.get("lessons")
    if isinstance(lessons, list):
        kept["lessons"] = [{key: value for key, value in lesson.items() if key != "ts"}
                          if isinstance(lesson, dict) else lesson for lesson in lessons]
    return kept


def cache_document(self, item: Item, route: dict) -> dict:
    """What the scout map depends on: the normalised input, the route, the role, the skills and the stub."""
    names = self._skills(item, "context-scout")
    texts = {}
    for name, _id, path in self._skill_files(item, "context-scout"):
        if name in names:
            try:
                texts[name] = sha256_hex(self._skill_body(path).encode("utf-8")) if path is not None else None
            except OSError:
                texts[name] = None
    origin, stub = self._stub("context-scout", route)
    return {"input": scout_input(item.input_doc),
            "route": [route["provider"], route["model"], route["effort"]],
            "role": render.load_role("context-scout", self.roles_dir)[0].get("instructions"),
            "skills": names, "skill_texts": texts,
            "stub": sha256_hex(canonical_json_bytes([origin, stub]))}


def cache_key(self, item: Item, route: dict) -> str:
    """The key of the scout map of a piece. See ``scout_input`` for what of the input counts."""
    return sha256_hex(canonical_json_bytes(cache_document(self, item, route)))


def cached(path) -> Optional[str]:
    """The map in the cache file, ``None`` unless it is a regular, non-empty file of UTF-8 text."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            return None
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return text if text.strip() else None


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
