# Architecture test implementation

`tests/architecture/rules.py` remains the rule API and ordered registry. The implementation partitions
preserve the existing diagnostics and are not product modules.

| File | Contract | Owner |
|---|---|---|
| `tests/architecture/_rule_context.py` | Rule context, generated provenance and shared type information | Architecture guardrails |
| `tests/architecture/_import_rules.py` | Layer imports, module graph and facade boundaries | Architecture guardrails |
| `tests/architecture/_boundary_rules.py` | Domain, application and host purity | Architecture guardrails |
| `tests/architecture/_guardrail_rules.py` | File sizes, neutral literals, generated headers and host IO | Architecture guardrails |
| `tests/architecture/_registration_rules.py` | Port, bus, settings and DDL declarations | Architecture guardrails |
| `tests/architecture/_sql_rules.py` | SQL construction and binding safety | Architecture guardrails |
| `tests/architecture/test_tree.py` | AST snapshot ordering, mutation isolation and fresh recollection | Architecture infrastructure regressions |
