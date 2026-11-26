"""Ready-task preview: golden scenarios, waiting reasons, required batches, footprint conflicts and routes."""

import copy
import itertools
import json
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

import pytest

from skm.modules.planning.domain.compile_graph import compile_execution_graph
from skm.modules.planning.domain.item import route_to_doc
from skm.modules.planning.domain.ready_preview import (
    LaneConflict,
    ReadyPreview,
    Waiting,
    preview_ready,
)
from skm.modules.planning.domain.specification import Specification, from_document, to_document
from skm.modules.planning.domain.validation.globs import globs_overlap
from skm.platform.schema.registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[4]
EXAMPLES = ROOT / "tests/fixtures/corpus/examples/plans"
SPECIFICATION = "urn:skm:planning:specification:v1"
ECONOMY = {"class": "economy", "effort": "low"}
IMPLEMENTATION = {"class": "implementation", "effort": "medium"}


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def _spec(doc: dict[str, Any], registry: SchemaRegistry) -> Specification:
    registry.require_valid(SPECIFICATION, doc)
    spec, findings = from_document(doc)
    assert findings == ()
    return spec


def _plan(phases: list[dict[str, Any]], items: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    """A minimal schema-valid document; entities get sequential ids in document order."""
    counter = iter(range(1, 10_000))

    def with_id(entity: dict[str, Any]) -> dict[str, Any]:
        return {"id": f"0192f5c4-0000-7000-8000-{next(counter):012x}", **entity}

    return {
        "schema": SPECIFICATION,
        "title": "Synthetic plan",
        "goal": "Exercise the preview.",
        "phases": [
            with_id({"title": p["key"], "goal": "g", "design_state": "detailed", **p}) for p in phases
        ],
        "items": [
            with_id(
                {
                    "phase": i["key"].split(".")[0],
                    "title": i["key"],
                    "summary": "s",
                    "why": "w",
                    "review": {"mode": "self", "reason": "synthetic"},
                    **i,
                }
            )
            for i in items
        ],
        **extra,
    }


def _hints(mount: str, *patterns: str) -> list[dict[str, str]]:
    return [{"mount": mount, "pattern": pattern, "change": "modify"} for pattern in patterns]


def _preview(
    spec: Specification, *, done: tuple[str, ...] = (), granted: tuple[str, ...] = (), limit: int = 8
) -> ReadyPreview:
    graph = compile_execution_graph(spec)
    return preview_ready(
        graph, spec, assume_done=frozenset(done), assume_granted=frozenset(granted), limit=limit
    )


def _golden_view(preview: ReadyPreview) -> dict[str, Any]:
    """The shape of a scenario in ``examples/plans/ready-preview.json``."""
    lanes = []
    for n, lane in enumerate(preview.lanes, start=1):
        view: dict[str, Any] = {"lane": f"L{n}", "kind": lane.kind}
        if lane.batch_key is not None:
            view["batch"] = lane.batch_key
        view["tasks"] = list(lane.tasks)
        view["route"] = None if lane.route is None else route_to_doc(lane.route)
        lanes.append(view)
    return {
        "limit": preview.limit,
        "assume_done": list(preview.assume_done),
        "assume_granted": list(preview.assume_granted),
        "lanes": lanes,
        "conflicts": [
            {"task": c.task, "with": c.with_task, "reason": c.reason, "paths": list(c.paths)}
            for c in preview.conflicts
        ],
        "waiting": [{"task": w.task, "reason": w.reason, "detail": list(w.detail)} for w in preview.waiting],
        "deferred": list(preview.deferred),
        "route_groups": [[f"L{index + 1}" for index in group.lanes] for group in preview.route_groups],
    }


@pytest.mark.parametrize("name", ["fresh", "phase-1-accepted"])
def test_golden_scenarios(registry, name):
    golden = json.loads((EXAMPLES / "ready-preview.json").read_text())
    scenario = next(s for s in golden["scenarios"] if s["name"] == name)
    spec = _spec(json.loads((EXAMPLES / "auth-refresh.specification.json").read_text()), registry)
    preview = _preview(
        spec,
        done=tuple(scenario["assume_done"]),
        granted=tuple(scenario["assume_granted"]),
        limit=scenario["limit"],
    )
    expected = {key: value for key, value in scenario.items() if key != "name"}
    assert _golden_view(preview) == expected


def test_preview_reads_only_and_writes_no_effective_values(registry):
    doc = _plan(
        [{"key": "P1"}],
        [{"key": "P1.1", "work_policy": {"role_intensity": {"reviewer": "light"}}}, {"key": "P1.2"}],
    )
    spec = _spec(doc, registry)
    before = copy.deepcopy(to_document(spec))
    graph = compile_execution_graph(spec)
    preview_ready(graph, spec, assume_done=frozenset(), assume_granted=frozenset(), limit=4)
    after: dict[str, Any] = to_document(spec)
    assert after == before
    assert "work_policy" not in after["items"][1]  # no default was added to the item that declared none
    assert graph == compile_execution_graph(spec)


def test_limit_is_capped_by_max_parallel_units(registry):
    doc = _plan(
        [{"key": "P1"}],
        [{"key": f"P1.{n}", "change_hints": _hints("repo", f"src/{n}.py")} for n in (1, 2, 3)],
        execution_constraints={"strategy": "dag", "max_parallel_units": 2},
    )
    preview = _preview(_spec(doc, registry), limit=5)
    assert preview.limit == 2
    assert [lane.tasks for lane in preview.lanes] == [("P1.1",), ("P1.2",)]
    assert preview.deferred == ("P1.3",)


def test_skeleton_phase_waits_for_design(registry):
    doc = _plan([{"key": "P1", "design_state": "skeleton"}], [{"key": "P1.1"}])
    preview = _preview(_spec(doc, registry))
    assert preview.lanes == ()
    assert preview.waiting[0] == Waiting("P1.1", "design_required", ("P1",))


def test_owner_gate_waits_until_granted_and_external_gate_always_waits(registry):
    doc = _plan(
        [{"key": "P1"}],
        [
            {"key": "P1.1", "authority": {"kind": "owner_gate", "gate": "SEC", "scope": "release"}},
            {"key": "P1.2", "authority": {"kind": "external_gate", "label": "vendor", "scope": "contract"}},
        ],
    )
    spec = _spec(doc, registry)
    waiting = {w.task: w for w in _preview(spec).waiting}
    assert waiting["P1.1"] == Waiting("P1.1", "owner_gate", ("SEC",))
    assert waiting["P1.2"] == Waiting("P1.2", "external_gate", ("vendor",))
    granted = _preview(spec, granted=("SEC", "vendor"))
    assert [lane.tasks for lane in granted.lanes] == [("P1.1",)]
    assert {w.task: w.reason for w in granted.waiting}["P1.2"] == "external_gate"


def test_dependencies_are_reported_before_design_and_authority(registry):
    doc = _plan(
        [{"key": "P1", "design_state": "skeleton"}],
        [{"key": "P1.1"}, {"key": "P1.2", "depends_on": ["P1.1"], "authority": {"kind": "owner_gate",
                                                                               "gate": "G", "scope": "s"}}],
    )  # fmt: skip
    waiting = {w.task: w for w in _preview(_spec(doc, registry)).waiting}
    assert waiting["P1.2"] == Waiting("P1.2", "dependencies", ("P1.1",))


def test_required_batch_starts_together_or_waits_as_a_whole(registry):
    doc = _plan(
        [{"key": "P1", "batches": [{"key": "B1", "items": ["P1.1", "P1.2"], "mode": "required"}]}],
        [
            {
                "key": "P1.1",
                "route": {"class": "implementation", "effort": "high", "runtime": "codex", "model": "m"},
                "change_hints": _hints("repo", "src/a.py"),
            },
            {
                "key": "P1.2",
                "route": {"class": "frontier", "effort": "low", "runtime": "codex", "model": "m"},
                "authority": {"kind": "owner_gate", "gate": "G", "scope": "s"},
                "change_hints": _hints("repo", "src/b.py"),
            },
        ],
    )
    spec = _spec(doc, registry)
    held = _preview(spec)
    assert held.lanes == ()
    assert held.waiting[:2] == (
        Waiting("P1.1", "batch_incomplete", ("P1.2",)),
        Waiting("P1.2", "owner_gate", ("G",)),
    )
    started = _preview(spec, granted=("G",))
    (lane,) = started.lanes
    assert (lane.kind, lane.tasks, lane.batch_key) == ("batch", ("P1.1", "P1.2"), "P1/B1")
    assert lane.route is not None
    assert route_to_doc(lane.route) == {
        "class": "frontier",
        "effort": "high",
        "runtime": "codex",
        "model": "m",
    }


def test_required_batch_with_an_entry_waiting_on_its_batch_offers_no_partial_lane(registry):
    batch = [{"key": "P1", "batches": [{"key": "B1", "items": ["P1.1", "P1.2", "P1.3"], "mode": "required"}]}]
    doc = _plan(
        batch,
        [
            {"key": "P1.1", "change_hints": _hints("repo", "src/a.py")},
            {"key": "P1.2", "depends_on": ["P1.1"], "change_hints": _hints("repo", "src/b.py")},
            {"key": "P1.3", "change_hints": _hints("repo", "src/c.py")},
        ],
    )
    spec = _spec(doc, registry)
    held = _preview(spec)
    assert held.lanes == ()
    assert held.waiting[:3] == (
        Waiting("P1.1", "batch_incomplete", ("P1.2",)),
        Waiting("P1.2", "dependencies", ("P1.1",)),
        Waiting("P1.3", "batch_incomplete", ("P1.2",)),
    )
    continued = _preview(spec, done=("P1.1",))
    assert [(lane.kind, lane.tasks) for lane in continued.lanes] == [("batch", ("P1.2", "P1.3"))]
    independent = _plan(batch, [{"key": key, "change_hints": _hints("repo", f"src/{key}.py")}
                                for key in ("P1.1", "P1.2", "P1.3")])  # fmt: skip
    (lane,) = _preview(_spec(independent, registry)).lanes
    assert (lane.kind, lane.tasks) == ("batch", ("P1.1", "P1.2", "P1.3"))


@pytest.mark.parametrize(
    ("second", "conflict"),
    [
        (_hints("repo", "src/*.py"), LaneConflict("P1.2", "P1.1", "write_scope_overlap",
                                                  ("repo:src/*.py", "repo:src/shared.py"))),
        (None, LaneConflict("P1.2", "P1.1", "footprint_unknown", ())),
    ],
)  # fmt: skip
def test_required_batch_whose_members_clash_is_rejected_as_a_whole(registry, second, conflict):
    doc = _plan(
        [{"key": "P1", "batches": [{"key": "B1", "items": ["P1.1", "P1.2"], "mode": "required"}]}],
        [
            {"key": "P1.1", "change_hints": _hints("repo", "src/shared.py")},
            {"key": "P1.2", **({} if second is None else {"change_hints": second})},
            {"key": "P1.3", "change_hints": _hints("repo", "src/shared.py")},
        ],
    )
    preview = _preview(_spec(doc, registry), limit=1)
    assert preview.conflicts == (conflict,)
    assert [(lane.kind, lane.tasks) for lane in preview.lanes] == [("task", ("P1.3",))]
    assert preview.deferred == ()  # the rejected batch took no slot


def test_footprint_conflicts_unknown_footprints_and_deferral(registry):
    doc = _plan(
        [{"key": "P1"}],
        [
            {"key": "P1.1", "change_hints": _hints("api", "src/a/*.py")},
            {"key": "P1.2", "change_hints": _hints("api", "./src/a/b.py")},
            {"key": "P1.3", "change_hints": _hints("web", "src/a/b.py")},
            {"key": "P1.4"},
            {"key": "P1.5", "change_hints": _hints("api", "docs/")},
        ],
    )
    spec = _spec(doc, registry)
    preview = _preview(spec)
    assert [lane.tasks for lane in preview.lanes] == [("P1.1",), ("P1.3",), ("P1.5",)]
    assert preview.conflicts == (
        LaneConflict("P1.2", "P1.1", "write_scope_overlap", ("api:./src/a/b.py", "api:src/a/*.py")),
        LaneConflict("P1.4", "P1.1", "footprint_unknown", ()),
    )
    limited = _preview(spec, limit=1)
    assert [lane.tasks for lane in limited.lanes] == [("P1.1",)]
    assert [c.task for c in limited.conflicts] == ["P1.2", "P1.4"]  # a clash is reported even without a slot
    assert limited.deferred == ("P1.3", "P1.5")


def test_directory_prefix_overlaps_its_files(registry):
    doc = _plan(
        [{"key": "P1"}],
        [
            {"key": "P1.1", "change_hints": _hints("api", "tests/")},
            {"key": "P1.2", "change_hints": _hints("api", "tests/x/y.py")},
        ],
    )
    (conflict,) = _preview(_spec(doc, registry)).conflicts
    assert (conflict.task, conflict.reason) == ("P1.2", "write_scope_overlap")


def test_two_globs_sharing_a_path_conflict_though_neither_matches_the_other(registry):
    doc = _plan(
        [{"key": "P1"}],
        [
            {"key": "P1.1", "change_hints": _hints("api", "src/a*.py")},
            {"key": "P1.2", "change_hints": _hints("api", "src/*b.py")},  # both match src/ab.py
            {"key": "P1.3", "change_hints": _hints("api", "src/*.md")},
        ],
    )
    preview = _preview(_spec(doc, registry))
    assert [lane.tasks for lane in preview.lanes] == [("P1.1",), ("P1.3",)]
    assert preview.conflicts == (
        LaneConflict("P1.2", "P1.1", "write_scope_overlap", ("api:src/*b.py", "api:src/a*.py")),
    )


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("src/a*.py", "src/*b.py"),  # src/ab.py
        ("src/*.py", "src/a?.py"),
        ("src/a**b", "src/ab"),  # "**" inside a segment is "*"
        ("a/**/c", "a/b/x/c"),  # a whole "**" segment spans segments
        ("src/**", "src"),  # ... and none
        ("**/*.py", "lib/x/y.py"),
        ("src/y.py", "**/x.py"),  # a plain path names everything under it: src/y.py/x.py
        ("src/*", "src/a/b.py"),  # src/a is a directory of src/a/b.py
        ("tests/", "tests/x/y.py"),
        ("./src//a/", "src/a/b.py"),
        ("src/[ab].py", "src/a.py"),
        ("src/[x", "src/[x/y"),  # an unclosed "[" is literal
        ("src/*/", "src/a/b.py"),  # the fence reads "src/*/" literally; the glob reading is kept
        ("src/*/", "src/*/b.py"),
    ],
)
def test_globs_overlap_when_some_path_lies_under_both(left, right):
    assert globs_overlap(left, right)
    assert globs_overlap(right, left)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("src/*.py", "src/*.md"),
        ("src/a*.py", "src/b*.py"),
        ("src/a?.py", "src/abc.py"),
        ("src/*.py", "src/a/b.py"),  # "*" does not cross "/"
        ("a*/c", "ab/x/c"),
        ("tests/*.py", "tests/unit/x.py"),
        ("src/**/*.py", "lib/x.py"),
        ("src/[ab].py", "src/c.md"),
        ("docs/", "src/a/*.py"),
        ("src", "srcx/y"),
        ("src/*/", "lib/x"),
    ],
)
def test_globs_are_disjoint_only_when_no_path_lies_under_both(left, right):
    assert not globs_overlap(left, right)
    assert not globs_overlap(right, left)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("src/[!a].py", "src/a.py"),  # a bracket set reads as any character
        ("/abs/x", "src/y"),
        ("../x", "src/y"),
        ("src/../x", "lib/y"),
        ("src\\x", "lib/y"),
        ("C:/x", "lib/y"),
        ("~/x", "lib/y"),
        ("", "src"),
        (".", "src/x"),  # the root
        ("./", "src/x"),
    ],
)
def test_unsupported_or_root_patterns_may_overlap_anything(left, right):
    assert globs_overlap(left, right)
    assert globs_overlap(right, left)


