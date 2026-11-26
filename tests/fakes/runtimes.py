"""Synthetic AgentRuntime requests. Never register fake in a production composition."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import UUID

from skm.kernel.isolation import IsolationProfile
from skm.modules.runtimes.domain.classes import RoleId
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
)

STEP = UUID("0193a7c2-5b10-7c11-8a00-3f1e2d4c5b6a")
RUN = UUID("0193a7c2-0000-7000-8000-000000000001")


def runtime_request(
    workdir: Path,
    *,
    step: UUID = STEP,
    run: UUID = RUN,
    role: RoleId = RoleId.EXECUTOR,
    task_key: str = "P1.1/U1",
) -> AgentRequest:
    workdir = workdir.resolve()
    prompt = "Perform the synthetic test task."
    paths = PathRules((PathRule(str(workdir), "**"),), ())
    owner = ProcessOwner(
        RUN, RUN, RUN, RUN, "step", step, "synthetic-owner-nonce", str(workdir.parent / "owners")
    )
    return AgentRequest(
        request_id=str(step),
        runtime_id="fake",
        model="resolved-model",
        effort=None,
        role=role,
        rendered_prompt=prompt,
        prompt_digest="sha256:" + sha256(prompt.encode()).hexdigest(),
        result_format=ResultFormat.JSON,
        result_schema_urn=f"urn:skm:execution:role-result:{role.value}:v1",
        workdir=str(workdir),
        permissions=PermissionGrant(
            paths, paths, CommandRules("none", (), (), ()), NetworkRules("none", ()), frozenset(), frozenset()
        ),
        isolation_profile=IsolationProfile.WORKTREE,
        process_owner=owner,
        config_mode="isolated",
        client_home=str(workdir.parent / "client-home"),
        resume_session_ref=None,
        session_policy="ephemeral",
        env_allowlist=(),
        extra_env={},
        secret_env={},
        mcp_servers=(),
        limits=RuntimeLimits(30, 10, None, None, 1024 * 1024),
        labels={"run_id": str(run), "task_key": task_key, "step_id": str(step)},
    )
