"""P00.05.b: product guardrails, phased contracts and stored counterexamples."""

import json
from datetime import UTC, datetime
from pathlib import Path
from time import time

import pytest

from ._allowlist import load
from ._manifests import dependencies
from ._tree import SourceFile, collect
from .rules import (
    ALL_RULES,
    DEFERRED_RULES,
    GUARDRAIL_RULES,
    RuleContext,
    rule_async_placement,
    rule_bus_registration,
    rule_cli_thin,
    rule_config_access,
    rule_db_ownership,
    rule_file_names,
    rule_file_size,
    rule_generated_header,
    rule_host_io,
    rule_module_graph,
    rule_neutral_literals,
    rule_no_fstring_sql,
    rule_no_test_overrides,
    rule_print_free,
    rule_private_imports,
    rule_provider_literals,
    rule_repository_ports_implemented,
    rule_settings_declared,
    rule_third_party_by_layer,
    size_warnings,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures/guardrails"
DEFERRED = FIXTURES / "deferred"


def source(path: str, text: str) -> SourceFile:
    return SourceFile.at(Path("src/skm") / path, text)


@pytest.fixture(scope="module")
def product_tree(session_root_tree: tuple[SourceFile, ...]) -> list[SourceFile]:
    return [file for file in session_root_tree if "overlays" not in file.path.parts]


@pytest.fixture(scope="module")
def allowances() -> tuple:
    return load(Path(__file__).with_name("allowlist.toml"), today=datetime.fromtimestamp(time(), UTC).date())


@pytest.fixture(scope="module")
def product_context(allowances, session_generated_outputs) -> RuleContext:
    ctx = RuleContext(dependencies(), root=ROOT, schema_allowances=allowances)
    ctx.generated_outputs = session_generated_outputs
    return ctx


@pytest.mark.parametrize("rule", ALL_RULES, ids=lambda rule: rule.__name__.removeprefix("rule_"))
def test_root_source_satisfies_guardrails(rule, product_tree, product_context, allowances, capsys) -> None:
    findings = [v for v in rule(product_tree, product_context) if not any(a.matches(v) for a in allowances)]
    if rule is rule_file_size:
        with capsys.disabled():
            for warning in size_warnings(product_tree):
                print(warning)
    assert not findings, "\n".join(v.render() for v in findings)


FIXTURE_RULES = [
    rule
    for rule in GUARDRAIL_RULES
    if rule.__name__.removeprefix("rule_").replace("_", "-") not in DEFERRED_RULES
    and rule is not rule_file_size
] + [rule_no_fstring_sql, rule_cli_thin]


@pytest.mark.parametrize("rule", FIXTURE_RULES, ids=lambda rule: rule.__name__.removeprefix("rule_"))
def test_stored_positive_and_negative_fixtures(rule) -> None:
    for kind in ("bad", "good"):
        root = FIXTURES / kind
        findings = rule(collect(root), RuleContext(root=root))
        assert bool(findings) == (kind == "bad"), "\n".join(v.render() for v in findings)
        for finding in findings:
            assert finding.line >= 1
            assert finding.rule == rule.__name__.removeprefix("rule_").replace("_", "-")
            assert finding.render().startswith(f"{finding.path}:{finding.line}: [{finding.rule}]")


@pytest.mark.parametrize(
    "rule",
    [rule_repository_ports_implemented, rule_bus_registration, rule_settings_declared, rule_db_ownership],
)
def test_stored_deferred_rule_examples(rule) -> None:
    for kind in ("bad", "good"):
        root = DEFERRED / kind
        findings = rule(collect(root), RuleContext({"planning": ("workspace",)}, root=root))
        assert bool(findings) == (kind == "bad"), "\n".join(v.render() for v in findings)


def test_each_deferred_rule_has_concrete_leaf_ids_and_automatic_activation() -> None:
    assert set(DEFERRED_RULES) == {
        "repository-ports-implemented",
        "bus-registration",
        "settings-declared",
        "db-ownership",
        "no-fstring-sql",
        "cli-thin",
    }
    rule_ids = {rule.__name__.removeprefix("rule_").replace("_", "-") for rule in ALL_RULES}
    assert set(DEFERRED_RULES) <= rule_ids
    for gate in DEFERRED_RULES.values():
        assert gate["when"]
        assert gate["leaves"]
        assert all(leaf.startswith("P") and len(leaf.split(".")) >= 2 for leaf in gate["leaves"])


def test_direct_sql_in_host_and_transitive_module_dependency_fail() -> None:
    tree = collect(FIXTURES / "bad")
    assert any(v.path.endswith("violates_host_io_sql.py") for v in rule_host_io(tree, RuleContext()))
    file = source(
        "modules/planning/application/violates_module_graph.py", "from skm.modules.access import public\n"
    )
    context = RuleContext({"planning": ("workspace",), "workspace": ("access",), "access": ()})
    assert any("not in depends_on" in v.message for v in rule_module_graph([file], context))


@pytest.mark.parametrize(
    "provider",
    ["claude", "claude-code", "claude_code", "codex", "grok", "cursor", "kiro", "anthropic", "openai"],
)
def test_provider_literals_are_case_insensitive_whole_constants(provider: str) -> None:
    assert rule_provider_literals(
        [source("modules/planning/public.py", f"NAME = {provider.upper()!r}")], RuleContext()
    )
    for path in ("adapters/runtimes/catalog.py", "bootstrap/runtimes.py"):
        assert not rule_provider_literals([source(path, f"NAME = {provider!r}")], RuleContext())
    assert not rule_provider_literals(
        [source("modules/planning/public.py", f"NAME = {'a ' + provider!r}")], RuleContext()
    )


@pytest.mark.parametrize(
    "code",
    [
        "import os as env\nx = env.environ['HOME']",
        "from os import getenv as read\nx = read('HOME')",
        "from os import putenv as write\nwrite('X', 'y')",
        "import os\nos.unsetenv('X')",
        "import tomllib as parser",
        "from tomllib import loads",
    ],
)
def test_config_access_rejects_aliases_and_imports(code: str) -> None:
    assert rule_config_access([source("entrypoints/api/routes/config.py", code)], RuleContext())
    for path in (
        "platform/config/sources/env.py",
        "bootstrap/config.py",
        "entrypoints/cli/main.py",
        "entrypoints/api/main.py",
    ):
        assert not rule_config_access([source(path, code)], RuleContext())


@pytest.mark.parametrize(
    "code",
    [
        "async def f(): pass",
        "async def f():\n    await g()",
        "async def f():\n    async with lock(): pass",
        "async def f():\n    async for item in items(): pass",
        "async def f():\n    return [item async for item in items()]",
    ],
)
def test_async_constructs_only_at_http_edge(code: str) -> None:
    assert rule_async_placement([source("entrypoints/worker/main.py", code)], RuleContext())
    for path in ("entrypoints/api/routes/events.py", "adapters/http_client/client.py"):
        assert not rule_async_placement([source(path, code)], RuleContext())


@pytest.mark.parametrize("case", json.loads((FIXTURES / "size_cases.json").read_text()))
def test_size_thresholds_and_generated_sql_exclusions(case) -> None:
    file = source("platform/parser.py", "# line\n" * case["lines"])
    assert bool(rule_file_size([file], RuleContext())) == case["violation"]
    assert bool(size_warnings([file])) == case["warning"]
    for path in (
        "modules/planning/generated/documents.py",
        "adapters/postgres/migrations/sql/0001_core_x.sql",
    ):
        excluded = source(path, "# line\n" * 1000)
        assert not rule_file_size([excluded], RuleContext())
        assert not size_warnings([excluded])


@pytest.mark.parametrize("name", ["utils", "helpers", "common", "misc", "manager", "base", "service"])
def test_all_grab_bag_names_and_exact_owner_exception(name: str) -> None:
    assert rule_file_names([source(f"platform/{name}.py", "")], RuleContext())
    assert not rule_file_names([source(f"platform/path_{name}.py", "")], RuleContext())
    allowances = load(
        Path(__file__).with_name("allowlist.toml"), today=datetime.fromtimestamp(time(), UTC).date()
    )
    assert all(a.reason and a.adr for a in allowances)
    canonical = rule_file_names([source("modules/execution/host/stages/base.py", "")], RuleContext())[0]
    assert any(a.matches(canonical) for a in allowances)
    renamed = rule_file_names([source("modules/execution/host/other/base.py", "")], RuleContext())[0]
    assert not any(a.matches(renamed) for a in allowances)


def test_generated_header_covers_kernel_nested_files_and_init_exception() -> None:
    for path in ("kernel/generated/contracts.py", "modules/planning/generated/nested/contracts.py"):
        assert rule_generated_header([source(path, "# hand written\n")], RuleContext())
        assert not rule_generated_header([source(path, "# generated by tools/gen.py\n")], RuleContext())
    assert not rule_generated_header([source("kernel/generated/__init__.py", "")], RuleContext())


@pytest.mark.parametrize(
    ("path", "package"),
    [
        ("kernel/ids.py", "httpx"),
        ("modules/planning/public.py", "httpx"),
        ("platform/config/sources/file.py", "jsonschema"),
        ("background/worker.py", "psycopg"),
        ("bootstrap/app.py", "keyring"),
        ("adapters/memory/planning/plan.py", "psycopg"),
        ("entrypoints/mcp/main.py", "starlette"),
        ("plugin_api/components.py", "requests"),
    ],
)
def test_third_party_matrix_denies_other_layers(path: str, package: str) -> None:
    assert rule_third_party_by_layer([source(path, f"import {package}.submodule")], RuleContext())


@pytest.mark.parametrize(
    ("path", "package"),
    [
        ("platform/schema/registry.py", "jsonschema"),
        ("platform/schema/validate.py", "referencing"),
        ("adapters/postgres/pool.py", "psycopg"),
        ("adapters/postgres/pool.py", "psycopg_pool"),
        ("adapters/http_client/client.py", "httpx"),
        ("adapters/secrets/store.py", "keyring"),
        ("entrypoints/api/app.py", "starlette"),
        ("entrypoints/api/app.py", "uvicorn"),
    ],
)
def test_third_party_matrix_allows_declared_edges(path: str, package: str) -> None:
    assert not rule_third_party_by_layer([source(path, f"import {package}")], RuleContext())


@pytest.mark.parametrize(
    "text",
    [
        "aXiOmA",
        "/Users/Operator/work",
        "/home/operator/work",
        r"C:\Users\Operator\work",
        "support@company.invalid",
        "PERPLEXITY",
        "personal+label@company.example",
    ],
)
def test_neutral_patterns_cover_non_python_text(text: str, tmp_path: Path) -> None:
    for relative in ("src/skm/schemas/data.json", "resources/packs/core/prompts/instructions.md"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    findings = rule_neutral_literals([], RuleContext(root=tmp_path))
    assert {v.path for v in findings} == {
        "src/skm/schemas/data.json",
        "resources/packs/core/prompts/instructions.md",
    }


def test_neutral_scan_excludes_tests_overlays_binary_and_allows_example_contacts(tmp_path: Path) -> None:
    for relative in (
        "tests/personal.md",
        "resources/overlays/author/profile.toml",
        "src/skm/tests/data.txt",
        "src/skm/overlays/data.txt",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("axioma operator@company.invalid")
    package = tmp_path / "src/skm"
    (package / "contacts.txt").write_text(
        "operator@example.test Operator@EXAMPLE.COM NOREPLY@company.invalid"
    )
    (package / "binary.dat").write_bytes(b"\xff\x00axioma")
    assert not rule_neutral_literals([], RuleContext(root=tmp_path))
    # Exemptions belong exclusively to the exact allowlist mechanism.
    findings = rule_neutral_literals([source("platform/names.py", "NAME = 'axioma'")], RuleContext())
    assert findings


@pytest.mark.parametrize(
    "path", ["entrypoints/cli/main.py", "entrypoints/api/main.py", "background/worker.py"]
)
def test_composition_override_aliases_remain_test_only(path: str) -> None:
    file = source(
        path, "from skm.bootstrap.app import build_app as make\nassemble = make\nassemble(overrides={})"
    )
    assert rule_no_test_overrides([file], RuleContext())
    assert not rule_no_test_overrides([source("bootstrap/app.py", file.text)], RuleContext())


def test_repository_inventory_and_protocol_adapters_do_not_activate_completeness() -> None:
    tree = collect(DEFERRED / "good")
    declarations = [file for file in tree if file.layer != "adapter"]
    protocol = source(
        "adapters/memory/planning/repositories.py",
        "from typing import Protocol\n"
        "from skm.modules.planning.ports import PlanRepository\n"
        "class MemoryPlanRepository(PlanRepository, Protocol): pass",
    )
    assert not rule_repository_ports_implemented([*declarations, protocol], RuleContext())
    active = RuleContext(implemented_ports=frozenset({"skm.modules.planning.ports.PlanRepository"}))
    assert len(rule_repository_ports_implemented(declarations, active)) == 2
    assert not rule_repository_ports_implemented(tree, RuleContext())


def test_repository_backend_is_enabled_only_when_materialized() -> None:
    tree = collect(DEFERRED / "good")
    memory_only = [file for file in tree if file.tech != "postgres"]
    assert not rule_repository_ports_implemented(memory_only, RuleContext())
    # Once a concrete Postgres adapter appears, its registration becomes mandatory.
    postgres = next(file for file in tree if file.name == "skm.adapters.postgres.planning.repositories")
    findings = rule_repository_ports_implemented([*memory_only, postgres], RuleContext())
    assert len(findings) == 1
    assert "no postgres implementation" in findings[0].message
    assert all("FutureRepository" not in v.message for v in findings)


@pytest.mark.parametrize("factory", ["None", "object()", "MissingFactory", "PlanRepository"])
def test_repository_registration_requires_a_callable_concrete_factory(factory: str) -> None:
    tree = [file for file in collect(DEFERRED / "good") if file.name != "skm.adapters.postgres.planning"]
    table = source(
        "adapters/postgres/planning/__init__.py",
        "from skm.modules.planning.ports import PlanRepository\n"
        + f"REPOSITORIES = {{PlanRepository: {factory}}}",
    )
    findings = rule_repository_ports_implemented([*tree, table], RuleContext())
    assert len(findings) == 1
    assert "no postgres implementation" in findings[0].message


def test_repository_completeness_is_per_port_and_accepts_lambda_and_mapping_proxy() -> None:
    tree = [file for file in collect(DEFERRED / "good") if file.name != "skm.adapters.postgres.planning"]
    table = source(
        "adapters/postgres/planning/__init__.py",
        "from types import MappingProxyType\n"
        "from skm.modules.planning.ports import PlanRepository\n"
        "from .repositories import PostgresPlanRepository\n"
        "REPOSITORIES = MappingProxyType({PlanRepository: lambda conn: PostgresPlanRepository(conn)})",
    )
    assert not rule_repository_ports_implemented([*tree, table], RuleContext())


def test_bus_registration_checks_missing_spec_membership_and_permission_separately() -> None:
    tree = collect(DEFERRED / "bad")
    findings = rule_bus_registration(tree, RuleContext())
    assert any("SPEC missing or not registered" in v.message for v in findings)
    assert any("permission" in v.message for v in findings)
    assert not rule_bus_registration([], RuleContext())
    good = collect(DEFERRED / "good")
    registry = source(
        "modules/planning/application/registry.py",
        "from .commands.violates_bus_registration import SPEC as command\n"
        "from .queries.sample import SPEC as query\n"
        "GROUP = (command,)\nCOMMANDS = GROUP\nQUERIES = (query,)",
    )
    good = [file for file in good if file.name != registry.name]
    assert not rule_bus_registration([*good, registry], RuleContext())


def test_bus_permission_catalog_cannot_be_extended_by_a_docstring() -> None:
    tree = [file for file in collect(DEFERRED / "good") if file.name != "skm.modules.access.permissions"]
    catalog = source("modules/access/permissions.py", '"plan.read"\nPERMISSIONS = frozenset({"other.right"})')
    assert len(rule_bus_registration([*tree, catalog], RuleContext())) == 2


def test_settings_calls_resolve_typed_receivers_aliases_and_public_views() -> None:
    public = source("modules/planning/public.py", "from .generated.settings import PlanningSettings")
    file = source(
        "modules/planning/application/read.py",
        "from skm.platform.config import EffectiveConfig\n"
        "from ..public import PlanningSettings as View\n"
        "def read(settings: EffectiveConfig):\n"
        "    settings.get('planning.depth')\n    return settings.section(View)",
    )
    context = RuleContext(root=DEFERRED / "good")
    assert not rule_settings_declared([public, file], context)
    bad = source(
        "modules/planning/application/read.py", file.text.replace("planning.depth", "planning.unknown")
    )
    assert rule_settings_declared([public, bad], context)
    unrelated = source("platform/mapping.py", "def read(mapping): return mapping.get('not.a.config.key')")
    assert not rule_settings_declared([unrelated], context)


@pytest.mark.parametrize(
    "call", ["ctx.config.get(key='planning.unknown')", "ctx.config.section(view=Unknown)"]
)
def test_settings_keyword_arguments_are_checked(call: str) -> None:
    assert rule_settings_declared(
        [source("modules/planning/application/read.py", call)], RuleContext(root=DEFERRED / "good")
    )


def test_db_ownership_checks_qualified_tables_direct_dependencies_and_settings_schema(tmp_path: Path) -> None:
    directory = tmp_path / "src/skm/adapters/postgres/migrations/sql"
    directory.mkdir(parents=True)
    path = directory / "0005_settings_entries.sql"
    path.write_text(
        "-- CREATE TABLE skm_wrong.table (id uuid REFERENCES skm_wrong.table);\n"
        "CREATE TABLE IF NOT EXISTS skm_config.entries (id uuid REFERENCES skm_core.scopes(id));\n"
    )
    context = RuleContext({"settings": ()}, root=tmp_path)
    assert not rule_db_ownership([], context)
    path.write_text(
        path.read_text()
        + 'CREATE TABLE "skm_access"."wrong" (id uuid REFERENCES skm_workspace.projects(id));\n'
    )
    findings = rule_db_ownership([], context)
    assert len(findings) == 2
    assert all(v.line == 3 for v in findings)  # comment masking preserves source line numbers


@pytest.mark.parametrize(
    "query",
    [
        "f'SELECT * FROM plans WHERE id = {identity}'",
        "'SELECT * FROM plans WHERE id = {}'.format(identity)",
        "'SELECT * FROM plans WHERE id = %s' % identity",
        "'SELECT * FROM plans WHERE id = ' + identity",
        "sql.SQL('SELECT * FROM {}').format(sql.Identifier(identity))",
        "sql.SQL(identity)",
    ],
)
def test_sql_external_data_cannot_become_syntax(query: str) -> None:
    file = source(
        "adapters/postgres/planning/plans.py",
        "from psycopg import sql\ndef get(conn, identity):\n    query = "
        + query
        + "\n    conn.execute(query, (identity,))\n    conn.executemany(query, [(identity,)])",
    )
    assert len(rule_no_fstring_sql([file], RuleContext())) == 2


@pytest.mark.parametrize(
    "query",
    [
        "'SELECT * FROM plans WHERE id = %s'",
        "f'SELECT {_COLUMNS} FROM plans WHERE id = %s'",
        "sql.SQL('SELECT * FROM {} WHERE id = %s').format(sql.Identifier(_TABLES[kind]))",
    ],
)
def test_sql_allows_parameters_and_constant_identifier_allowlists(query: str) -> None:
    file = source(
        "adapters/postgres/planning/plans.py",
        "from psycopg import sql\n_COLUMNS = 'id, title'\n"
        "_TABLES = {'plan': 'plans', 'draft': 'drafts'}\n"
        "def get(conn, identity, kind):\n    query = "
        + query
        + "\n    conn.execute(query=query, params=(identity,))",
    )
    assert not rule_no_fstring_sql([file], RuleContext())


def test_sql_cannot_shadow_a_constant_with_an_external_argument_or_reassignment() -> None:
    prefix = "_COLUMNS = 'id'\n"
    for body in (
        "def get(conn, _COLUMNS):\n    conn.execute(f'SELECT {_COLUMNS} FROM plans')",
        "def get(conn, identity):\n    query = 'SELECT id FROM plans'\n"
        "    query = f'SELECT {identity} FROM plans'\n    conn.execute(query)",
    ):
        assert rule_no_fstring_sql(
            [source("adapters/postgres/planning/plans.py", prefix + body)], RuleContext()
        )


@pytest.mark.parametrize(
    "body",
    [
        "def get(conn, identities):\n    for _COLUMNS in identities:\n"
        "        conn.execute(f'SELECT {_COLUMNS} FROM plans')",
        "def get(conn, identity):\n    (_COLUMNS,) = (identity,)\n"
        "    conn.execute(f'SELECT {_COLUMNS} FROM plans')",
        "get = lambda conn, _COLUMNS: conn.execute(f'SELECT {_COLUMNS} FROM plans')",
        "def get(conn, identity):\n    conn.execute(f'SELECT {_COLUMNS:{identity}} FROM plans')",
        "def get(conn, identity):\n    conn.execute(**{'query': f'SELECT {identity} FROM plans'})",
    ],
)
def test_sql_external_syntax_cannot_hide_in_bindings_format_specs_or_kwargs(body: str) -> None:
    file = source("adapters/postgres/planning/plans.py", "_COLUMNS = 'id'\n" + body)
    assert rule_no_fstring_sql([file], RuleContext())


@pytest.mark.parametrize("code", ["print('debug')", "import builtins as b\nemit = b.print\nemit('message')"])
def test_print_free_rejects_mcp_tools(code: str) -> None:
    for path in ("entrypoints/mcp/server.py", "entrypoints/mcp/tools/plan.py"):
        for file_path in (Path("src/skm") / path, ROOT / "src/skm" / path):
            findings = rule_print_free([SourceFile.at(file_path, code)], RuleContext())
            assert len(findings) == 1
            assert findings[0].rule == "print-free"


@pytest.mark.parametrize("code", ["print('debug')", "import builtins as b\nemit = b.print\nemit('message')"])
def test_print_is_allowed_only_in_cli_and_tools(code: str) -> None:
    assert rule_print_free([source("background/worker.py", code)], RuleContext())
    assert not rule_print_free([source("entrypoints/cli/render.py", code)], RuleContext())
    for path in (Path("tools/report.py"), ROOT / "tools/report.py"):
        assert not rule_print_free([SourceFile.at(path, code)], RuleContext())


def test_neutral_allowlist_exempts_only_owner_required_literals_at_exact_paths() -> None:
    allowances = load(
        Path(__file__).with_name("allowlist.toml"), today=datetime.fromtimestamp(time(), UTC).date()
    )
    tree = [source("schemas/settings/worker.v1.json", '"worker@skm.invalid"\n"private@company.invalid"')]
    findings = rule_neutral_literals(tree, RuleContext())
    assert len(findings) == 2
    remaining = [v for v in findings if not any(a.matches(v) for a in allowances)]
    assert len(remaining) == 1
    assert remaining[0].detail == "private@company.invalid"


def test_config_sources_package_may_access_environment() -> None:
    file = source("platform/config/sources/__init__.py", "import os\nos.getenv('SKM_INSTANCE')\n")
    assert not rule_config_access([file], RuleContext())


def test_provider_literals_distinguishes_symbol_names_from_provider_values() -> None:
    file = source(
        "kernel/pagination.py",
        'from typing import NewType\n__all__ = ["Cursor"]\nCursor = NewType("Cursor", str)\n',
    )
    assert not rule_provider_literals([file], RuleContext())
    value = source("kernel/selection.py", 'provider = "cursor"\n')
    assert rule_provider_literals([value], RuleContext())


@pytest.fixture
def generated_schema_data(tmp_path):
    import importlib

    from ._allowlist import Allowance

    generator = importlib.import_module("tools.gen")
    relative = Path("src/skm/schemas/demo/item.v1.json")
    document = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:skm:demo:item:v1",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "provider": {"type": "string", "enum": ["codex", "cursor"], "default": "codex"},
            "contact": {"type": "string", "default": "worker@skm.invalid"},
        },
        "x-skm-codegen": {
            "python": {"module": "skm.modules.demo.generated.documents", "class": "Item", "kind": "dataclass"}
        },
    }
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(document))
    generator.generate(tmp_path, only="python")
    output = tmp_path / "src/skm/modules/demo/generated/documents.py"
    context = RuleContext(
        root=tmp_path,
        schema_allowances=(
            Allowance(
                "neutral-literals", relative.as_posix(), "worker@skm.invalid", "source fixture", "fixture"
            ),
        ),
    )
    return output, context


