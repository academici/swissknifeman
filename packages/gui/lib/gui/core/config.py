"""ConfigService: the configuration editor behind ``/v1/config`` (stdlib + aicore).

Reading goes through ``aicore.config`` (``units.discover``, ``load_module_schema``, ``resolve``, ``read_layer``);
writing only through ``aicore.config.apply_layer_patch`` (I3) into the layers ``machine`` and ``project``. A change is
a *preview* first (no side effects, an entry of the in-memory :class:`PreviewStore`), then a *commit* of that preview
by its ``preview_id``: the patch comes from the stored record, never from the commit request, and the file is written
only if it still has the revision the preview was computed on (I8). Secrets are references (``env://``,
``keyring://``); no value of a secret leaves this module (I6). Every method blocks (files, the layer lock): the HTTP
layer runs them in a worker thread.
"""
from __future__ import annotations

import collections
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from aicore.config import (LAYER_NAMES, ConfigError, apply_layer_patch, load_module_schema, plan_layer_edit,
                           read_layer, resolve)
from aicore.config import units
from aicore.config.secrets import is_secret_ref, split_ref
from aicore.state import machine_config_file, project_config_file
from aicore.util.digest import digest_json, sha256_tagged
from aicore.util.redact import env_secrets, redact_document, redact_text

from .. import contracts
from ..errors import GuiError

VIEW_CONTRACT = "urn:swissknifeman:gui:config-view:v1"
MUTATION_CONTRACT = "urn:swissknifeman:gui:config-mutation:v1"
WRITABLE_LAYERS = ("machine", "project")
SECRET_SCHEMES = ("env", "keyring")
RAW_MAX_BYTES = 262144
STORE_MAX = 64
EVENT_TYPE = "gui.config.changed"
AUDIT_ACTION = "config.commit"

Key = Tuple[str, ...]


def _noop(_message: str) -> None:
    return None


@dataclass(frozen=True)
class PreviewRecord:
    """What a preview computed; the commit writes exactly ``ops`` into ``file`` if it still has ``revision``."""

    preview_id: str
    module: str
    layer: str
    project_id: Optional[str]
    project_root: Optional[str]
    file: str  # realpath of the layer file
    revision: str
    schema_digest: str
    ops: Tuple[Tuple[str, str, Any], ...]
    issues: Tuple[Dict[str, str], ...]
    confirm_required: bool
    confirm_reasons: Tuple[str, ...]
    keys: Tuple[str, ...]


