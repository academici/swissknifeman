"""Contract suite for isolated ``client_home`` lifecycle across runtime adapters.

Verifies ``runtimes §4.3.1``, ``adapters §5.11``, K16, K17, and S-55 across ``claude_code`` and
``codex`` without invoking real host CLI binaries.
"""

from __future__ import annotations

import os
import shutil
import sys
import textwrap
from hashlib import sha256
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import pytest

from skm.adapters.runtimes.claude_code import launch as claude_launch
from skm.adapters.runtimes.claude_code.runtime import ClaudeCodeRuntime
from skm.adapters.runtimes.codex import launch as codex_launch
from skm.adapters.runtimes.codex.runtime import CodexRuntime
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, ValidationFailed
from skm.kernel.isolation import IsolationProfile
from skm.modules.runtimes.domain import request as req_dom
from skm.modules.runtimes.domain.capability import parse_capabilities
from skm.modules.runtimes.domain.classes import Effort, RoleId
from skm.modules.runtimes.domain.installation import AuthState
from skm.platform.config.sources.document import decode_document

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests/fixtures/runtimes/config-isolation"
CLAUDE_CAPS_PATH = ROOT / "src/skm/adapters/runtimes/claude_code/capabilities.toml"
CODEX_CAPS_PATH = ROOT / "src/skm/adapters/runtimes/codex/capabilities.toml"


