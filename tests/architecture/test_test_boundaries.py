"""Test-only composition never leaks into product entry points or background work."""

import pytest

from architecture._test_boundaries import violations


def test_product_keeps_fault_injection_and_overrides_in_tests(session_root_tree) -> None:
    assert session_root_tree, "architecture smoke must inspect real product files"
    errors = [error for file in session_root_tree for error in violations(file.display_path, file.text)]
    assert not errors, "\n".join(errors)


@pytest.mark.parametrize("area", ["entrypoints/cli", "entrypoints/worker", "background"])
@pytest.mark.parametrize(
    "source",
    [
        "build_app(overrides=ports)",
        "bootstrap.build_app(overrides=ports)",
        "from skm.bootstrap.app import build_app as assemble\nassemble(overrides=ports)",
    ],
)
def test_rejects_test_overrides_at_product_edges(area: str, source: str) -> None:
    assert any(
        "CompositionOverrides is test-only" in e for e in violations(f"src/skm/{area}/main.py", source)
    )


@pytest.mark.parametrize("source", ["plan.maybe_fail(point)", "def maybe_fail(point): pass"])
def test_rejects_product_fault_hooks(source: str) -> None:
    assert violations("src/skm/bootstrap/app.py", source)


@pytest.mark.parametrize("source", ["import tests.support", "from tests.support import fault_injection"])
def test_rejects_product_import_of_test_infrastructure(source: str) -> None:
    assert violations("src/skm/bootstrap/app.py", source)


def test_allows_ordinary_product_composition() -> None:
    assert not violations("src/skm/entrypoints/cli/main.py", "app = build_app(backend='postgres')")
