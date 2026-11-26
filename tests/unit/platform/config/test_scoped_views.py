"""A typed settings view contains exactly the leaves of its own chain."""

import importlib
from dataclasses import asdict
from pathlib import Path
from runpy import run_path

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.execution.generated.settings import (
    ExecutionHostView,
    ExecutionReviewSettings,
    ExecutionSettings,
)
from skm.modules.integrations.generated.settings import HooksDocument
from skm.platform.config.keys import MISSING, Chain
from skm.platform.config.registry import SettingsRegistry

_HERE = Path(__file__).parent
effective = run_path(str(_HERE / "test_lazy_validation.py"))["effective"]
real_registry = run_path(str(_HERE / "test_registry_all_sections.py"))["real_registry"]


def leaves(view: type) -> set[str]:
    from importlib import import_module

    keys = set()
    for _wire, _name, spec, _required, _default, _has_default, key in view._FIELDS:
        if key:
            keys.add(key)
        else:
            keys.update(leaves(getattr(import_module(spec[3][0]), spec[3][1])))
    return keys


def test_all_generated_views_partition_each_mixed_section() -> None:
    registry: SettingsRegistry = real_registry()
    for section in registry.sections():
        host = getattr(section.view, "_HOST_VIEW", None)
        if host is None:
            assert len({spec.chain for spec in registry.keys(section=section.id)}) == 1
            assert leaves(section.view) == set(section.keys)
            continue
        work_keys = leaves(section.view)
        host_keys = leaves(host)
        assert work_keys.isdisjoint(host_keys), section.id
        assert work_keys == {s.key for s in registry.keys(section=section.id, chain=Chain.WORK)}
        assert host_keys == {s.key for s in registry.keys(section=section.id, chain=Chain.HOST)}


def test_execution_review_and_mixed_supervisor_have_only_work_fields() -> None:
    config = effective(registry=real_registry())
    view = config.section(ExecutionSettings)
    assert type(view.review) is ExecutionReviewSettings
    assert view.review.max_rounds == config.get("execution.review.max_rounds")
    assert view.supervisor.max_recoveries == config.get("execution.supervisor.max_recoveries")
    assert not hasattr(view.supervisor, "grace_seconds")
    assert not hasattr(view.supervisor, "diagnostic_snapshot")
    assert "grace_seconds" not in repr(view.supervisor)
    assert "grace_seconds" not in asdict(view.supervisor)
    assert "grace_seconds" not in view.supervisor.to_json()
    with pytest.raises(ValidationFailed) as failure:
        config.section(ExecutionHostView)
    assert failure.value.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED


def test_mixed_hooks_full_document_keeps_its_original_nested_host_type() -> None:
    registry = real_registry()
    values = {
        spec.key: spec.default for spec in registry.keys(section="hooks") if spec.default is not MISSING
    }
    document = HooksDocument.from_settings(values)
    assert type(document.host).__name__ == "HooksHostSettings"
    assert HooksDocument.from_json(document.to_json()) == document


def test_projected_name_collision_is_rejected() -> None:
    model = importlib.import_module("tools.codegen.model")
    scoped = importlib.import_module("tools.codegen.scoped_settings")
    first = model.Declaration("one", "urn:one", "", "example", "Same", "x.ts", "Same", "dataclass")
    second = model.Declaration("two", "urn:two", "", "example", "Same", "x.ts", "Same", "dataclass")
    with pytest.raises(model.CodegenError, match="projected type name collision"):
        scoped.project(model.Model({}, {"one": first, "two": second}))


def test_unknown_nested_group_cannot_bypass_scope_projection() -> None:
    model = importlib.import_module("tools.codegen.model")
    scoped = importlib.import_module("tools.codegen.scoped_settings")
    root = model.Declaration(
        "root", "urn:demo", "", "example", "DemoSettings", "x.ts", "Demo", "settings_view"
    )
    root.section = "demo"
    root.root = "root"
    root.fields = [
        model.Field("work", "work", model.Type("int"), True, settings_key="demo.work"),
        model.Field("host", "host", model.Type("int"), True, settings_key="demo.host"),
        model.Field("foreign", "foreign", model.Type("ref", ref="foreign"), True),
    ]
    foreign = model.Declaration(
        "foreign", "urn:foreign", "", "other", "Foreign", "y.ts", "Foreign", "dataclass"
    )
    document = {"properties": {"work": {"x-skm": {"chain": "work"}}, "host": {"x-skm": {"chain": "host"}}}}
    with pytest.raises(model.CodegenError, match="cannot scope settings group"):
        scoped.project(model.Model({"urn:demo": document}, {"root": root, "foreign": foreign}))