def _write_exec(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    os.chmod(path, 0o700)
    return path


def _install_mock_cli(tmp_path: Path, template_name: str, bin_name: str) -> Path:
    raw = (FIXTURES / "mock_bin" / template_name).read_text(encoding="utf-8")
    return _write_exec(tmp_path / "bin" / bin_name, raw.replace("__PYTHON__", sys.executable))


def _plant_tree(src: Path, dst: Path, *, canary_dir: Path | None = None) -> Path:
    dst.mkdir(parents=True, exist_ok=True)
    for item in sorted(src.rglob("*")):
        target = dst / item.relative_to(src)
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        text = item.read_text(encoding="utf-8")
        if canary_dir is not None:
            text = text.replace("__CANARY_DIR__", str(canary_dir))
        target.write_text(text, encoding="utf-8")
    return dst


def _poisoned_user_home(tmp_path: Path, *, with_credentials: bool = True) -> Path:
    home = _plant_tree(FIXTURES / "user_home", tmp_path / "user_home", canary_dir=tmp_path / "canaries")
    if with_credentials:
        for rel, src_name in (
            (Path(".claude") / claude_launch.CREDENTIAL_FILENAME, "claude_valid.json"),
            (Path(".codex") / codex_launch.CREDENTIAL_FILENAME, "codex_valid.json"),
        ):
            cred = home / rel
            cred.write_bytes((FIXTURES / "credentials" / src_name).read_bytes())
            os.chmod(cred, 0o600)
    return home


def _make_request(
    *,
    runtime_id: str,
    workdir: Path,
    state_dir: Path,
    attempt_id: UUID | None = None,
    config_mode: Literal["isolated", "inherit"] = "isolated",
    isolation_profile: IsolationProfile = IsolationProfile.WORKTREE,
    client_home: Path | str | None = "auto",
    session_policy: Literal["ephemeral", "persistent"] = "ephemeral",
    resume_session_ref: str | None = None,
    env_allowlist: tuple[str, ...] = (),
    extra_env: dict[str, str] | None = None,
    extra_read_roots: tuple[str, ...] = (),
    extra_write_roots: tuple[str, ...] = (),
    mcp_servers: tuple[req_dom.McpServerSpec, ...] = (),
    secret_token: str = "skm-client-home-secret-token-777",
) -> tuple[req_dom.AgentRequest, req_dom.ProcessOwnership]:
    workdir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    att_id, step_id = attempt_id or uuid4(), uuid4()
    owner = req_dom.ProcessOwner(
        att_id,
        att_id,
        att_id,
        att_id,
        "step",
        step_id,
        "contract-client-home-nonce-01",
        str(state_dir / "id"),
    )
    ownership = req_dom.ProcessOwnership(owner, "pgroup_best_effort", f"pgroup/{step_id}")
    if client_home == "auto":
        resolved_home = (
            None if config_mode == "inherit" else str(state_dir / "client-homes" / str(att_id) / runtime_id)
        )
    else:
        resolved_home = None if client_home is None else str(client_home)

    prompt = "Verify isolated client_home contract."
    read_rules = req_dom.PathRules(
        tuple(req_dom.PathRule(r, "**") for r in (str(workdir), *extra_read_roots)), ()
    )
    write_rules = req_dom.PathRules(
        tuple(req_dom.PathRule(r, "**") for r in (str(workdir), *extra_write_roots)), ()
    )
    req = req_dom.AgentRequest(
        request_id=str(step_id),
        runtime_id=runtime_id,
        model="sonnet" if runtime_id == "claude_code" else "gpt-5.3-codex",
        effort=Effort.HIGH,
        role=RoleId.EXECUTOR,
        rendered_prompt=prompt,
        prompt_digest=f"sha256:{sha256(prompt.encode('utf-8')).hexdigest()}",
        result_format=req_dom.ResultFormat.TEXT,
        result_schema_urn=None,
        workdir=str(workdir),
        permissions=req_dom.PermissionGrant(
            fs_read=read_rules,
            fs_write=write_rules,
            commands=req_dom.CommandRules("any", (), (), ()),
            network=req_dom.NetworkRules("none", ()),
            tools=frozenset(),
            external_effects=frozenset(),
        ),
        isolation_profile=isolation_profile,
        process_owner=owner,
        config_mode=config_mode,
        client_home=resolved_home,
        resume_session_ref=resume_session_ref,
        session_policy=session_policy,
        env_allowlist=env_allowlist,
        extra_env=extra_env or {},
        secret_env={"SKM_TOKEN": req_dom.SecretStr(secret_token)},
        mcp_servers=mcp_servers,
        limits=req_dom.RuntimeLimits(60, 15, 6, None, 2 * 1024 * 1024),
        labels={"attempt_id": str(att_id), "step_id": str(step_id)},
    )
    return req, ownership


@pytest.mark.parametrize(
    ("runtime_id", "caps_path", "expected_dirs", "cred_name"),
    [
        (
            "claude_code",
            CLAUDE_CAPS_PATH,
            claude_launch.WRITABLE_CLIENT_HOME_DIRS,
            claude_launch.CREDENTIAL_FILENAME,
        ),
        (
            "codex",
            CODEX_CAPS_PATH,
            codex_launch.WRITABLE_CLIENT_HOME_DIRS,
            codex_launch.CREDENTIAL_FILENAME,
        ),
    ],
)
def test_client_home_layout_permissions_and_declaration_parity(
    tmp_path: Path,
    runtime_id: Literal["claude_code", "codex"],
    caps_path: Path,
    expected_dirs: tuple[str, ...],
    cred_name: str,
) -> None:
    caps = parse_capabilities(decode_document(caps_path.read_text(encoding="utf-8"), "toml"))
    assert caps.config_isolation is not None
    assert caps.config_isolation.writable_home_dirs == expected_dirs
    assert caps.config_isolation.credential_mounts[0].target == cred_name

    workdir, state_dir = tmp_path / "workdir", tmp_path / "state"
    user_home = _poisoned_user_home(tmp_path, with_credentials=True)
    attempt_id = uuid4()
    req, _ = _make_request(runtime_id=runtime_id, workdir=workdir, state_dir=state_dir, attempt_id=attempt_id)
    assert req.client_home is not None
    raw_home = Path(req.client_home)
    assert raw_home == state_dir / "client-homes" / str(attempt_id) / runtime_id

    raw_home.mkdir(parents=True, exist_ok=True)
    os.chmod(raw_home, 0o755)  # noqa: S103 - intentional permissive mode to verify 0700 tightening

    resolved_workdir = workdir.resolve(strict=True)
    prepare_fn = (
        claude_launch.prepare_isolated_client_home
        if runtime_id == "claude_code"
        else codex_launch.prepare_isolated_client_home
    )
    prepared = prepare_fn(
        req, workdir=resolved_workdir, user_home=user_home, copy_credentials=True, has_env_auth=False
    )

    assert prepared.stat().st_mode & 0o777 == 0o700
    for subdir in expected_dirs:
        sub_path = prepared / subdir
        assert sub_path.is_dir()
        assert sub_path.stat().st_mode & 0o777 == 0o700

    cred_path = prepared / cred_name
    assert cred_path.is_file()
    assert cred_path.stat().st_mode & 0o777 == 0o600
    assert {p.name for p in prepared.iterdir()} == {*expected_dirs, cred_name}


@pytest.mark.parametrize("runtime_id", ["claude_code", "codex"])
def test_missing_or_disabled_credential_copy_fails_closed_before_spawn(
    tmp_path: Path, runtime_id: Literal["claude_code", "codex"]
) -> None:
    workdir, state_dir = tmp_path / "workdir", tmp_path / "state"
    user_home = _poisoned_user_home(tmp_path, with_credentials=True)
    req, _ = _make_request(runtime_id=runtime_id, workdir=workdir, state_dir=state_dir)

    stub_bin = _write_exec(
        tmp_path / "bin" / runtime_id,
        textwrap.dedent(
            """\
            #!/bin/sh
            if [ "$1" = "--version" ]; then echo "2.1.266"; exit 0; fi
            if [ "$1" = "login" ]; then echo "Not logged in"; exit 1; fi
            cat <<'EOF'
            Usage: cli -p --output-format --verbose --model --effort --permission-prompts
            --safe-mode --no-session-persistence --setting-sources --settings --resume
            --tools --disallowedTools --permission-mode --allowedTools --add-dir
            --mcp-config --strict-mcp-config --dangerously-skip-permissions
            exec resume login -a --ask-for-approval -c --config -C --cd -m -s --sandbox
            --json --ephemeral --dangerously-bypass-approvals-and-sandbox
            EOF
            """
        ),
    )

    rt_instance: ClaudeCodeRuntime | CodexRuntime = (
        ClaudeCodeRuntime(
            state_dir=state_dir,
            binary=str(stub_bin),
            user_home=user_home,
            copy_credentials=False,
            environ={"ANTHROPIC_API_KEY": "unallowlisted-ambient-key"},
        )
        if runtime_id == "claude_code"
        else CodexRuntime(
            state_dir=state_dir,
            binary=str(stub_bin),
            user_home=user_home,
            copy_credentials=False,
            environ={"OPENAI_API_KEY": "unallowlisted-ambient-key"},
        )
    )

    with pytest.raises(CapabilityUnavailable) as exc_info:
        rt_instance.start(req)
    assert exc_info.value.code is ErrorCode.RUNTIME_AUTH_EXPIRED
    assert exc_info.value.details.get("reason") == "credentials_missing"
    assert rt_instance.auth_state is AuthState.EXPIRED

    auth_var = "ANTHROPIC_API_KEY" if runtime_id == "claude_code" else "OPENAI_API_KEY"
    req_env, ownership = _make_request(
        runtime_id=runtime_id,
        workdir=workdir,
        state_dir=state_dir,
        env_allowlist=(auth_var,),
        extra_env={auth_var: "explicit-synthetic-key"} if runtime_id == "claude_code" else None,
    )
    step_dir = state_dir / "steps" / req_env.request_id
    if runtime_id == "claude_code":
        plan_c = claude_launch.build_launch_plan(
            req_env,
            binary_path=str(stub_bin),
            step_dir=step_dir,
            ownership=ownership,
            host_environ={auth_var: "allowlisted-synthetic-key"},
            copy_credentials=False,
            user_home=user_home,
        )
        assert plan_c.client_home is not None
        assert not (plan_c.client_home / claude_launch.CREDENTIAL_FILENAME).exists()
    else:
        custom_codex_user = tmp_path / "codex_home_user"
        custom_codex_user.mkdir()
        (custom_codex_user / codex_launch.CREDENTIAL_FILENAME).write_bytes(
            (FIXTURES / "credentials/codex_valid.json").read_bytes()
        )
        plan_x = codex_launch.build_launch_plan(
            req_env,
            binary_path=str(stub_bin),
            step_dir=step_dir,
            ownership=ownership,
            host_environ={},
            copy_credentials=True,
            user_home=tmp_path / "empty_home",
            codex_home_user=custom_codex_user,
        )
        assert plan_x.client_home is not None
        assert (plan_x.client_home / codex_launch.CREDENTIAL_FILENAME).stat().st_mode & 0o777 == 0o600


def test_client_home_boundary_symlink_and_s55_grant_rejections(tmp_path: Path) -> None:
    workdir, state_dir = tmp_path / "workdir", tmp_path / "state"
    user_home = _poisoned_user_home(tmp_path, with_credentials=True)
    claude_caps = parse_capabilities(decode_document(CLAUDE_CAPS_PATH.read_text(encoding="utf-8"), "toml"))

    req_missing, _ = _make_request(
        runtime_id="claude_code", workdir=workdir, state_dir=state_dir, client_home=None
    )
    with pytest.raises(ValidationFailed) as exc_mismatch:
        req_dom.validate_request(req_missing, claude_caps)
    assert exc_mismatch.value.code is ErrorCode.SCHEMA_INVALID
    assert exc_mismatch.value.details["reason"] == "client_home_mismatch"

    req_in_wt, _ = _make_request(
        runtime_id="claude_code", workdir=workdir, state_dir=state_dir, client_home=workdir / ".home"
    )
    with pytest.raises(ValidationFailed) as exc_in_wt:
        req_dom.validate_request(req_in_wt, claude_caps)
    assert exc_in_wt.value.details["reason"] == "client_home_inside_worktree"

    valid_home = state_dir / "client-homes" / str(uuid4()) / "claude_code"
    for is_read in (True, False):
        req_s55, _ = _make_request(
            runtime_id="claude_code",
            workdir=workdir,
            state_dir=state_dir,
            client_home=valid_home,
            extra_read_roots=(str(valid_home),) if is_read else (),
            extra_write_roots=() if is_read else (str(valid_home),),
        )
        with pytest.raises(ValidationFailed) as exc_s55:
            req_dom.validate_request(req_s55, claude_caps)
        assert exc_s55.value.details["reason"] == "grant_outside_worktree"

    resolved_workdir = workdir.resolve(strict=True)
    sym_home = tmp_path / "sym_client_home"
    sym_home.symlink_to(tmp_path / "real_target")
    req_sym, _ = _make_request(runtime_id="codex", workdir=workdir, state_dir=state_dir, client_home=sym_home)
    with pytest.raises(ValidationFailed) as exc_sym:
        codex_launch.prepare_isolated_client_home(
            req_sym,
            workdir=resolved_workdir,
            user_home=user_home,
            copy_credentials=True,
            has_env_auth=False,
        )
    assert exc_sym.value.details["reason"] == "client_home_symlink"

    parent_escape = tmp_path / "escape_parent"
    parent_escape.symlink_to(resolved_workdir)
    req_escape, _ = _make_request(
        runtime_id="claude_code",
        workdir=workdir,
        state_dir=state_dir,
        client_home=parent_escape / "nested_home",
    )
    with pytest.raises(ValidationFailed) as exc_esc:
        claude_launch.prepare_isolated_client_home(
            req_escape,
            workdir=resolved_workdir,
            user_home=user_home,
            copy_credentials=True,
            has_env_auth=False,
        )
    assert exc_esc.value.details["reason"] == "client_home_inside_worktree"

    sym_user_home = tmp_path / "sym_user_home"
    (sym_user_home / ".codex").mkdir(parents=True)
    (sym_user_home / ".codex" / codex_launch.CREDENTIAL_FILENAME).symlink_to(
        FIXTURES / "credentials/codex_valid.json"
    )
    req_src_sym, _ = _make_request(runtime_id="codex", workdir=workdir, state_dir=state_dir)
    with pytest.raises(ValidationFailed) as exc_src_sym:
        codex_launch.prepare_isolated_client_home(
            req_src_sym,
            workdir=resolved_workdir,
            user_home=sym_user_home,
            copy_credentials=True,
            has_env_auth=False,
        )
    assert exc_src_sym.value.details["reason"] == "source_credentials_symlink"

    req_step, ownership = _make_request(runtime_id="claude_code", workdir=workdir, state_dir=state_dir)
    with pytest.raises(ValidationFailed) as exc_step:
        claude_launch.build_launch_plan(
            req_step,
            binary_path="/bin/echo",
            step_dir=workdir / ".skm-step",
            ownership=ownership,
            host_environ={},
            user_home=user_home,
        )
    assert exc_step.value.details["reason"] == "step_dir_inside_worktree"


def test_k16_poisoned_canaries_suppressed_and_attempt_lifecycle_isolated(tmp_path: Path) -> None:
    canary_dir = tmp_path / "canaries"
    canary_dir.mkdir()
    workdir = _plant_tree(FIXTURES / "worktree", tmp_path / "workdir", canary_dir=canary_dir)
    user_home = _poisoned_user_home(tmp_path, with_credentials=True)
    state_dir = tmp_path / "state"

    claude_bin = _install_mock_cli(tmp_path, "claude_canary.txt", "claude")
    codex_bin = _install_mock_cli(tmp_path, "codex_canary.txt", "codex")
    claude_rt = ClaudeCodeRuntime(state_dir=state_dir, binary=str(claude_bin), user_home=user_home)
    codex_rt = CodexRuntime(state_dir=state_dir, binary=str(codex_bin), user_home=user_home)
    attempt_a, attempt_b = uuid4(), uuid4()

    req_a1, _ = _make_request(
        runtime_id="claude_code",
        workdir=workdir,
        state_dir=state_dir,
        attempt_id=attempt_a,
        session_policy="persistent",
    )
    h_a1 = claude_rt.start(req_a1)
    _ = tuple(claude_rt.events(h_a1))
    res_a1 = claude_rt.result(h_a1)
    assert (res_a1.outcome, res_a1.final_text) == ("completed", "turns=1")
    assert list(canary_dir.iterdir()) == []

    req_a2, _ = _make_request(
        runtime_id="claude_code",
        workdir=workdir,
        state_dir=state_dir,
        attempt_id=attempt_a,
        session_policy="persistent",
        resume_session_ref="sess_iso_01",
    )
    h_a2 = claude_rt.start(req_a2)
    _ = tuple(claude_rt.events(h_a2))
    assert claude_rt.result(h_a2).final_text == "turns=2"

    req_b1, _ = _make_request(
        runtime_id="claude_code",
        workdir=workdir,
        state_dir=state_dir,
        attempt_id=attempt_b,
        session_policy="persistent",
    )
    h_b1 = claude_rt.start(req_b1)
    _ = tuple(claude_rt.events(h_b1))
    assert claude_rt.result(h_b1).final_text == "turns=1"

    req_cx1, _ = _make_request(
        runtime_id="codex",
        workdir=workdir,
        state_dir=state_dir,
        attempt_id=attempt_a,
        session_policy="persistent",
        extra_env={"SKM_TEST_CANARY_DIR": str(canary_dir)},
    )
    h_cx1 = codex_rt.start(req_cx1)
    _ = tuple(codex_rt.events(h_cx1))
    res_cx1 = codex_rt.result(h_cx1)
    assert (res_cx1.outcome, res_cx1.final_text) == ("completed", "turns=1")
    assert list(canary_dir.iterdir()) == []

    attempt_a_root = state_dir / "client-homes" / str(attempt_a)
    attempt_b_root = state_dir / "client-homes" / str(attempt_b)
    assert (attempt_a_root / "claude_code").is_dir()
    assert (attempt_a_root / "codex").is_dir()
    shutil.rmtree(attempt_a_root)
    assert not attempt_a_root.exists()
    assert (attempt_b_root / "claude_code").is_dir()
    assert (user_home / ".claude" / claude_launch.CREDENTIAL_FILENAME).is_file()
    assert (user_home / ".codex" / codex_launch.CREDENTIAL_FILENAME).is_file()
