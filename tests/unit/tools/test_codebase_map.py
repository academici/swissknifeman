"""The navigation map follows the actual module graph instead of becoming another stale registry."""

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_codebase_map_dependencies_match_all_actual_module_manifests() -> None:
    text = (ROOT / "docs/architecture/CODEBASE-MAP.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| \[([a-z]+)\]\([^\n|]+\) \| `(\[[^`]+\]|\[\])` \|", text, re.MULTILINE)
    documented = {name: tuple(json.loads(dependencies)) for name, dependencies in rows}
    actual = {}
    for path in (ROOT / "src/skm/modules").glob("*/module.py"):
        # Reading literal manifest metadata avoids importing all product handlers in a unit test.
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        declaration = next(
            node.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "MODULE" for target in node.targets)
        )
        assert isinstance(declaration, ast.Call)
        metadata = {keyword.arg: keyword.value for keyword in declaration.keywords}
        actual[ast.literal_eval(metadata["id"])] = ast.literal_eval(metadata["depends_on"])
    assert len(rows) == len(documented) == len(actual) == 14
    assert documented == actual
