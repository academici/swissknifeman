"""Opt-in live probe gate for Claude Code runtime adapter (Dossier §4).

CRITICAL: Never invokes the real ``claude`` CLI during default test runs. Execution requires
``SKM_EVALS=1`` (and ``-m evals`` when marker filtering is active).
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from skm.adapters.runtimes.claude_code.runtime import ClaudeCodeRuntime
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.ids import HostId
from skm.kernel.isolation import IsolationProfile
from skm.modules.runtimes.domain.classes import Effort, RoleId
from skm.modules.runtimes.domain.detection import DetectProbe
from skm.modules.runtimes.domain.installation import AuthState
from skm.modules.runtimes.domain.request import (
    AgentRequest,
    CommandRules,
    NetworkRules,
    PathRule,
    PathRules,
    PermissionGrant,
    ProcessOwner,
    ResultFormat,
    RuntimeLimits,
    SecretStr,
)
from skm.modules.runtimes.domain.result import validate_result_observation
from skm.modules.runtimes.domain.session_events import validate_event_stream

_EVALS_ENABLED = os.environ.get("SKM_EVALS") == "1"

pytestmark = [
    pytest.mark.evals,
    pytest.mark.skipif(not _EVALS_ENABLED, reason="opt-in live Claude probe requires SKM_EVALS=1"),
]


def _require_live_claude() -> tuple[str, dict[str, str]]:
    env = dict(os.environ)
    binary = env.get("SKM_CLAUDE_BINARY", "claude")
    located = shutil.which(binary, path=env.get("PATH"))
    if located is None:
        pytest.skip(f"live Claude CLI binary {binary!r} is not installed on PATH")
    user_home = Path(env.get("HOME", ""))
    has_cred_file = user_home.is_dir() and (user_home / ".claude" / ".credentials.json").is_file()
    has_env_token = bool(env.get("ANTHROPIC_API_KEY") or env.get("CLAUDE_CODE_OAUTH_TOKEN"))
    if not (has_cred_file or has_env_token):
        pytest.skip("live Claude credentials not present in ~/.claude/.credentials.json or env")
    return located, env


def _make_live_request(
    workdir: Path,
    state_dir: Path,
    *,
    prompt: str,
    writable: bool = False,
    shell_mode: str = "none",
    session_policy: str = "ephemeral",
    resume_session_ref: str | None = None,
    tools: frozenset[str] = frozenset(),
    model: str = "haiku",
    timeout_seconds: int = 90,
) -> AgentRequest:
    step_id = uuid4()
    run_id = uuid4()
    read_rules = PathRules((PathRule(str(workdir), "**"),), ())
    write_rules = PathRules((PathRule(str(workdir), "**"),), ()) if writable else PathRules((), ())
    cmd_mode = "any" if shell_mode == "any" else "none"
    owner = ProcessOwner(
        host_id=run_id,
        worker_id=run_id,
        attempt_id=run_id,
        stage_record_id=run_id,
        unit_kind="step",
        unit_id=step_id,
        owner_nonce="live-probe-owner-nonce-0001",
        identity_dir=str(state_dir / "identities"),
    )
    client_home = state_dir / "client-homes" / str(run_id) / "claude_code"
    env_allow = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")
    return AgentRequest(
        request_id=str(step_id),
        runtime_id="claude_code",
        model=model,
        effort=Effort.LOW,
        role=RoleId.EXECUTOR if writable else RoleId.REVIEWER,
        rendered_prompt=prompt,
        prompt_digest=f"sha256:{sha256(prompt.encode('utf-8')).hexdigest()}",
        result_format=ResultFormat.TEXT,
        result_schema_urn=None,
        workdir=str(workdir),
        permissions=PermissionGrant(
            fs_read=read_rules,
            fs_write=write_rules,
            commands=CommandRules(cmd_mode, (), (), ()),
            network=NetworkRules("any", ()),
            tools=tools,
            external_effects=frozenset(),
        ),
        isolation_profile=IsolationProfile.WORKTREE,
        process_owner=owner,
        config_mode="isolated",
        client_home=str(client_home),
        resume_session_ref=resume_session_ref,
        session_policy="persistent" if session_policy == "persistent" else "ephemeral",
        env_allowlist=env_allow,
        extra_env={},
        secret_env={"SKM_TOKEN": SecretStr("skm-live-probe-redacted-token-999")},
        mcp_servers=(),
        limits=RuntimeLimits(
            timeout_seconds=timeout_seconds,
            idle_timeout_seconds=30,
            max_turns=4,
            max_output_tokens=None,
            max_output_bytes=8 * 1024 * 1024,
        ),
        labels={"run_id": str(run_id), "step_id": str(step_id)},
    )


def test_live_probe_binary_identity_and_launch_signature(tmp_path: Path) -> None:
    """Gate #1: Exact immutable binary identity and canonical launch signature."""
    binary, env = _require_live_claude()
    runtime = ClaudeCodeRuntime(state_dir=tmp_path / "state", binary=binary, environ=env)
    host_id = HostId(uuid4())
    inst = runtime.detect(DetectProbe(host_id=host_id, binary=binary, env_allowlist=(), timeout_seconds=20))
    assert inst.runtime_id == "claude_code"
    assert inst.version is not None
    assert inst.binary_locator == str(Path(binary).resolve())
    assert inst.details["binary_sha256"].startswith("sha256:")
    assert inst.details["launch_config_digest"] == runtime.launch_config_digest
    assert runtime.capabilities().supports(
        next(c for c in runtime.capabilities().records if c.value == "headless_execution")
    )


