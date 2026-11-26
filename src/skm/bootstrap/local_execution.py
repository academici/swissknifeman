"""Compose single-step host-local execution and record private context consumption."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from skm.bootstrap.runtimes import RUNTIME_FACTORIES
from skm.kernel.errors import error_for
from skm.kernel.isolation import IsolationProfile
from skm.modules.runtimes.domain.request import CommandRules, NetworkRules, PathRule, PathRules, ResultFormat
from skm.modules.runtimes.public import AgentRequest, PermissionGrant, ProcessOwner, RoleId, RuntimeLimits
from skm.platform.fs.atomic_write import atomic_write

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from skm.kernel.id_generator import IdGenerator
    from skm.kernel.ids import RunId

__all__ = ["LocalRun", "local_run_root", "run_ephemeral"]


def local_run_root(environ: Mapping[str, str], home: Path) -> Path:
    return Path(environ.get("XDG_STATE_HOME") or home / ".local/state") / "skm" / "local-runs"


@dataclass(frozen=True, slots=True)
class LocalRun:
    root: Path
    id: RunId

    @property
    def _private_marker(self) -> Path:
        return self.root / str(self.id) / "host-private"

    def mark_host_private_consumed(self) -> None:
        """Record the permanent restriction before handing private context to the runtime."""
        self._private_marker.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_write(self._private_marker, b"HOST_PRIVATE\n", mode=0o600)


def run_ephemeral(
    run: LocalRun,
    prompt: str,
    *,
    model: str,
    workdir: Path,
    environ: Mapping[str, str],
    ids: IdGenerator,
    host_private_episodes: Sequence[str] = (),
) -> str:
    """Run one fresh read-only session using the installed runtime adapter."""
    if host_private_episodes:
        run.mark_host_private_consumed()
        prompt = "\n\n".join((prompt, *host_private_episodes))
    workdir = workdir.resolve(strict=True)
    with TemporaryDirectory(prefix="skm-ephemeral-") as directory:
        state_dir = Path(directory)
        runtime = RUNTIME_FACTORIES["codex"](state_dir=state_dir, environ=environ)
        step_id = ids.new_id()
        owner = ProcessOwner(
            ids.new_id(),
            ids.new_id(),
            ids.new_id(),
            ids.new_id(),
            "step",
            step_id,
            secrets.token_hex(24),
            str(state_dir / "identities"),
        )
        request = AgentRequest(
            request_id=str(step_id),
            runtime_id=runtime.runtime_id,
            model=model,
            effort=None,
            role=RoleId.EXECUTOR,
            rendered_prompt=prompt,
            prompt_digest=f"sha256:{sha256(prompt.encode()).hexdigest()}",
            result_format=ResultFormat.TEXT,
            result_schema_urn=None,
            workdir=str(workdir),
            permissions=PermissionGrant(
                PathRules((PathRule(str(workdir), "**"),), ()),
                PathRules((), ()),
                CommandRules("none", (), (), ()),
                NetworkRules("none", ()),
                frozenset(),
                frozenset(),
            ),
            isolation_profile=IsolationProfile.LANDLOCK,
            process_owner=owner,
            config_mode="isolated",
            client_home=str(state_dir / "client-home"),
            resume_session_ref=None,
            session_policy="ephemeral",
            env_allowlist=(),
            extra_env={},
            secret_env={},
            mcp_servers=(),
            limits=RuntimeLimits(600, 120, None, None, 2 * 1024 * 1024),
            labels={"run_id": str(run.id)},
        )
        handle = runtime.start(request)
        try:
            for _ in runtime.events(handle):
                pass
            result = runtime.result(handle)
        except BaseException:
            runtime.cancel(handle, grace_seconds=5)
            raise
        if result.failure is not None:
            raise error_for(result.failure.code, "host-local runtime failed")
        return result.final_text
