"""CLI-edge binding of one indexed admission to one bounded provider activity."""
from __future__ import annotations

import json
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from . import business_dispatch, dispatch, security, worker
from .providers import claude_code, codex, parity
from .providers.common import AdapterRefusal


class ProviderActivityPort:
    """Run only an already-indexed admission; scheduler remains provider-free."""

    def __init__(self, plan_dir: Path, admission: dict[str, Any], *,
                 registry: dict[str, Any] | None = None,
                 runner: Callable[..., dict[str, Any]] = worker.run,
                 content_resolver: Callable[[str], bytes | None] | None = None) -> None:
        self.plan_dir = plan_dir.resolve()
        self.admission = dispatch.verify_admission(admission)
        security.indexed_admission(self.plan_dir, self.plan_dir / "artifacts/P2/p3-smoke-admissions" / f"{self.admission['task']['provider']}.json")
        self.registry = registry or {"codex": codex, "claude-code": claude_code}
        if set(self.registry) != {"codex", "claude-code"}:
            raise AdapterRefusal("MAPPING_UNKNOWN")
        self.runner = runner
        self.content_resolver = content_resolver or (lambda _hash: None)

    def _request(self) -> dict[str, Any]:
        task, grant = self.admission["task"], self.admission["grant"]
        matrix_path = self.plan_dir / "artifacts/P0/provider-matrix-v1.json"
        try:
            if hashlib.sha256(matrix_path.read_bytes()).hexdigest() != task["source_hashes"]["provider_matrix"]:
                raise AdapterRefusal("MAPPING_UNKNOWN")
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
            providers = [row for row in matrix["providers"] if row.get("provider") == task["provider"]]
            if len(providers) != 1 or not isinstance(providers[0].get("version"), str):
                raise AdapterRefusal("MAPPING_UNKNOWN")
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise AdapterRefusal("MAPPING_UNKNOWN") from exc
        return {
            "provider": {"id": task["provider"], "cli_version": providers[0]["version"], "mapping_state": "supported"},
            "route": {"model_class": grant["route"]["model_class"], "effort": grant["route"]["effort"],
                      "capabilities": list(grant["capabilities"])},
            "permissions": {"approval_mode": "never", "sandbox_mode": "read_only", "network_mode": "disabled",
                            "source": "indexed-admission"},
            "budgets": dict(task["budgets"]),
            "bundle": {"content_refs": [task["prompt"]["content_hash"], task["response_schema"]["content_hash"]]},
            "child_policy": {"mode": "forbidden", "max_children": 0, "allowed_capabilities": []},
        }

    @staticmethod
    def _refusal(reason: str) -> dict[str, Any]:
        return {"kind": "provider_unavailable", "reason_code": reason, "process_count": 0}

    def __call__(self, slice_value: dict[str, Any]) -> dict[str, Any]:
        if slice_value.get("input_hashes", {}).get("admission") != self.admission["admission_hash"]:
            return self._refusal("LINKAGE_MISMATCH")
        provider_id = self.admission["task"]["provider"]
        try:
            mapping = parity.load_mapping(self.plan_dir / "artifacts/P3/provider-parity-v1.json")
            adapter_name = parity.lookup_provider(parity.build_registry(mapping["registry"]), provider_id)
            if adapter_name.rsplit(".", 1)[-1].replace("claude_code", "claude-code") != provider_id:
                raise AdapterRefusal("MAPPING_UNKNOWN")
            adapter = self.registry[provider_id]
            request = self._request()
            security.request(self.admission, request)
            prepared = adapter.prepare(request, plan_dir=self.plan_dir, native_tools=(),
                                       content_resolver=self.content_resolver)
        except (AdapterRefusal, KeyError) as exc:
            return self._refusal(getattr(exc, "reason", "MAPPING_UNKNOWN"))
        try:
            with tempfile.TemporaryDirectory(prefix="artifex-p3-") as cwd:
                result = self.runner(prepared["argv"], cwd=cwd, env=security.environment({}), stdin=prepared["stdin"],
                                   timeout_ms=request["budgets"]["timeout_ms"],
                                   max_output_bytes=request["budgets"]["max_output_bytes"],
                                   max_event_count=request["budgets"]["max_event_count"],
                                   normalizer=lambda rows, exit_code: adapter.fold_records(rows, request, exit_code=exit_code))
                return security.observation(result)
        except (KeyError, TypeError, OSError, security.SecurityRefusal):
            return self._refusal("MAPPING_UNKNOWN")


