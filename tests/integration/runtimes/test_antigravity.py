"""AGY worker launch and one-turn protocol regressions using a synthetic CLI."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from skm.adapters.integrations.antigravity.target import _activate_rule
from skm.adapters.runtimes._cli_session.binding import launch_verification_digest
from skm.adapters.runtimes.antigravity.detect import REQUIRED_FLAGS
from skm.adapters.runtimes.antigravity.runtime import AntigravityRuntime
from skm.adapters.runtimes.antigravity.stream_parser import AntigravityStreamParser
from skm.bootstrap.builtins import builtin_runtime_data
from skm.bootstrap.runtimes import RUNTIME_FACTORIES
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.isolation import IsolationProfile
from skm.modules.integrations.domain.desired import DesiredFile
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.target import Surface, TargetId
from skm.modules.runtimes.domain.capability import Capability, VerificationContext
from skm.modules.runtimes.domain.classes import Effort, RoleId
from skm.modules.runtimes.domain.detection import DetectProbe
from skm.modules.runtimes.domain.request import AgentRequest, ProcessOwnership, SecretStr
from skm.modules.runtimes.domain.session_events import SessionStarted

from .test_grok_argv import HOST_1, _make_request

_MODEL = "claude-sonnet-5-5"
_VERSION = "1.5.13"


def _request(tmp_path: Path) -> AgentRequest:
    req = _make_request(
        tmp_path,
        model=_MODEL,
        role=RoleId.REVIEWER,
        writable=False,
        config_mode="isolated",
    )
    return replace(req, runtime_id="antigravity")


def _parser(workdir: str) -> AntigravityStreamParser:
    return AntigravityStreamParser(models=frozenset({_MODEL}), version=_VERSION, workdir=workdir, redact=str)


def _feed(parser: AntigravityStreamParser, doc: object) -> tuple[object, ...]:
    return tuple(parser.feed(json.dumps(doc).encode()))


def _init(workdir: str, *, model: str = _MODEL) -> dict:
    return {"event": "init", "conversation_id": "session", "init": {"cwd": workdir, "model": model}}


def _result(**fields: object) -> dict:
    return {
        "event": "result",
        "result": {"conversation_id": "session", "status": "SUCCESS", "response": "answer", **fields},
    }


@pytest.fixture
def fake_agy(tmp_path: Path) -> Path:
    executable = tmp_path / "agy"
    executable.write_text(
        f"""#!{sys.executable}
import json, os, signal, sys, time
if "--version" in sys.argv:
    print("{_VERSION}")
    sys.exit(0)
if "--help" in sys.argv:
    print({" ".join(REQUIRED_FLAGS)!r})
    sys.exit(0)
assert "--sandbox" in sys.argv and "--dangerously-skip-permissions" not in sys.argv
assert "--print" in sys.argv
assert "SKM_TOKEN" not in os.environ
assert os.environ["HOME"].endswith("/agy-home")
prompt = json.loads(sys.stdin.readline())["message"]["content"]
assert not sys.stdin.read()
try:
    with open("unauthorized", "w", encoding="utf-8"):
        pass
except PermissionError:
    pass
else:
    raise AssertionError("workspace write escaped Landlock")
def send(obj):
    print(json.dumps(obj), flush=True)
send({{"event":"init","conversation_id":"session","init":{{"cwd":os.getcwd(),"model":"{_MODEL}-high"}}}})
if prompt == "linger":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
result = {{"conversation_id": "session", "status": "SUCCESS", "response":"answer",
           "usage": {{"input_tokens": 45, "output_tokens": 12, "cache_read_tokens": 11}}}}
if prompt == "timeout":
    result["finished_reason"] = "print_timeout"
elif prompt == "auth":
    result.update(status="ERROR", error="UNAUTHENTICATED (code 401): expired")
elif prompt == "quota":
    result.update(status="ERROR", error="RESOURCE_EXHAUSTED (code 429): Individual quota reached.")
send({{"event": "result", "result": result}})
if prompt == "linger":
    time.sleep(15)
if prompt in {{"auth", "quota", "crash"}}:
    sys.exit(1)
