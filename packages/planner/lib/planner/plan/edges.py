"""The single table of plan link fields and the typed edge list built from it (D11, knowledge/read-api#ref-grammar).

Only ``LINK_FIELDS`` knows which fields of a plan document are links; ``check`` resolves them and the read verbs
walk them through ``edges``. Reverse edges (who depends on X) are derived by the readers, never stored here.
Everything is defensive: a broken plan yields fewer edges, it never raises.
"""
from __future__ import annotations

from typing import Any, Iterator, NamedTuple

from . import store
from .model import id_sort_key, parse_ref

EDGE_KINDS = ("depends_on", "related", "decision", "applies_to", "unit_depends_on", "parent", "consumes", "produces",
              "supersedes")
# ``related`` carries its own closed ``relation`` (item.related[].relation); the other kinds use ``relation`` only
# where a field says so below.


class Edge(NamedTuple):
    """One typed link. ``source``/``target`` are refs (``from``/``to`` in JSON); a ``brief/<Bn>`` source is a node name."""

    source: str
    target: str
    kind: str
    relation: str | None
    note: str | None
    where: str  # "<file>/<json pointer>" of the field, as used by check issues

    def as_dict(self) -> dict:
        return {"from": self.source, "to": self.target, "kind": self.kind, "relation": self.relation,
                "note": self.note, "where": self.where}


class LinkField(NamedTuple):
    doc: str  # document kind: brief | phase | item | decision | unit | document
    path: tuple[str, ...]  # field path; "*" walks every element of a list
    kind: str  # one of EDGE_KINDS
    targets: tuple[str, ...] | None = None  # allowed ref kinds of the value, None = any local kind
    relation: str | None = None  # fixed relation
    relation_key: str | None = None  # sibling key that holds the relation
    note_key: str | None = None  # sibling key that holds the note
    prefix: str = ""  # prepended to the stored value to form the ref
    scoped: bool = False  # the value is local to the owning item (a bare unit id)
    when: tuple[str, str] | None = None  # (sibling key, value) a link must have
    origin: tuple[str, str] | None = None  # (prefix, sibling key) naming the source when it is not the document


LINK_FIELDS: tuple[LinkField, ...] = (
    LinkField("brief", ("requirements", "*", "owners", "*"), "applies_to", origin=("brief/", "id")),
    LinkField("phase", ("depends_on", "*"), "depends_on", ("phase",)),
    LinkField("item", ("depends_on", "*"), "depends_on", ("item",)),
    LinkField("item", ("related", "*", "ref"), "related", relation_key="relation", note_key="note"),
    LinkField("item", ("decisions", "*"), "decision", ("decision",)),
    LinkField("item", ("result", "decision"), "decision", ("decision",), relation="result"),
    LinkField("item", ("reads", "*", "ref"), "consumes", relation="reads"),
    LinkField("item", ("artifacts", "*", "id"), "consumes", ("artifact",), prefix="artifact/", when=("role", "input")),
    LinkField("item", ("artifacts", "*", "id"), "produces", ("artifact",), prefix="artifact/", when=("role", "output")),
    LinkField("decision", ("applies_to", "*"), "applies_to", ("phase", "item")),
    LinkField("decision", ("supersedes", "*"), "supersedes", ("decision",)),
    LinkField("document", ("applies_to", "*"), "applies_to", ("phase", "item")),
    LinkField("unit", ("depends_on", "*"), "unit_depends_on", ("unit",), scoped=True),
    LinkField("unit", ("parent",), "parent", ("unit",), scoped=True),
)

# Stored back-pointers: (document kind, field) -> (document kind, forward field) that must name the owner back.
BACKLINKS: dict[tuple[str, str], tuple[str, str]] = {("decision", "superseded_by"): ("decision", "supersedes")}


def _safe_key(identifier: str) -> tuple:
    try:
        return 0, id_sort_key(identifier)
    except ValueError:
        return 1, identifier


