"""Deterministic, schema-validated Bundle v1 producer."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from task import plan_layout, plan_lint, plan_projection, plan_weight, token_estimate


class BundleError(ValueError):
    """A Bundle v1 cannot be resolved, validated, or freshness-checked."""


BUNDLE_VERSION = "1.0.0"
GENERATOR_VERSION = "1.0.0"
_ITEM = re.compile(r"^P\d+\.\d+$")
_SECTION = re.compile(r"§\s*(\d+(?:\.\d+)*)")
_SCHEMA = Path(__file__).resolve().parents[2] / "configs" / "bundle-v1.schema.json"


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _without(value: dict, key: str) -> dict:
    return {name: data for name, data in value.items() if name != key}


def _schema() -> dict:
    try:
        return json.loads(_SCHEMA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleError(f"schema Bundle v1 не читается: {_SCHEMA}") from exc


def _check(value, schema: dict, root: dict, path: str = "$"):
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/"):
            raise BundleError(f"schema Bundle v1: неподдерживаемая ссылка {ref}")
        return _check(value, root["$defs"][ref.rsplit("/", 1)[-1]], root, path)
    if "oneOf" in schema:
        valid = []
        for variant in schema["oneOf"]:
            try:
                _check(value, variant, root, path)
                valid.append(variant)
            except BundleError:
                pass
        if len(valid) != 1:
            raise BundleError(f"{path}: не проходит ровно один вариант schema")
        return
    if "const" in schema and value != schema["const"]:
        raise BundleError(f"{path}: ожидается {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise BundleError(f"{path}: значение вне enum")
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            raise BundleError(f"{path}: ожидается object")
        missing = [name for name in schema.get("required", ()) if name not in value]
        if missing:
            raise BundleError(f"{path}: нет обязательных полей {', '.join(missing)}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                raise BundleError(f"{path}: лишние поля {', '.join(extra)}")
        for name, child in properties.items():
            if name in value:
                _check(value[name], child, root, f"{path}.{name}")
    elif kind == "array":
        if not isinstance(value, list):
            raise BundleError(f"{path}: ожидается array")
        for index, child in enumerate(value):
            _check(child, schema.get("items", {}), root, f"{path}[{index}]")
    elif kind == "string":
        if not isinstance(value, str):
            raise BundleError(f"{path}: ожидается string")
        if len(value) < schema.get("minLength", 0):
            raise BundleError(f"{path}: строка короче minLength")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise BundleError(f"{path}: не проходит pattern")
    elif kind == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise BundleError(f"{path}: ожидается integer")
        if value < schema.get("minimum", value):
            raise BundleError(f"{path}: меньше minimum")


def validate(model: dict) -> None:
    schema = _schema()
    _check(model, schema, schema)


def _fields(plan_dir: Path, item_id: str) -> dict:
    phase_id = item_id.split(".")[0]
    try:
        phase_path = plan_layout.phase_path(plan_dir, phase_id)
    except plan_layout.PlanLayoutError as exc:
        raise BundleError(str(exc)) from exc
    diagnostics = plan_lint.Diagnostics()
    parsed = plan_lint.parse_phase_md(phase_path, phase_id, diagnostics,
                                      layout=plan_layout.layout_version(plan_dir))
    if parsed is None or item_id not in parsed["items"]:
        raise BundleError(f"{item_id}: ТЗ не найдено")
    return {name: value for name, (value, _line) in parsed["items"][item_id][0]["fields"].items()}


def _raw_entries(value: str, field: str) -> list[str]:
    entries = plan_weight.split_entries(value)
    if field == "Inputs" and len(entries) == 1:
        entries = [part.strip() for part in entries[0].split(" · ") if part.strip()]
    return entries


def _relative(path: Path, plan_dir: Path, repo_root: Path) -> str:
    for root in (plan_dir, repo_root):
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
    raise BundleError(f"вход вне plan/repo root: {path}")


def _selectors(raw: str) -> list[dict]:
    sections = _SECTION.findall(raw)
    return ([{"kind": "section", "anchor": section} for section in sections]
            or [{"kind": "whole_file"}])


def _selected_bytes(raw: bytes, selector: dict, path: Path) -> bytes:
    if selector["kind"] == "whole_file":
        return raw
    try:
        lines = raw.splitlines(keepends=True)
        text = [line.decode("utf-8") for line in lines]
    except UnicodeDecodeError as exc:
        raise BundleError(f"{path}: section selector требует UTF-8") from exc
    anchor = selector["anchor"]
    start = next((index for index, line in enumerate(text)
                  if re.match(rf"^#+\s+{re.escape(anchor)}(?:[.\s]|$)", line)), None)
    if start is None:
        raise BundleError(f"{path}: section {anchor!r} не найдена")
    level = len(text[start]) - len(text[start].lstrip("#"))
    end = next((index for index in range(start + 1, len(text))
                if re.match(r"^#+\s", text[index])
                and len(text[index]) - len(text[index].lstrip("#")) <= level), len(lines))
    return b"".join(lines[start:end])


def model(plan_dir, item_id: str) -> dict:
    plan_dir = Path(plan_dir)
    if not _ITEM.fullmatch(item_id):
        raise BundleError("item должен иметь форму Pn.m")
    if plan_layout.layout_version(plan_dir) != "v2":
        raise BundleError("Bundle v1 существует только для Layout v2")
    fields = _fields(plan_dir, item_id)
    repo_root = plan_weight.repo_root_for(plan_dir)
    declarations, entries = {"inputs": [], "required_reads": []}, []
    for field, key in (("Inputs", "inputs"), ("Required Reads", "required_reads")):
        for ordinal, raw in enumerate(_raw_entries(fields.get(field, ""), field), 1):
            candidates = plan_weight.path_candidates(raw)
            if not candidates:
                raise BundleError(f"unresolvable_entry: {raw}")
            for token, _declared in candidates:
                source = plan_weight.resolve_candidate(token, (plan_dir, repo_root))
                if source is None:
                    raise BundleError(f"unresolvable_entry: {raw}")
                source_raw = source.read_bytes()
                for selector in _selectors(raw):
                    selected = _selected_bytes(source_raw, selector, source)
                    unit = {"ordinal": ordinal, "raw": raw, "path": _relative(source, plan_dir, repo_root),
                            "selector": selector}
                    declarations[key].append(unit)
                    entries.append({"declaration_ref": {"field": field, "ordinal": ordinal},
                                    "path": unit["path"], "selector": selector,
                                    "sha256": _sha(source_raw), "selected_sha256": _sha(selected),
                                    "estimated_tokens": token_estimate.estimate_text(selected.decode("utf-8", errors="replace"))})
    declaration = {**declarations}
    declaration["sha256"] = _sha(canonical_json(declaration).encode("utf-8"))
    artifact = token_estimate.load_artifact()
    calibration_raw = token_estimate.DEFAULT_ARTIFACT_PATH.read_bytes()
    result = {"$schema": "urn:swissknifeman:task:bundle:v1", "bundle_version": BUNDLE_VERSION,
              "item_id": item_id,
              "provenance": {"generator": "task.plan_bundle", "generator_version": GENERATOR_VERSION,
                             "calibration_id": _sha(calibration_raw),
                             "model_id": artifact["calibration_target"]["requested_model_id"]},
              "declaration": declaration, "entries": entries}
    result["manifest_sha256"] = _sha(canonical_json(result).encode("utf-8"))
    validate(result)
    return result


def render(plan_dir, item_id: str) -> str:
    return canonical_json(model(plan_dir, item_id))


def build(plan_dir, item_id: str, *, check: bool = False) -> Path:
    try:
        target = plan_layout.carrier_path(plan_dir, "bundle", item_id=item_id)
        plan_projection.write_or_check(target, render(plan_dir, item_id), check=check)
        return target
    except (plan_layout.PlanLayoutError, plan_projection.ProjectionError) as exc:
        raise BundleError(str(exc)) from exc


def build_all(plan_dir, *, check: bool = False) -> tuple[Path, ...]:
    plan_dir = Path(plan_dir)
    return tuple(build(plan_dir, path.stem, check=check)
                 for phase in plan_layout.phase_paths(plan_dir)
                 for path in plan_layout.item_spec_paths(plan_dir, phase))