def test_fresh_schema_enum_and_default_data_are_inert(generated_schema_data):
    path, context = generated_schema_data
    file = SourceFile.at(path, path.read_text())
    assert not rule_provider_literals([file], context)
    findings = rule_neutral_literals([file], context)
    assert not [v for v in findings if not any(a.matches(v) for a in context.schema_allowances)]


@pytest.mark.parametrize(
    "body",
    [
        '\nprovider = "codex"\n',
        '\ndef choose():\n    return "codex"\n',
        '\ncontact = "worker@skm.invalid"\n',
        '\nItem._FIELDS += (("injected", "injected", ("str", (), (), ()), False, "codex", True, ""),)\n',
    ],
)
def test_generated_header_never_exempts_manual_or_executable_values(generated_schema_data, body):
    path, context = generated_schema_data
    text = path.read_text() + body
    file = SourceFile.at(path, text)
    findings = rule_provider_literals([file], context) + rule_neutral_literals([file], context)
    assert findings
    assert any(v.line >= len(path.read_text().splitlines()) + 1 for v in findings)


def test_generated_neutral_default_needs_its_exact_source_exception(generated_schema_data):
    path, context = generated_schema_data
    file = SourceFile.at(path, path.read_text())
    context.schema_allowances = ()
    assert any(v.path == file.display_path for v in rule_neutral_literals([file], context))


