"""The stdlib emitter turns the canonical error catalog into ``kernel/generated`` deterministically."""

import ast
import copy
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
EMITTER_PATH = ROOT / "tools" / "codegen" / "error_catalog.py"


def _load_emitter() -> ModuleType:
    spec = importlib.util.spec_from_file_location("skm_test_error_catalog_emitter", EMITTER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


emitter = _load_emitter()
CATALOG_RELPATH: Path = emitter.CATALOG_RELPATH
SCHEMA_RELPATH: Path = emitter.SCHEMA_RELPATH
OUTPUT_DIR_RELPATH: Path = emitter.OUTPUT_DIR_RELPATH


def _scaffold(tmp_path: Path) -> Path:
    """A clean scaffold: only the schema and the data document, no kernel/platform module."""
    for relative in (SCHEMA_RELPATH, CATALOG_RELPATH):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return tmp_path


def _document() -> dict[str, Any]:
    return json.loads((ROOT / CATALOG_RELPATH).read_text(encoding="utf-8"))


def _schema() -> dict[str, Any]:
    return json.loads((ROOT / SCHEMA_RELPATH).read_text(encoding="utf-8"))


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(EMITTER_PATH), *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=60,
        check=False,
    )


def test_canonical_catalog_is_valid() -> None:
    assert emitter.validate_catalog(_document(), _schema()) == []


def test_committed_generated_files_are_fresh() -> None:
    assert emitter.generate(ROOT, check=True) == []


def test_render_is_deterministic_and_follows_document_order() -> None:
    document = _document()
    first = emitter.render_error_codes(document)
    assert first == emitter.render_error_codes(copy.deepcopy(document))
    positions = [first.index(f'    {row["code"]} = "{row["code"]}"') for row in document["codes"]]
    assert positions == sorted(positions)
    assert first.endswith("\n")
    assert "\r" not in first


def test_clean_scaffold_generates_without_kernel_modules_and_second_run_is_noop(tmp_path: Path) -> None:
    root = _scaffold(tmp_path)
    first = _run("--root", str(root))
    assert first.returncode == 0, first.stderr
    target = root / OUTPUT_DIR_RELPATH
    assert sorted(path.name for path in target.iterdir()) == ["__init__.py", "error_codes.py"]
    assert (target / "error_codes.py").read_text(encoding="utf-8") == (
        ROOT / OUTPUT_DIR_RELPATH / "error_codes.py"
    ).read_text(encoding="utf-8")
    snapshot = {path.name: path.read_bytes() for path in target.iterdir()}
    second = _run("--root", str(root))
    assert second.returncode == 0, second.stderr
    assert second.stdout == ""
    assert {path.name: path.read_bytes() for path in target.iterdir()} == snapshot
    assert _run("--check", "--root", str(root)).returncode == 0