class BusinessProviderActivityPort:
    """D108-only request projection.

    It deliberately does not run a provider: P5.5 can prove the argv projection
    without turning one of the fourteen D105 admissions into pilot evidence.
    """

    def __init__(self, plan_dir: Path, admission: dict[str, Any], *, g2_digest: str,
                 g2b_digest: str, modules: dict[str, Any] | None = None,
                 runner: Callable[..., dict[str, Any]] = worker.run,
                 version_probe: Callable[[str, str], str | None] | None = None) -> None:
        self.plan_dir = plan_dir.resolve()
        self.admission = admission
        self.g2_digest, self.g2b_digest = g2_digest, g2b_digest
        self.modules = modules or {"codex": codex, "claude-code": claude_code}
        if set(self.modules) != {"codex", "claude-code"}:
            raise AdapterRefusal("MAPPING_UNKNOWN")
        self.runner = runner
        self.version_probe = version_probe or self._live_version

    def request(self, *, provider_version: str, cwd: Path) -> dict[str, Any]:
        return business_dispatch.request(self.admission, provider_version=provider_version, cwd=cwd)

    @staticmethod
    def _live_version(binary: str, _provider_id: str) -> str | None:
        try:
            completed = subprocess.run([binary, "--version"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                       check=False, env={"PATH": os.defpath})
        except OSError:
            return None
        return completed.stdout.decode("utf-8", "replace").strip() or None

    def _prompt(self) -> str:
        files = ", ".join(self.admission["task"]["files"])
        return ("Work only in these admission-declared files: " + files
                + ". Implement the bounded repository slice, modify no other path, create no "
                  "commit, then return only a JSON object satisfying the supplied schema.")

    def run(self, *, cwd: Path, binary: str | None = None) -> dict[str, Any]:
        """Execute exactly one D105 business admission through a fresh provider process.

        Composes the same admission→argv→activity→schedule shape as
        ``ProviderActivityPort`` (D108/P5.5), routed through ``build_business_argv``/
        ``fold_business_records``/``worker.run`` instead of the smoke mapper pair.
        """
        provider_id = self.admission["task"]["provider"]
        adapter = self.modules.get(provider_id)
        if adapter is None:
            return {"kind": "provider_unavailable", "reason_code": "MAPPING_UNKNOWN", "process_count": 0}
        try:
            resolved_binary = binary or adapter.resolve_binary()
        except AdapterRefusal as exc:
            return {"kind": "provider_unavailable", "reason_code": exc.reason, "process_count": 0}
        if self.version_probe(resolved_binary, provider_id) != adapter.BUSINESS_VERSION:
            return {"kind": "provider_unavailable", "reason_code": "MAPPING_UNKNOWN", "process_count": 0}
        try:
            request = self.request(provider_version=adapter.BUSINESS_VERSION, cwd=cwd)
        except business_dispatch.BusinessRefusal as exc:
            return {"kind": "provider_unavailable", "reason_code": exc.reason, "process_count": 0}
        schema = self.plan_dir / "artifacts/P5/business-worker-output-schema-v1.json"
        mcp_config: Path | None = None
        try:
            if provider_id == "codex":
                argv = adapter.build_business_argv(request, schema_path=schema, cwd=cwd, binary=resolved_binary)
                stdin = self._prompt().encode("utf-8")
                fold: Callable[[list[str], int], dict[str, Any]] = (
                    lambda rows, exit_code: adapter.fold_records(rows, request, exit_code=exit_code))
            else:
                fd, mcp_name = tempfile.mkstemp(prefix="artifex-p5-mcp-", suffix=".json")
                mcp_config = Path(mcp_name)
                os.close(fd)
                mcp_config.write_text('{"mcpServers":{}}', encoding="utf-8")
                argv = adapter.build_business_argv(request, schema_path=schema, cwd=cwd,
                                                   mcp_config_path=mcp_config, binary=resolved_binary)
                argv[-1] = self._prompt()
                stdin = b""
                fold = lambda rows, exit_code: adapter.fold_business_records(rows, request, exit_code=exit_code)
        except AdapterRefusal as exc:
            return {"kind": "provider_unavailable", "reason_code": exc.reason, "process_count": 0}
        try:
            result = self.runner(argv, cwd=cwd, env=security.environment({}), stdin=stdin,
                                timeout_ms=request["budgets"]["timeout_ms"],
                                max_output_bytes=request["budgets"]["max_output_bytes"],
                                max_event_count=request["budgets"]["max_event_count"], normalizer=fold)
            return security.observation(result)
        finally:
            if mcp_config is not None:
                mcp_config.unlink(missing_ok=True)