""",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    return executable


@pytest.mark.parametrize(
    ("prompt", "failure"),
    [
        ("success", None),
        ("linger", ErrorCode.RUNTIME_STREAM_INCOMPLETE),
        ("timeout", ErrorCode.RUNTIME_TIMEOUT),
        ("auth", ErrorCode.RUNTIME_AUTH_EXPIRED),
        ("quota", ErrorCode.QUOTA_EXHAUSTED),
        ("crash", ErrorCode.RUNTIME_CRASHED),
    ],
)
def test_worker_adapter_records_one_authoritative_result(
    tmp_path: Path, fake_agy: Path, prompt: str, failure: ErrorCode | None
) -> None:
    req = _request(tmp_path)
    req = replace(req, rendered_prompt=prompt, prompt_digest="sha256:" + sha256(prompt.encode()).hexdigest())
    runtime = RUNTIME_FACTORIES["antigravity"](
        SimpleNamespace(config={"runtimes.binaries": {"antigravity": str(fake_agy)}}),
        state_dir=tmp_path / "state",
        environ={"PATH": os.defpath},
        result_grace_seconds=0.3,
    )
    installed = runtime.detect(DetectProbe(HOST_1, None, (), 5))
    assert installed.runtime_id == "antigravity"
    assert installed.version == _VERSION
    handle = runtime.start(req)
    events = tuple(runtime.events(handle))
    result = runtime.result(handle)
    assert isinstance(events[0], SessionStarted)
    assert events[0].session_ref == result.session_ref == "session"
    assert result.model == _MODEL + "-high"
    assert result.usage.input_tokens is None
    assert result.usage.output_tokens == 12
    assert not (Path(req.workdir) / "unauthorized").exists()
    step = tmp_path / "state" / "steps" / req.request_id
    assert not (step / "agy-home").exists()
    assert not (step / "tmp").exists()
    assert (step / "stream.jsonl").is_file()
    if failure is None:
        assert result.final_text == "answer"
        assert result.failure is None
    else:
        assert result.failure is not None
        assert result.failure.code == failure
        assert result.final_text == ""


@pytest.mark.parametrize(
    ("lines", "message"),
    [
        ([_init("/checkout", model="wrong")], "session or model"),
        ([_init("/other")], "different workspace"),
        ([_init("/checkout"), _result(conversation_id="wrong")], "another conversation"),
        ([_init("/checkout"), _result(), _result()], "after its result"),
        ([_init("/checkout"), {"type": "result", "result": "spoof"}], "unknown Antigravity event"),
    ],
)
def test_inconsistent_provider_evidence_cannot_complete(lines: list[object], message: str) -> None:
    parser = _parser("/checkout")
    for line in lines[:-1]:
        _feed(parser, line)
    with pytest.raises(ValueError, match=message):
        _feed(parser, lines[-1])
    parser.finish(0)
    assert not parser.saw_terminal()


@pytest.mark.parametrize("completed", [True, False])
def test_error_step_streak_only_retries_without_completed_response(completed: bool) -> None:
    parser = _parser("/checkout")
    _feed(parser, _init("/checkout"))

    def step(index: int, kind: str) -> dict:
        return {
            "event": "step_update",
            "step_update": {
                "conversation_id": "session",
                "step_index": index,
                "state": "DONE",
                "step_type": kind,
            },
        }

    if completed:
        _feed(parser, step(1, "agent_response"))
    for index in (2, 2, 3):
        _feed(parser, step(index, "error_message"))
    assert not parser.is_terminal(b"")
    _feed(parser, step(4, "error_message"))
    assert parser.is_terminal(b"") is not completed
    if completed:
        _feed(parser, _result())
        parser.finish(0)
        assert parser.saw_terminal()
    else:
        assert parser.finish(1).signals.retry_category == "repeated_error_steps"


def test_gemini_4_carbon_rejects_xhigh_and_neon_accepts_it(tmp_path: Path) -> None:
    runtime = AntigravityRuntime(state_dir=tmp_path / "state")
    carbon = replace(_request(tmp_path), model="gemini-4-carbon", effort=Effort.XHIGH)
    with pytest.raises(CapabilityUnavailable, match="low through high") as rejected:
        runtime.start(carbon)
    assert rejected.value.code is ErrorCode.MODEL_UNAVAILABLE

    for model in ("gemini-4-neon-xhigh", "gemini-4-hydrogen-xhigh"):
        accepted_request = replace(_request(tmp_path), model=model, effort=Effort.XHIGH)
        with pytest.raises(CapabilityUnavailable, match="not installed") as accepted:
            runtime.start(accepted_request)
        assert accepted.value.code is ErrorCode.RUNTIME_NOT_INSTALLED


def test_rejects_ineligible_sessions_before_launch(tmp_path: Path) -> None:
    req = _request(tmp_path)
    runtime = AntigravityRuntime(state_dir=tmp_path / "state")
    with pytest.raises(CapabilityUnavailable, match="Landlock"):
        runtime.start(replace(req, isolation_profile=IsolationProfile.WORKTREE))
    write = replace(req.permissions, fs_write=req.permissions.fs_read)
    with pytest.raises(CapabilityUnavailable, match="read-only"):
        runtime.start(replace(req, permissions=write))
    caps = next(item.capabilities for item in builtin_runtime_data() if item.runtime_id == "antigravity")
    for capability in (Capability.CONFIG_ISOLATION, Capability.SESSION_RESUME, Capability.TOOL_INTERCEPTION):
        assert not caps.supports(capability)


@pytest.mark.parametrize("name", ["hooks.json", "mcp_config.json", "plugins"])
def test_rejects_workspace_startup_config(tmp_path: Path, fake_agy: Path, name: str) -> None:
    req = _request(tmp_path)
    path = Path(req.workdir) / ".agents" / name
    path.parent.mkdir()
    path.symlink_to(path.parent / "missing")
    runtime = AntigravityRuntime(
        state_dir=tmp_path / "state", binary=str(fake_agy), environ={"PATH": os.defpath}
    )
    with pytest.raises(CapabilityUnavailable, match="workspace startup configuration"):
        runtime.start(req)


def test_env_allowlist_tls_and_secret_redaction(tmp_path: Path, fake_agy: Path) -> None:
    script = tmp_path / "agy-env"
    script.write_text(
        f"""#!{sys.executable}