def test_live_probe_isolated_auth_and_worktree_canary_suppression(tmp_path: Path) -> None:
    """Gates #2, #3, #7: Isolated auth, missing-cred refusal, native terminal, and K16 hook canary."""
    binary, env = _require_live_claude()
    workdir = tmp_path / "repo"
    workdir.mkdir()
    state_dir = tmp_path / "state"

    # Plant an untrusted worktree hook canary in <worktree>/.claude/settings.json (K16).
    canary_file = tmp_path / "hook_canary_triggered"
    claude_dir = workdir / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "hooks": [
                                {"command": f"touch {canary_file}", "type": "command"},
                            ],
                            "matcher": "*",
                        }
                    ],
                    "UserPromptSubmit": [
                        {
                            "hooks": [
                                {"command": f"touch {canary_file}", "type": "command"},
                            ]
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    # Without credential copy and without env auth tokens, isolated mode must fail closed.
    stripped_env = {k: v for k, v in env.items() if k not in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")}
    no_cred_rt = ClaudeCodeRuntime(
        state_dir=state_dir / "nocred",
        binary=binary,
        environ=stripped_env,
        copy_credentials=False,
    )
    with pytest.raises(CapabilityUnavailable) as exc_info:
        no_cred_rt.start(_make_live_request(workdir, state_dir / "nocred", prompt="Reply with OK only."))
    assert exc_info.value.code is ErrorCode.RUNTIME_AUTH_EXPIRED
    assert no_cred_rt.auth_state is AuthState.EXPIRED

    # With credential copy in isolated client home, turn completes with native result and canary stays absent.
    runtime = ClaudeCodeRuntime(state_dir=state_dir, binary=binary, environ=env, copy_credentials=True)
    req = _make_live_request(workdir, state_dir, prompt="Reply with the exact word PONG and nothing else.")
    handle = runtime.start(req)
    events = list(runtime.events(handle))
    result = runtime.result(handle)

    assert validate_event_stream(events) == ()
    assert validate_result_observation(result, request_id=UUID(req.request_id)) == ()
    assert result.outcome == "completed"
    assert "PONG" in result.final_text.upper()
    assert runtime.auth_state is AuthState.OK
    assert not canary_file.exists(), "untrusted worktree .claude/settings.json hook executed!"


def test_live_probe_tool_interception_and_denial_hints(tmp_path: Path) -> None:
    """Gate #4: Read-only tool enforcement blocks file creation in workdir."""
    binary, env = _require_live_claude()
    workdir = tmp_path / "repo"
    workdir.mkdir()
    forbidden_target = workdir / "must_not_exist.txt"
    runtime = ClaudeCodeRuntime(state_dir=tmp_path / "state", binary=binary, environ=env)
    req = _make_live_request(
        workdir,
        tmp_path / "state",
        prompt=(
            "Attempt to create must_not_exist.txt containing 'hello' if permitted; "
            "if write tools are unavailable or denied, reply DENIED."
        ),
        writable=False,
        shell_mode="none",
    )
    handle = runtime.start(req)
    events = list(runtime.events(handle))
    result = runtime.result(handle)
    assert validate_event_stream(events) == ()
    assert not forbidden_target.exists()
    assert result.outcome in ("completed", "failed")


def test_live_probe_session_resume_and_cancellation(tmp_path: Path) -> None:
    """Gates #5 & #6: Persistent session resume inside isolated client home and clean cancel containment."""
    binary, env = _require_live_claude()
    workdir = tmp_path / "repo"
    workdir.mkdir()
    state_dir = tmp_path / "state"
    runtime = ClaudeCodeRuntime(state_dir=state_dir, binary=binary, environ=env)

    first_req = _make_live_request(
        workdir,
        state_dir,
        prompt="Remember code token ZEBRA-739 and reply STORED.",
        session_policy="persistent",
    )
    first_handle = runtime.start(first_req)
    first_result = runtime.result(first_handle)
    assert first_result.outcome == "completed"
    assert first_result.session_ref is not None

    # Reuse the exact same isolated client_home for the resumed turn.
    resumed_req = _make_live_request(
        workdir,
        state_dir,
        prompt="What code token did I ask you to remember? Reply with the token only.",
        session_policy="persistent",
        resume_session_ref=first_result.session_ref,
    )
    resumed_req = AgentRequest(
        **{
            **{f: getattr(resumed_req, f) for f in resumed_req.__dataclass_fields__},
            "client_home": first_req.client_home,
        }
    )
    resumed_handle = runtime.start(resumed_req)
    resumed_result = runtime.result(resumed_handle)
    assert resumed_result.outcome == "completed"
    assert "ZEBRA-739" in resumed_result.final_text

    # Cancellation check: start a turn and cancel it immediately, verifying marker cleanup.
    cancel_req = _make_live_request(
        workdir,
        state_dir,
        prompt="Write a detailed 500-line essay on distributed consensus algorithms.",
    )
    cancel_handle = runtime.start(cancel_req)
    cancel_out: list[object] = []

    def _trigger_cancel() -> None:
        time.sleep(0.2)
        cancel_out.append(runtime.cancel(cancel_handle, grace_seconds=2.0))

    stopper = threading.Thread(target=_trigger_cancel, daemon=True)
    stopper.start()
    cancel_events = list(runtime.events(cancel_handle))
    stopper.join(timeout=15.0)
    cancel_res = runtime.result(cancel_handle)
    assert validate_event_stream(cancel_events) == ()
    assert cancel_res.outcome in ("cancelled", "completed")
    assert not list((state_dir / "identities").glob("*.json"))


def test_live_probe_subagent_usage_disclosure_fact(tmp_path: Path) -> None:
    """Gate #8: Subagent Task invocation records SubagentUsage(used=..., disclosed=False)."""
    binary, env = _require_live_claude()
    workdir = tmp_path / "repo"
    workdir.mkdir()
    (workdir / "hello.txt").write_text("subagent-probe-fact\n", encoding="utf-8")
    state_dir = tmp_path / "state"
    runtime = ClaudeCodeRuntime(state_dir=state_dir, binary=binary, environ=env)
    req = _make_live_request(
        workdir,
        state_dir,
        prompt="Use the Task subagent tool to read hello.txt and report its single line.",
        tools=frozenset({"Task"}),
    )
    handle = runtime.start(req)
    events = list(runtime.events(handle))
    result = runtime.result(handle)
    assert validate_event_stream(events) == ()
    assert result.usage.subagents.disclosed is False
