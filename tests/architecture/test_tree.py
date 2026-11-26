"""Source snapshots retain traversal order and never share mutable fact results."""

import ast
from pathlib import Path

from ._tree import SourceFile, aliases, async_defs, calls, collect, imports, string_constants
from .rules import RuleContext, rule_no_fstring_sql


def test_cached_facts_preserve_ast_order_and_return_independent_containers() -> None:
    file = SourceFile.at(
        Path("src/skm/platform/example.py"),
        "from pathlib import Path as P\n"
        "read = P\n"
        "async def run():\n"
        "    return await consume(read('first'), label='second')\n",
    )
    expected_nodes = tuple(ast.walk(file.tree))
    assert file.nodes == expected_nodes
    assert file.parents == {child: node for node in expected_nodes for child in ast.iter_child_nodes(node)}
    assert [(call.name, call.line) for call in calls(file)] == [
        ("consume", 4),
        ("pathlib.Path", 4),
    ]
    assert string_constants(file) == [("first", 4), ("second", 4)]
    assert [type(node) for node in async_defs(file)] == [ast.AsyncFunctionDef, ast.Await]
    assert aliases(file) == {"P": "pathlib.Path", "read": "pathlib.Path"}

    expected_imports = imports(file)
    expected_calls = calls(file)
    expected_strings = string_constants(file)
    expected_async = async_defs(file)
    imports(file).clear()
    calls(file).clear()
    string_constants(file).clear()
    async_defs(file).clear()
    aliases(file).clear()
    assert imports(file) == expected_imports
    assert calls(file) == expected_calls
    assert string_constants(file) == expected_strings
    assert async_defs(file) == expected_async
    assert aliases(file)["read"] == "pathlib.Path"


def test_recollection_observes_file_edits_without_changing_earlier_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "src/skm/adapters/postgres/example.py"
    path.parent.mkdir(parents=True)
    path.write_text("def run(conn):\n    conn.execute('SELECT 1')\n")
    original = collect(tmp_path)
    assert not rule_no_fstring_sql(original, RuleContext())
    assert string_constants(original[0]) == [("SELECT 1", 2)]

    path.write_text("def run(conn, query):\n    conn.execute(query)\n")
    edited = collect(tmp_path)
    findings = rule_no_fstring_sql(edited, RuleContext())
    assert [(finding.rule, finding.line) for finding in findings] == [("no-fstring-sql", 2)]
    assert string_constants(edited[0]) == []
    assert not rule_no_fstring_sql(original, RuleContext())
    assert string_constants(original[0]) == [("SELECT 1", 2)]


def test_in_memory_sources_at_the_same_path_have_separate_facts() -> None:
    path = Path("src/skm/platform/example.py")
    first = SourceFile.at(path, "import builtins as b\nb.print('first')\n")
    second = SourceFile.at(path, "import os as b\nb.getenv('second')\n")
    assert [call.name for call in calls(first)] == ["builtins.print"]
    assert [call.name for call in calls(second)] == ["os.getenv"]
    assert string_constants(first) == [("first", 2)]
    assert string_constants(second) == [("second", 2)]
