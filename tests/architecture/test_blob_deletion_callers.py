"""Architectural guardrail for G22 (artifacts §6.1, §7, §18): bounded ``delete_unreferenced`` callers.

Physical object deletion outside staging recovery is permitted exclusively inside
``artifacts.expire_staged_blobs`` and ``artifacts.prune_orphan_objects``.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ALLOWED_DELETE_CALLERS = frozenset(
    {
        "src/skm/modules/artifacts/application/commands/expire_staged_blobs.py",
        "src/skm/modules/artifacts/application/commands/prune_orphan_objects.py",
    }
)


def find_delete_unreferenced_callers(files: dict[str, str]) -> dict[str, list[int]]:
    """Return ``{rel_path: [lineno, ...]}`` for every direct or reflective ``delete_unreferenced`` use."""
    callers: dict[str, list[int]] = {}
    for rel_path, source in sorted(files.items()):
        if "delete_unreferenced" not in source and "\\" not in source:
            continue
        tree = ast.parse(source, filename=rel_path)
        lines: list[int] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if (
                    (isinstance(func, ast.Attribute) and func.attr == "delete_unreferenced")
                    or (isinstance(func, ast.Name) and func.id == "delete_unreferenced")
                    or (
                        isinstance(func, ast.Name)
                        and func.id == "getattr"
                        and len(node.args) >= 2
                        and isinstance(node.args[1], ast.Constant)
                        and node.args[1].value == "delete_unreferenced"
                    )
                ):
                    lines.append(node.lineno)
        if lines:
            callers[rel_path] = sorted(lines)
    return callers


def test_blob_deletion_callers_guardrail(session_root_tree) -> None:
    sources = {file.display_path: file.text for file in session_root_tree}
    callers = find_delete_unreferenced_callers(sources)
    unexpected = set(callers) - ALLOWED_DELETE_CALLERS
    assert not unexpected, f"Forbidden delete_unreferenced callers: { {k: callers[k] for k in unexpected} }"
    assert set(callers) == ALLOWED_DELETE_CALLERS


def test_blob_deletion_callers_detects_synthetic_violation() -> None:
    synthetic = {
        "src/skm/modules/artifacts/application/commands/trash_file.py": (
            "def bad(store, loc):\n"
            "    store.delete_unreferenced(loc)\n"
            "    getattr(store, 'delete_unreferenced')(loc)\n"
        )
    }
    found = find_delete_unreferenced_callers(synthetic)
    assert found == {"src/skm/modules/artifacts/application/commands/trash_file.py": [2, 3]}