_SEGMENTS = ("a", "b", "ab", "ab.py", "x.py", "a.md", "[x", "*", "src")
_PATTERNS = (
    "a", "a/", "a/b", "ab.py", "*", "*/", "**", "a/**", "**/x.py", "a/**/b", "*.py", "a*.py", "*b.py",
    "a?", "?b*", "[ab]", "[!a]*", "[x", "[x/*", "*/*.md", "src/*", "src/**/x.py", "a/*/b", "*/a.md/", "a**",
    "**/*/a",
)  # fmt: skip


def _fence_matches(path: tuple[str, ...], pattern: str) -> bool:
    """The write-scope fence of adapters §3.5, restated for paths that need no normalisation."""
    parts = tuple(part for part in pattern.split("/") if part not in ("", "."))
    if pattern.endswith("/") or not any(char in pattern for char in "*?["):
        return path[: len(parts)] == parts

    def segments(at: int, rest: tuple[str, ...]) -> bool:
        if not rest:
            return at == len(path)
        if rest[0] == "**":
            return any(segments(n, rest[1:]) for n in range(at, len(path) + 1))
        return at < len(path) and fnmatchcase(path[at], rest[0]) and segments(at + 1, rest[1:])

    return segments(0, parts)


def test_globs_overlap_never_misses_a_shared_path():
    paths = [
        path for depth in (1, 2, 3) for path in itertools.product(_SEGMENTS, repeat=depth)
    ]  # fmt: skip
    under = {
        pattern: {path for path in paths if any(_fence_matches(path[:n], pattern) for n in range(1, 4))}
        for pattern in _PATTERNS
    }
    missed = [
        (left, right)
        for left, right in itertools.combinations_with_replacement(_PATTERNS, 2)
        if under[left] & under[right] and not globs_overlap(left, right)
    ]
    assert missed == []