class PreviewStore:
    """Previews in the memory of the backend process: at most ``max_items``, each valid for ``ttl_s`` seconds.

    The oldest one is dropped when the store is full. ``clock`` is injected so tests move time. A restart of the
    backend empties it (a commit of an earlier preview is then ``PREVIEW_STALE``).
    """

    def __init__(self, ttl_s: Callable[[], float], *, max_items: int = STORE_MAX,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl_s = ttl_s
        self._max = max_items
        self._clock = clock
        self._items: "collections.OrderedDict[str, Tuple[float, PreviewRecord]]" = collections.OrderedDict()
        self._lock = threading.Lock()

    def _purge(self) -> None:
        now = self._clock()
        for key in [key for key, (expires, _record) in self._items.items() if expires <= now]:
            del self._items[key]

    def put(self, record: PreviewRecord) -> None:
        with self._lock:
            self._purge()
            self._items.pop(record.preview_id, None)
            self._items[record.preview_id] = (self._clock() + self._ttl_s(), record)
            while len(self._items) > self._max:
                self._items.popitem(last=False)

    def get(self, preview_id: str) -> Optional[PreviewRecord]:
        with self._lock:
            self._purge()
            held = self._items.get(preview_id)
            return None if held is None else held[1]

    def drop(self, preview_id: str) -> None:
        with self._lock:
            self._items.pop(preview_id, None)

    def __len__(self) -> int:
        with self._lock:
            self._purge()
            return len(self._items)


def _json_value(value: Any) -> Any:
    """A TOML value as a JSON value (scalars and lists of scalars)."""
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _text(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value else None


class ConfigService:
    """Modules, view, preview and commit of the configuration of a module.

    ``config`` returns the ``[gui.config]`` settings (``lock_timeout_s``, ``preview_ttl_s``). ``audit(action, target,
    decision, details)`` records a decision (no values); ``emit_project(type, data, subject, root)`` journals an event
    in a project; ``emit_machine(type, data, subject)`` publishes one without a journal. A failing hook never fails a
    write that already happened.
    """

    def __init__(self, env: Mapping[str, str], config: Callable[[], Any], *,
                 audit: Optional[Callable[[str, str, str, Mapping[str, Any]], None]] = None,
                 emit_project: Optional[Callable[[str, Mapping[str, Any], str, str], None]] = None,
                 emit_machine: Optional[Callable[[str, Mapping[str, Any], str], None]] = None,
                 clock: Callable[[], float] = time.monotonic, home: Optional[str] = None) -> None:
        self.env = env
        self._config = config
        self._audit = audit
        self._emit_project = emit_project
        self._emit_machine = emit_machine
        self._home = home
        self.store = PreviewStore(lambda: float(self._config().preview_ttl_s), clock=clock)

    # --- helpers ------------------------------------------------------------------------------------------

    def _secrets(self) -> List[str]:
        return env_secrets(self.env)

    def _safe(self, text: str) -> str:
        return redact_text(str(text), secrets=self._secrets())

    def _unit(self, module: str) -> units.UnitInfo:
        found = units.discover(dict(self.env)).get(module)
        if found is None:
            raise GuiError("NOT_FOUND", f"no module {module!r} with a configuration schema")
        return found

    def _schema(self, module: str) -> Tuple[Any, Dict[str, Any], str]:
        """``(ModuleSchema, schema document, digest of the schema file)``."""
        info = self._unit(module)
        try:
            data = info.schema_path.read_bytes()
            document = json.loads(data.decode("utf-8"))
            return load_module_schema(info.schema_path, module), document, sha256_tagged(data)
        except (OSError, ValueError, ConfigError) as exc:
            raise GuiError("HANDLER_FAILED", f"the configuration schema of {module} cannot be read: "
                                             f"{self._safe(str(exc))}") from None

    def _layer_file(self, layer: str, project_root: Optional[str]) -> Path:
        if layer == "machine":
            return Path(machine_config_file(env=self.env, home=self._home))
        if layer == "project":
            if project_root is None:
                raise GuiError("INPUT_INVALID", "the project layer needs a project_id",
                               issues=[{"pointer": "/layer", "code": "project", "message": "choose a project"}])
            return Path(project_config_file(project_root))
        raise GuiError("CONFIG_LAYER_FORBIDDEN", f"layer {layer!r} cannot be written from the GUI; "
                                                 f"use {' or '.join(WRITABLE_LAYERS)}")

    def _resolve(self, module: str, schema: Any, project_root: Optional[str],
                 layer_texts: Optional[Mapping[str, str]] = None):
        try:
            return resolve(module, schema=schema, project=project_root, env=dict(self.env), home=self._home,
                           warn=_noop, layer_texts=layer_texts)
        except ConfigError as exc:
            raise self._invalid(exc) from None

    def _invalid(self, exc: ConfigError, key: str = "") -> GuiError:
        pointer = "/patch" if not (exc.key or key) else f"/patch/{exc.key or key}"
        return GuiError("INPUT_INVALID", self._safe(f"the configuration cannot be used: {exc.message}"),
                        issues=[{"pointer": pointer, "code": exc.code, "message": self._safe(exc.message)}])

    def _read(self, module: str, schema: Any, layer: str, path: Path):
        try:
            return read_layer(path, module, schema=schema, layer=layer)
        except ConfigError as exc:
            raise self._invalid(exc) from None

    def _check(self, document: Dict[str, Any], contract: str) -> Dict[str, Any]:
        problems = contracts.validate(document, contract)
        if problems:
            raise GuiError("OUTPUT_INVALID", f"the response does not match {contract}/v1: "
                                             f"{problems[0].path or '/'} {problems[0].code}")
        return document

    # --- modules and view ---------------------------------------------------------------------------------

    def modules(self) -> Dict[str, Any]:
        listed = []
        for module, info in sorted(units.discover(dict(self.env)).items()):
            title = description = None
            try:
                document = json.loads(info.schema_path.read_text(encoding="utf-8"))
                title, description = _text(document.get("title")), _text(document.get("description"))
            except (OSError, ValueError, AttributeError):
                pass
            listed.append({"id": module, "title": title, "description": description})
        return self._check({"$schema": VIEW_CONTRACT, "kind": "config_modules", "modules": listed}, "config-view")

    @staticmethod
    def _origin(value: Any = None, layer: Optional[str] = None, file: Optional[str] = None,
                line: Optional[int] = None, source: Optional[str] = None) -> Dict[str, Any]:
        return {"value": None if value is None else _json_value(value), "layer": layer, "file": file, "line": line,
                "source": source}

    def view(self, module: str, project_root: Optional[str], project_id: Optional[str] = None) -> Dict[str, Any]:
        schema, schema_document, schema_digest = self._schema(module)
        resolved = self._resolve(module, schema, project_root)
        snapshots: Dict[str, Any] = {}
        layers = []
        for info in resolved.layers:
            row = {"name": info.name, "file": info.file, "present": bool(info.present), "writable": False,
                   "revision": None, "raw": None, "raw_truncated": False}
            if info.name in WRITABLE_LAYERS and info.file is not None:
                snapshot = self._read(module, schema, info.name, Path(info.file))
                snapshots[info.name] = snapshot
                row["writable"] = True
                row["revision"] = snapshot.revision
                if len(snapshot.text.encode("utf-8")) > RAW_MAX_BYTES:
                    row["raw_truncated"] = True
                else:
                    row["raw"] = redact_text(snapshot.text, secrets=self._secrets())
            layers.append(row)
        explained = {entry.key: entry for entry in resolved.explain()}
        entries = []
        names: Dict[Key, List[str]] = {}
        for spec in schema.maps.values():
            found = resolved.get(spec.key)
            names[spec.key] = list(found) if isinstance(found, dict) else []
        for leaf_key in self._leaf_keys(schema, names):
            leaf = schema.leaf(leaf_key)
            dotted = ".".join(leaf_key)
            entry: Dict[str, Any] = {
                "key": dotted, "type": leaf.type, "secret": bool(leaf.secret),
                "description": _text(leaf.description), "allowed_layers": list(leaf.layers) if leaf.layers else None,
                "effective": self._origin(), "overridden": [],
                "layer_values": {name: _json_value(snapshots[name].values[dotted])
                                 if name in snapshots and dotted in snapshots[name].values else None
                                 for name in WRITABLE_LAYERS}}
            if leaf.has_default:
                entry["default"] = _json_value(leaf.default)
            found_entry = explained.get(dotted)
            if found_entry is not None:
                entry["effective"] = self._origin(found_entry.value, found_entry.layer, found_entry.file,
                                                  found_entry.line, found_entry.source)
                entry["overridden"] = [self._origin(item.value, item.layer, item.file, item.line, item.source)
                                       for item in found_entry.overridden]
            entries.append(entry)
        maps = [{"key": ".".join(spec.key), "entry_pattern": spec.pattern or None, "entries": names[spec.key]}
                for spec in schema.maps.values()]
        document = {"$schema": VIEW_CONTRACT, "kind": "config_view", "module": module, "project_id": project_id,
                    "schema_digest": schema_digest, "schema": schema_document, "layers": layers,
                    "entries": entries, "maps": maps, "warnings": list(resolved.warnings)}
        document = redact_document(document, secrets=self._secrets())
        return self._check(document, "config-view")

    @staticmethod
    def _leaf_keys(schema: Any, names: Mapping[Key, Sequence[str]]) -> List[Key]:
        keys: List[Key] = list(schema.leaves)
        for spec in schema.maps.values():
            for name in names.get(spec.key, ()):
                if spec.value_leaf is not None:
                    keys.append(spec.key + (name,))
                else:
                    keys.extend(spec.key + (name, prop) for prop in (spec.value_table or ()))
        return keys

    # --- preview ------------------------------------------------------------------------------------------

    def preview(self, module: str, project_root: Optional[str], project_id: Optional[str],
                request: Mapping[str, Any]) -> Dict[str, Any]:
        if request.get("module") != module:
            raise GuiError("INPUT_INVALID", "the module of the body differs from the module of the path",
                           issues=[{"pointer": "/module", "code": "const", "message": f"expected {module}"}])
        layer = request["layer"]
        path = self._layer_file(layer, project_root)
        schema, _document, schema_digest = self._schema(module)
        snapshot = self._read(module, schema, layer, path)
        if snapshot.revision != request["expected_revision"]:
            raise GuiError("CONFIG_REVISION_CONFLICT", "the file changed since the revision of the request",
                           details={"current_revision": snapshot.revision})
        patch = [dict(op) for op in request["patch"]]
        issues: List[Dict[str, str]] = []
        ops: List[Tuple[str, str, Any]] = []
        for op in patch:
            key, kind = op["key"], op["op"]
            leaf = schema.find_leaf(key)
            if kind == "set" and leaf is not None and leaf.secret and not self._secret_ref_ok(op["value"]):
                issues.append({"key": key, "code": "SECRET_REF_INVALID",
                               "message": "a secret key takes only a reference env://NAME or keyring://NAME "
                                          "(value redacted)"})
                continue
            ops.append((kind, key, op.get("value") if kind == "set" else None))
        plan = self._plan(module, schema, snapshot.text, ops, layer, str(path))
        first_key = patch[0]["key"]
        for problem in plan.issues:
            key = problem.key if problem.key and self._key_ok(problem.key) else first_key
            issues.append({"key": key, "code": problem.code, "message": self._safe(problem.message)})
        before = self._resolve(module, schema, project_root)
        try:
            after = self._resolve(module, schema, project_root, {layer: plan.text_after})
        except GuiError:
            after = before
        eff_before = {entry.key: entry for entry in before.explain()}
        eff_after = {entry.key: entry for entry in after.explain()}
        failed = {issue["key"] for issue in issues}
        applied = [key for _kind, key, _value in ops if key not in failed]
        diff_keys: List[str] = []
        for key in [op["key"] for op in patch if schema.find_leaf(op["key"]) is not None]:
            if key not in diff_keys:
                diff_keys.append(key)
        for key in [*eff_after, *eff_before]:
            if key not in diff_keys and self._differs(eff_before.get(key), eff_after.get(key)):
                diff_keys.append(key)
        diff = [{"key": key, "before": self._layer_value(plan.before.get(key)),
                 "after": self._layer_value(plan.after.get(key)),
                 "effective_before": self._effective(eff_before.get(key)),
                 "effective_after": self._effective(eff_after.get(key))} for key in diff_keys]
        reasons = self._reasons(schema, patch, layer, applied, eff_after)
        revision = snapshot.revision
        file = os.path.realpath(path)
        preview_id = digest_json({"module": module, "layer": layer, "file": file, "revision": revision,
                                  "patch": self._patch_form(patch), "schema_digest": schema_digest,
                                  "project_id": project_id})
        keys = tuple(dict.fromkeys(op["key"] for op in patch))
        self.store.put(PreviewRecord(
            preview_id=preview_id, module=module, layer=layer, project_id=project_id, project_root=project_root,
            file=file, revision=revision, schema_digest=schema_digest, ops=tuple(ops), issues=tuple(issues),
            confirm_required=bool(reasons), confirm_reasons=tuple(reasons), keys=keys))
        document = {"$schema": MUTATION_CONTRACT, "kind": "preview", "preview_id": preview_id, "module": module,
                    "layer": layer, "file": str(path), "revision": revision, "diff": diff, "issues": issues,
                    "confirm_required": bool(reasons), "confirm_reasons": reasons}
        document = redact_document(document, secrets=self._secrets())
        return self._check(document, "config-mutation")

    @staticmethod
    def _key_ok(key: str) -> bool:
        return re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z0-9_-]+)*", key) is not None

    @staticmethod
    def _secret_ref_ok(value: Any) -> bool:
        if not (isinstance(value, str) and is_secret_ref(value)):
            return False
        try:
            return split_ref(value)[0] in SECRET_SCHEMES
        except ConfigError:
            return False

    @staticmethod
    def _plan(module: str, schema: Any, text: str, ops: Sequence[Tuple[str, str, Any]], layer: str, file: str):
        try:
            return plan_layer_edit(text, module, ops, schema=schema, layer=layer, file=file)
        except ConfigError as exc:
            raise GuiError("INPUT_INVALID", f"the layer file is invalid: {exc.message}",
                           issues=[{"pointer": "/layer", "code": exc.code, "message": exc.message}]) from None

    @staticmethod
    def _patch_form(patch: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        """The patch for ``digest_json`` (no floats): values as their canonical JSON text."""
        return [{"op": op["op"], "key": op["key"],
                 **({"value": json.dumps(op["value"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)}
                    if op["op"] == "set" else {})} for op in patch]

    @staticmethod
    def _layer_value(value: Any) -> Any:
        return None if value is None else _json_value(value)

    @staticmethod
    def _effective(entry: Any) -> Dict[str, Any]:
        if entry is None:
            return {"value": None, "layer": None}
        return {"value": _json_value(entry.value), "layer": entry.layer}

    @staticmethod
    def _differs(left: Any, right: Any) -> bool:
        if left is None or right is None:
            return left is not right
        return (left.value, left.layer) != (right.value, right.layer)

    @staticmethod
    def _reasons(schema: Any, patch: Sequence[Mapping[str, Any]], layer: str, applied: Sequence[str],
                 eff_after: Mapping[str, Any]) -> List[str]:
        reasons: List[str] = []
        if layer == "machine":
            reasons.append("machine_layer")
        if any((leaf := schema.find_leaf(op["key"])) is not None and leaf.secret for op in patch):
            reasons.append("secret_key")
        if any(op["op"] == "unset" for op in patch):
            reasons.append("unset")
        rank = LAYER_NAMES.index(layer)
        for key in dict.fromkeys(op["key"] for op in patch):
            found = eff_after.get(key)
            if key in applied and found is not None and LAYER_NAMES.index(found.layer) > rank:
                reason = f"shadowed:{found.layer}"
                if reason not in reasons:
                    reasons.append(reason)
        return reasons

    # --- commit -------------------------------------------------------------------------------------------

    def commit(self, module: str, layer: str, project_root: Optional[str], project_id: Optional[str],
               request: Mapping[str, Any]) -> Dict[str, Any]:
        if layer not in WRITABLE_LAYERS:
            raise GuiError("CONFIG_LAYER_FORBIDDEN", f"layer {layer!r} cannot be written from the GUI")
        record = self.store.get(request["preview_id"])
        if (record is None or record.module != module or record.layer != layer or record.project_id != project_id
                or request["expected_revision"] != record.revision):
            raise GuiError("PREVIEW_STALE", "this preview is unknown, expired or made for another change; "
                                            "preview the change again")
        target = f"{module}:{layer}"
        if record.issues:
            raise GuiError("INPUT_INVALID", "the preview has issues and cannot be committed",
                           issues=[{"pointer": f"/patch/{issue['key']}", "code": issue["code"],
                                    "message": issue["message"]} for issue in record.issues])
        if record.confirm_required and request.get("confirmed") is not True:
            self._record(target, "refused", {"code": "CONFIRMATION_REQUIRED", "file": record.file,
                                             "keys": list(record.keys)})
            raise GuiError("CONFIRMATION_REQUIRED", "this change must be confirmed",
                           details={"confirm_reasons": ",".join(record.confirm_reasons)})
        schema, _document, schema_digest = self._schema(module)
        path = self._layer_file(layer, project_root)
        if schema_digest != record.schema_digest or os.path.realpath(path) != record.file:
            raise GuiError("PREVIEW_STALE", "the schema or the file of the module changed after the preview")
        timeout = float(self._config().lock_timeout_s)
        try:
            result = apply_layer_patch(path, module, list(record.ops), schema=schema, layer=layer,
                                       expected_revision=record.revision, lock_timeout_s=timeout,
                                       project=project_root if layer == "project" else None,
                                       env=dict(self.env), home=self._home)
        except ConfigError as exc:
            self._fail(exc, module, schema, layer, path, record, target)
            raise  # pragma: no cover - _fail always raises
        self.store.drop(record.preview_id)
        revision_after = result.revision
        self._record(target, "applied", {"file": record.file, "revision_before": record.revision,
                                         "revision_after": revision_after, "keys": list(record.keys)})
        if result.changed:
            self._announce(module, layer, project_root, record.keys, revision_after)
        document = {"$schema": MUTATION_CONTRACT, "kind": "commit_result", "revision": revision_after,
                    "file": str(path), "backup": None if result.backup is None else str(result.backup)}
        return self._check(redact_document(document, secrets=self._secrets()), "config-mutation")

    def _fail(self, exc: ConfigError, module: str, schema: Any, layer: str, path: Path, record: PreviewRecord,
              target: str) -> None:
        details = {"code": exc.code, "file": record.file, "keys": list(record.keys)}
        if exc.code == "CONFIG_REVISION_CONFLICT":
            self._record(target, "refused", details)
            current = None
            try:
                current = read_layer(path, module, schema=schema, layer=layer).revision
            except ConfigError:
                pass
            raise GuiError("CONFIG_REVISION_CONFLICT", "the file changed since the preview; reload it",
                           details={"current_revision": current} if current else None) from None
        if exc.code == "CONFIG_LOCKED":
            self._record(target, "refused", details)
            raise GuiError("CONFIG_LOCKED", "another writer holds the lock of the file; try again") from None
        self._record(target, "refused", details)
        raise self._invalid(exc) from None

    # --- audit and events ---------------------------------------------------------------------------------

    def _record(self, target: str, decision: str, details: Mapping[str, Any]) -> None:
        if self._audit is None:
            return
        try:
            self._audit(AUDIT_ACTION, target, decision, dict(details))
        except Exception:  # noqa: BLE001 - an audit failure never undoes a write
            pass

    def _announce(self, module: str, layer: str, project_root: Optional[str], keys: Sequence[str],
                  revision: str) -> None:
        data = {"module": module, "layer": layer, "keys": list(keys), "revision": revision}
        try:
            if layer == "project" and project_root is not None and self._emit_project is not None:
                self._emit_project(EVENT_TYPE, data, module, project_root)
            elif layer == "machine" and self._emit_machine is not None:
                self._emit_machine(EVENT_TYPE, data, module)
        except Exception:  # noqa: BLE001 - journaling never undoes a write
            pass