def test_emitter_imports_only_the_standard_library() -> None:
    tree = ast.parse(EMITTER_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "the emitter must not use relative imports"
            imported.add((node.module or "").split(".")[0])
    assert imported <= set(sys.stdlib_module_names)
    assert "skm" not in imported


def test_check_reports_stale_and_missing_files(tmp_path: Path) -> None:
    root = _scaffold(tmp_path)
    missing = _run("--check", "--root", str(root))
    assert missing.returncode == 1
    assert "error_codes.py" in missing.stderr
    assert _run("--root", str(root)).returncode == 0
    generated = root / OUTPUT_DIR_RELPATH / "error_codes.py"
    generated.write_text(generated.read_text(encoding="utf-8") + "# hand edit\n", encoding="utf-8")
    stale = _run("--check", "--root", str(root))
    assert stale.returncode == 1
    assert str(generated) in stale.stderr
    assert generated.read_text(encoding="utf-8").endswith("# hand edit\n"), "--check must not write"
    assert _run("--root", str(root)).returncode == 0
    assert _run("--check", "--root", str(root)).returncode == 0


def test_invalid_catalog_stops_the_emitter_without_output(tmp_path: Path) -> None:
    root = _scaffold(tmp_path)
    document = _document()
    document["codes"].append(copy.deepcopy(document["codes"][0]))
    (root / CATALOG_RELPATH).write_text(json.dumps(document), encoding="utf-8")
    result = _run("--root", str(root))
    assert result.returncode == 2
    assert "duplicate code 'NOT_FOUND'" in result.stderr
    assert not (root / OUTPUT_DIR_RELPATH).exists()


def _mutations() -> list[tuple[str, Any, str]]:
    def duplicate_code(doc: dict[str, Any]) -> None:
        doc["codes"].append(copy.deepcopy(doc["codes"][3]))

    def unknown_category(doc: dict[str, Any]) -> None:
        doc["codes"][0]["category"] = "fatal"

    def lower_case_code(doc: dict[str, Any]) -> None:
        doc["codes"][0]["code"] = "not_found"

    def extra_field(doc: dict[str, Any]) -> None:
        doc["codes"][0]["owner"] = "kernel"

    def missing_field(doc: dict[str, Any]) -> None:
        del doc["codes"][0]["retryable"]

    def empty_codes(doc: dict[str, Any]) -> None:
        doc["codes"] = []

    def http_out_of_range(doc: dict[str, Any]) -> None:
        doc["codes"][0]["http_status"] = 700

    def cli_exit_is_bool(doc: dict[str, Any]) -> None:
        doc["codes"][0]["cli_exit"] = True

    def retryable_not_bool(doc: dict[str, Any]) -> None:
        doc["codes"][0]["retryable"] = "no"

    def wrong_schema_urn(doc: dict[str, Any]) -> None:
        doc["schema"] = "urn:skm:kernel:error-catalog:v2"

    def category_default_missing(doc: dict[str, Any]) -> None:
        doc["categories"].pop()

    def empty_description(doc: dict[str, Any]) -> None:
        doc["codes"][0]["description"] = ""

    def top_level_extra(doc: dict[str, Any]) -> None:
        doc["generated_at"] = "now"

    return [
        ("duplicate", duplicate_code, "duplicate code"),
        ("unknown_category", unknown_category, "unknown category 'fatal'"),
        ("lower_case_code", lower_case_code, "catalog.codes[0].code"),
        ("extra_field", extra_field, "unexpected field 'owner'"),
        ("missing_field", missing_field, "missing required field 'retryable'"),
        ("empty_codes", empty_codes, "catalog.codes: must be a non-empty array"),
        ("http_out_of_range", http_out_of_range, "catalog.codes[0].http_status"),
        ("cli_exit_is_bool", cli_exit_is_bool, "catalog.codes[0].cli_exit"),
        ("retryable_not_bool", retryable_not_bool, "catalog.codes[0].retryable"),
        ("wrong_schema_urn", wrong_schema_urn, "catalog.schema"),
        ("category_default_missing", category_default_missing, "has no default mapping"),
        ("empty_description", empty_description, "catalog.codes[0].description"),
        ("top_level_extra", top_level_extra, "unexpected field 'generated_at'"),
    ]


@pytest.mark.parametrize(("name", "mutate", "expected"), _mutations(), ids=[case[0] for case in _mutations()])
def test_validation_rejects_broken_catalogs(name: str, mutate: Any, expected: str) -> None:
    document = _document()
    mutate(document)
    problems = emitter.validate_catalog(document, _schema())
    assert any(expected in problem for problem in problems), (name, problems)


def test_validation_rejects_non_object_document() -> None:
    assert emitter.validate_catalog([], _schema()) == ["catalog: must be an object"]


def test_generated_module_matches_the_data_document() -> None:
    from skm.kernel.generated import error_codes

    document = _document()
    assert [member.value for member in error_codes.ErrorCode] == [row["code"] for row in document["codes"]]
    assert [member.value for member in error_codes.ErrorCategory] == [
        row["category"] for row in document["categories"]
    ]
    assert document["version"] == error_codes.CATALOG_VERSION
    for row in document["codes"]:
        info = error_codes.CATALOG[error_codes.ErrorCode(row["code"])]
        assert info.category.value == row["category"]
        assert (info.http_status, info.cli_exit, info.retryable, info.description) == (
            row["http_status"],
            row["cli_exit"],
            row["retryable"],
            row["description"],
        )
