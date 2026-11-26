"""One canonical ecosystem and extension vocabulary (I-03.3).

The maps used to live as private dicts in context, knowledge, planning, learning and research.
Those modules now import ``skm.kernel.languages``. A fresh hardcoded dict of the same shape
is a regression.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Modules named by I-03.3, plus the two maps that were folded into the same source.
CONSUMERS = (
    "src/skm/modules/context/domain/render.py",
    "src/skm/modules/context/domain/steering_selection.py",
    "src/skm/modules/knowledge/domain/graph_answer.py",
    "src/skm/modules/knowledge/host/derive_project_graph.py",
    "src/skm/modules/learning/domain/check_commands.py",
    "src/skm/modules/execution/domain/workflow/task_facts.py",
    "src/skm/modules/planning/application/revision_writer.py",
    "src/skm/adapters/research/filesystem.py",
)

# A dict whose keys are extensions, ecosystem ids, or language names mapped to extension
# tuples is the duplicate this task removes. Language-name keys catch the old steering map
# (``"typescript": (".ts", ".tsx")``) even when no ecosystem id overlaps.
_ECOSYSTEM_KEYS = frozenset(
    {
        "python",
        "node",
        "php",
        "cargo",
        "go",
        "ruby",
        "brew",
        "dart",
        "jvm",
        "pypi",
        "npm",
        "composer",
        "pub",
        "maven",
        "rubygems",
    }
)


def _string_keys(node: ast.Dict) -> list[str]:
    keys: list[str] = []
    for key in node.keys:
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            return []
        keys.append(key.value)
    return keys


def _extension_tuple(node: ast.expr) -> bool:
    if not isinstance(node, ast.Tuple | ast.List) or not node.elts:
        return False
    return all(
        isinstance(elt, ast.Constant) and isinstance(elt.value, str) and elt.value.startswith(".")
        for elt in node.elts
    )


def _language_extension_map(node: ast.Dict) -> bool:
    """True when every value is a tuple of suffixes, as in the old ``_LANGUAGES`` map."""
    if any(key is None for key in node.keys):
        return False
    keys = _string_keys(node)
    if len(keys) < 3 or any(key.startswith(".") for key in keys):
        return False
    return all(_extension_tuple(value) for value in node.values)


def _hardcoded_maps(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict) or len(node.keys) < 3:
            continue
        keys = _string_keys(node)
        if not keys:
            continue
        if (
            all(key.startswith(".") for key in keys)
            or _ECOSYSTEM_KEYS.intersection(keys)
            or _language_extension_map(node)
        ):
            lines.append(node.lineno)
    return lines


def test_consumers_import_the_kernel_vocabulary() -> None:
    missing = [
        path for path in CONSUMERS if "skm.kernel.languages" not in (ROOT / path).read_text(encoding="utf-8")
    ]
    assert missing == []


def test_consumers_keep_no_hardcoded_extension_or_ecosystem_dict() -> None:
    offenders = {
        path: _hardcoded_maps(ast.parse((ROOT / path).read_text(encoding="utf-8"))) for path in CONSUMERS
    }
    assert {path: lines for path, lines in offenders.items() if lines} == {}


def test_language_name_to_extension_tuples_are_hardcoded_maps() -> None:
    """The old steering ``_LANGUAGES`` map has no ecosystem id and must still be caught."""
    source = """
_LANGUAGES = {
    "typescript": (".ts", ".tsx"),
    "javascript": (".js", ".jsx", ".mjs", ".cjs"),
    "markdown": (".md",),
}
"""
    assert _hardcoded_maps(ast.parse(source)) == [2]


def test_plain_name_dicts_are_not_vocabulary_maps() -> None:
    source = """
NAMES = {"alpha": "one", "beta": "two", "gamma": "three"}
"""
    assert _hardcoded_maps(ast.parse(source)) == []


def test_canonical_module_is_the_only_owner() -> None:
    source = (ROOT / "src/skm/kernel/languages.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    maps = _hardcoded_maps(tree)
    assert maps
    assert "language_for_ecosystem" in source