def _leaves(node: Any, path: tuple[str, ...], pointer: str = "", element: dict | None = None
            ) -> Iterator[tuple[str, str, dict, dict]]:
    """``(pointer, value, holder, element)`` per string leaf: ``holder`` owns the leaf, ``element`` is the dict at
    the first list level of the path (the requirement that lists owners, the related entry, ...)."""
    head, rest = path[0], path[1:]
    if head == "*":
        for index, child in enumerate(node if isinstance(node, list) else []):
            here = element if element is not None else (child if isinstance(child, dict) else {})
            if rest:
                yield from _leaves(child, rest, f"{pointer}/{index}", here)
            elif isinstance(child, str):
                yield f"{pointer}/{index}", child, {}, here
    elif isinstance(node, dict):
        value = node.get(head)
        if rest:
            yield from _leaves(value, rest, f"{pointer}/{head}", element)
        elif isinstance(value, str):
            yield f"{pointer}/{head}", value, node, element if element is not None else node


def documents(plan: store.Plan) -> Iterator[tuple[str, str, str, dict]]:
    """``(kind, key, node name, doc)`` of every document that can carry links, in a fixed order."""
    yield "brief", "", "brief", plan.brief
    for key in sorted(plan.phases, key=_safe_key):
        yield "phase", key, key, plan.phases[key]
    for key in sorted(plan.items, key=_safe_key):
        yield "item", key, key, plan.items[key]
    for key in sorted(plan.decisions, key=_safe_key):
        yield "decision", key, key, plan.decisions[key]
    for key in sorted(plan.units, key=lambda k: tuple(_safe_key(part) for part in k.split("/"))):
        yield "unit", key, key, plan.units[key]
    for key in sorted(plan.documents):
        yield "document", key, f"knowledge/{key}", plan.documents[key]


def tagged(plan: store.Plan) -> Iterator[tuple[LinkField, Edge]]:
    """Every link with the table row that declared it, in a deterministic order (document, row, list index)."""
    for kind, key, name, doc in documents(plan):
        if not isinstance(doc, dict):
            continue
        rel = plan.rel(plan.path(kind, key or None))
        for field in LINK_FIELDS:
            if field.doc != kind:
                continue
            for pointer, value, holder, element in _leaves(doc, field.path):
                if field.when and holder.get(field.when[0]) != field.when[1]:
                    continue
                source = name
                if field.origin:
                    ident = element.get(field.origin[1])
                    if not isinstance(ident, str):
                        continue
                    source = f"{field.origin[0]}{ident}"
                target = f"{key.split('/')[0]}/{value}" if field.scoped else f"{field.prefix}{value}"
                relation = field.relation or (holder.get(field.relation_key) if field.relation_key else None)
                note = holder.get(field.note_key) if field.note_key else None
                yield field, Edge(source, target, field.kind, relation if isinstance(relation, str) else None,
                                  note if isinstance(note, str) else None, f"{rel}{pointer}")


def edges(plan: store.Plan) -> list[Edge]:
    """Every link of the plan as an ``Edge``."""
    return [edge for _field, edge in tagged(plan)]


def declared_artifacts(plan: store.Plan) -> list[tuple[str, str, dict]]:
    """``(artifact id, owning item, entry)`` for every artifact entry with an id, in item order."""
    found = []
    for key in sorted(plan.items, key=_safe_key):
        entries = plan.items[key].get("artifacts") if isinstance(plan.items[key], dict) else None
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                found.append((entry["id"], key, entry))
    return found


def locate(plan: store.Plan, ref: str) -> dict | None:
    """The document, knowledge section or artifact entry a LOCAL ``ref`` names; None when it does not exist.

    Raises ``ValueError`` for a malformed ref. A qualified ref names another plan and is never located here.
    """
    parsed = parse_ref(ref)
    if parsed.plan is not None:
        raise ValueError(f"qualified ref {ref!r} is not local")
    kind, target = parsed.kind, parsed.target
    if kind == "knowledge":
        doc = plan.documents.get(target)
        if doc is None or parsed.section is None:
            return doc
        sections = doc.get("sections") if isinstance(doc, dict) else None
        return next((s for s in sections or [] if isinstance(s, dict) and s.get("id") == parsed.section), None) \
            if isinstance(sections, list) else None
    if kind == "artifact":
        owned = [(item, entry) for ident, item, entry in declared_artifacts(plan) if ident == target]
        return next((entry for _item, entry in owned if entry.get("role") == "output"), None)
    table = {"phase": plan.phases, "item": plan.items, "decision": plan.decisions, "unit": plan.units}[kind]
    return table.get(target)
