"""Small counterexamples for every P00.05.a rule and shared AST/exception behavior."""

import ast
from datetime import date
from pathlib import Path

import pytest

from ._allowlist import load
from ._layers import Layer, classify
from ._manifests import dependencies
from ._tree import SourceFile, async_defs, calls, collect, imports, string_constants
from .rules import (
    RULES,
    RuleContext,
    Violation,
    rule_application_boundary,
    rule_db_ownership,
    rule_domain_purity,
    rule_host_boundary,
    rule_host_io,
    rule_import_cycles,
    rule_layer_imports,
    rule_module_facade,
    rule_module_graph,
    rule_no_fstring_sql,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"


def source(path: str, text: str) -> SourceFile:
    return SourceFile.at(Path("src/skm") / path, text)


@pytest.mark.parametrize("rule", RULES, ids=lambda rule: rule.__name__.removeprefix("rule_"))
def test_rule_has_bad_fixture_and_allowed_boundary(rule) -> None:
    context = RuleContext({"planning": ("workspace",), "workspace": (), "access": ()})
    name = rule.__name__.removeprefix("rule_")
    bad = collect(FIXTURES / "bad_tree")
    findings = [v for v in rule(bad, context) if v.path.endswith(f"violates_{name}.py")]
    assert findings
    for finding in findings:
        assert finding.line >= 1
        assert finding.rule == name.replace("_", "-")
        assert finding.render().startswith(f"{finding.path}:{finding.line}: [{finding.rule}]")
    assert rule(collect(FIXTURES / "good_tree"), context) == []


@pytest.fixture(scope="module")
def root_tree(session_root_tree: tuple[SourceFile, ...]) -> list[SourceFile]:
    return list(session_root_tree)


@pytest.fixture(scope="module")
def root_context() -> RuleContext:
    return RuleContext(dependencies())


@pytest.mark.parametrize("rule", RULES, ids=lambda rule: rule.__name__.removeprefix("rule_"))
def test_materialized_tree_satisfies_import_rules(rule, root_tree, root_context) -> None:
    findings = rule(root_tree, root_context)
    assert not findings, "\n".join(v.render() for v in findings)


@pytest.mark.parametrize(
    ("path", "layer"),
    [
        ("kernel/generated/commands.py", Layer.KERNEL),
        ("platform/config/sources/env.py", Layer.PLATFORM),
        ("modules/planning/domain/plan.py", Layer.DOMAIN),
        ("modules/planning/ports.py", Layer.PORTS),
        ("modules/planning/application/x.py", Layer.APPLICATION),
        ("modules/planning/host/x.py", Layer.HOST),
        ("modules/planning/generated/commands.py", Layer.GENERATED),
        ("modules/planning/public.py", Layer.PUBLIC),
        *(
            (f"modules/planning/{name}.py", Layer.MODULE_META)
            for name in ("module", "settings", "permissions", "errors")
        ),
        ("application_bus/bus.py", Layer.BUS),
        ("adapters/postgres/planning/plan.py", Layer.ADAPTER),
        ("background/leases.py", Layer.BACKGROUND),
        ("entrypoints/worker/main.py", Layer.ENTRYPOINT),
        ("sdk/__init__.py", Layer.ENTRYPOINT),
        ("bootstrap/composition.py", Layer.BOOTSTRAP),
        ("plugin_api/stages.py", Layer.PLUGIN_API),
    ],
)
def test_classify_all_layers(path: str, layer: Layer) -> None:
    assert classify(Path("src/skm") / path) == layer


def test_imports_resolve_symbols_packages_aliases_and_relative_init() -> None:
    file = source(
        "modules/planning/application/x.py",
        "from ...workspace import public as workspace\n"
        "from ..domain.plan import Plan as P\nimport os.path as paths\n",
    )
    assert [(r.module, r.names, r.bindings) for r in imports(file)] == [
        ("skm.modules.workspace", ("public",), ("workspace",)),
        ("skm.modules.planning.domain.plan", ("Plan",), ("P",)),
        ("os.path", (), ("paths",)),
    ]
    init = source("modules/planning/domain/__init__.py", "from .plan import Plan")
    assert imports(init)[0].targets == ("skm.modules.planning.domain.plan.Plan",)
    file = source("modules/planning/domain/x.py", "from ... import workspace as w")
    assert imports(file)[0].targets == ("skm.modules.workspace",)


def test_ast_calls_constants_and_async_constructs() -> None:
    file = source(
        "modules/planning/domain/x.py",
        "import datetime as d\nfrom uuid import uuid4 as new\n"
        "make = new\nvalue = make()\nstamp = d.datetime.now()\n"
        "label = 'sample'\nasync def run():\n    await wait()\n"
        "    async with lock():\n        async for item in stream():\n            pass\n",
    )
    assert {call.name for call in calls(file)} >= {"uuid.uuid4", "datetime.datetime.now"}
    assert ("sample", 6) in string_constants(file)
    assert {type(n) for n in async_defs(file)} == {
        ast.AsyncFunctionDef,
        ast.Await,
        ast.AsyncWith,
        ast.AsyncFor,
    }


@pytest.mark.parametrize(
    "statement",
    [
        "import skm.modules.workspace.domain.plan as plan",
        "from skm.modules.workspace import domain as plan",
        "from ...workspace.domain import plan",
        "from skm.modules import workspace",
        "from skm.modules.workspace.public import *",
        "if TYPE_CHECKING:\n    from skm.modules.workspace.ports import ProjectRepository",
    ],
)
def test_no_from_alias_relative_or_type_guard_facade_bypass(statement: str) -> None:
    file = source("modules/planning/application/x.py", statement)
    assert rule_module_facade([file], RuleContext())


@pytest.mark.parametrize(
    "statement",
    [
        "from skm.application_bus import client as bus",
        "from skm.application_bus import bus",
        "import skm.application_bus.host as host",
        "from skm.platform import process",
        "from skm.modules.planning import host",
    ],
)
def test_application_layer_restrictions_cover_from_import(statement: str) -> None:
    file = source("modules/planning/application/x.py", statement)
    assert rule_layer_imports([file], RuleContext())


def test_graph_checks_direct_edges_cycles_and_unknown_modules() -> None:
    file = source("modules/planning/application/x.py", "from skm.modules.access import public")
    ctx = RuleContext({"planning": ("workspace",), "workspace": ("access",), "access": ()})
    assert rule_module_graph([file], ctx)  # A transitive dependency is insufficient.
    assert "cycle:" in rule_module_graph([], RuleContext({"a": ("b",), "b": ("a",)}))[0].message
    assert "unknown" in rule_module_graph([], RuleContext({"a": ("missing",)}))[0].message


def _cycle_pair(directory: str, first: str, second: str) -> list[SourceFile]:
    """Two files whose imports point at each other; each import line is given verbatim."""
    package = "skm." + directory.replace("/", ".")
    return [
        source(f"{directory}/a.py", first.format(other=f"{package}.b")),
        source(f"{directory}/b.py", second.format(other=f"{package}.a")),
    ]


TOP = "from {other} import X\n"
DEFERRED = "def f() -> None:\n    from {other} import X\n"
GUARDED = "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from {other} import X\n"


@pytest.mark.parametrize("directory", ["modules/planning/domain", "adapters/git", "entrypoints/cli"])
def test_module_level_import_cycle_fails_in_every_layer(directory: str) -> None:
    findings = rule_import_cycles(_cycle_pair(directory, TOP, TOP), RuleContext())
    assert {Path(v.path).name for v in findings} == {"a.py", "b.py"}
    assert all(v.rule == "import-cycles" for v in findings)


def test_function_local_import_cannot_hide_a_domain_or_ports_cycle() -> None:
    assert rule_import_cycles(_cycle_pair("modules/planning/domain", TOP, DEFERRED), RuleContext())
    ports = [
        source("modules/planning/ports.py", "from skm.modules.planning.domain.a import X\n"),
        source(
            "modules/planning/domain/a.py", "def f() -> None:\n    from skm.modules.planning.ports import P\n"
        ),
    ]
    assert rule_import_cycles(ports, RuleContext())


def test_deferred_imports_outside_the_pure_core_and_type_guards_do_not_count() -> None:
    assert not rule_import_cycles(_cycle_pair("adapters/git", TOP, DEFERRED), RuleContext())
    assert not rule_import_cycles(_cycle_pair("modules/planning/domain", TOP, GUARDED), RuleContext())
    # Different modules' domains never form a pure-core pair; module-facade rejects such imports anyway.
    mixed = [
        source("modules/planning/domain/a.py", "from skm.modules.access.domain.b import X\n"),
        source(
            "modules/access/domain/b.py",
            "def f() -> None:\n    from skm.modules.planning.domain.a import X\n",
        ),
    ]
    assert not rule_import_cycles(mixed, RuleContext())


def test_selected_annotation_contract_cannot_become_runtime_dependency() -> None:
    prefix = (
        "from typing import TYPE_CHECKING as TC\nif TC:\n"
        "    from skm.application_bus.host import HostContext as H\n"
    )
    path = "modules/execution/ports.py"
    valid = source(path, prefix + "def run(ctx: H) -> None: ...\n")
    assert not rule_layer_imports([valid], RuleContext())
    for usage in (
        "ctx = H()",
        "factory = H",
        "class Host(H): pass",
        "def run(ctx=H): pass",
        "def run(ctx: H()): pass",
    ):
        file = source(path, prefix + usage)
        assert rule_layer_imports([file], RuleContext()), usage
    assert rule_layer_imports(
        [source(path, "from skm.application_bus.host import HostContext as H")], RuleContext()
    )
    assert rule_layer_imports([source("modules/planning/domain/x.py", prefix)], RuleContext())


@pytest.mark.parametrize("tail", ["value = P('.')", "factory = P", "P.read_text(value)"])
def test_path_contract_is_annotation_only(tail: str) -> None:
    path = "modules/execution/ports.py"
    prefix = "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from pathlib import Path as P\n"
    assert not rule_domain_purity([source(path, prefix + "def run(path: P): ...")], RuleContext())
    assert rule_domain_purity([source(path, prefix + tail)], RuleContext())


def test_annotated_path_parameters_and_fields_cannot_perform_io() -> None:
    prefix = "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from pathlib import Path as P\n"
    for body in (
        "def run(path: P): return path.read_text()",
        "class Environment:\n    root: P\n    def run(self): return self.root.read_bytes()",
    ):
        file = source("modules/execution/host/environment.py", prefix + body)
        findings = rule_host_io([file], RuleContext())
        assert any("pathlib.Path.read_" in v.message for v in findings)


@pytest.mark.parametrize("annotation", ["Path", "Path | None", '"Path"', '"Path | None"'])
@pytest.mark.parametrize("import_form", ["from pathlib import Path", "from pathlib import Path as P"])
def test_path_union_and_forward_annotations_preserve_io_boundary(annotation: str, import_form: str) -> None:
    if import_form.endswith("as P"):
        annotation = annotation.replace("Path", "P")
    prefix = f"from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    {import_form}\n"
    for declaration, operation in (
        (f"def run(root: {annotation}):\n    ", "root.read_text()"),
        (
            f"class Environment:\n    root: {annotation}\n    def run(self):\n        ",
            "self.root.read_text()",
        ),
    ):
        path = "modules/execution/host/environment.py"
        allowed = source(path, prefix + declaration + "pass\n")
        assert not rule_host_io([allowed], RuleContext())
        forbidden = source(path, prefix + declaration + operation + "\n")
        findings = rule_host_io([forbidden], RuleContext())
        line = len((prefix + declaration).splitlines())
        assert any(
            v.path == forbidden.display_path
            and v.line == line
            and v.rule == "host-io"
            and "pathlib.Path.read_text" in v.message
            for v in findings
        ), [v.render() for v in findings]


def test_type_checking_name_must_not_be_rebound() -> None:
    for text in (
        "from typing import TYPE_CHECKING as TC\nTC = True\nif TC:\n"
        "    from skm.application_bus.host import HostContext\n",
        "import typing as t\nt = custom\nif t.TYPE_CHECKING:\n"
        "    from skm.application_bus.host import HostContext\n",
    ):
        file = source("modules/execution/ports.py", text)
        assert rule_layer_imports([file], RuleContext())


def test_purity_does_not_lose_earlier_call_when_alias_is_rebound() -> None:
    file = source(
        "modules/planning/domain/x.py", "from builtins import open as read\nread('x')\nread = safe\n"
    )
    assert rule_domain_purity([file], RuleContext())


def test_adapter_metadata_and_dependency_graph_exemption() -> None:
    file = source("adapters/postgres/planning/plan.py", "from skm.modules.workspace import public")
    assert (file.layer, file.module, file.tech) == (Layer.ADAPTER, "planning", "postgres")
    assert not rule_module_graph([file], RuleContext())
    assert not rule_module_facade([file], RuleContext())
    assert source("adapters/postgres/migrations/runner.py", "").module is None
    assert source("adapters/postgres/errors.py", "").module is None


def test_ast_model_does_not_execute_source_and_async_comprehensions_are_visible() -> None:
    file = source(
        "modules/planning/host/x.py", "raise RuntimeError('never execute')\nx = [v async for v in stream]"
    )
    assert len(async_defs(file)) == 1
    assert isinstance(async_defs(file)[0], ast.comprehension)
    assert string_constants(file) == [("never execute", 1)]


@pytest.mark.parametrize(
    "statement",
    [
        "from datetime import datetime as D\nD.now()",
        "import datetime as d\nd.date.today()",
        "from builtins import open as read\nread('x')",
        "import time as t\nt.sleep(1)",
        "from uuid import uuid4 as fresh\nnew = fresh\nnew()",
        "if TYPE_CHECKING:\n    import subprocess",
    ],
)
def test_purity_and_host_io_resolve_aliases(statement: str) -> None:
    assert rule_domain_purity([source("modules/planning/domain/x.py", statement)], RuleContext())
    assert rule_host_io([source("modules/planning/host/x.py", statement)], RuleContext())


def port_sources() -> list[SourceFile]:
    return [
        source(
            "modules/planning/ports.py",
            "from typing import Protocol\nfrom skm.kernel.ports_uow import repository_port as repo\n"
            "from skm.kernel.gateways import host_gateway as host, control_plane_gateway as control\n"
            "@repo\nclass Repo(Protocol): ...\n@host\nclass Vcs(Protocol): ...\n"
            "@control\nclass BlobStore(Protocol): ...\n",
        ),
        source(
            "modules/planning/public.py",
            "from .ports import Repo as Reader, Vcs as Gateway\n"
            "def get(uow, key): ...\ndef pure(value): return value\n",
        ),
    ]


@pytest.mark.parametrize(
    "statement",
    [
        "from ..ports import Repo as R",
        "from .. import ports as p",
        "from ..public import Reader as R",
        "from ..public import get as query",
        "from ..ports import BlobStore",
        "from skm.kernel import ports_uow as u",
        "from skm.kernel.ports_uow import UnitOfWork as U",
        "from skm.kernel.ports_uow import UnitOfWorkFactory as Factory",
        "def run(uow): pass",
    ],
)
def test_host_cannot_import_repositories_transactions_or_uow_facades(statement: str) -> None:
    tree = [*port_sources(), source("modules/planning/host/x.py", statement)]
    assert rule_host_boundary(tree, RuleContext())


def test_host_can_import_pure_public_function_and_host_gateway() -> None:
    tree = [
        *port_sources(),
        source("modules/planning/host/x.py", "from ..public import pure\nfrom ..ports import Vcs as Gateway"),
    ]
    assert not rule_host_boundary(tree, RuleContext())


def test_assignment_aliases_preserve_boundary_owners() -> None:
    ports, public = port_sources()
    ports = SourceFile.at(ports.path, ports.text + "\nVcsAlias = Vcs\nVcsChain = VcsAlias\n")
    public = SourceFile.at(public.path, public.text + "\nread = get\nread_chain = read\n")
    for name in ("Vcs", "VcsAlias", "VcsChain"):
        application = source("modules/planning/application/x.py", f"# caller\nfrom ..ports import {name}\n")
        findings = rule_application_boundary([ports, public, application], RuleContext())
        assert [(v.path, v.line, v.rule) for v in findings] == [
            (application.display_path, 2, "application-boundary")
        ], name
    for name in ("get", "read", "read_chain"):
        host = source("modules/planning/host/x.py", f"# caller\nfrom ..public import {name}\n")
        findings = rule_host_boundary([ports, public, host], RuleContext())
        assert [(v.path, v.line, v.rule) for v in findings] == [(host.display_path, 2, "host-boundary")], name


def test_assignment_aliases_preserve_allowed_gateways_and_pure_functions() -> None:
    ports, public = port_sources()
    ports = SourceFile.at(ports.path, ports.text + "\nVcsAlias = Vcs\nVcsChain = VcsAlias\n")
    public = SourceFile.at(public.path, public.text + "\ndecide = pure\ndecide_chain = decide\n")
    host = source(
        "modules/planning/host/x.py", "from ..ports import VcsChain\nfrom ..public import decide_chain\n"
    )
    assert not rule_host_boundary([ports, public, host], RuleContext())
    application = source("modules/planning/application/x.py", "from ..public import decide_chain\n")
    assert not rule_application_boundary([ports, public, application], RuleContext())


def test_assignment_alias_cycles_terminate() -> None:
    public = source("modules/planning/public.py", "first = second\nsecond = first\n")
    host = source("modules/planning/host/x.py", "from ..public import first\n")
    assert not rule_host_boundary([public, host], RuleContext())


def test_inherited_gateway_marker_and_reexported_namespaces_are_not_a_bypass() -> None:
    ports, public = port_sources()
    ports = SourceFile.at(ports.path, ports.text + "\nclass WrappedVcs(Vcs, Protocol): ...\n")
    public = SourceFile.at(
        public.path,
        public.text + "\nfrom . import ports as contracts\nfrom .ports import WrappedVcs as Wrapped\n",
    )
    for statement in (
        "from ..public import Wrapped",
        "from ..public import contracts",
        "from .. import public",
    ):
        application = source("modules/planning/application/x.py", statement)
        assert rule_application_boundary([ports, public, application], RuleContext())
    host = source("modules/planning/host/x.py", "from ..ports import WrappedVcs")
    assert not rule_host_boundary([ports, public, host], RuleContext())
    for statement in ("from ..public import contracts", "from .. import public"):
        host = source("modules/planning/host/x.py", statement)
        assert rule_host_boundary([ports, public, host], RuleContext())


def test_host_cannot_receive_uow_as_context_attribute() -> None:
    file = source("modules/planning/host/x.py", "def run(ctx): return ctx.uow.commit()")
    assert rule_host_boundary([file], RuleContext())


@pytest.mark.parametrize(
    "statement",
    [
        "from ..ports import Vcs as Gateway",
        "from ..public import Gateway as Vcs",
        "from .. import ports as p",
        "from skm.application_bus.host import HostContext as H",
    ],
)
def test_application_cannot_hide_host_gateway_behind_alias_or_facade(statement: str) -> None:
    tree = [*port_sources(), source("modules/planning/application/x.py", statement)]
    assert rule_application_boundary(tree, RuleContext())


@pytest.mark.parametrize(
    "statement",
    [
        "from skm.application_bus.host import HostContext as H",
        "from skm.application_bus.client import SkmClient as C",
        "import skm.application_bus.client as c",
        "from skm.application_bus import host as h",
        "def run(deps): return deps.client",
    ],
)
def test_host_stage_only_receives_stage_deps(statement: str) -> None:
    file = source("modules/execution/host/stages/run_checks.py", statement)
    assert rule_host_boundary([file], RuleContext())


def test_allowlist_requires_justification_checks_expiry_and_matches_exact_detail(tmp_path: Path) -> None:
    path = tmp_path / "allowlist.toml"
    entry = (
        '[[allow]]\nrule="domain-purity"\npath="src/skm/modules/planning/domain/x.py"\n'
        'detail="import of os"\nreason="migration"\nadr="0002"\nuntil="2026-10-27"\n'
    )
    path.write_text(entry)
    allowances = load(path, today=date(2026, 10, 27))
    assert allowances[0].matches(
        Violation("domain-purity", "src/skm/modules/planning/domain/x.py", 1, "import of os")
    )
    assert not allowances[0].matches(
        Violation("host-io", "src/skm/modules/planning/domain/x.py", 1, "import of os")
    )
    assert not allowances[0].matches(
        Violation("domain-purity", "src/skm/modules/planning/domain/x.py", 1, "import of sys")
    )
    with pytest.raises(ValueError, match="expired"):
        load(path, today=date(2026, 10, 28))
    for key in ("reason", "adr", "detail", "rule", "path"):
        path.write_text("\n".join(line for line in entry.splitlines() if not line.startswith(key + "=")))
        with pytest.raises(ValueError, match="required"):
            load(path, today=date(2026, 10, 27))


def test_allowlist_canonical_glob_and_symbol_detail_do_not_allow_other_imports(tmp_path: Path) -> None:
    path = tmp_path / "allowlist.toml"
    path.write_text(
        '[[allow]]\nrule="domain-purity"\npath="src/skm/modules/*/domain/**"\n'
        'detail="pathlib.PurePosixPath"\nreason="pure relative paths"\nadr="0002"\n'
    )
    file = source("modules/planning/domain/path.py", "from pathlib import PurePosixPath, Path")
    allowance = load(path, today=date(2026, 10, 27))[0]
    findings = rule_domain_purity([file], RuleContext())
    remaining = [v for v in findings if not allowance.matches(v)]
    assert len(findings) == 2
    assert len(remaining) == 1
    assert remaining[0].detail == "pathlib.Path"


RUNNER = "adapters/postgres/migrations/runner.py"
RUNNER_ARGS = 'cast("str", sql), cast("psycopg.abc.Params | None", params)'
RUNNER_ALLOWED = """\
class MigrationSession:
    def execute(self, sql, params=None):
        self._conn.execute(cast("str", sql), cast("psycopg.abc.Params | None", params))
"""


def _runner_findings(tmp_path: Path, text: str) -> tuple[list[Violation], list[Violation]]:
    """SQL-rule violations of a runner.py with ``text``, and those the real allowlist leaves uncovered."""
    file = source(RUNNER, text)
    target = tmp_path / "src/skm" / RUNNER
    target.parent.mkdir(parents=True)
    target.write_text(text, encoding="utf-8")
    allowances = load(Path(__file__).with_name("allowlist.toml"), today=date(2026, 10, 27))
    findings = rule_no_fstring_sql([file], RuleContext())
    return findings, [v for v in findings if not any(a.matches(v, root=tmp_path) for a in allowances)]


def test_runner_sql_allowance_covers_exact_trusted_calls_only(tmp_path: Path) -> None:
    findings, remaining = _runner_findings(tmp_path, RUNNER_ALLOWED)
    assert len(findings) == 1
    assert not remaining


@pytest.mark.parametrize(
    "text",
    [
        # value interpolated into the very call text
        RUNNER_ALLOWED.replace('cast("str", sql)', 'f"SELECT {params}"'),
        # a value interpolated into the statement name before an otherwise identical call
        RUNNER_ALLOWED.replace("        self._conn", '        sql = f"SELECT {params}"\n        self._conn'),
        RUNNER_ALLOWED.replace("        self._conn", "        sql += params\n        self._conn"),
        RUNNER_ALLOWED.replace("        self._conn", '        sql = "SELECT " + params\n        self._conn'),
        # the same text outside a function, and a new call that no entry names
        'self._conn.execute(cast("str", sql), cast("psycopg.abc.Params | None", params))\n',
        RUNNER_ALLOWED.replace(RUNNER_ARGS, "f'DROP {name}'"),
        RUNNER_ALLOWED.replace(RUNNER_ARGS, "'DROP ' + name"),
    ],
    ids=[
        "fstring-call",
        "fstring-assigned",
        "augmented",
        "concatenated",
        "module-level",
        "new-fstring",
        "new-concat",
    ],
)
def test_runner_sql_allowance_does_not_cover_value_interpolation(tmp_path: Path, text: str) -> None:
    findings, remaining = _runner_findings(tmp_path, text)
    assert findings
    assert remaining


def test_runner_sql_allowances_are_pinned_to_statements() -> None:
    allowances = load(Path(__file__).with_name("allowlist.toml"), today=date(2026, 10, 27))
    runner_entries = [a for a in allowances if a.path.endswith("migrations/runner.py")]
    assert runner_entries
    assert all(a.statement for a in runner_entries)


@pytest.mark.parametrize(
    "invalid",
    [
        '[[allow]]\nrule="domain-purity"\n',
        '[[allow]]\nrule="x"\npath="x"\ndetail="x"\nreason="x"\nadr="0002"\nstatement=""',
        'allow = "all"',
        '[[allow]]\nrule="x"\npath="x"\ndetail="x"\nreason=""\nadr="0002"',
        '[[allow]]\nrule="x"\npath="x"\ndetail="x"\nreason="x"\nadr="0002"\nuntil=42',
    ],
)
def test_invalid_allowlists_fail_closed(tmp_path: Path, invalid: str) -> None:
    path = tmp_path / "allowlist.toml"
    path.write_text(invalid)
    with pytest.raises(ValueError, match=r"expected|required|until|statement"):
        load(path, today=date(2026, 10, 27))


def test_cancellation_primitives_are_limited_to_kernel_cancel() -> None:
    permitted = "\n".join(
        [
            "from threading import Event, Lock",
            "from time import monotonic",
            "Event(); Lock(); monotonic()",
            "",
        ]
    )
    assert not rule_domain_purity([source("kernel/cancel.py", permitted)], RuleContext())
    assert rule_domain_purity([source("kernel/other.py", permitted)], RuleContext())
    for denied in (
        "import threading\n",
        "from threading import Thread\n",
        "import time\n",
        "from time import sleep\n",
        "from time import time\ntime()\n",
        "from pathlib import Path\n",
    ):
        assert rule_domain_purity([source("kernel/cancel.py", denied)], RuleContext()), denied


@pytest.mark.parametrize(
    "statement",
    [
        "from threading import Event as Wake, Lock as Guard\nfrom time import monotonic as now\n"
        "event = Wake(); lock = Guard(); deadline = now()\nevent.wait(0)\n",
        "from threading import Event\nfrom threading import Lock\nfrom time import monotonic\n"
        "wake = Event; mutex = Lock; clock = monotonic\nwake(); mutex(); clock()\n",
    ],
)
def test_cancellation_exception_accepts_exact_primitives_and_aliases(statement: str) -> None:
    assert not rule_domain_purity([source("kernel/cancel.py", statement)], RuleContext())


@pytest.mark.parametrize(
    "path",
    [
        "kernel/other.py",
        "kernel/generated/cancel.py",
        "kernel/cancel/__init__.py",
        "modules/planning/domain/cancel.py",
        "modules/planning/ports.py",
        "modules/planning/generated/cancel.py",
        "modules/planning/host/cancel.py",
    ],
)
def test_cancellation_exception_cannot_cover_another_file_or_layer(path: str) -> None:
    file = source(path, "from threading import Event, Lock\nfrom time import monotonic\nmonotonic()\n")
    check = rule_host_io if file.layer == Layer.HOST else rule_domain_purity
    findings = check([file], RuleContext())
    assert {finding.detail for finding in findings} >= {"threading.Event", "threading.Lock", "time.monotonic"}


@pytest.mark.parametrize(
    ("statement", "target"),
    [
        ("import threading as threads", "threading"),
        ("import time as clock", "time"),
        ("from threading import Thread as Worker", "threading.Thread"),
        ("from threading import RLock", "threading.RLock"),
        ("from threading import Timer", "threading.Timer"),
        ("from threading import Condition", "threading.Condition"),
        ("from time import sleep as wait", "time.sleep"),
        ("from time import time as now", "time.time"),
        ("from time import monotonic_ns", "time.monotonic_ns"),
        ("from time import perf_counter", "time.perf_counter"),
        ("import os", "os"),
        ("import subprocess", "subprocess"),
        ("from pathlib import Path", "pathlib.Path"),
        ("from threading import Event, Thread", "threading.Thread"),
        ("from time import monotonic, sleep", "time.sleep"),
    ],
)
def test_cancellation_exception_preserves_prohibited_imports(statement: str, target: str) -> None:
    findings = rule_domain_purity([source("kernel/cancel.py", statement)], RuleContext())
    assert target in {finding.detail for finding in findings}


@pytest.mark.parametrize(
    ("statement", "target"),
    [
        ("print('forbidden')", "print"),
        ("open('forbidden')", "open"),
        ("__import__('threading')", "__import__"),
        ("time.sleep(1)", "time.sleep"),
        ("time.time()", "time.time"),
        ("from time import sleep as wait\nwait(1)", "time.sleep"),
        ("from time import time as now\nnow()", "time.time"),
        ("from uuid import uuid4 as new\nnew()", "uuid.uuid4"),
        ("from datetime import datetime as DT\nDT.now()", "datetime.datetime.now"),
        ("from pathlib import Path as P\nP('.')", "pathlib.Path"),
    ],
)
def test_cancellation_exception_preserves_other_purity_calls(statement: str, target: str) -> None:
    prefix = "from threading import Event, Lock\nfrom time import monotonic\n"
    findings = rule_domain_purity([source("kernel/cancel.py", prefix + statement)], RuleContext())
    assert any(finding.detail == target and "call of" in finding.message for finding in findings)


def test_memory_core_import_exception_is_symbol_and_owner_scoped() -> None:
    ctx = RuleContext()
    for statement in (
        "from skm.application_bus.ports import AuditLog, OutboxState",
        "from skm.application_bus.ports import IdempotencyReceipt",
    ):
        assert not rule_layer_imports([source("adapters/memory/core/state.py", statement)], ctx)
    assert not rule_layer_imports(
        [
            source(
                "adapters/memory/uow.py",
                "from skm.application_bus.registry import SSE_DESTINATION, OUTBOX_EXTERNAL_PREFIXES",
            )
        ],
        ctx,
    )
    for path, statement in (
        ("adapters/postgres/core/state.py", "from skm.application_bus.ports import AuditLog"),
        ("adapters/memory/core/state.py", "from skm.application_bus.ports import Authorizer"),
        ("adapters/memory/core/state.py", "import skm.application_bus.ports"),
        ("adapters/memory/core/state.py", "from skm.application_bus.registry import SSE_DESTINATION"),
        ("adapters/memory/uow.py", "from skm.application_bus.registry import BusRegistry"),
        ("adapters/memory/uow.py", "from skm.application_bus.bus import Bus"),
    ):
        assert rule_layer_imports([source(path, statement)], ctx), (path, statement)


def test_project_baseline_uses_each_tables_owner_and_machine_ddl_stays_local(tmp_path: Path) -> None:
    migrations = tmp_path / "src/skm/adapters/postgres/migrations"
    project_sql, machine_sql = migrations / "sql", migrations / "machine_sql"
    project_sql.mkdir(parents=True)
    machine_sql.mkdir()
    (project_sql / "0001_core_baseline.sql").write_text(
        "CREATE TABLE skm_planning.draft (workspace uuid REFERENCES skm_workspace.workspaces);\n"
        "ALTER TABLE ONLY skm_workspace.workspaces ADD FOREIGN KEY (draft) REFERENCES skm_planning.draft;\n"
    )
    (machine_sql / "0001_host_baseline.sql").write_text(
        "CREATE TABLE skm_host.binding (id uuid REFERENCES skm_core.scopes);\n"
    )
    context = RuleContext({"planning": ("workspace",), "workspace": ()}, root=tmp_path)
    findings = rule_db_ownership([], context)
    assert [(Path(item.path).name, item.line, item.message) for item in findings] == [
        ("0001_core_baseline.sql", 2, "reference to 'skm_planning' is outside depends_on of workspace"),
        ("0001_host_baseline.sql", 1, "reference to 'skm_core' is outside depends_on of host"),
    ]
