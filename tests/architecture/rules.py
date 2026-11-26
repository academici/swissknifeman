"""Architecture-rule facade; keep rule identities and suite order stable.

Implementations live beside this module by responsibility. Import rules here
for fixtures and audits so their calling convention stays unchanged.
"""

from ._boundary_rules import (
    FORBIDDEN_CALLS,
    FORBIDDEN_IMPORTS,
    rule_application_boundary,
    rule_domain_purity,
    rule_host_boundary,
    rule_host_io,
)
from ._guardrail_rules import (
    GRAB_BAG_NAMES,
    LEGACY_PACKAGES,
    PROVIDERS,
    rule_async_placement,
    rule_cli_thin,
    rule_config_access,
    rule_file_names,
    rule_file_size,
    rule_generated_header,
    rule_neutral_literals,
    rule_no_legacy,
    rule_no_test_overrides,
    rule_print_free,
    rule_provider_literals,
    rule_third_party_by_layer,
    size_warnings,
)
from ._import_rules import (
    rule_import_cycles,
    rule_layer_imports,
    rule_module_facade,
    rule_module_graph,
    rule_private_imports,
)
from ._registration_rules import (
    rule_bus_registration,
    rule_db_ownership,
    rule_repository_ports_implemented,
    rule_settings_declared,
)
from ._rule_context import (
    ANNOTATION_CONTRACTS,
    DECLARATION_CONTRACTS,
    PATH_CONTRACTS,
    VALUE_ANNOTATIONS,
    RuleContext,
    Violation,
)
from ._sql_rules import rule_no_fstring_sql

__all__ = [
    "ALL_RULES",
    "ANNOTATION_CONTRACTS",
    "DECLARATION_CONTRACTS",
    "DEFERRED_RULES",
    "FORBIDDEN_CALLS",
    "FORBIDDEN_IMPORTS",
    "GRAB_BAG_NAMES",
    "GUARDRAIL_RULES",
    "LEGACY_PACKAGES",
    "PATH_CONTRACTS",
    "PROVIDERS",
    "RULES",
    "VALUE_ANNOTATIONS",
    "RuleContext",
    "Violation",
    "rule_application_boundary",
    "rule_async_placement",
    "rule_bus_registration",
    "rule_cli_thin",
    "rule_config_access",
    "rule_db_ownership",
    "rule_domain_purity",
    "rule_file_names",
    "rule_file_size",
    "rule_generated_header",
    "rule_host_boundary",
    "rule_host_io",
    "rule_import_cycles",
    "rule_layer_imports",
    "rule_module_facade",
    "rule_module_graph",
    "rule_neutral_literals",
    "rule_no_fstring_sql",
    "rule_no_legacy",
    "rule_no_test_overrides",
    "rule_print_free",
    "rule_private_imports",
    "rule_provider_literals",
    "rule_repository_ports_implemented",
    "rule_settings_declared",
    "rule_third_party_by_layer",
    "size_warnings",
]

RULES = (
    rule_layer_imports,
    rule_module_facade,
    rule_module_graph,
    rule_import_cycles,
    rule_domain_purity,
    rule_host_boundary,
    rule_application_boundary,
    rule_host_io,
)

DEFERRED_RULES = {
    "repository-ports-implemented": {
        "leaves": ("P04.02.a", "P04.02.b", "P04.04.a", "P04.04.b"),
        "when": "per implemented port and materialized backend; "
        "REPOSITORIES or a concrete adapter activates it",
    },
    "bus-registration": {
        "leaves": ("P01.08.a",),
        "when": "a command/query source file exists (P00 does not create handler files)",
    },
    "settings-declared": {
        "leaves": ("P02.02", "P02.04.a"),
        "when": "a config.get/section call exists; declarations come from settings schemas",
    },
    "db-ownership": {
        "leaves": ("P03.01.a", "P03.02.b"),
        "when": "a numbered migration contains CREATE TABLE or REFERENCES",
    },
    "no-fstring-sql": {
        "leaves": ("P03.01.a", "P03.03.a"),
        "when": "a Postgres adapter calls execute/executemany",
    },
    "cli-thin": {
        "leaves": ("P02.08.a",),
        "when": "an entrypoint imports module code (already enforced by layer-imports)",
    },
}

GUARDRAIL_RULES = (
    rule_provider_literals,
    rule_config_access,
    rule_async_placement,
    rule_print_free,
    rule_file_names,
    rule_file_size,
    rule_private_imports,
    rule_generated_header,
    rule_no_legacy,
    rule_third_party_by_layer,
    rule_no_test_overrides,
    rule_neutral_literals,
    rule_repository_ports_implemented,
    rule_bus_registration,
    rule_settings_declared,
    rule_db_ownership,
    rule_cli_thin,
    rule_no_fstring_sql,
)

ALL_RULES = (*RULES, *GUARDRAIL_RULES)
