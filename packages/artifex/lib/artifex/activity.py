"""CLI-edge binding of one indexed admission to one bounded provider activity."""
from __future__ import annotations

import json
import hashlib
import tempfile
from pathlib import Path
from typing import Any, Callable

from . import dispatch, security, worker
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
