"""Run local-mode CLI dispatch with real provider leases and controlled runtime results."""

import json
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from io import StringIO
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from skm.adapters.host_commands import local_gate
from skm.application_bus.client import EmbeddedClient
from skm.bootstrap import local_modes
from skm.entrypoints.cli.commands import _adhoc, ask
from skm.entrypoints.cli.main import main
from skm.kernel.error_codes import ErrorCode
from skm.modules.runtimes.public import (
    AgentRequest,
    Capability,
    ErrorClass,
    ExitInfo,
    ProviderFailure,
    RuntimeResult,
    ToolDenial,
    unknown_usage,
)
from skm.platform.process import runner
from skm.platform.process.runner import ProcessResult
from support.adhoc import workflow


def _unexpected(*_: object, **_kwargs: object) -> Any:
    pytest.fail("unexpected external call")


def _invoke(*args: str, env: Mapping[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    out, err = StringIO(), StringIO()
    code = main(("--json", *args), stdout=out, stderr=err, environ=env or {}, backend=_unexpected)
    assert out.getvalue(), err.getvalue()
    return code, json.loads(out.getvalue())


def _completed(text: str = "answered", *, session: str | None = None, denied: bool = False) -> RuntimeResult:
    return RuntimeResult(
        "completed",
        text,
        None,
        session,
        None,
        unknown_usage(),
        None,
        ExitInfo(0, None, False, 1),
        False,
        (ToolDenial("write", "forbidden"),) if denied else (),
        0,
        None,
        None,
    )


@dataclass
class _Runtime:
    runtime_id: str = "codex"
    results: list[RuntimeResult] = field(default_factory=list)
    requests: list[AgentRequest] = field(default_factory=list)
    resume: bool = True
    barrier: Barrier | None = None

    def capabilities(self) -> "_Runtime":
        return self

    def supports(self, cap: Capability) -> bool:
        assert cap is Capability.SESSION_RESUME
        return self.resume

    def start(self, request: AgentRequest) -> None:
        self.requests.append(request)
        if self.barrier is not None:
            self.barrier.wait(timeout=3)

    def events(self, _handle: None) -> Iterator[object]:
        return iter(())

    def result(self, _handle: None) -> RuntimeResult:
        return self.results.pop(0)

    def cancel(self, _handle: None, *, grace_seconds: float) -> None:
        _unexpected(grace_seconds)


@dataclass
class _LocalCLI:
    cwd: Path
    env: dict[str, str]
    registry: Path
    runtimes: dict[str, _Runtime]

    def run(self, group: str, *args: str) -> tuple[int, dict[str, Any]]:
        return _invoke(
            group,
            "question or task",
            "--registry",
            str(self.registry),
            "--cwd",
            str(self.cwd),
            *args,
            env=self.env,
        )


@pytest.fixture
def local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _LocalCLI:
    cwd, home = tmp_path / "checkout", tmp_path / "home"
    cwd.mkdir()
    home.mkdir()
    registry = tmp_path / "pool.toml"
    registry.write_text(
        """
schema_version = 2
[slots.first]
runtime_id = "codex"
transport = "cli_subprocess"
models = [{name = "example-model", is_compat = false}]
[slots.second]
runtime_id = "claude_code"
transport = "cli_subprocess"
models = [{name = "example-model", is_compat = false}]
""",
        encoding="utf-8",
    )
    runtimes = {"codex": _Runtime(), "claude_code": _Runtime(runtime_id="claude_code")}

    def factory(runtime_id: str, **kwargs: object) -> _Runtime:
        assert kwargs["copy_credentials"] is False
        return runtimes[runtime_id]

    monkeypatch.setattr(
        local_modes,
        "RUNTIME_FACTORIES",
        {
            "codex": lambda **kwargs: factory("codex", **kwargs),
            "claude_code": lambda **kwargs: factory("claude_code", **kwargs),
        },
    )
    return _LocalCLI(cwd, {"HOME": str(home), "PATH": "/usr/bin:/bin"}, registry, runtimes)


def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(EmbeddedClient, "ask", _unexpected)
    monkeypatch.setattr(EmbeddedClient, "dispatch", _unexpected)
    monkeypatch.setattr(_adhoc, "resolve_project_id", _unexpected)
    monkeypatch.setattr(ask, "runtime_gateways", _unexpected)
    monkeypatch.setattr("skm.bootstrap.provider_accounts.QuotaProber.probe", _unexpected)
    monkeypatch.setattr("subprocess.Popen", _unexpected)


def test_ask_dry_run_is_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    _offline(monkeypatch)
    code, out = _invoke("ask", "preview", "--slot", "unavailable", "--schema", "missing.json", "--dry-run")
    assert code == 0
    assert out["result"]["read_only"] is True
    assert out["result"]["slot"] == "unavailable"
    assert out["result"]["schema"] == "missing.json"


def test_ask_retries_with_local_schema(local: _LocalCLI) -> None:
    path = local.cwd / "schema.json"
    path.write_text(
        json.dumps(
            {
                "type": "object",
                "required": ["count"],
                "properties": {"count": {"$ref": "#/$defs/counter"}},
                "$defs": {"counter": {"type": "integer"}},
            }
        ),
        encoding="utf-8",
    )
    runtime = local.runtimes["codex"]
    runtime.results.extend((_completed("not JSON"), _completed('{"count": "2"}'), _completed('{"count": 2}')))
    code, out = local.run("ask", "--schema", str(path))
    assert code == 0
    assert out["result"]["structured"] == {"count": 2}
    assert len(runtime.requests) == 3
    assert all(request.permissions.fs_write.allow == () for request in runtime.requests)
    assert all('"counter"' in request.rendered_prompt for request in runtime.requests)
    assert "previous JSON response was rejected" in runtime.requests[1].rendered_prompt


def test_ask_stops_after_three_schema_retries(local: _LocalCLI) -> None:
    path = local.cwd / "schema.json"
    path.write_text('{"type": "number"}', encoding="utf-8")
    runtime = local.runtimes["codex"]
    runtime.results.extend([_completed('"invalid"')] * 4)
    code, out = local.run("ask", "--schema", str(path))
    assert code == 1
    assert "does not match" in out["result"]["error"]
    assert len(runtime.requests) == 4


@pytest.mark.parametrize("keyword", ["$ref", "$dynamicRef"])
def test_ask_rejects_external_schema_references(
    local: _LocalCLI, monkeypatch: pytest.MonkeyPatch, keyword: str
) -> None:
    monkeypatch.setattr("urllib.request.urlopen", _unexpected)
    path = local.cwd / "schema.json"
    path.write_text(json.dumps({keyword: "https://invalid.example/schema.json"}), encoding="utf-8")
    code, out = local.run("ask", "--schema", str(path))
    assert code == 1
    assert "external JSON Schema references are forbidden" in out["result"]["error"]
    assert not local.runtimes["codex"].requests
    assert local_gate.LocalUserSchemaValidator().validate({}, path)[0] is False


@pytest.mark.parametrize("target", ["a description", 12, None, [], {"type": "unknown"}])
def test_ask_rejects_invalid_local_schema_reference(local: _LocalCLI, target: object) -> None:
    path = local.cwd / "schema.json"
    path.write_text(json.dumps({"$ref": "#/example", "example": target}), encoding="utf-8")
    runtime = local.runtimes["codex"]
    runtime.results.append(_completed("{}"))
    code, out = local.run("ask", "--schema", str(path))
    assert code == 1, out
    assert "invalid user JSON Schema" in out["result"]["error"]
    assert not runtime.requests
    assert local_gate.LocalUserSchemaValidator().validate({}, path)[0] is False


@pytest.mark.parametrize("index", ["-1", "01", "+1", "%2D1"])
def test_ask_rejects_invalid_schema_pointer_array_index(local: _LocalCLI, index: str) -> None:
    path = local.cwd / "schema.json"
    path.write_text(json.dumps({"$ref": f"#/data/{index}", "data": [False, True]}), encoding="utf-8")
    runtime = local.runtimes["codex"]
    runtime.results.append(_completed("{}"))
    code, out = local.run("ask", "--schema", str(path))
    assert code == 1, out
    assert "unresolvable user JSON Schema reference" in out["result"]["error"]
    assert not runtime.requests
    assert local_gate.LocalUserSchemaValidator().validate({}, path)[0] is False


@pytest.mark.parametrize(
    "schema",
    [
        pytest.param({"$id": "https://[", "type": "object"}, id="root"),
        pytest.param({"$defs": {"item": {"$id": "https://["}}}, id="embedded"),
    ],
)
def test_ask_rejects_invalid_schema_id(local: _LocalCLI, schema: dict[str, Any]) -> None:
    path = local.cwd / "schema.json"
    path.write_text(json.dumps(schema), encoding="utf-8")
    runtime = local.runtimes["codex"]
    runtime.results.append(_completed("{}"))
    code, out = local.run("ask", "--schema", str(path))
    assert code == 1, out
    assert "invalid user JSON Schema" in out["result"]["error"]
    assert not runtime.requests
    assert local_gate.LocalUserSchemaValidator().validate({}, path)[0] is False


@pytest.mark.parametrize(
    "subschema",
    [
        pytest.param({"$schema": "http://json-schema.org/draft-04/schema#", "id": 12}, id="draft-04-id"),
        pytest.param({"$schema": 12}, id="numeric-dialect"),
        pytest.param({"type": "unknown"}, id="invalid-type"),
        pytest.param(12, id="numeric-subschema"),
    ],
)
def test_ask_rejects_invalid_embedded_schema(local: _LocalCLI, subschema: object) -> None:
    path = local.cwd / "schema.json"
    path.write_text(json.dumps({"$defs": {"item": subschema}}), encoding="utf-8")
    code, out = local.run("ask", "--schema", str(path))
    assert code == 1, out
    assert "invalid user JSON Schema" in out["result"]["error"]
    assert not local.runtimes["codex"].requests
    assert local_gate.LocalUserSchemaValidator().validate({}, path)[0] is False


@pytest.mark.parametrize("shell", [False, True])
def test_do_gate_resume_and_redacted_tail(
    local: _LocalCLI, monkeypatch: pytest.MonkeyPatch, shell: bool
) -> None:
    command = 'quality-check "one argument" && other'
    expected = ("/bin/sh", "-c", command) if shell else ("quality-check", "one argument", "&&", "other")
    calls: list[tuple[str, ...]] = []
    output = "\n".join(f"gate-line-{i:02}" for i in range(45)) + "\napi_key=super-secret-key"

    def gate(argv: tuple[str, ...], **kwargs: Any) -> ProcessResult:
        assert argv == expected
        assert kwargs["cwd"] == local.cwd
        assert kwargs["timeout_seconds"] == 120.0
        assert kwargs["max_stdout_bytes"] == 1_048_576
        calls.append(argv)
        status = 1 if len(calls) == 1 else 0
        return ProcessResult(argv, status, output.encode(), b"", False, False, False, 0.0, None)

    monkeypatch.setattr(local_gate, "run", gate)
    runtime = local.runtimes["codex"]
    runtime.results.extend((_completed(session="provider-session"), _completed("fixed")))
    shell_flag = ("--gate-shell",) if shell else ()
    code, out = local.run("do", "--gate", command, "--max-gate-retries", "2", *shell_flag)
    assert code == 0
    assert out["result"]["answer"] == "fixed"
    assert len(calls) == 2
    first, retry = runtime.requests
    assert first.permissions.fs_write.allow
    assert first.client_home == retry.client_home
    assert first.request_id != retry.request_id
    assert first.session_policy == retry.session_policy == "persistent"
    assert first.resume_session_ref is None
    assert retry.resume_session_ref == "provider-session"
    assert "gate-line-05" not in retry.rendered_prompt
    assert "gate-line-06" in retry.rendered_prompt
    assert "gate-line-44" in retry.rendered_prompt
    assert "super-secret-key" not in retry.rendered_prompt


def test_do_gate_retry_gets_last_40_lines_after_truncation(
    local: _LocalCLI, monkeypatch: pytest.MonkeyPatch
) -> None:
    statuses = iter((1, 0))

    def launch(*_args: object, merge_stderr: bool = False, **_kwargs: object) -> tuple[bool, None]:
        return merge_stderr, None

    def child(
        merge_stderr: bool,
        _owned: None,
        on_stdout: Callable[[bytes], None],
        on_stderr: Callable[[bytes], None],
        **_kwargs: object,
    ) -> SimpleNamespace:
        status = next(statuses)
        if status:
            block = (b"x" * 1023 + b"\n") * 64
            for _ in range(17):
                on_stdout(block)
            for i in range(45):
                feed = on_stdout if merge_stderr or i % 2 == 0 else on_stderr
                feed(f"diagnostic {i:02}\n".encode())
        return SimpleNamespace(collect=lambda *_: status, leader_code=status, timed_out=False, started=0.0)

    monkeypatch.setattr(runner, "launch", launch)
    monkeypatch.setattr(runner, "_Child", child)
    runtime = local.runtimes["codex"]
    runtime.results.extend((_completed(), _completed("fixed")))
    code, out = local.run("do", "--gate", "quality-check", "--max-gate-retries", "1")
    assert code == 0, out
    assert out["result"]["answer"] == "fixed"
    _, retry = runtime.requests
    assert retry.rendered_prompt.splitlines()[-41:] == [
        "gate failed (exit 1) (output truncated). Fix the issue shown by the gate and try again.",
        *(f"diagnostic {i:02}" for i in range(5, 45)),
    ]


def test_do_denials_stop_before_gate(local: _LocalCLI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local_gate, "run", _unexpected)
    local.runtimes["codex"].results.append(_completed(denied=True))
    code, out = local.run("do", "--gate", "quality-check", "--max-gate-retries", "2")
    assert code == 1
    assert "tool denials" in out["result"]["error"]
    assert len(local.runtimes["codex"].requests) == 1


def test_do_runtime_failure_stops_before_gate(local: _LocalCLI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local_gate, "run", _unexpected)
    failure = ProviderFailure(
        ErrorClass.AUTHENTICATION, ErrorCode.RUNTIME_AUTH_EXPIRED, False, "expired", None, None, "structured"
    )
    local.runtimes["codex"].results.append(replace(_completed(""), outcome="failed", failure=failure))
    code, out = local.run("do", "--gate", "quality-check", "--max-gate-retries", "2")
    assert code == 1
    assert "RUNTIME_AUTH_EXPIRED" in out["result"]["error"]
    assert len(local.runtimes["codex"].requests) == 1


def test_do_requires_resume_capability_before_running(
    local: _LocalCLI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(local_gate, "run", _unexpected)
    runtime = local.runtimes["codex"]
    runtime.resume = False
    code, out = local.run("do", "--gate", "quality-check", "--max-gate-retries", "2")
    assert code == 1
    assert "SESSION_RESUME" in out["result"]["error"]
    assert not runtime.requests


@pytest.mark.parametrize(("supports_resume", "allow_fresh"), [(True, False), (True, True), (False, True)])
def test_do_missing_session_policy(
    local: _LocalCLI, monkeypatch: pytest.MonkeyPatch, supports_resume: bool, allow_fresh: bool
) -> None:
    statuses = iter((1, 0))

    def gate(argv: tuple[str, ...], **_: Any) -> ProcessResult:
        return ProcessResult(argv, next(statuses), b"failed check", b"", False, False, False, 0.0, None)

    monkeypatch.setattr(local_gate, "run", gate)
    runtime = local.runtimes["codex"]
    runtime.resume = supports_resume
    runtime.results.extend((_completed(), _completed()))
    options = ("--allow-fresh-retry",) if allow_fresh else ()
    code, out = local.run("do", "--gate", "quality-check", "--max-gate-retries", "2", *options)
    assert code == (0 if allow_fresh else 1)
    if allow_fresh:
        assert len(runtime.requests) == 2
        assert runtime.requests[1].resume_session_ref is None
        assert "failed check" in runtime.requests[1].rendered_prompt
    else:
        assert len(runtime.requests) == 1
        assert "no session_ref" in out["result"]["error"]


def test_do_gate_gets_clean_environment(local: _LocalCLI, monkeypatch: pytest.MonkeyPatch) -> None:
    clean = dict(local.env)
    local.env.update(
        OPENAI_API_KEY="provider-key",
        SKM_DATABASE_URL="db-dsn",
        DATABASE_URL="another-dsn",
        CODEX_HOME="/host/provider-profile",
    )

    def gate(argv: tuple[str, ...], **kwargs: Any) -> ProcessResult:
        assert kwargs["env"] == clean
        return ProcessResult(argv, 0, b"", b"", False, False, False, 0.0, None)

    monkeypatch.setattr(local_gate, "run", gate)
    runtime = local.runtimes["codex"]
    runtime.results.append(_completed())
    code, out = local.run("do", "--gate", "quality-check")
    assert code == 0, out


@pytest.mark.parametrize("allow_partial", [False, True])
def test_deliberate_runs_distinct_slots_concurrently_and_reports_partial_failure(
    local: _LocalCLI, allow_partial: bool
) -> None:
    barrier = Barrier(2)
    for runtime in local.runtimes.values():
        runtime.barrier = barrier
    local.runtimes["codex"].results.append(_completed("first opinion"))
    local.runtimes["claude_code"].results.append(_completed(denied=True))
    options = ("--allow-partial",) if allow_partial else ()
    code, out = local.run("deliberate", "--slot", "first", "--slot", "second", *options)
    assert code == (0 if allow_partial else 1)
    first, second = out["result"]["answers"]
    assert (first["slot"], first["answer"]) == ("first", "first opinion")
    assert second["slot"] == "second"
    assert "tool denials" in second["error"]
    left, right = [runtime.requests[0] for runtime in local.runtimes.values()]
    assert left.permissions.fs_write.allow == right.permissions.fs_write.allow == ()
    assert left.config_mode == right.config_mode == "isolated"
    assert left.client_home != right.client_home


def test_deliberate_refuses_duplicate_slots(local: _LocalCLI) -> None:
    code, out = local.run("deliberate", "--slot", "first", "--slot", "first")
    assert code == 1
    assert "distinct slots" in out["error"]["message"]
    assert not local.runtimes["codex"].requests


@pytest.mark.parametrize("uuid_project", [False, True])
@pytest.mark.parametrize("group", ["exec", "pipe"])
def test_adhoc_dry_run_is_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, group: str, uuid_project: bool
) -> None:
    _offline(monkeypatch)
    path = tmp_path / "workflow.json"
    if group == "pipe":
        path.write_text(json.dumps(workflow()), encoding="utf-8")
    extra = (str(path),) if group == "pipe" else ()
    project = str(UUID(int=1)) if uuid_project else "workspace/sample"
    code, out = _invoke(group, *extra, "inspect", "--dry-run", "--project", project)
    assert code == 0
    result = out["result"]
    assert result["project_ref"] == (
        project if uuid_project else f"{project} (unresolved in offline dry-run)"
    )
    assert result["slot"] == "deferred (resolved by control-plane worker at claim time)"
    assert result["payload"]["project_id"] == (project if uuid_project else None)
    assert result["payload"]["prompt"] == "inspect"
    if group == "pipe":
        assert result["payload"]["workflow"]["id"] == "standalone-pipe"
