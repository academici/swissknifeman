"""The research stage: the researcher asks the configured sources and answers a closed research-result, which the
work source keeps (or the artifacts of the piece, when it cannot)."""
from __future__ import annotations

from pathlib import Path
import shlex
from typing import Optional

from orch.conductor import contract, prompts
from orch.conductor.domain.item import Item, done_steps
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure.files import write_json
from orch.settings import ORCH_ROOT


def wanted(self, item: Item) -> bool:
    """Whether the piece gets a research stage (``orch.research.policy``, ``conditional`` when unset): ``required`` asks
    for one before every piece, ``off`` never, ``conditional`` only when the input says the designer of the plan needs
    research for it (``research.need`` is ``required``; no heuristic of the conductor)."""
    policy = (getattr(self.settings, "research", None) or {}).get("policy") or "conditional"
    if policy == "conditional":
        return ((item.input_doc or {}).get("research") or {}).get("need") == "required"
    return policy == "required"


def query(item: Item) -> str:
    doc = item.input_doc
    text = f"Research for this work: {str(doc.get('goal') or '').strip()}"
    return text + (f"\n\nWhy it is done: {str(doc['why']).strip()}" if doc.get("why") else "")


def research(self, item: Item, number: int = 1) -> Optional[dict]:
    """The research stage: the researcher role asks the configured sources (``orch.py research query``) and answers a
    closed ``research-result``; the result is then saved where the work source keeps research (a plan: its ``research``
    folder, declared as an input of the item; a file input: its artifacts) and, when the source cannot, kept in the
    artifacts of the piece. ``None`` when the piece gets no research stage."""
    if not self._research_wanted(item):
        return None
    from orch import research as research_mod
    sources = [source.id for source in research_mod.sources_from(self.settings)]
    if not sources:
        raise Stop("RESEARCH_NO_SOURCES", "the piece needs research (orch.research.policy "
                   f"{(self.settings.research or {}).get('policy') or 'conditional'}), but [orch.research.sources] names no source")
    role, key = "researcher", f"research.{number}"
    route = item.routes[role]
    folder = item.directory / "research"

    def run() -> dict:
        query_file = folder / f"query-{number}.txt"
        query_file.parent.mkdir(parents=True, exist_ok=True)
        query = self._research_query(item)
        query_file.write_text(query + "\n", encoding="utf-8")
        prompt = prompts.researcher(item.input_doc, item=item.ref, step=key, query=query, sources=sources,
                                    command=self._research_command(sources, query_file), roles_dir=self.roles_dir, stub=self._stub(role), skills=self._skills(item, role),
                                    repo_rules=self._repo_rules(item, role), skill_texts=self._skill_texts(item, role))
        doc, meta = self._role(item, key, role, prompt, "research-result",
                               extra=lambda found: contract.research_problems(sources, found))
        saved = write_json(folder / f"result-{number}.json", doc)
        return {"result": doc, "file": self._relative(saved), **meta}

    found = self._step(item, key, run, role=role, route=self.label(route),
                       verdict=lambda result: f"{len(result['result']['claims'])} claim(s), "
                                              f"{len(result['result']['unknowns'])} unknown(s)")
    self._step(item, f"research-save.{number}", lambda: self._research_save(item, number, found), role="registrar",
               route=self.conductor.get("registrar") or "orch/conductor",
               verdict=lambda result: f"{result['outcome']} {result.get('path') or ''}".strip())
    return found["result"]


def command(self, sources: list, query_file: Path) -> str:
    """The one command a read-only role asks a source with. ``python3`` as a bare name: the launch catalog allows the researcher
    and the advisor ``python3 *orch.py research query *`` and, for an invocation config, ``python3 *orch.py --config *
    research query *``; any other option before the verb is outside that allowance."""
    argv = ["python3", str(ORCH_ROOT / "scripts" / "orch.py"), "research", "query", "--source", sources[0],
            "--query-file", str(query_file)]
    if self.config_file:
        argv[2:2] = ["--config", str(self.config_file)]
    return shlex.join(argv)


def researched(item: Item) -> dict:
    """``{result, path}`` of the research stage of the piece for the executor prompt: the closed research-result and the
    file that keeps it (``research-save.1`` says where; the artifacts of the piece when the work source did not take it);
    ``{}`` when the piece had no research stage."""
    steps = done_steps(item.state.get("steps") or {})
    found = (steps.get("research.1") or {}).get("result") or {}
    if not found.get("result"):
        return {}
    saved = (steps.get("research-save.1") or {}).get("result") or {}
    return {"result": found["result"], "path": saved.get("path") or found.get("file") or ""}


def paths(item: Item) -> set:
    """The files the work source saved research results in (a plan's ``research`` folder): a commit of the piece takes them."""
    saved = (step.get("result") or {} for key, step in done_steps(item.state.get("steps") or {}).items()
             if key.startswith("research-save."))
    return {found["path"] for found in saved if found.get("outcome") in ("recorded", "no-op") and found.get("path")}