def test_manual_generated_metadata_edit_loses_schema_provenance(generated_schema_data):
    path, context = generated_schema_data
    text = path.read_text().replace("worker@skm.invalid", "personal@company.invalid")
    findings = rule_neutral_literals([SourceFile.at(path, text)], context)
    assert any(v.detail == "personal@company.invalid" for v in findings)


def test_source_exception_does_not_cover_another_generated_field(generated_schema_data):
    import importlib

    path, context = generated_schema_data
    schema = context.root / "src/skm/schemas/demo/item.v1.json"
    document = json.loads(schema.read_text())
    # A different contact has no source exception, even in the same fresh output.
    document["properties"]["other"] = {"type": "string", "default": "private@company.invalid"}
    schema.write_text(json.dumps(document))
    importlib.import_module("tools.gen").generate(context.root, only="python")
    findings = rule_neutral_literals([SourceFile.at(path, path.read_text())], context)
    assert any(v.detail == "private@company.invalid" for v in findings)


def test_source_exception_cannot_cross_schema_owners_in_one_generated_file(generated_schema_data):
    import importlib

    path, context = generated_schema_data
    source_path = context.root / "src/skm/schemas/demo/item.v1.json"
    document = json.loads(source_path.read_text())
    document["$id"] = "urn:skm:demo:other:v1"
    document["x-skm-codegen"]["python"]["class"] = "Other"
    source_path.with_name("other.v1.json").write_text(json.dumps(document))
    importlib.import_module("tools.gen").generate(context.root, only="python")
    findings = rule_neutral_literals([SourceFile.at(path, path.read_text())], context)
    generated = [v for v in findings if v.path == "src/skm/modules/demo/generated/documents.py"]
    assert generated
    # Only the unapproved schema's default and its class initializer remain findings.
    assert len(generated) == 2