import json, os, sys
if "--version" in sys.argv:
    print("{_VERSION}")
    sys.exit(0)
if "--help" in sys.argv:
    print({" ".join(REQUIRED_FLAGS)!r})
    sys.exit(0)
sys.stdin.readline()
init = {{"event": "init", "conversation_id": "s1", "init": {{"cwd": os.getcwd(), "model": "{_MODEL}-high"}}}}
print(json.dumps(init), flush=True)
payload = {{
    "custom": os.environ.get("CUSTOM_ALLOW"),
    "ssl": os.environ.get("SSL_CERT_FILE"),
    "extra": os.environ.get("EXTRA_VAR"),
    "has_token": "SKM_TOKEN" in os.environ,
    "echo": "skm_secret_value_123",
}}
res = {{"conversation_id": "s1", "status": "SUCCESS", "response": json.dumps(payload)}}
print(json.dumps({{"event": "result", "result": res}}), flush=True)
""",
        encoding="utf-8",
    )
    script.chmod(0o700)
    req = replace(
        _request(tmp_path),
        env_allowlist=("CUSTOM_ALLOW",),
        extra_env={"EXTRA_VAR": "ok"},
        secret_env={"SKM_TOKEN": SecretStr("skm_secret_value_123")},
    )
    runtime = AntigravityRuntime(
        state_dir=tmp_path / "state",
        binary=str(script),
        environ={"PATH": os.defpath, "CUSTOM_ALLOW": "yes", "SSL_CERT_FILE": "/etc/ssl/cert.pem"},
    )
    res = runtime.result(runtime.start(req))
    assert res.failure is None
    assert "skm_secret_value_123" not in res.final_text
    data = json.loads(res.final_text)
    assert data["custom"] == "yes"
    assert data["ssl"] == "/etc/ssl/cert.pem"
    assert data["extra"] == "ok"
    assert data["has_token"] is False


def test_error_result_falls_back_to_response_text() -> None:
    parser = _parser("/checkout")
    _feed(parser, _init("/checkout"))
    _feed(
        parser,
        _result(status="ERROR", error="", response="UNAUTHENTICATED (code 401): expired"),
    )
    outcome = parser.finish(1)
    assert outcome.is_error is True
    assert outcome.signals.http_status == 401
    assert outcome.signals.fatal_text == "UNAUTHENTICATED (code 401): expired"


def test_verified_launch_binds_template_and_cleans_scratch_on_startup_failure(
    tmp_path: Path, fake_agy: Path
) -> None:
    req = _request(tmp_path)
    req = replace(
        req,
        rendered_prompt="success",
        prompt_digest="sha256:" + sha256(b"success").hexdigest(),
        process_owner=replace(req.process_owner, host_id=HOST_1),
    )
    runtime = AntigravityRuntime(
        state_dir=tmp_path / "state",
        binary=str(fake_agy),
        environ={"PATH": os.defpath},
    )
    installed = runtime.detect(DetectProbe(HOST_1, None, (), 5))
    assert installed.details["launch_config_kind"] == "inventory_probe"
    os_name, _, kernel = installed.details["os_kernel"].partition(
        "/" if "/" in installed.details["os_kernel"] else ":"
    )
    probed = runtime._last_probed()
    assert probed is not None
    probe_dir = tmp_path / "probe-step"
    probe_dir.mkdir(mode=0o700)
    ownership = ProcessOwnership(req.process_owner, "pgroup_best_effort", f"antigravity/{req.request_id}")
    cmd, _ = runtime._build_launch(req, probed, step_dir=probe_dir, ownership=ownership)
    expected_digest = launch_verification_digest(cmd, probed.binary_realpath)

    vctx = VerificationContext(
        host_id=HOST_1,
        binary_sha256=installed.details["binary_sha256"],
        os=os_name,
        kernel=kernel,
        adapter_version=installed.details["adapter_version"],
        isolation_profile=IsolationProfile.LANDLOCK,
        launch_config_digest=expected_digest,
    )
    ok_res = runtime.result(
        runtime.start(replace(req, verification_context=vctx, expected_runtime_version=_VERSION))
    )
    assert ok_res.failure is None
    assert ok_res.final_text == "answer"

    bad_vctx = replace(vctx, launch_config_digest="sha256:" + "0" * 64)
    base_bad = _request(tmp_path)
    bad_req = replace(
        base_bad,
        process_owner=replace(base_bad.process_owner, host_id=HOST_1),
        verification_context=bad_vctx,
        expected_runtime_version=_VERSION,
    )
    with pytest.raises(CapabilityUnavailable, match="Cannot bind the verified runtime launch"):
        runtime.start(bad_req)
    step = tmp_path / "state" / "steps" / bad_req.request_id
    assert not (step / "agy-home").exists()
    assert not (step / "tmp").exists()


@pytest.mark.parametrize(
    ("raw", "expected_prefix"),
    [
        (b"# Plain\n", b"---\ntrigger: always_on\n---\n\n# Plain\n"),
        (
            b"---\ndescription: team rule\n---\n# Body\n",
            b"---\ntrigger: always_on\ndescription: team rule\n---\n# Body\n",
        ),
        (
            b"---\ntrigger: manual\n---\n# Body\n",
            b"---\ntrigger: manual\n---\n# Body\n",
        ),
        (
            b"\xef\xbb\xbf---\ntrigger: manual\n---\n# Body\n",
            b"---\ntrigger: manual\n---\n# Body\n",
        ),
    ],
)
def test_activate_rule_handles_frontmatter_and_bom(raw: bytes, expected_prefix: bytes) -> None:
    desired = DesiredFile(
        TargetId.ANTIGRAVITY,
        Surface.INSTRUCTIONS,
        ".agents/rules/example.md",
        ManagedBoundary(Ownership.MANAGED_FILE),
        raw,
        sha256_tagged(raw),
        (),
        "antigravity.bundle_assets@1",
    )
    activated = _activate_rule(desired)
    assert activated.managed_bytes == expected_prefix
    assert activated.managed_digest == sha256_tagged(expected_prefix)