def test_gate_lanes_take_a_slot_but_occupy_no_footprint(registry):
    doc = _plan(
        [{"key": "P1"}, {"key": "P2", "depends_on": []}], [{"key": "P1.1"}, {"key": "P2.1", "route": ECONOMY}]
    )
    preview = _preview(_spec(doc, registry), done=("P1.1",), limit=2)
    assert [(lane.kind, lane.tasks) for lane in preview.lanes] == [
        ("gate", ("P1#gate",)),
        ("task", ("P2.1",)),
    ]
    assert preview.conflicts == ()  # the unknown footprint of P2.1 does not clash with a gate
    assert preview.waiting == (Waiting("P2#gate", "dependencies", ("P2.1",)),)
    assert _preview(_spec(doc, registry), done=("P1.1",), limit=1).deferred == ("P2.1",)


def test_route_groups_join_equal_routes_and_routeless_lanes_ride_with_the_first(registry):
    doc = _plan(
        [{"key": "P1"}, {"key": "P2", "depends_on": []}],
        [
            {"key": "P1.1"},
            {"key": "P2.1", "route": ECONOMY, "change_hints": _hints("repo", "a")},
            {"key": "P2.2", "route": IMPLEMENTATION, "change_hints": _hints("repo", "b")},
            {"key": "P2.3", "route": ECONOMY, "change_hints": _hints("repo", "c")},
        ],
    )
    preview = _preview(_spec(doc, registry), done=("P1.1",))
    assert [(lane.kind, lane.tasks) for lane in preview.lanes] == [
        ("gate", ("P1#gate",)),
        ("task", ("P2.1",)),
        ("task", ("P2.2",)),
        ("task", ("P2.3",)),
    ]
    groups = [(route_to_doc(group.route), group.lanes) for group in preview.route_groups]
    assert groups == [(ECONOMY, (0, 1, 3)), (IMPLEMENTATION, (2,))]


def test_assume_done_is_reported_in_task_order(registry):
    doc = _plan([{"key": "P1"}], [{"key": "P1.1"}, {"key": "P1.2"}])
    preview = _preview(_spec(doc, registry), done=("P1.2", "unknown", "P1.1"), granted=("b", "a"))
    assert preview.assume_done == ("P1.1", "P1.2", "unknown")
    assert preview.assume_granted == ("a", "b")
    assert [lane.tasks for lane in preview.lanes] == [("P1#gate",)]
