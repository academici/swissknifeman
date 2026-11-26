"""default_schema_root: packaged tree first, checkout tree as fallback, nothing from the environment."""

from pathlib import Path

import pytest

from skm.platform.schema import locator


def test_default_root_is_inside_the_package(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # the working directory must not matter
    root = locator.default_schema_root()
    assert root.is_dir()
    assert (root / "kernel" / "defs.v1.json").is_file()
    assert (root / "workspace" / "commands" / "create-project.v1.json").is_file()


def test_checkout_root_walks_up_to_src_skm_schemas(tmp_path: Path) -> None:
    schemas = tmp_path / "repo" / "src" / "skm" / "schemas"
    schemas.mkdir(parents=True)
    deep = tmp_path / "repo" / "src" / "skm" / "platform" / "schema" / "locator.py"
    assert locator.checkout_schema_root(deep) == schemas


def test_checkout_root_requires_the_schemas_directory(tmp_path: Path) -> None:
    (tmp_path / "repo" / "src" / "skm").mkdir(parents=True)
    found = locator.checkout_schema_root(tmp_path / "repo" / "src" / "skm" / "x.py")
    # tmp_path may itself sit inside a checkout; only the incomplete repo below it must be skipped
    assert found is None or tmp_path not in found.parents


def test_missing_package_tree_falls_back_to_the_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    package = tmp_path / "checkout" / "src" / "skm"
    (package / "schemas").mkdir(parents=True)
    monkeypatch.setattr(locator.resources, "files", lambda _package: empty)
    monkeypatch.setattr(locator.skm, "__file__", str(package / "__init__.py"))
    assert locator.default_schema_root() == package / "schemas"


def test_nothing_found_is_a_runtime_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(locator.resources, "files", lambda _package: tmp_path)
    monkeypatch.setattr(locator, "checkout_schema_root", lambda _start: None)
    with pytest.raises(RuntimeError, match="schemas not found"):
        locator.default_schema_root()
