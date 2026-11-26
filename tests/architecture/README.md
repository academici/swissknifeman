# Architecture checks

Run `uv run --frozen pytest -q -n 0 tests/architecture` for the complete rule suite
and its negative fixtures. Product checks and small counterexamples exercise the
same functions exported by [rules.py](rules.py); rule IDs and suite order live there.

| Responsibility | Implementation |
| --- | --- |
| Lazy source snapshots, resolved imports and calls | [_tree.py](_tree.py) |
| Findings, exact exceptions and schema provenance | [_rule_context.py](_rule_context.py) |
| Import layers, public facades, dependency graph, import cycles and private imports | [_import_rules.py](_import_rules.py) |
| Domain purity, port markers and host/application boundaries | [_boundary_rules.py](_boundary_rules.py) |
| Source hygiene, environment access and neutral literals | [_guardrail_rules.py](_guardrail_rules.py) |
| Bus, repository and settings registration; DDL ownership | [_registration_rules.py](_registration_rules.py) |
| SQL bindings, shadowing and identifier allowlists | [_sql_rules.py](_sql_rules.py) |

For a focused counterexample, use a fresh source snapshot without importing the
product module:

```python
from pathlib import Path
from tests.architecture._tree import SourceFile
from tests.architecture.rules import RuleContext, rule_domain_purity

file = SourceFile.at(Path("src/skm/modules/planning/domain/example.py"), "import os\n")
assert rule_domain_purity([file], RuleContext())
```

`SourceFile` caches its source, AST, node order and derived facts for the lifetime
of that instance. Treat the AST as read-only; create a new snapshot or call
`collect(root)` again after editing a file. Fact helpers return independent lists
or dictionaries. No cache is shared across different files, fixtures or sessions.