def test_schema_metadata_cannot_exempt_generated_import_boundaries(generated_schema_data):
    from .rules import rule_layer_imports, rule_module_facade

    path, context = generated_schema_data
    for statement in (
        "from skm.platform.config.secrets import SecretRef",
        "from skm.modules.other.generated.documents import Private",
    ):
        file = SourceFile.at(path, path.read_text() + "\n" + statement)
        assert rule_layer_imports([file], context) or rule_module_facade([file], context)


CLI_IDENTITY = "from skm.adapters.runtimes._cli_session.identity import X\n"
EXECUTION_DTOS = "from skm.modules.execution.application._dtos import X\n"


def _private_findings(*files: SourceFile) -> list[str]:
    return [Path(v.path).name for v in rule_private_imports(list(files), RuleContext())]


def test_private_module_is_reachable_only_from_its_owning_package() -> None:
    package = source("adapters/runtimes/__init__.py", "")
    sibling = source(
        "adapters/runtimes/grok/a.py", "from skm.adapters.runtimes._cli_session.identity import X\n"
    )
    outsider = source("bootstrap/b.py", CLI_IDENTITY)
    assert _private_findings(package, sibling, outsider) == ["b.py"]


def test_private_name_is_reachable_only_from_the_package_of_its_module() -> None:
    sibling = source("platform/config/loader.py", "from skm.platform.config.registry import _digest\n")
    outsider = source("bootstrap/plugins.py", "from skm.platform.config.registry import _digest\n")
    assert _private_findings(sibling, outsider) == ["plugins.py"]


def test_a_product_module_owns_its_private_internals_as_a_whole() -> None:
    facade = source("modules/execution/public.py", EXECUTION_DTOS)
    other = source(
        "modules/planning/application/c.py", "from skm.modules.execution.application._dtos import X\n"
    )
    assert _private_findings(facade, other) == ["c.py"]


def test_only_generated_code_shares_the_private_codec_runtime() -> None:
    generated = source(
        "modules/planning/generated/views.py", "from skm.kernel.generated._codec import convert\n"
    )
    handwritten = source("platform/config/d.py", "from skm.kernel.generated._codec import SecretRef\n")
    assert _private_findings(generated, handwritten) == ["d.py"]
