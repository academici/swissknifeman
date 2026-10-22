"""Work source port: where orchestration runs get their work and where they register its outcome.

The extension point ``orch:work-source`` (``unit.json``) is served by a command plugin of ``aicore.ext.plugins``;
the configuration names the plugin (``work_source``). Every call is checked on both sides against the contract
``schemas/work-source/v1`` (``input``, ``output``): a request orch builds wrongly never leaves, and an answer that
does not match the contract is a failure of the plugin, never data. The report a register request carries is the kind
``register-report`` of the same contract (``orch.worksource_report``). Refusals of the source (a blocked claim, a
refused registration) are answers with a ``reason_code``; the caller decides what they mean.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from aicore.ext import plugins
from aicore.ext.errors import ExtError
from aicore.util import schema

from orch.settings import ORCH_ROOT

POINT = "orch:work-source"
CONTRACT_DIR = ORCH_ROOT / "schemas" / "work-source" / "v1"
OPS = ("claim", "brief", "register", "commit", "release", "note", "research")
REPORT_KIND = "register-report"
KINDS = ("input", "output", REPORT_KIND)
_REGISTRY: list = []


class WorkSourceError(Exception):
    """``WORK_SOURCE_UNAVAILABLE`` (no usable plugin), ``WORK_SOURCE_FAILED`` (the call or its answer failed) or
    ``INPUT_INVALID`` (orch built a request outside the contract)."""

    def __init__(self, code: str, message: str, data: Mapping[str, Any] | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.data = dict(data or {})


class WorkSource(Protocol):
    """A work source: the operations of ``work-source/v1``, each returning its output document. ``release`` is optional: a
    source that does not serve it keeps the claim, and the caller treats the refusal as "not released". ``note`` is
    optional too: a source that does not serve it loses the note of support work, never the work. So is ``research``: the
    result of a research stage stays in the artifacts of the run."""

    def claim(self, **fields: Any) -> dict: ...

    def brief(self, **fields: Any) -> dict: ...

    def register(self, **fields: Any) -> dict: ...

    def commit(self, **fields: Any) -> dict: ...

    def release(self, **fields: Any) -> dict: ...

    def note(self, **fields: Any) -> dict: ...

    def research(self, **fields: Any) -> dict: ...


def _registry():
    if not _REGISTRY:
        _REGISTRY.append(schema.load_contract_set(CONTRACT_DIR)[0])
    return _REGISTRY[0]


def problems(doc: object, kind: str) -> list[str]:
    """Violations of ``work-source/v1`` ``kind`` by ``doc`` as ``pointer: message`` lines. ``input`` and ``output`` are
    checked against the branch of their ``op`` so that the messages name the field that is wrong; ``register-report``
    (the report of a register request) is checked as a whole."""
    if kind not in KINDS:
        raise schema.SchemaProfileError(f"unknown work-source kind: {kind!r}")
    registry = _registry()
    if kind == REPORT_KIND:
        return [issue.message for issue in schema.validate(doc, kind, registry)]
    op = doc.get("op") if isinstance(doc, dict) else None
    if op not in OPS:
        return [f"/op: must be one of {', '.join(OPS)}"]
    node, owner = registry.resolve(f"#/$defs/{op}", f"urn:swissknifeman:orch:work-source:{kind}:v1")
    issues = schema.validate_node(registry, node, owner, doc)
    return [f"{issue.path or '/'}: {issue.message}" for issue in issues]


class PluginWorkSource:
    """The work source served by the plugin ``plugin_id`` of ``[aicore.plugins]``.

    The registration is looked up on every call (the configuration and the manifest may change between steps of a
    run); the plugin is described before each invocation by ``aicore.ext.plugins``.
    """

    def __init__(self, plugin_id: str, *, project: str | Path | None = None, env: Mapping[str, str] | None = None,
                 config_file: str | Path | None = None):
        self.plugin_id = plugin_id
        self.project = project
        self.env = env
        self.config_file = config_file

    def _registration(self) -> plugins.Registration:
        try:
            registration = plugins.find_registration(self.plugin_id, self.project, env=self.env,
                                                     config_file=self.config_file)
        except ExtError as error:
            raise WorkSourceError("WORK_SOURCE_UNAVAILABLE", f"work source {self.plugin_id}: {error.code}: "
                                  f"{error.message}") from None
        if not registration.enabled:
            raise WorkSourceError("WORK_SOURCE_UNAVAILABLE", f"work source {self.plugin_id} is disabled")
        if not registration.usable:
            problem = registration.problem or {"code": "PLUGIN_MANIFEST_INVALID", "message": "no manifest"}
            raise WorkSourceError("WORK_SOURCE_UNAVAILABLE", f"work source {self.plugin_id}: {problem['code']}: "
                                  f"{problem['message']}")
        if POINT not in registration.manifest.points:
            raise WorkSourceError("WORK_SOURCE_UNAVAILABLE", f"plugin {self.plugin_id} does not provide {POINT}")
        return registration

    def call(self, op: str, fields: Mapping[str, Any]) -> dict:
        request = {"op": op, **{key: value for key, value in fields.items() if value is not None}}
        found = problems(request, "input")
        if found:
            raise WorkSourceError("INPUT_INVALID", f"{op} request outside work-source/v1: {'; '.join(found[:3])}",
                                  {"issues": found})
        result = plugins.invoke_one(self._registration(), POINT, request, env=self.env, project=self.project)
        if result.status != "ok" or not isinstance(result.output, dict):
            code = result.code or result.status
            raise WorkSourceError("WORK_SOURCE_FAILED", f"work source {self.plugin_id} {op}: {code}: "
                                  f"{result.error or 'no output'}", {"plugin_code": code})
        found = problems(result.output, "output")
        if found or result.output.get("op") != op:
            found = found or [f"/op: answers {result.output.get('op')!r} to {op!r}"]
            raise WorkSourceError("WORK_SOURCE_FAILED", f"work source {self.plugin_id} {op} answered outside "
                                  f"work-source/v1: {'; '.join(found[:3])}", {"issues": found})
        return result.output

    def claim(self, **fields: Any) -> dict:
        return self.call("claim", fields)

    def brief(self, **fields: Any) -> dict:
        return self.call("brief", fields)

    def register(self, **fields: Any) -> dict:
        return self.call("register", fields)

    def commit(self, **fields: Any) -> dict:
        return self.call("commit", fields)

    def release(self, **fields: Any) -> dict:
        return self.call("release", fields)

    def note(self, **fields: Any) -> dict:
        return self.call("note", fields)

    def research(self, **fields: Any) -> dict:
        return self.call("research", fields)
